"""
Rate Limiting ve Güvenlik Middleware'leri
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import re
from typing import Callable
from .settings import settings

# Rate limiter instance
limiter = Limiter(key_func=get_remote_address)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Güvenlik başlıkları middleware'i"""
    
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        
        # Güvenlik başlıkları
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
        
        return response

class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """Input sanitization middleware'i"""
    
    def __init__(self, app, patterns=None):
        super().__init__(app)
        self.patterns = patterns or [
            r'<script.*?>.*?</script>',  # XSS patterns
            r'javascript:',
            r'on\w+\s*=',  # Event handlers
        ]
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.patterns]
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Path ve query parameters'ları kontrol et
        for param in list(request.path_params.values()) + list(request.query_params.values()):
            if isinstance(param, str) and self._contains_malicious_pattern(param):
                raise HTTPException(status_code=400, detail="Malicious input detected")
        
        response = await call_next(request)
        return response
    
    def _contains_malicious_pattern(self, text: str) -> bool:
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return True
        return False

# IP rate limiting decorator'ları
def get_client_ip(request: Request) -> str:
    """Client IP adresini al"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return get_remote_address(request)

# Rate limit decorator'ları
api_rate_limit = "10/minute"
ingest_rate_limit = "5/minute" 
admin_rate_limit = "30/minute"

# CORS ayarları
def get_cors_origins():
    """CORS origins'ları döndür"""
    if settings.ENV == "production":
        return ["https://yourdomain.com"]
    else:
        return ["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"]

# IP whitelisting için decorator
def require_whitelisted_ip():
    """IP whitelisting decorator (gelecekte implement edilecek)"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# Input validation helpers
def validate_url(url: str) -> bool:
    """URL validation"""
    if not url:
        return False
    try:
        from urllib.parse import urlparse
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def sanitize_filename(filename: str) -> str:
    """Dosya adı sanitization"""
    if not filename:
        return "unnamed"
    
    # Güvenli karakterler
    safe_chars = re.sub(r'[^\w\-\.]', '_', filename)
    return safe_chars[:255]  # Maksimum 255 karakter
