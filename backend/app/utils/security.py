"""
Utilidades de seguridad para DataMap
Funciones para generación de tokens, sanitización, manejo de IPs, etc.
"""

import functools
import hashlib
import hmac
import ipaddress
import logging
import os
import re
import secrets
import string
from typing import Any, Optional, Tuple, Union

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
        Obtiene la IP real del cliente considerando proxies de confianza.

        Las cabeceras X-Forwarded-For / X-Real-IP solo se usan si la conexión viene de
        un proxy de confianza (TRUSTED_PROXIES; por defecto redes privadas y loopback,
        donde están el balanceador de la plataforma o el proxy de docker). Antes se
        tomaba la primera IP de X-Forwarded-For, que la pone el propio cliente: rotando
        la cabecera se esquivaba cualquier límite por IP.

        X-Forwarded-For se recorre de derecha a izquierda (cada proxy añade al final la
        IP de quien le conectó) y se devuelve la primera IP que no es de un proxy.

        Args:
            request: Request de FastAPI

        Returns:
            str: IP del cliente
        """
        peer = request.client.host if request.client else None
        if not peer:
            return "unknown"
        if not _is_trusted_proxy(peer):
            return str(peer)

        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            hops = [hop.strip() for hop in forwarded_for.split(",")]
            for hop in reversed(hops):
                ip = _parse_ip(hop)
                if ip is None:
                    # Entrada malformada: lo que haya a su izquierda no es fiable
                    break
                if not _is_trusted_proxy(hop):
                    return str(ip)

        real_ip = _parse_ip((request.headers.get("X-Real-IP") or "").strip())
        if real_ip is not None:
            return str(real_ip)

        return str(peer)

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


_DEFAULT_TRUSTED_PROXIES = "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"


def _parse_ip(value: str) -> Optional[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


@functools.lru_cache(maxsize=8)
def _trusted_proxy_networks(
    spec: str,
) -> Tuple[Union[ipaddress.IPv4Network, ipaddress.IPv6Network], ...]:
    networks = []
    for item in spec.split(","):
        item = item.strip()
        if not item or item.lower() == "none":
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logging.getLogger(__name__).warning(f"Ignoring invalid TRUSTED_PROXIES entry: {item}")
    return tuple(networks)


def _is_trusted_proxy(value: str) -> bool:
    """True si la IP pertenece a TRUSTED_PROXIES (CIDRs separados por comas, "none" = ninguno)."""
    ip = _parse_ip(value)
    if ip is None:
        return False
    networks = _trusted_proxy_networks(os.getenv("TRUSTED_PROXIES", _DEFAULT_TRUSTED_PROXIES))
    return any(ip in network for network in networks)
