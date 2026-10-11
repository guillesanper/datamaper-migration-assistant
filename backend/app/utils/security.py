"""
Utilidades de seguridad para DataMap
Funciones para generación de tokens, sanitización, manejo de IPs, etc.
"""

import hashlib
import hmac
import re
import secrets
import string
from typing import Any, Optional, Union

import bleach  # type: ignore[import-untyped]
from fastapi import Request
from user_agents import parse

from app.config.security import security_settings


class SecurityUtils:
    """Utilidades de seguridad centralizadas"""

    @staticmethod
    def generate_secure_otp(length: Optional[int] = None) -> str:
        """
        Genera un OTP seguro alfanumérico

        Args:
            length: Longitud del OTP (por defecto usa configuración)

        Returns:
            str: OTP generado
        """
        if length is None:
            length = security_settings.OTP_LENGTH

        charset = security_settings.OTP_CHARSET
        return "".join(secrets.choice(charset) for _ in range(length))

    @staticmethod
    def generate_csrf_token(length: Optional[int] = None) -> str:
        """
        Genera un token CSRF seguro

        Args:
            length: Longitud del token (por defecto usa configuración)

        Returns:
            str: Token CSRF generado
        """
        if length is None:
            length = security_settings.CSRF_TOKEN_LENGTH

        return secrets.token_urlsafe(length)

    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """
        Genera un token seguro genérico

        Args:
            length: Longitud del token

        Returns:
            str: Token generado
        """
        return secrets.token_urlsafe(length)

    @staticmethod
    def sanitize_input(input_str: str, max_length: int = 255) -> str:
        """
        Sanitiza entrada de usuario

        Args:
            input_str: String a sanitizar
            max_length: Longitud máxima permitida

        Returns:
            str: String sanitizado
        """
        if not input_str:
            return ""

        # Remover caracteres de control primero (antes de bleach)
        cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", input_str)

        # Limpiar HTML/scripts
        cleaned = bleach.clean(cleaned, tags=[], strip=True)

        # Truncar si es necesario
        if len(cleaned) > max_length:
            cleaned = cleaned[:max_length]

        return str(cleaned.strip())

    @staticmethod
    def sanitize_email(email: str) -> str:
        """
        Sanitiza y normaliza email

        Args:
            email: Email a sanitizar

        Returns:
            str: Email sanitizado
        """
        if not email:
            return ""

        email = SecurityUtils.sanitize_input(email, 254)  # RFC 5321 limit
        return email.lower().strip()

    @staticmethod
    def sanitize_username(username: str) -> str:
        """
        Sanitiza username permitiendo solo caracteres alfanuméricos y algunos especiales

        Args:
            username: Username a sanitizar

        Returns:
            str: Username sanitizado
        """
        if not username:
            return ""

        # Permitir solo letras, números, guiones y guiones bajos
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "", username)

        # Truncar si es necesario
        if len(sanitized) > 50:
            sanitized = sanitized[:50]

        return sanitized.strip()

    @staticmethod
    def get_client_ip(request: Request) -> str:
        """
        Obtiene la IP del cliente considerando los proxies de confianza

        X-Forwarded-For solo cuenta si hay proxies de confianza delante (TRUSTED_PROXY_HOPS > 0):
        con N saltos, la IP es la entrada N-ésima desde la derecha, la que añadió el primer proxy
        de confianza; las de su izquierda las puede escribir el cliente. Con 0 saltos (por
        defecto) la cabecera se ignora y se usa la IP del socket. X-Real-IP y X-Forwarded no se
        usan: no hay forma de saber quién las escribió.

        Args:
            request: Request de FastAPI

        Returns:
            str: IP del cliente
        """
        socket_ip = str(request.client.host) if request.client else "unknown"

        hops = security_settings.TRUSTED_PROXY_HOPS
        forwarded_for = request.headers.get("X-Forwarded-For") if hops > 0 else None
        if forwarded_for:
            entries = [entry.strip() for entry in forwarded_for.split(",") if entry.strip()]
            # Con menos entradas que saltos la cadena no es la esperada: no se fía
            if len(entries) >= hops:
                return entries[-hops]

        return socket_ip

    @staticmethod
    def hash_ip_address(ip_address: str) -> str:
        """
        Hashea una dirección IP para privacidad

        Args:
            ip_address: IP a hashear

        Returns:
            str: Hash de la IP
        """
        if not security_settings.HASH_IP_ADDRESSES:
            return ip_address

        salt = security_settings.IP_HASH_SALT.encode("utf-8")
        ip_bytes = ip_address.encode("utf-8")

        return hashlib.sha256(salt + ip_bytes).hexdigest()[:16]

    @staticmethod
    def get_user_agent_info(request: Request) -> dict:
        """
        Extrae información del User-Agent

        Args:
            request: Request de FastAPI

        Returns:
            dict: Información del User-Agent
        """
        user_agent_string = request.headers.get("User-Agent", "")
        user_agent = parse(user_agent_string)

        return {
            "browser": f"{user_agent.browser.family} {user_agent.browser.version_string}",
            "os": f"{user_agent.os.family} {user_agent.os.version_string}",
            "device": user_agent.device.family,
            "is_mobile": user_agent.is_mobile,
            "is_tablet": user_agent.is_tablet,
            "is_pc": user_agent.is_pc,
            "is_bot": user_agent.is_bot,
            "raw": user_agent_string[:200],  # Truncar para almacenamiento
        }

    @staticmethod
    def create_hmac_signature(data: str, secret: str) -> str:
        """
        Crea una firma HMAC para verificación de integridad

        Args:
            data: Datos a firmar
            secret: Clave secreta

        Returns:
            str: Firma HMAC
        """
        return hmac.new(secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()

    @staticmethod
    def verify_hmac_signature(data: str, signature: str, secret: str) -> bool:
        """
        Verifica una firma HMAC

        Args:
            data: Datos originales
            signature: Firma a verificar
            secret: Clave secreta

        Returns:
            bool: True si la firma es válida
        """
        expected_signature = SecurityUtils.create_hmac_signature(data, secret)
        return hmac.compare_digest(signature, expected_signature)

    @staticmethod
    def is_safe_redirect_url(url: str, allowed_hosts: Optional[list[Any]] = None) -> bool:
        """
        Verifica si una URL es segura para redirección

        Args:
            url: URL a verificar
            allowed_hosts: Lista de hosts permitidos

        Returns:
            bool: True si la URL es segura
        """
        if not url:
            return False

        # URLs relativas son seguras
        if url.startswith("/") and not url.startswith("//"):
            return True

        # Si no hay hosts permitidos, solo URLs relativas
        if not allowed_hosts:
            return False

        # Verificar hosts permitidos
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            return parsed.netloc in allowed_hosts
        except Exception:
            return False

    @staticmethod
    def mask_sensitive_data(data: str, mask_char: str = "*", visible_chars: int = 4) -> str:
        """
        Enmascara datos sensibles para logging

        Args:
            data: Datos a enmascarar
            mask_char: Carácter para enmascarar
            visible_chars: Caracteres visibles al final

        Returns:
            str: Datos enmascarados
        """
        if not data or len(data) <= visible_chars:
            return mask_char * len(data) if data else ""

        masked_length = len(data) - visible_chars
        return mask_char * masked_length + data[-visible_chars:]

    @staticmethod
    def validate_password_strength(password: str) -> dict:
        """
        Valida la fortaleza de una contraseña

        Args:
            password: Contraseña a validar

        Returns:
            dict: Resultado de la validación
        """
        result: dict[str, Any] = {"is_valid": True, "errors": [], "score": 0, "suggestions": []}

        if len(password) < 8:
            result["errors"].append("La contraseña debe tener al menos 8 caracteres")
            result["is_valid"] = False
        else:
            result["score"] += 1

        if not re.search(r"[a-z]", password):
            result["errors"].append("La contraseña debe contener al menos una letra minúscula")
            result["is_valid"] = False
        else:
            result["score"] += 1

        if not re.search(r"[A-Z]", password):
            result["errors"].append("La contraseña debe contener al menos una letra mayúscula")
            result["is_valid"] = False
        else:
            result["score"] += 1

        if not re.search(r"[0-9]", password):
            result["errors"].append("La contraseña debe contener al menos un número")
            result["is_valid"] = False
        else:
            result["score"] += 1

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            result["suggestions"].append(
                "Considera añadir caracteres especiales para mayor seguridad"
            )
        else:
            result["score"] += 1

        if len(password) >= 12:
            result["score"] += 1

        # Verificar patrones comunes
        common_patterns = [
            r"123456",
            r"password",
            r"qwerty",
            r"abc123",
            r"admin",
            r"letmein",
            r"welcome",
            r"monkey",
        ]

        for pattern in common_patterns:
            if re.search(pattern, password.lower()):
                result["errors"].append("La contraseña contiene patrones comunes")
                result["is_valid"] = False
                break

        return result


# Funciones de conveniencia
def generate_otp() -> str:
    """Genera un OTP usando la configuración por defecto"""
    return SecurityUtils.generate_secure_otp()


def sanitize_input(input_str: str) -> str:
    """Sanitiza entrada usando configuración por defecto"""
    return SecurityUtils.sanitize_input(input_str)


def get_client_ip(request: Request) -> str:
    """Obtiene IP del cliente"""
    return SecurityUtils.get_client_ip(request)
