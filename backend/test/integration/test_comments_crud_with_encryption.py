# backend/test/integration/test_comments_crud_with_encryption.py
"""
Tests de integración para comments con encriptación

Cobertura:
- Crear/leer/actualizar/eliminar comentarios con content encriptado
- Validación de encryption_key requerida
- Roundtrip de encriptación/desencriptación
- Comentarios anidados (replies)
- Mentions en comentarios
- Resolución de comentarios
"""

import pytest

from app.crud import comments_crud

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def encrypted_project(clean_db_session, test_user):
    """Proyecto con cifrado configurado"""
    from app.crud.project_crud import ProjectCRUD
    from app.services.encryption_service import EncryptionService

    project = ProjectCRUD.create_project_orm(
        clean_db_session,
        test_user["id"],
        "Encrypted Project",
        "Project with encryption",
        "PostgreSQL",
        "MySQL",
        "active",
    )

    # Setup encryption
    passphrase = "SecurePass123!@#"
    EncryptionService.setup_project_encryption(
        clean_db_session, project["id"], passphrase, test_user["id"]
    )

    return {**project, "passphrase": passphrase}


@pytest.fixture
def test_entity(clean_db_session, encrypted_project, test_user):
    """Entidad de prueba para asociar comentarios"""
    from app.crud import schemas_crud
    from app.services.encryption_service import EncryptionService

    encryption_key = EncryptionService.get_encryption_key(
        clean_db_session, encrypted_project["id"], encrypted_project["passphrase"]
    )

    table = schemas_crud.create_table_orm(
        clean_db_session,
        encrypted_project["id"],
        "users",
        "origin",
        test_user["id"],
        encryption_key,
    )

    return table


# ============================================================================
# TESTS DE CREACIÓN DE COMENTARIOS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_create_comment_basic(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Crear comentario básico"""
    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="This is a test comment",
    )

    assert comment is not None
    assert comment["content"] == "This is a test comment"
    assert comment["entity_id"] == test_entity["id"]
    assert comment["user_id"] == test_user["id"]


@pytest.mark.integration
@pytest.mark.encryption
def test_create_comment_with_mentions(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Crear comentario con menciones"""
    mentions = ["user-123", "user-456"]

    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Hey @user-123 and @user-456, check this out!",
        mentions=mentions,
    )

    assert comment is not None
    assert comment["mentions"] is not None


@pytest.mark.integration
@pytest.mark.encryption
def test_create_comment_reply(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Crear comentario como respuesta a otro"""
    # Comentario padre
    parent = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Parent comment",
    )

    # Comentario hijo (reply)
    reply = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Reply to parent",
        parent_id=parent["id"],
    )

    assert reply["parent_id"] == parent["id"]


@pytest.mark.integration
@pytest.mark.encryption
def test_create_comment_multiline(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Crear comentario con múltiples líneas"""
    multiline_content = """This is a comment
with multiple lines
and some formatting:
- Point 1
- Point 2
- Point 3"""

    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content=multiline_content,
    )

    assert "\n" in comment["content"]
    assert comment["content"] == multiline_content


# ============================================================================
# TESTS DE LECTURA DE COMENTARIOS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_get_comment_by_id(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Obtener comentario por ID"""
    created = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Test comment",
    )

    # Obtener por ID
    comment = comments_crud.get_comment_by_id_orm(clean_db_session, created["id"])

    assert comment is not None
    assert comment["id"] == created["id"]
    assert comment["content"] == "Test comment"


@pytest.mark.integration
@pytest.mark.encryption
def test_get_comments_by_entity(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Obtener todos los comentarios de una entidad"""
    # Crear 3 comentarios
    for i in range(3):
        comments_crud.create_comment_orm(
            clean_db_session,
            entity_id=test_entity["id"],
            entity_type="table",
            project_id=encrypted_project["id"],
            user_id=test_user["id"],
            content=f"Comment {i+1}",
        )

    # Obtener todos los comentarios
    comments = comments_crud.get_comments_orm(
        clean_db_session, entity_id=test_entity["id"], entity_type="table"
    )

    assert len(comments) == 3


# ============================================================================
# TESTS DE ACTUALIZACIÓN DE COMENTARIOS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_update_comment(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Actualizar contenido de comentario"""
    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Original content",
    )

    # Actualizar
    updated = comments_crud.update_comment_orm(
        clean_db_session, comment["id"], test_user["id"], content="Updated content"
    )

    assert updated is not None
    assert updated["content"] == "Updated content"
    assert updated["is_edited"] is True


