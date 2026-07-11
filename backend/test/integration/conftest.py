"""
Integration Test Fixtures

Fixtures adicionales específicas para tests de integración.
"""

import pytest

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_unique_user_data(worker_id, base_username="testuser", base_email="test@example.com"):
    """
    Genera datos de usuario únicos por worker para evitar colisiones en pytest-xdist.

    Args:
        worker_id: El worker_id de pytest-xdist
        base_username: Username base (sin sufijo)
        base_email: Email base (sin sufijo)

    Returns:
        tuple: (username, email) con sufijo de worker si es necesario
    """
    if worker_id == "master":
        return base_username, base_email

    # Extraer la parte local del email (antes del @)
    local_part, domain = base_email.split("@")
    unique_email = f"{local_part}_{worker_id}@{domain}"
    unique_username = f"{base_username}_{worker_id}"

    return unique_username, unique_email
