"""
Structured logging ve monitoring sistemi
"""
import structlog
import logging
import sys
from datetime import datetime
from typing import Any, Dict
from fastapi import Request
import time
import json
from .settings import settings

# Logging configuration
def setup_logging():
    """Logging sistemi kurulumu"""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    formatter = structlog.dev.ConsoleRenderer()
    handler.setFormatter(formatter)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

# Logger instance
logger = structlog.get_logger()

class LogContext:
    """Request context için logging helper"""
    def __init__(self, request: Request):
        self.request = request
        self.start_time = time.time()
        
    def get_request_info(self) -> Dict[str, Any]:
        """Request bilgilerini topla"""
        return {
            "method": self.request.method,
            "url": str(self.request.url),
            "client_ip": self.request.client.host if self.request.client else None,
            "user_agent": self.request.headers.get("user-agent"),
            "timestamp": datetime.utcnow().isoformat(),
        }

class PerformanceLogger:
    """Performance metrikleri için logger"""
    
    @staticmethod
    def log_job_start(job_id: str, job_type: str, **kwargs):
        """Job başlangıç log'u"""
        logger.info(
            "job_started",
            job_id=job_id,
            job_type=job_type,
            **kwargs
        )
    
    @staticmethod
    def log_job_end(job_id: str, status: str, duration: float, **kwargs):
        """Job bitiş log'u"""
        logger.info(
            "job_completed",
            job_id=job_id,
            status=status,
            duration=duration,
            **kwargs
        )
    
    @staticmethod
    def log_job_error(job_id: str, error: str, **kwargs):
        """Job hata log'u"""
        logger.error(
            "job_failed",
            job_id=job_id,
            error=error,
            **kwargs
        )
    
    @staticmethod
    def log_api_request(request_info: Dict[str, Any], response_time: float, status_code: int):
        """API request log'u"""
        logger.info(
            "api_request",
            **request_info,
            response_time=response_time,
            status_code=status_code
        )

class HealthChecker:
    """Health check sistemi"""
    
    @staticmethod
    def check_redis() -> Dict[str, Any]:
        """Redis health check"""
        try:
            from redis import Redis
            r = Redis.from_url(settings.REDIS_URL)
            r.ping()
            return {"status": "healthy", "service": "redis"}
        except Exception as e:
            return {"status": "unhealthy", "service": "redis", "error": str(e)}
    
    @staticmethod
    def check_qdrant() -> Dict[str, Any]:
        """Qdrant health check"""
        try:
            import httpx
            response = httpx.get(f"{settings.QDRANT_URL}/health")
            return {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "service": "qdrant",
                "status_code": response.status_code
            }
        except Exception as e:
            return {"status": "unhealthy", "service": "qdrant", "error": str(e)}
    
    @staticmethod
    def check_system() -> Dict[str, Any]:
        """Sistem durumu check"""
        import psutil
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @classmethod
    def get_full_health_status(cls) -> Dict[str, Any]:
        """Tam health status"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "redis": cls.check_redis(),
            "qdrant": cls.check_qdrant(),
            "system": cls.check_system(),
            "overall": "healthy"  # Tüm servisler healthy ise
        }

# Metrics collector
class MetricsCollector:
    """Sistem metrikleri toplayıcı"""
    
    def __init__(self):
        self.job_metrics = {
            "total_jobs": 0,
            "completed_jobs": 0,
            "failed_jobs": 0,
            "average_duration": 0.0
        }
        self.api_metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "average_response_time": 0.0
        }
    
    def increment_job_metric(self, metric: str):
        """Job metriği artır"""
        if metric in self.job_metrics and isinstance(self.job_metrics[metric], int):
            self.job_metrics[metric] += 1
    
    def update_job_duration(self, duration: float):
        """Job süre güncelle"""
        # Ortalama süre hesapla
        total_jobs = self.job_metrics["completed_jobs"]
        if total_jobs > 1:
            current_avg = self.job_metrics["average_duration"]
            self.job_metrics["average_duration"] = (current_avg * (total_jobs - 1) + duration) / total_jobs
        else:
            self.job_metrics["average_duration"] = duration
    
    def increment_api_metric(self, metric: str):
        """API metriği artır"""
        if metric in self.api_metrics and isinstance(self.api_metrics[metric], int):
            self.api_metrics[metric] += 1
    
    def update_response_time(self, response_time: float):
        """API response süre güncelle"""
        total_requests = self.api_metrics["total_requests"]
        if total_requests > 1:
            current_avg = self.api_metrics["average_response_time"]
            self.api_metrics["average_response_time"] = (current_avg * (total_requests - 1) + response_time) / total_requests
        else:
            self.api_metrics["average_response_time"] = response_time
    
    def get_metrics(self) -> Dict[str, Any]:
        """Tüm metrikleri döndür"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "jobs": self.job_metrics.copy(),
            "api": self.api_metrics.copy()
        }

# Global metrics instance
metrics = MetricsCollector()