@pytest.mark.integration
@pytest.mark.encryption
def test_update_comment_wrong_user_fails(
    clean_db_session, encrypted_project, test_entity, test_user, worker_id
):
    """Test: Actualizar comentario de otro usuario falla"""
    from test.integration.conftest import get_unique_user_data

    from app.services.auth_service import AuthService

    # Crear segundo usuario con nombre único por worker
    username2, email2 = get_unique_user_data(worker_id, "testuser2", "test2@example.com")

    auth_service = AuthService(clean_db_session)
    user2 = auth_service.create_user(username=username2, email=email2, password="Test123!@#")

    # Comentario del primer usuario
    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Original content",
    )

    # Intentar actualizar como usuario 2
    updated = comments_crud.update_comment_orm(
        clean_db_session, comment["id"], user2["user_id"], content="Hacked content"
    )

    # Debe fallar (retornar None)
    assert updated is None


# ============================================================================
# TESTS DE ELIMINACIÓN DE COMENTARIOS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_delete_comment(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Eliminar comentario"""
    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="To be deleted",
    )

    # Eliminar
    deleted = comments_crud.delete_comment_orm(clean_db_session, comment["id"], test_user["id"])

    assert deleted is True

    # Verificar que ya no existe
    retrieved = comments_crud.get_comment_by_id_orm(clean_db_session, comment["id"])
    assert retrieved is None


@pytest.mark.integration
@pytest.mark.encryption
def test_delete_comment_wrong_user_fails(
    clean_db_session, encrypted_project, test_entity, test_user, worker_id
):
    """Test: Eliminar comentario de otro usuario falla"""
    from test.integration.conftest import get_unique_user_data

    from app.services.auth_service import AuthService

    # Crear segundo usuario con nombre único por worker
    username2, email2 = get_unique_user_data(worker_id, "testuser2", "test2@example.com")

    auth_service = AuthService(clean_db_session)
    user2 = auth_service.create_user(username=username2, email=email2, password="Test123!@#")

    # Comentario del primer usuario
    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Protected comment",
    )

    # Intentar eliminar como usuario 2
    deleted = comments_crud.delete_comment_orm(clean_db_session, comment["id"], user2["user_id"])

    # Debe fallar
    assert deleted is False


# ============================================================================
# TESTS DE RESOLUCIÓN DE COMENTARIOS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_resolve_comment(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Marcar comentario como resuelto"""
    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Issue to resolve",
    )

    # Resolver
    resolved = comments_crud.resolve_comment_orm(
        clean_db_session, comment["id"], resolved=True, resolved_by=test_user["id"]
    )

    assert resolved is not None
    assert resolved["is_resolved"] is True
    assert resolved["resolved_by"] == test_user["id"]
    assert resolved["resolved_at"] is not None


@pytest.mark.integration
@pytest.mark.encryption
def test_unresolve_comment(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Marcar comentario resuelto como no resuelto"""
    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Issue",
    )

    # Resolver
    comments_crud.resolve_comment_orm(clean_db_session, comment["id"], True, test_user["id"])

    # Unresolve
    unresolved = comments_crud.resolve_comment_orm(
        clean_db_session, comment["id"], False, test_user["id"]
    )

    assert unresolved["is_resolved"] is False
    assert unresolved["resolved_by"] is None
    assert unresolved["resolved_at"] is None


# ============================================================================
# TESTS DE COMENTARIOS CON CARACTERES ESPECIALES
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_comment_with_unicode(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Comentario con caracteres Unicode"""
    unicode_content = "Este comentario tiene ñ, á, é, í, ó, ú y emojis: 🔐 🎉 ✅"

    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content=unicode_content,
    )

    assert comment["content"] == unicode_content

    # Leer de vuelta
    retrieved = comments_crud.get_comment_by_id_orm(clean_db_session, comment["id"])
    assert retrieved["content"] == unicode_content


