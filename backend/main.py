# main.py
import mimetypes
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.middleware.csrf_protection import csrf_middleware
from app.middleware.encryption_session import EncryptionSessionMiddleware
from app.middleware.request_logging import request_logging_middleware

# Importar middlewares de seguridad
from app.middleware.security_headers import setup_security_middlewares
from app.routers import (
    activity,
    admin,
    auth,
    billing,
    comments,
    db_connections,
    encryption,
    locks,
    mappings,
    migration,
    notifications,
    projects,
    realtime,
    schemas,
    settings,
    user_settings,
    versions,
)
from app.utils.cookies import sign_cookie, verify_signed_cookie
from app.utils.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES

load_dotenv()

app = FastAPI(title="DataMapper API", version="1.0.0")

# Determinar el entorno
ENV = os.getenv("ENV", "production")
IS_DEVELOPMENT = ENV in ["development", "dev", "debug"]

# Configurar CORS: orígenes del frontend en CORS_ALLOWED_ORIGINS (separados por comas).
# Antes la lista de producción estaba vacía (solo localhost): un frontend en otro dominio
# no podía llamar a la API, y en producción se aceptaban orígenes localhost con cookies.
DEV_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


def get_allowed_origins(env_value: str, is_development: bool) -> list:
    configured = [o.strip().rstrip("/") for o in env_value.split(",") if o.strip()]
    if "*" in configured:
        # allow_credentials=True con "*" haría que cualquier web use la sesión del usuario
        raise ValueError("CORS_ALLOWED_ORIGINS cannot contain '*'")
    return (DEV_ORIGINS if is_development else []) + configured


allowed_origins = get_allowed_origins(os.getenv("CORS_ALLOWED_ORIGINS", ""), IS_DEVELOPMENT)
if not allowed_origins:
    print("⚠️  CORS_ALLOWED_ORIGINS no configurado: solo funcionará un frontend del mismo origen")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Middleware de sesiones de cifrado (debe ir antes de los routers)
app.add_middleware(EncryptionSessionMiddleware)

# Configurar middlewares de seguridad
# En desarrollo, deshabilitar HSTS
setup_security_middlewares(app, enable_csp=True, enable_hsts=not IS_DEVELOPMENT)

# El rate limiting va por ruta (@rate_limit en routers/auth.py), no como middleware global

# Middleware de protección CSRF (deshabilitado en desarrollo)
if not IS_DEVELOPMENT:
    app.middleware("http")(csrf_middleware)


# Middleware para resolver el locale en cada request
@app.middleware("http")
async def resolve_locale_middleware(request: Request, call_next):
    # 1) lang por query SIEMPRE tiene prioridad
    qs_lang = request.query_params.get("lang")
    if qs_lang in SUPPORTED_LOCALES:
        locale = qs_lang
        set_cookie_from_query = True
    else:
        set_cookie_from_query = False
        # 2) cookie firmada si no viene query
        cookie_val = request.cookies.get("locale")
        loc = verify_signed_cookie(cookie_val) if cookie_val else None
        if loc in SUPPORTED_LOCALES:
            locale = loc
        else:
            # 3) Accept-Language muy básico
            header = (request.headers.get("Accept-Language") or "").lower()
            locale = "en-US" if header.startswith("en") else DEFAULT_LOCALE

    request.state.locale = locale
    response = await call_next(request)

    # Si se pasó ?lang= válido, persistimos en cookie para siguientes peticiones
    if set_cookie_from_query:
        response.set_cookie(
            key="locale",
            value=sign_cookie(locale),
            max_age=60 * 60 * 24 * 365,
            path="/",
            secure=not IS_DEVELOPMENT,  # Solo secure en producción
            httponly=True,
            samesite="Lax",
        )
    return response


# Rutas
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(schemas.router)
app.include_router(mappings.router)
app.include_router(settings.router)
app.include_router(notifications.router)
app.include_router(realtime.router)
app.include_router(billing.router)

# Collaboration & Version Control routes
app.include_router(versions.router)
app.include_router(locks.router)
app.include_router(comments.router)
app.include_router(activity.router)

# Encryption routes
app.include_router(encryption.router)

# Database Connections routes (External DB introspection)
app.include_router(db_connections.router)

# Migration routes (Script generation and execution)
app.include_router(migration.router)
app.include_router(migration.global_router)


# User settings routes
app.include_router(user_settings.router)

# Admin routes
app.include_router(admin.router)

# Request logging middleware (fire-and-forget, registra todos los endpoints salvo excluidos)
app.middleware("http")(request_logging_middleware)


# Ensure .webp MIME type is registered (not always present on Windows)
mimetypes.add_type("image/webp", ".webp")

# Static files for user uploads (avatars, etc.)
os.makedirs("uploads/avatars", exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory="uploads"), name="uploads")


# Ruta de health check
@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "1.0.0", "environment": ENV}


# Ruta raíz
@app.get("/")
def home():
    return {"message": "DataMapper API", "version": "1.0.0"}
