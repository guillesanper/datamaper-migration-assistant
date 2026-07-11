# test/fixtures/test_data.py
"""
Datos de prueba reutilizables para tests
Proporciona constantes y funciones para generar datos de test
"""

import uuid
from datetime import datetime, timedelta

# ============================================================================
# DATOS DE USUARIOS
# ============================================================================

SAMPLE_USERS = [
    {
        "id": "user-test-001",
        "username": "testuser1",
        "email": "testuser1@example.com",
        "full_name": "Test User One",
    },
    {
        "id": "user-test-002",
        "username": "testuser2",
        "email": "testuser2@example.com",
        "full_name": "Test User Two",
    },
    {
        "id": "user-test-003",
        "username": "admin_test",
        "email": "admin@example.com",
        "full_name": "Admin Test User",
    },
]


# ============================================================================
# DATOS DE PROYECTOS
# ============================================================================

SAMPLE_PROJECTS = [
    {
        "id": "project-test-001",
        "name": "Test Project Alpha",
        "description": "Project for testing purposes",
        "owner_id": "user-test-001",
    },
    {
        "id": "project-test-002",
        "name": "Test Project Beta",
        "description": "Another test project",
        "owner_id": "user-test-002",
    },
]


# ============================================================================
# DATOS DE VERSIONES
# ============================================================================

SAMPLE_VERSIONS = [
    {
        "id": "version-test-001",
        "project_id": "project-test-001",
        "entity_id": "entity-001",
        "entity_type": "table",
        "version_number": 1,
        "snapshot": '{"columns": ["id", "name", "email"]}',
        "created_by": "user-test-001",
    },
    {
        "id": "version-test-002",
        "project_id": "project-test-001",
        "entity_id": "entity-001",
        "entity_type": "table",
        "version_number": 2,
        "snapshot": '{"columns": ["id", "name", "email", "phone"]}',
        "created_by": "user-test-001",
    },
]


# ============================================================================
# DATOS DE TAGS
# ============================================================================

SAMPLE_TAGS = [
    {"name": "v1.0.0", "description": "First stable release", "color": "#FF5733"},
    {"name": "v2.0.0", "description": "Major update", "color": "#33FF57"},
    {"name": "stable", "description": "Stable version", "color": "#3357FF"},
    {"name": "production", "description": "Production ready", "color": "#F39C12"},
    {"name": "beta", "description": "Beta testing", "color": "#9B59B6"},
]


# ============================================================================
# COLORES COMUNES PARA TAGS
# ============================================================================

TAG_COLORS = [
    "#FF5733",  # Rojo
    "#33FF57",  # Verde
    "#3357FF",  # Azul
    "#F39C12",  # Naranja
    "#9B59B6",  # Púrpura
    "#1ABC9C",  # Turquesa
    "#E74C3C",  # Rojo oscuro
    "#3498DB",  # Azul claro
    "#2ECC71",  # Verde claro
    "#E67E22",  # Naranja oscuro
]


# ============================================================================
# COOKIES DE PRUEBA
# ============================================================================

SAMPLE_COOKIE_VALUES = [
    "user123",
    "session_abc123",
    "user@example.com",
    "token|123456|2025-01-01",
    "simple",
    "with-dashes",
    "with_underscores",
    "with.dots",
]


# ============================================================================
# FUNCIONES GENERADORAS
# ============================================================================


def generate_test_user(index=0, **overrides):
    """
    Genera un usuario de prueba con valores por defecto

    Args:
        index: Índice para generar IDs únicos
        **overrides: Campos a sobrescribir

    Returns:
        Dict con datos de usuario
    """
    user = {
        "id": f"user-gen-{index}-{uuid.uuid4().hex[:8]}",
        "username": f"testuser{index}",
        "email": f"testuser{index}@example.com",
        "full_name": f"Test User {index}",
        "created_at": datetime.utcnow(),
    }
    user.update(overrides)
    return user


def generate_test_project(index=0, owner_id="user-test-001", **overrides):
    """
    Genera un proyecto de prueba

    Args:
        index: Índice para generar IDs únicos
        owner_id: ID del dueño del proyecto
        **overrides: Campos a sobrescribir

    Returns:
        Dict con datos de proyecto
    """
    project = {
        "id": f"project-gen-{index}-{uuid.uuid4().hex[:8]}",
        "name": f"Test Project {index}",
        "description": f"Generated test project {index}",
        "owner_id": owner_id,
        "created_at": datetime.utcnow(),
    }
    project.update(overrides)
    return project


