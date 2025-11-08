from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, Field
from rq import Queue
from redis import Redis
from rq.job import Job
from uuid import uuid4
import asyncio
import json
from typing import AsyncGenerator
from starlette.responses import StreamingResponse
from datetime import datetime
import httpx
import time

from .settings import settings
from .pipeline import process_video_job
from .auth import get_current_user, require_admin, authenticate_user, create_access_token, User, Token
from .middleware import limiter, SecurityHeadersMiddleware, InputSanitizationMiddleware, get_cors_origins
from .logging import setup_logging, logger, LogContext, PerformanceLogger, HealthChecker, metrics

# Logging sistemini başlat
setup_logging()

# Uygulama başlangıcı
app = FastAPI(
    title="Agent Ingest API - Enhanced",
    description="Güvenli ve güçlendirilmiş video ingest API sistemi",
    version="2.0.0"
)

# CORS ayarları
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Güvenlik middleware'leri
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(InputSanitizationMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Redis bağlantısı
redis_conn = Redis.from_url(settings.REDIS_URL)
queue = Queue(settings.RQ_QUEUE, connection=redis_conn)

# Modeller
class IngestRequest(BaseModel):
    url: HttpUrl
    confirm_rights: bool | None = None
    priority: int = Field(default=0, ge=0, le=10)
    callback_url: str | None = None

class AdminSettings(BaseModel):
    enable_n8n: bool = False
    n8n_webhook_url: str | None = Field(default=None, description="n8n Webhook URL (Production) for triggers")
    enable_telegram: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    auto_trigger_n8n_on_finish: bool = False
    max_concurrent_jobs: int = Field(default=5, ge=1, le=20)
    job_timeout_minutes: int = Field(default=60, ge=5, le=480)

class LoginRequest(BaseModel):
    username: str
    password: str

class JobBatchRequest(BaseModel):
    urls: list[HttpUrl]
    confirm_rights: bool = True

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    uptime: float
    services: dict

SETTINGS_KEY = "admin:settings"

def load_settings() -> AdminSettings:
    raw = redis_conn.get(SETTINGS_KEY)
    if not raw:
        return AdminSettings()
    try:
        data = json.loads(raw)
        return AdminSettings(**data)
    except Exception:
        return AdminSettings()

def save_settings(s: AdminSettings) -> None:
    redis_conn.set(SETTINGS_KEY, json.dumps(s.model_dump()))

# Global start time for uptime calculation
start_time = time.time()

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Request timing ve logging middleware"""
    start_time = time.time()
    
    # Request context oluştur
    log_context = LogContext(request)
    request_info = log_context.get_request_info()
    
    # Request'i logla
    logger.info("Request started", **request_info)
    
    process_time = time.time() - start_time
    response = await call_next(request)
    
    # Response time hesapla
    process_time = time.time() - start_time
    
    # Response'u logla ve metrikleri güncelle
    status_code = response.status_code
    PerformanceLogger.log_api_request(request_info, process_time, status_code)
    
    # Metrikleri güncelle
    metrics.increment_api_metric("total_requests")
    metrics.update_response_time(process_time)
    
    if 200 <= status_code < 400:
        metrics.increment_api_metric("successful_requests")
    else:
        metrics.increment_api_metric("failed_requests")
    
    # Response header'a processing time ekle
    response.headers["X-Process-Time"] = str(process_time)
    
    logger.info("Request completed", 
               status_code=status_code, 
               process_time=process_time,
               **request_info)
    
    return response

# Health check endpoints
@app.get("/health", response_model=HealthResponse)
@limiter.limit("100/minute")
async def health(request: Request):
    """Temel health check"""
    uptime = time.time() - start_time
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="2.0.0",
        uptime=uptime,
        services={"api": "healthy"}
    )

@app.get("/health/detailed")
@limiter.limit("30/minute")
@require_admin
async def detailed_health(request: Request, current_user: User = Depends(get_current_user)):
    """Detaylı health check"""
    health_status = HealthChecker.get_full_health_status()
    return health_status

@app.get("/metrics")
@limiter.limit("10/minute")
@require_admin
async def get_metrics(request: Request, current_user: User = Depends(get_current_user)):
    """Sistem metrikleri"""
    return metrics.get_metrics()

# Authentication endpoints
@app.post("/auth/login", response_model=Token)
@limiter.limit("5/minute")
async def login(request: Request, login_data: LoginRequest):
    """Kullanıcı girişi"""
    user = authenticate_user(login_data.username, login_data.password)
    if not user:
        logger.warning("Login failed", username=login_data.username, ip=request.client.host)
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    logger.info("Login successful", username=user.username, ip=request.client.host)
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/me")
@limiter.limit("100/minute")
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Mevcut kullanıcı bilgileri"""
    return current_user

# Video ingest endpoints
@app.post("/ingest")
@limiter.limit("5/minute")
async def ingest(
    request: Request,
    payload: IngestRequest,
    current_user: User = Depends(get_current_user)
):
    """Video ingest işlemi"""
    
    # URL validation
    if not payload.url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    if settings.REQUIRE_RIGHTS_CONFIRM and not payload.confirm_rights:
        raise HTTPException(status_code=400, detail="You must confirm you have rights to process this content.")

    job_id = str(uuid4())
    
    # Job meta bilgilerini ekle
    job_meta = {
        "user": current_user.username,
        "priority": payload.priority,
        "callback_url": payload.callback_url,
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Job'u kuyruğa ekle
    job: Job = queue.enqueue(
        process_video_job, 
        str(payload.url), 
        job_id=job_id, 
        job_timeout="1h",
        meta=job_meta
    )
    
    # Metrikleri güncelle
    metrics.increment_job_metric("total_jobs")
    PerformanceLogger.log_job_start(job_id, "video_ingest", user=current_user.username)
    
    # Recent jobs listesi güncelle
    redis_conn.lpush("jobs:recent", job.id)
    redis_conn.ltrim("jobs:recent", 0, 199)
    
    logger.info("Job started", job_id=job_id, user=current_user.username, url=str(payload.url))
    
    return {
        "job_id": job.id, 
        "status": job.get_status(refresh=False),
        "message": "Ingestion started successfully"
    }

@app.post("/ingest/batch")
@limiter.limit("2/minute")
async def batch_ingest(
    request: Request,
    payload: JobBatchRequest,
    current_user: User = Depends(get_current_user)
):
    """Toplu video ingest"""
    if not payload.confirm_rights:
        raise HTTPException(status_code=400, detail="You must confirm rights for all videos")
    
    job_ids = []
    for url in payload.urls:
        job_id = str(uuid4())
        job_meta = {
            "user": current_user.username,
            "priority": 0,
            "created_at": datetime.utcnow().isoformat(),
            "batch_id": str(uuid4())
        }
        
        job = queue.enqueue(
            process_video_job, 
            str(url), 
            job_id=job_id, 
            job_timeout="1h",
            meta=job_meta
        )
        
        job_ids.append(job.id)
        metrics.increment_job_metric("total_jobs")
        
        # Recent jobs listesine ekle
        redis_conn.lpush("jobs:recent", job.id)
    
    redis_conn.ltrim("jobs:recent", 0, 199)
    
    logger.info("Batch ingestion started", batch_size=len(job_ids), user=current_user.username)
    
    return {
        "batch_id": str(uuid4()),
        "job_ids": job_ids,
        "message": f"Batch ingestion started for {len(job_ids)} videos"
    }

# Job management endpoints
@app.get("/jobs/{job_id}")
@limiter.limit("50/minute")
async def job_status(
    request: Request,
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Job durumu"""
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        
        # Sadece kendi joblarını görebilsin (admin hariç)
        job_meta = job.meta or {}
        if not current_user.is_admin and job_meta.get("user") != current_user.username:
            raise HTTPException(status_code=403, detail="Access denied to this job")
        
        return {
            "job_id": job.id,
            "status": job.get_status(),
            "enqueued_at": str(job.enqueued_at) if job.enqueued_at else None,
            "started_at": str(job.started_at) if job.started_at else None,
            "ended_at": str(job.ended_at) if job.ended_at else None,
            "result": job.result if job.is_finished else None,
            "meta": job.meta,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail="Job not found")

@app.get("/jobs")
@limiter.limit("30/minute")
async def jobs_list(
    request: Request,
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Job listesi"""
    # Admin tüm jobları, normal kullanıcı sadece kendi joblarını görür
    if current_user.is_admin:
        ids = redis_conn.lrange("jobs:recent", 0, max(0, limit - 1))
    else:
        # Sadece kendi joblarını filtrele (basit implementasyon)
        ids = redis_conn.lrange("jobs:recent", 0, max(0, limit - 1))
    
    out = []
    for b in ids:
        jid = b.decode()
        try:
            job = Job.fetch(jid, connection=redis_conn)
            job_meta = job.meta or {}
            
            # Sadece kendi joblarını göster
            if current_user.is_admin or job_meta.get("user") == current_user.username:
                out.append({
                    "job_id": job.id,
                    "status": job.get_status(),
                    "enqueued_at": str(job.enqueued_at) if job.enqueued_at else None,
                    "started_at": str(job.started_at) if job.started_at else None,
                    "ended_at": str(job.ended_at) if job.ended_at else None,
                    "user": job_meta.get("user", "unknown")
                })
        except Exception:
            continue
    
    return {"items": out}

@app.get("/jobs/{job_id}/stream")
@limiter.limit("20/minute")
async def job_stream(
    request: Request,
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Job stream (SSE)"""
    async def event_gen() -> AsyncGenerator[bytes, None]:
        last_status = None
        try:
            while True:
                job = Job.fetch(job_id, connection=redis_conn)
                
                # Authorization check
                job_meta = job.meta or {}
                if not current_user.is_admin and job_meta.get("user") != current_user.username:
                    yield _sse_format({"error": "Access denied"}).encode()
                    break
                
                status = job.get_status()
                if status != last_status:
                    payload = {
                        "job_id": job.id,
                        "status": status,
                        "enqueued_at": str(job.enqueued_at) if job.enqueued_at else None,
                        "started_at": str(job.started_at) if job.started_at else None,
                        "ended_at": str(job.ended_at) if job.ended_at else None,
                        "result": job.result if job.is_finished else None,
                    }
                    yield _sse_format(payload).encode()
                    last_status = status
                
                # End stream when finished/failed
                if status in {"finished", "failed", "stopped", "deferred"}:
                    break
                    
                await asyncio.sleep(1)
        except Exception as e:
            yield _sse_format({"job_id": job_id, "status": "unknown", "error": str(e)}).encode()

    return StreamingResponse(event_gen(), media_type="text/event-stream")

@app.post("/jobs/{job_id}/cancel")
@limiter.limit("10/minute")
async def cancel_job(
    request: Request,
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Job iptal etme"""
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        
        # Authorization check
        job_meta = job.meta or {}
        if not current_user.is_admin and job_meta.get("user") != current_user.username:
            raise HTTPException(status_code=403, detail="Access denied to this job")
        
        job.cancel()
        logger.info("Job cancelled", job_id=job_id, user=current_user.username)
        
        return {"ok": True, "status": job.get_status(), "message": "Job cancelled successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cancel failed: {e}")

# Admin endpoints
@app.get("/admin/settings")
@limiter.limit("30/minute")
@require_admin
async def admin_get_settings(request: Request, current_user: User = Depends(get_current_user)):
    """Admin ayarları getir"""
    return load_settings().model_dump()

@app.post("/admin/settings")
@limiter.limit("10/minute")
@require_admin
async def admin_set_settings(
    request: Request,
    payload: AdminSettings,
    current_user: User = Depends(get_current_user)
):
    """Admin ayarları güncelle"""
    save_settings(payload)
    logger.info("Settings updated", user=current_user.username)
    return {"ok": True, "message": "Settings updated successfully"}

# Integration endpoints
@app.post("/integrations/ping")
@limiter.limit("5/minute")
@require_admin
async def integrations_ping(request: Request, current_user: User = Depends(get_current_user)):
    """Entegrasyon test"""
    s = load_settings()
    result = {"n8n": False, "telegram": False}

    # n8n ping
    if s.enable_n8n and s.n8n_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.post(s.n8n_webhook_url, json={"type": "ping", "ts": datetime.utcnow().isoformat()})
            result["n8n"] = r.status_code // 100 == 2
        except Exception:
            result["n8n"] = False

    # Telegram ping
    if s.enable_telegram and s.telegram_bot_token:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"https://api.telegram.org/bot{s.telegram_bot_token}/getMe")
            data = r.json()
            result["telegram"] = bool(data.get("ok"))
        except Exception:
            result["telegram"] = False

    logger.info("Integration ping", user=current_user.username, result=result)
    return result

@app.post("/jobs/{job_id}/trigger/n8n")
@limiter.limit("5/minute")
async def trigger_n8n(
    request: Request,
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """n8n webhook tetikle"""
    s = load_settings()
    if not (s.enable_n8n and s.n8n_webhook_url):
        raise HTTPException(status_code=400, detail="n8n not configured or disabled")
    
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        
        # Authorization check
        job_meta = job.meta or {}
        if not current_user.is_admin and job_meta.get("user") != current_user.username:
            raise HTTPException(status_code=403, detail="Access denied to this job")
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    payload = {
        "job_id": job.id,
        "status": job.get_status(),
        "result": job.result if job.is_finished else None,
        "meta": job.meta,
        "ts": datetime.utcnow().isoformat(),
        "user": current_user.username
    }
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(s.n8n_webhook_url, json=payload)
        ok = r.status_code // 100 == 2
        
        logger.info("n8n trigger", job_id=job_id, user=current_user.username, success=ok)
        
        return {"ok": ok, "status_code": r.status_code, "text": r.text[:500]}
    except Exception as e:
        logger.error("n8n trigger failed", job_id=job_id, user=current_user.username, error=str(e))
        raise HTTPException(status_code=500, detail=f"n8n trigger failed: {e}")

class TelegramMessage(BaseModel):
    message: str

@app.post("/notify/telegram")
@limiter.limit("10/minute")
@require_admin
async def notify_telegram(
    request: Request,
    payload: TelegramMessage,
    current_user: User = Depends(get_current_user)
):
    """Telegram bildirimi gönder"""
    s = load_settings()
    if not (s.enable_telegram and s.telegram_bot_token and s.telegram_chat_id):
        raise HTTPException(status_code=400, detail="Telegram not configured or disabled")
    
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, data={"chat_id": s.telegram_chat_id, "text": payload.message})
        data = r.json()
        if not data.get("ok"):
            raise HTTPException(status_code=400, detail=f"Telegram error: {data}")
        
        logger.info("Telegram notification sent", user=current_user.username)
        return {"ok": True, "message": "Telegram notification sent successfully"}
    except Exception as e:
        logger.error("Telegram notification failed", user=current_user.username, error=str(e))
        raise HTTPException(status_code=500, detail=f"Telegram notification failed: {e}")

# Utility functions
def _sse_format(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("Agent Ingest API v2.0.0 started", version="2.0.0", environment=settings.ENV)

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Agent Ingest API shutting down", version="2.0.0")