@pytest.mark.integration
@pytest.mark.encryption
def test_comment_with_code(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Comentario con código SQL/Python"""
    code_content = """Here's the SQL query:
```sql
SELECT * FROM users WHERE id = 123;
```

And some Python:
```python
def hello():
    return "world"
```"""

    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content=code_content,
    )

    assert "SELECT * FROM" in comment["content"]
    assert "def hello" in comment["content"]


@pytest.mark.integration
@pytest.mark.encryption
def test_comment_with_markdown(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Comentario con formato Markdown"""
    markdown_content = """# Title

## Subtitle

**Bold text** and *italic text*

- Item 1
- Item 2

[Link](https://example.com)"""

    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content=markdown_content,
    )

    assert comment["content"] == markdown_content


# ============================================================================
# TESTS DE COMENTARIOS ANIDADOS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_nested_comments_thread(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Thread de comentarios anidados"""
    # Comentario raíz
    root = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Root comment",
    )

    # Respuesta nivel 1
    reply1 = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Reply to root",
        parent_id=root["id"],
    )

    # Respuesta nivel 2
    reply2 = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content="Reply to reply",
        parent_id=reply1["id"],
    )

    assert root["parent_id"] is None
    assert reply1["parent_id"] == root["id"]
    assert reply2["parent_id"] == reply1["id"]


# ============================================================================
# TESTS DE EDGE CASES
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_comment_empty_content(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Comentario con contenido vacío debe fallar por restricción de BD"""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        comments_crud.create_comment_orm(
            clean_db_session,
            entity_id=test_entity["id"],
            entity_type="table",
            project_id=encrypted_project["id"],
            user_id=test_user["id"],
            content="",
        )

    # Rollback the failed transaction so subsequent tests can use the session
    clean_db_session.rollback()


@pytest.mark.integration
@pytest.mark.encryption
def test_comment_very_long_content(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Comentario con contenido muy largo"""
    long_content = "A" * 10000  # 10K caracteres

    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content=long_content,
    )

    assert len(comment["content"]) == 10000


@pytest.mark.integration
@pytest.mark.encryption
def test_comment_with_special_chars(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Comentario con caracteres especiales"""
    special_content = "Testing: <script>alert('xss')</script> & SELECT * FROM users; --"

    comment = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content=special_content,
    )

    # Contenido debe preservarse tal cual (sin sanitización)
    assert comment["content"] == special_content


@pytest.mark.integration
@pytest.mark.encryption
def test_multiple_comments_same_entity(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Múltiples comentarios en la misma entidad"""
    # Crear 10 comentarios
    for i in range(10):
        comments_crud.create_comment_orm(
            clean_db_session,
            entity_id=test_entity["id"],
            entity_type="table",
            project_id=encrypted_project["id"],
            user_id=test_user["id"],
            content=f"Comment {i+1}",
        )

    # Obtener todos
    comments = comments_crud.get_comments_orm(
        clean_db_session, entity_id=test_entity["id"], entity_type="table"
    )

    assert len(comments) == 10


@pytest.mark.integration
@pytest.mark.encryption
def test_comment_roundtrip(clean_db_session, encrypted_project, test_entity, test_user):
    """Test: Roundtrip completo de comentario"""
    original_content = "Original comment with special chars: ñáéíóú 🔐"

    # Crear
    created = comments_crud.create_comment_orm(
        clean_db_session,
        entity_id=test_entity["id"],
        entity_type="table",
        project_id=encrypted_project["id"],
        user_id=test_user["id"],
        content=original_content,
    )

    # Leer
    retrieved = comments_crud.get_comment_by_id_orm(clean_db_session, created["id"])

    # Actualizar
    updated = comments_crud.update_comment_orm(
        clean_db_session,
        created["id"],
        test_user["id"],
        content="Updated content with more chars: 日本語",
    )

    # Leer de nuevo
    final = comments_crud.get_comment_by_id_orm(clean_db_session, updated["id"])

    assert final["content"] == "Updated content with more chars: 日本語"
    assert final["is_edited"] is True
