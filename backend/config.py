import os

from app.utils.i18n import DEFAULT_LOCALE, translate

ENV = os.getenv("ENV", "prod")
SECRET_KEY = os.getenv("SECRET_KEY")
if ENV in ["development", "dev", "debug"]:
    SECURE_COOKIES = False
else:
    SECURE_COOKIES = os.getenv("SECURE_COOKIES", "True").lower() == "true"

# Vigencia de la sesión de usuario (horas): una única fuente para la fila de user_sessions
# (expires_at) y para el Max-Age de la cookie, que no pueden diferir
SESSION_LIFETIME_HOURS = int(os.getenv("SESSION_LIFETIME_HOURS", "24"))

# Redis Configuration (Encryption Session Cache)
REDIS_URL = os.getenv("REDIS_URL")  # Formato: redis://[:password@]host:port/db
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_SSL = os.getenv("REDIS_SSL", "false").lower() == "true"

# Encryption Session Configuration
ENCRYPTION_SESSION_TIMEOUT = int(
    os.getenv("ENCRYPTION_SESSION_TIMEOUT", "10800")
)  # 3 horas default

# Configuración de la ruta base y plantillas
BASE_DIR = os.path.join(os.path.dirname(__file__), "app")


# Fábrica para crear la función _ con el locale de la request
def make_translator(request):
    loc = getattr(request.state, "locale", DEFAULT_LOCALE)
    return lambda key, **kwargs: translate(key, loc, **kwargs)
