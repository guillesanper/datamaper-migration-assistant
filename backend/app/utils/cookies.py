import os
from typing import Any, Dict, Optional

from itsdangerous import URLSafeSerializer

from config import SECURE_COOKIES

SECRET_KEY = os.getenv("SECRET_KEY")
serializer = URLSafeSerializer(SECRET_KEY or "")

SESSION_COOKIE_CONFIG: Dict[str, Any] = {
    "httponly": True,
    "secure": SECURE_COOKIES,
    "samesite": "strict",
    "max_age": 60 * 60 * 24 * 7,  # 7 días
}


def sign_cookie(value: str) -> str:
    return str(serializer.dumps(value))


def verify_signed_cookie(value: str) -> Optional[str]:
    try:
        return str(serializer.loads(value))
    except Exception:
        return None