def generate_test_version(
    index=0, project_id="project-test-001", entity_id="entity-001", **overrides
):
    """
    Genera una versión de prueba

    Args:
        index: Índice para generar IDs únicos
        project_id: ID del proyecto
        entity_id: ID de la entidad
        **overrides: Campos a sobrescribir

    Returns:
        Dict con datos de versión
    """
    version = {
        "id": f"version-gen-{index}-{uuid.uuid4().hex[:8]}",
        "project_id": project_id,
        "entity_id": entity_id,
        "entity_type": "table",
        "version_number": index + 1,
        "snapshot": '{"columns": ["id", "name"]}',
        "created_by": "user-test-001",
        "created_at": datetime.utcnow(),
    }
    version.update(overrides)
    return version


def generate_test_tag(
    index=0, version_id="version-test-001", project_id="project-test-001", **overrides
):
    """
    Genera un tag de prueba

    Args:
        index: Índice para generar nombres únicos
        version_id: ID de la versión
        project_id: ID del proyecto
        **overrides: Campos a sobrescribir

    Returns:
        Dict con datos de tag
    """
    tag = {
        "name": f"v{index}.0.0",
        "version_id": version_id,
        "project_id": project_id,
        "description": f"Generated tag {index}",
        "color": TAG_COLORS[index % len(TAG_COLORS)],
        "created_by": "user-test-001",
        "created_at": datetime.utcnow(),
    }
    tag.update(overrides)
    return tag


def generate_multiple_tags(count=5, **base_kwargs):
    """
    Genera múltiples tags de prueba

    Args:
        count: Número de tags a generar
        **base_kwargs: Parámetros base para todos los tags

    Returns:
        Lista de dicts con datos de tags
    """
    return [generate_test_tag(i, **base_kwargs) for i in range(count)]


# ============================================================================
# DATOS DE PRUEBA PARA FECHAS
# ============================================================================


def get_test_timestamps():
    """
    Retorna timestamps útiles para testing

    Returns:
        Dict con varios timestamps de prueba
    """
    now = datetime.utcnow()
    return {
        "now": now,
        "one_hour_ago": now - timedelta(hours=1),
        "one_day_ago": now - timedelta(days=1),
        "one_week_ago": now - timedelta(weeks=1),
        "one_month_ago": now - timedelta(days=30),
        "one_hour_future": now + timedelta(hours=1),
        "one_day_future": now + timedelta(days=1),
    }


# ============================================================================
# VALIDACIONES COMUNES
# ============================================================================


def is_valid_uuid(value):
    """
    Verifica si un string es un UUID válido

    Args:
        value: String a validar

    Returns:
        bool: True si es UUID válido
    """
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False


def is_valid_timestamp(value):
    """
    Verifica si un valor es un timestamp válido

    Args:
        value: Valor a validar

    Returns:
        bool: True si es timestamp válido
    """
    return isinstance(value, datetime)


# ============================================================================
# HELPERS PARA COMPARACIÓN
# ============================================================================


def assert_tag_equals(tag1, tag2, ignore_fields=None):
    """
    Compara dos tags ignorando ciertos campos

    Args:
        tag1: Primer tag
        tag2: Segundo tag
        ignore_fields: Lista de campos a ignorar (ej: ['created_at', 'id'])

    Returns:
        bool: True si son iguales (ignorando campos especificados)
    """
    if ignore_fields is None:
        ignore_fields = ["created_at", "id"]

    for key in tag1:
        if key not in ignore_fields:
            if tag1.get(key) != tag2.get(key):
                return False
    return True


# ============================================================================
# DATOS PARA TESTS DE EDGE CASES
# ============================================================================

EDGE_CASE_STRINGS = [
    "",  # Empty string
    " ",  # Single space
    "   ",  # Multiple spaces
    "a" * 1000,  # Very long string
    "special!@#$%^&*()chars",  # Special characters
    "🚀 emoji test 🎉",  # Emojis
    "line1\nline2\nline3",  # Multiline
    "it's a test with 'quotes'",  # Quotes
    "tab\there",  # Tabs
    "\\backslash\\test",  # Backslashes
]

EDGE_CASE_COLORS = [
    "#000000",  # Black
    "#FFFFFF",  # White
    "#FFF",  # Short format
    "red",  # Named color (may not be valid)
    "",  # Empty
    None,  # None
]
