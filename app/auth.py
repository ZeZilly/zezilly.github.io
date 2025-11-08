"""
Authentication ve Authorization modülü
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import secrets
import string
from .settings import settings

# JWT ayarları
SECRET_KEY = settings.SECRET_KEY if hasattr(settings, 'SECRET_KEY') else secrets.token_urlsafe(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Şifre hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token
security = HTTPBearer()

# Token modeli
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# Kullanıcı modeli
class User(BaseModel):
    username: str
    email: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False

class UserInDB(User):
    hashed_password: str

# Demo kullanıcı veritabanı (gerçek uygulamada veritabanı kullanılacak)
fake_users_db: Dict[str, UserInDB] = {
    "admin": {
        "username": "admin",
        "email": "admin@example.com",
        "hashed_password": pwd_context.hash("admin123"),
        "is_active": True,
        "is_admin": True,
    },
    "user": {
        "username": "user", 
        "email": "user@example.com",
        "hashed_password": pwd_context.hash("user123"),
        "is_active": True,
        "is_admin": False,
    }
}

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Şifre doğrulama"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Şifre hashleme"""
    return pwd_context.hash(password)

def get_user(username: str) -> Optional[UserInDB]:
    """Kullanıcı bilgilerini al"""
    user_dict = fake_users_db.get(username)
    if user_dict:
        return UserInDB(**user_dict)
    return None

def authenticate_user(username: str, password: str) -> Optional[User]:
    """Kullanıcı kimlik doğrulama"""
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return User(username=user.username, email=user.email, is_active=user.is_active, is_admin=user.is_admin)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """JWT token oluşturma"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    """Token doğrulama"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    return token_data

def get_current_user(token_data: TokenData = Depends(verify_token)) -> User:
    """Mevcut kullanıcıyı al"""
    user = get_user(token_data.username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return User(username=user.username, email=user.email, is_active=user.is_active, is_admin=user.is_admin)

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Admin yetkisi gerektiren endpoint'ler için"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user

# Rate limiting için yardımcı fonksiyonlar
def generate_api_key() -> str:
    """API key oluşturma"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(32))

# API key storage (gerçek uygulamada veritabanı kullanılacak)
api_keys: Dict[str, Dict[str, Any]] = {}
