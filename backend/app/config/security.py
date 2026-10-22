"""
Configuración de seguridad para DataMap
Contiene todas las configuraciones relacionadas con seguridad, rate limiting, CSRF, etc.
"""

import os
from typing import Any, Dict, Optional

from app.utils.master_key import InvalidMasterKeyError, parse_master_key


class SecuritySettings:
    """Configuraciones de seguridad centralizadas"""

    # === RATE LIMITING ===
    # En login el máximo es de FALLOS por ventana: los logins correctos no cuentan
    RATE_LIMIT_LOGIN_ATTEMPTS = int(os.getenv("RATE_LIMIT_LOGIN_ATTEMPTS", "5"))
    RATE_LIMIT_LOGIN_WINDOW = int(os.getenv("RATE_LIMIT_LOGIN_WINDOW", "900"))  # 15 minutos

    RATE_LIMIT_REGISTER_ATTEMPTS = int(os.getenv("RATE_LIMIT_REGISTER_ATTEMPTS", "3"))
    RATE_LIMIT_REGISTER_WINDOW = int(os.getenv("RATE_LIMIT_REGISTER_WINDOW", "3600"))  # 1 hora

    RATE_LIMIT_FORGOT_ATTEMPTS = int(os.getenv("RATE_LIMIT_FORGOT_ATTEMPTS", "3"))
    RATE_LIMIT_FORGOT_WINDOW = int(os.getenv("RATE_LIMIT_FORGOT_WINDOW", "3600"))  # 1 hora

    RATE_LIMIT_VERIFY_ATTEMPTS = int(os.getenv("RATE_LIMIT_VERIFY_ATTEMPTS", "10"))
    RATE_LIMIT_VERIFY_WINDOW = int(os.getenv("RATE_LIMIT_VERIFY_WINDOW", "3600"))  # 1 hora

    RATE_LIMIT_RESEND_ATTEMPTS = int(os.getenv("RATE_LIMIT_RESEND_ATTEMPTS", "3"))
    RATE_LIMIT_RESEND_WINDOW = int(os.getenv("RATE_LIMIT_RESEND_WINDOW", "600"))  # 10 minutos

    RATE_LIMIT_RESET_ATTEMPTS = int(os.getenv("RATE_LIMIT_RESET_ATTEMPTS", "5"))
    RATE_LIMIT_RESET_WINDOW = int(os.getenv("RATE_LIMIT_RESET_WINDOW", "3600"))  # 1 hora

    # Saltos de proxy de confianza delante de la app: con N > 0 la IP del cliente es la entrada
    # N-ésima (desde la derecha) de X-Forwarded-For; con 0, la IP del socket (cabecera ignorada)
    TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))

    # === CSRF PROTECTION ===
    CSRF_TOKEN_LENGTH = int(os.getenv("CSRF_TOKEN_LENGTH", "32"))
    CSRF_TOKEN_EXPIRY = int(os.getenv("CSRF_TOKEN_EXPIRY", "3600"))  # 1 hora
    CSRF_SECRET_KEY = os.getenv("CSRF_SECRET_KEY", os.getenv("SECRET_KEY", "default-csrf-secret"))

    # === OTP CONFIGURATION ===
    OTP_LENGTH = int(os.getenv("OTP_LENGTH", "8"))  # Cambiado de 6 a 8
    OTP_EXPIRY_MINUTES = int(os.getenv("OTP_EXPIRY_MINUTES", "15"))
    OTP_CHARSET = os.getenv("OTP_CHARSET", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")  # Alfanumérico
    # Intentos fallidos permitidos por código: al llegar a este número el OTP se invalida
    OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))

    # === ACCOUNT LOCKOUT ===
    MAX_FAILED_LOGIN_ATTEMPTS = int(os.getenv("MAX_FAILED_LOGIN_ATTEMPTS", "5"))
    ACCOUNT_LOCKOUT_DURATION = int(os.getenv("ACCOUNT_LOCKOUT_DURATION", "1800"))  # 30 minutos

    # === SECURITY HEADERS ===
    CONTENT_SECURITY_POLICY = os.getenv(
        "CONTENT_SECURITY_POLICY",
        "default-src 'self'; script-src 'self' 'unsafe-inline' https://js.stripe.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.stripe.com https://cdn.jsdelivr.net; "
        "frame-src https://js.stripe.com https://hooks.stripe.com;",
    )

    X_FRAME_OPTIONS = os.getenv("X_FRAME_OPTIONS", "DENY")
    X_CONTENT_TYPE_OPTIONS = os.getenv("X_CONTENT_TYPE_OPTIONS", "nosniff")
    X_XSS_PROTECTION = os.getenv("X_XSS_PROTECTION", "1; mode=block")
    REFERRER_POLICY = os.getenv("REFERRER_POLICY", "strict-origin-when-cross-origin")
    STRICT_TRANSPORT_SECURITY = os.getenv(
        "STRICT_TRANSPORT_SECURITY", "max-age=31536000; includeSubDomains"
    )

    # === LOGGING ===
    SECURITY_LOG_LEVEL = os.getenv("SECURITY_LOG_LEVEL", "INFO")
    LOG_FAILED_ATTEMPTS = os.getenv("LOG_FAILED_ATTEMPTS", "true").lower() == "true"
    LOG_SUCCESSFUL_LOGINS = os.getenv("LOG_SUCCESSFUL_LOGINS", "true").lower() == "true"

    # === IP PRIVACY ===
    HASH_IP_ADDRESSES = os.getenv("HASH_IP_ADDRESSES", "true").lower() == "true"
    IP_HASH_SALT = os.getenv("IP_HASH_SALT", os.getenv("SECRET_KEY", "default-ip-salt"))

    # === ENCRYPTION (AES-256-GCM + Argon2id) ===
    ENCRYPTION_ENABLED = os.getenv("ENCRYPTION_ENABLED", "false").lower() == "true"

    # Argon2id configuration (OWASP 2025 recommendations)
    ARGON2_MEMORY_COST = int(os.getenv("ARGON2_MEMORY_COST", str(64 * 1024)))  # 64 MiB in KB
    ARGON2_TIME_COST = int(os.getenv("ARGON2_TIME_COST", "3"))  # Iterations
    ARGON2_PARALLELISM = int(os.getenv("ARGON2_PARALLELISM", "1"))  # Degree of parallelism

    # Data retention policies
    DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "90"))  # 90 days default
    AUTO_PURGE_ON_PROJECT_COMPLETE = (
        os.getenv("AUTO_PURGE_ON_PROJECT_COMPLETE", "false").lower() == "true"
    )
    ENCRYPTION_SESSION_TIMEOUT = int(
        os.getenv("ENCRYPTION_SESSION_TIMEOUT", "3600")
    )  # 1 hour (SECURITY HARDENED)

    # === PASSPHRASE RATE LIMITING ===
    # Rate limiting específico para verificación de passphrases de encriptación
    # Previene ataques de fuerza bruta en passphrases
    PASSPHRASE_MAX_ATTEMPTS = int(os.getenv("PASSPHRASE_MAX_ATTEMPTS", "5"))
    PASSPHRASE_WINDOW_SECONDS = int(os.getenv("PASSPHRASE_WINDOW_SECONDS", "600"))  # 10 minutos
    PASSPHRASE_LOCKOUT_SECONDS = int(os.getenv("PASSPHRASE_LOCKOUT_SECONDS", "900"))  # 15 minutos

    # Feature Flags para encriptación
    ENABLE_KEY_ROTATION = (
        os.getenv("ENABLE_KEY_ROTATION", "false").lower() == "true"
    )  # NO habilitar hasta completar implementación
    ENABLE_ENCRYPTION_SESSION_REFRESH = (
        os.getenv("ENABLE_ENCRYPTION_SESSION_REFRESH", "true").lower() == "true"
    )

    # === SESSION TOKEN ROTATION (FASE 2.2) ===
    # Previene session fixation attacks mediante rotación de tokens
    # Configuración del grace period para manejar race conditions
    SESSION_ROTATION_GRACE_PERIOD = int(
        os.getenv("SESSION_ROTATION_GRACE_PERIOD", "30")
    )  # 30 segundos default

    # Background tasks
    ENCRYPTION_CLEANUP_INTERVAL_MINUTES = int(
        os.getenv("ENCRYPTION_CLEANUP_INTERVAL_MINUTES", "15")
    )  # Cleanup cada 15 minutos
    RATE_LIMITER_CLEANUP_INTERVAL_MINUTES = int(
        os.getenv("RATE_LIMITER_CLEANUP_INTERVAL_MINUTES", "60")
    )  # Cleanup cada hora

    # === CLEANUP ===
    CLEANUP_INTERVAL_HOURS = int(os.getenv("CLEANUP_INTERVAL_HOURS", "24"))
    SECURITY_LOGS_RETENTION_DAYS = int(os.getenv("SECURITY_LOGS_RETENTION_DAYS", "90"))
    RATE_LIMIT_RETENTION_DAYS = int(os.getenv("RATE_LIMIT_RETENTION_DAYS", "7"))
    CSRF_TOKEN_RETENTION_DAYS = int(os.getenv("CSRF_TOKEN_RETENTION_DAYS", "1"))

    # === ENDPOINTS PROTEGIDOS ===
    CSRF_PROTECTED_METHODS = ["POST", "PUT", "PATCH", "DELETE"]
    CSRF_EXEMPT_ENDPOINTS = [
        "/api/webhooks/stripe",  # Webhooks externos
        "/api/health",  # Health checks
        "/static/",  # Archivos estáticos
        "/docs",  # Documentación de API
        "/openapi.json",  # OpenAPI schema
        "/favicon.ico",  # Favicon
    ]

    # 🔐 CSRF Exemptions específicos para encriptación (Fase 1.6)
    # Estos endpoints usan httpOnly cookies con SameSite=Strict (inmunes a CSRF)
    # La protección CSRF viene de las cookies, no de tokens
    # Referencia: Auditoría de Seguridad 2025-01-03, Fase 1.1 + 1.6
    CSRF_EXEMPT_ENCRYPTION_ENDPOINTS = [
        "/encryption/setup",
        "/encryption/verify",
        "/encryption/rotate-key",
        "/encryption/enable",
        "/encryption/disable",
    ]

    # Rutas que NO requieren CSRF en modo desarrollo
    DEVELOPMENT_CSRF_EXEMPT = [
        "/",  # Página principal
        "/projects",  # Proyectos
        "/billing",  # Facturación
        "/settings",  # Configuraciones
        "/schemas",  # Esquemas
        "/table_attributes",  # Atributos de tabla
        "/project_visual",  # Visualización de proyecto
    ]

    # === CONFIGURACIÓN DE DESARROLLO ===
    DEVELOPMENT_MODE = os.getenv("ENV", "production").lower() in ["development", "dev", "debug"]
    DISABLE_CSRF_IN_DEVELOPMENT = os.getenv("DISABLE_CSRF_IN_DEV", "true").lower() == "true"

    def get_rate_limit_config(
        self, endpoint: str, rule: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Obtiene la configuración de rate limiting aplicable a un endpoint

        La regla explícita (la del decorador de la ruta) manda sobre la de por defecto; en
        desarrollo, la configuración permisiva manda sobre ambas.
        """
        # En modo desarrollo, usar configuración muy permisiva
        if self.DEVELOPMENT_MODE:
            # Configuración súper permisiva para desarrollo
            dev_config = {
                "max_attempts": 1000,  # Muchísimos intentos en desarrollo
                "window_seconds": 60,  # Ventana de solo 1 minuto
                "block_duration": 10,  # Solo 10 segundos de bloqueo
            }
            return dev_config

        if rule is not None:
            return rule

        # Configuración para producción
        default_config = {
            "max_attempts": 20,  # Más intentos en producción
            "window_seconds": 3600,  # 1 hora
            "block_duration": 300,  # 5 minutos de bloqueo
        }

        return default_config

    @classmethod
    def is_csrf_protected_endpoint(cls, path: str, method: str) -> bool:
        """
        Determina si un endpoint requiere protección CSRF

        Lógica:
        1. En desarrollo con DISABLE_CSRF_IN_DEV=true → No requiere CSRF
        2. Si método no es POST/PUT/PATCH/DELETE → No requiere CSRF
        3. Si está en CSRF_EXEMPT_ENDPOINTS → No requiere CSRF
        4. Si es endpoint de encriptación → No requiere CSRF (usa SameSite=Strict cookies)
        5. En desarrollo, rutas adicionales exentas → No requiere CSRF
        6. Todo lo demás → Requiere CSRF

        Args:
            path: Path del request (ej: /api/projects/123/encryption/verify)
            method: Método HTTP (GET, POST, etc.)

        Returns:
            True si requiere CSRF token, False si está exento
        """
        # En modo desarrollo, opcionalmente deshabilitar CSRF completamente
        if cls.DEVELOPMENT_MODE and cls.DISABLE_CSRF_IN_DEVELOPMENT:
            return False

        if method not in cls.CSRF_PROTECTED_METHODS:
            return False

        # Verificar rutas siempre exentas
        for exempt_path in cls.CSRF_EXEMPT_ENDPOINTS:
            if path.startswith(exempt_path):
                return False

        # 🔐 NUEVO: Verificar endpoints de encriptación (usan SameSite=Strict cookies)
        for encryption_endpoint in cls.CSRF_EXEMPT_ENCRYPTION_ENDPOINTS:
            if encryption_endpoint in path:
                return False

        # En modo desarrollo, exentar rutas adicionales
        if cls.DEVELOPMENT_MODE:
            for exempt_path in cls.DEVELOPMENT_CSRF_EXEMPT:
                if path == exempt_path or path.startswith(exempt_path + "/"):
                    return False

        return True

    @classmethod
    def get_security_headers(cls) -> Dict[str, str]:
        """Retorna todos los headers de seguridad configurados"""
        return {
            "X-Content-Type-Options": cls.X_CONTENT_TYPE_OPTIONS,
            "X-Frame-Options": cls.X_FRAME_OPTIONS,
            "X-XSS-Protection": cls.X_XSS_PROTECTION,
            "Referrer-Policy": cls.REFERRER_POLICY,
            "Content-Security-Policy": cls.CONTENT_SECURITY_POLICY,
            "Strict-Transport-Security": cls.STRICT_TRANSPORT_SECURITY,
        }


# Instancia global de configuración
security_settings = SecuritySettings()


def _validate_secrets(errors: list, warnings: list) -> None:
    """SECRET_KEY y ENCRYPTION_MASTER_KEY (antes no se comprobaban al arrancar)."""
    # Firma la cookie de sesión (app/utils/cookies.py); vacío = firma con clave ""
    secret_key = os.getenv("SECRET_KEY", "")
    if not secret_key.strip():
        errors.append("SECRET_KEY debe configurarse en producción")
    elif len(secret_key) < 32:
        warnings.append("SECRET_KEY debería tener al menos 32 caracteres aleatorios")

    # Cifra las credenciales de las conexiones a BDs externas
    master_key = os.getenv("ENCRYPTION_MASTER_KEY")
    if not master_key:
        warnings.append(
            "ENCRYPTION_MASTER_KEY no configurada: las conexiones a BDs externas no funcionarán"
        )
        return
    try:
        parse_master_key(master_key)
    except InvalidMasterKeyError as e:
        errors.append(str(e))


# Validaciones de configuración
def validate_security_config():
    """Valida que la configuración de seguridad sea correcta"""
    errors = []
    warnings = []

    if security_settings.CSRF_SECRET_KEY == "default-csrf-secret":
        errors.append("CSRF_SECRET_KEY debe ser configurado en producción")

    if security_settings.IP_HASH_SALT == "default-ip-salt":
        errors.append("IP_HASH_SALT debe ser configurado en producción")

    _validate_secrets(errors, warnings)

    if security_settings.OTP_LENGTH < 6:
        errors.append("OTP_LENGTH debe ser al menos 6 caracteres")

    # Sin SMTP el código OTP no llega al usuario (fuera de desarrollo tampoco se imprime)
    if not (os.getenv("SMTP_SERVER") and os.getenv("EMAIL_FROM")):
        warnings.append(
            "SMTP_SERVER/EMAIL_FROM no configurados: los códigos de verificación no se entregarán"
        )

    # Detrás del proxy de Render (que fija RENDER=true) con 0 saltos todos los usuarios comparten
    # la IP del proxy: los límites por IP serían globales
    on_render = os.getenv("RENDER", "").strip().lower() == "true"
    if on_render and security_settings.TRUSTED_PROXY_HOPS == 0:
        warnings.append(
            "TRUSTED_PROXY_HOPS=0 en Render: todos los usuarios comparten IP y los límites por IP "
            "serán globales (fija TRUSTED_PROXY_HOPS; ver backend/docs/DEPLOYMENT_GUIDE.md)"
        )

    # Con "*" uvicorn confía en cualquier cliente y reescribe request.client con la primera
    # entrada de X-Forwarded-For, que escribe el cliente
    if os.getenv("FORWARDED_ALLOW_IPS", "").strip() == "*":
        warnings.append(
            "FORWARDED_ALLOW_IPS=*: uvicorn confiaría en cualquier cliente y request.client "
            "pasaría a ser suplantable (lista solo las IPs de los proxies de confianza)"
        )

    # Validaciones de cifrado
    if security_settings.ENCRYPTION_ENABLED:
        # Validar Argon2id memory cost (mínimo 16 MiB, recomendado 64 MiB)
        if security_settings.ARGON2_MEMORY_COST < 16 * 1024:
            errors.append(
                f"ARGON2_MEMORY_COST debe ser al menos {16 * 1024} KB (16 MiB). "
                f"Actual: {security_settings.ARGON2_MEMORY_COST} KB"
            )
        elif security_settings.ARGON2_MEMORY_COST < 64 * 1024:
            warnings.append(
                f"ARGON2_MEMORY_COST es menor que el recomendado (64 MiB). "
                f"Actual: {security_settings.ARGON2_MEMORY_COST} KB"
            )

        # Validar iterations (mínimo 2, recomendado 3)
        if security_settings.ARGON2_TIME_COST < 2:
            errors.append(
                f"ARGON2_TIME_COST debe ser al menos 2. "
                f"Actual: {security_settings.ARGON2_TIME_COST}"
            )
        elif security_settings.ARGON2_TIME_COST < 3:
            warnings.append(
                f"ARGON2_TIME_COST es menor que el recomendado (3). "
                f"Actual: {security_settings.ARGON2_TIME_COST}"
            )

        # Validar parallelism (mínimo 1)
        if security_settings.ARGON2_PARALLELISM < 1:
            errors.append(
                f"ARGON2_PARALLELISM debe ser al menos 1. "
                f"Actual: {security_settings.ARGON2_PARALLELISM}"
            )

        # Validar data retention
        if security_settings.DATA_RETENTION_DAYS < 1:
            errors.append(
                f"DATA_RETENTION_DAYS debe ser al menos 1. "
                f"Actual: {security_settings.DATA_RETENTION_DAYS}"
            )

    # En producción, mostrar warnings
    if not security_settings.DEVELOPMENT_MODE:
        if len(warnings) > 0:
            print(f"⚠️  ADVERTENCIAS DE SEGURIDAD:\n   - " + "\n   - ".join(warnings))

        if len(errors) > 0:
            raise ValueError(f"❌ ERRORES CRÍTICOS DE SEGURIDAD:\n   - " + "\n   - ".join(errors))

    return len(errors) == 0


# Ejecutar validación al importar
if __name__ != "__main__":
    validate_security_config()
