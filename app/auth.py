import hashlib
import os
import datetime
import jwt
from typing import Optional, Dict, Any
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRATION_MINUTES, DATABASE_PATH
from app.database import get_db

security = HTTPBearer()

def hash_password(password: str) -> str:
    """Hashes password with random salt using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}${dk.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the salted PBKDF2 hash."""
    try:
        salt, expected_hex = hashed_password.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return hmac_equal(dk.hex(), expected_hex)
    except Exception:
        return False

def hmac_equal(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    import hmac
    return hmac.compare_digest(a, b)

def create_access_token(user_id: str, email: str, role: str) -> str:
    """Generates signed JWT access token with expiration."""
    exp = datetime.datetime.utcnow() + datetime.timedelta(minutes=JWT_EXPIRATION_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": exp
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def verify_access_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a signed JWT access token."""
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization token.")

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> Dict[str, Any]:
    """FastAPI dependency for authenticating protected routes."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload.")
        
        with get_db(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, email, role FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
            return dict(user)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization token.")

def require_admin(current_user: Dict[str, Any] = Security(get_current_user)) -> Dict[str, Any]:
    """RBAC dependency requiring admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin permissions required.")
    return current_user
