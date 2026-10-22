import hashlib
import os
from typing import Any, Dict, Optional

from fastapi import Request
from itsdangerous import URLSafeSerializer

from config import SECURE_COOKIES, SESSION_LIFETIME_HOURS

SECRET_KEY = os.getenv("SECRET_KEY")
serializer = URLSafeSerializer(SECRET_KEY or "")

SESSION_COOKIE_CONFIG: Dict[str, Any] = {
    "httponly": True,
    "secure": SECURE_COOKIES,
    "samesite": "strict",
    "max_age": SESSION_LIFETIME_HOURS * 3600,  # igual que expires_at de la sesión en BD
}


def sign_cookie(value: str) -> str:
    return str(serializer.dumps(value))


def verify_signed_cookie(value: str) -> Optional[str]:
    try:
        return str(serializer.loads(value))
    except Exception:
        return None


def get_session_token_hash(request: Request) -> Optional[str]:
    """
    Hash sha256 del token de la sesión actual, el que se guarda en user_sessions.

    Sale de la cookie firmada `session` de la petición. Devuelve None si no hay cookie o su
    firma no es válida (p. ej. con autenticación por API key no hay sesión de cookie).
    """
    signed_cookie = request.cookies.get("session")
    session_token = verify_signed_cookie(signed_cookie) if signed_cookie else None
    if not session_token:
        return None
    return hashlib.sha256(session_token.encode()).hexdigest()
