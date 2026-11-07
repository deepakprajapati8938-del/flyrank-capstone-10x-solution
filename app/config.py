import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Application Configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "incidentpulse.db"))
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Authentication & JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super_secret_jwt_hmac_signing_key_replace_in_production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "1440"))

# Caching Configuration
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))

# AI Provider Configuration ($0 / Free Tier with Deterministic Fallback)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "gemini-1.5-flash")
