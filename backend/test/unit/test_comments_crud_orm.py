"""
Unit tests for comments_crud.py ORM functions

Tests para las 9 funciones ORM de comments_crud:
1. create_comment_orm() - Test creación con parent_id y mentions
2. update_comment_orm() - Test actualización (solo autor)
3. delete_comment_orm() - Test eliminación (solo autor)
4. resolve_comment_orm() - Test marcar como resuelto/no resuelto
5. get_comment_by_id_orm() - Test obtención con JOINs y subconsultas
6. get_comments_orm() - Test listado con filtros (resolved, replies)
7. mark_as_read_orm() - Test marcar como leído (ON CONFLICT)
8. get_unread_count_orm() - Test contador de no leídos
9. check_comment_owner_orm() - Test verificación de ownership

Estructura:
- Usa SessionLocal para crear sesiones de SQLAlchemy
- Fixtures para crear datos de prueba (usuarios, proyectos)
- Rollback automático después de cada test
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

# Importar TODOS los modelos ORM desde __init__ para que SQLAlchemy resuelva las relaciones
import app.models.orm as orm
from app.crud.comments_crud import (
    check_comment_owner_orm,
    create_comment_orm,
    delete_comment_orm,
    get_comment_by_id_orm,
    get_comments_orm,
    get_unread_count_orm,
    mark_as_read_orm,
    resolve_comment_orm,
    update_comment_orm,
)
from app.database.session import SessionLocal
from app.models.orm import Comment, Project, User

# ============================================================================
# FIXTURES
# ============================================================================
# Nota: db_session fixture está definido en conftest.py


@pytest.fixture
def test_user(db_session):
    """
    Crea un usuario de prueba en la base de datos.

    Returns:
        User: Instancia del modelo User creada en la BD
    """
    user = User(
        id=uuid4(),
        username=f"test_user_{uuid4().hex[:8]}",
        email=f"test_{uuid4().hex[:8]}@example.com",
        password_hash="hashed_password_123",
        is_verified=True,
        is_deleted=False,
        failed_login_attempts=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_user2(db_session):
    """
    Crea un segundo usuario de prueba para tests con múltiples usuarios.

    Returns:
        User: Instancia del modelo User creada en la BD
    """
    user = User(
        id=uuid4(),
        username=f"test_user2_{uuid4().hex[:8]}",
        email=f"test2_{uuid4().hex[:8]}@example.com",
        password_hash="hashed_password_456",
        is_verified=True,
        is_deleted=False,
        failed_login_attempts=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_project(db_session, test_user):
    """
    Crea un proyecto de prueba en la base de datos.

    Returns:
        Project: Instancia del modelo Project creada en la BD
    """
    project = Project(
        id=uuid4(),
        name=f"Test Project {uuid4().hex[:8]}",
        description="Test project for comments",
        owner_id=test_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    db_session.commit()
    return project


# ============================================================================
# TESTS
# ============================================================================


def test_create_comment_orm(db_session, test_user, test_project):
    """Test: create_comment_orm crea un comentario correctamente"""
    entity_id = str(uuid4())

    result = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="This is a test comment",
    )

    assert result is not None
    assert result["entity_id"] == entity_id
    assert result["entity_type"] == "mapping"
    assert result["project_id"] == str(test_project.id)
    assert result["user_id"] == str(test_user.id)
    assert result["content"] == "This is a test comment"
    assert result["parent_id"] is None
    assert result["mentions"] is None
    assert result["is_edited"] is False
    assert result["is_resolved"] is False


def test_create_comment_with_parent_orm(db_session, test_user, test_project):
    """Test: create_comment_orm con parent_id (reply)"""
    entity_id = str(uuid4())

    # Crear comentario padre
    parent = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="table",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Parent comment",
    )

    # Crear reply
    reply = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="table",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Reply comment",
        parent_id=parent["id"],
    )

    assert reply is not None
    assert reply["parent_id"] == parent["id"]
    assert reply["content"] == "Reply comment"


def test_create_comment_with_mentions_orm(db_session, test_user, test_user2, test_project):
    """Test: create_comment_orm con mentions (JSONB array)"""
    entity_id = str(uuid4())
    mentions = [str(test_user2.id)]

    result = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="column",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content=f"Hey @{test_user2.username}, check this out",
        mentions=mentions,
    )

    assert result is not None
    assert result["mentions"] == mentions


def test_update_comment_orm(db_session, test_user, test_project):
    """Test: update_comment_orm actualiza contenido (solo autor)"""
    entity_id = str(uuid4())

    # Crear comentario
    comment = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Original content",
    )

    # Actualizar como autor
    updated = update_comment_orm(
        db=db_session,
        comment_id=comment["id"],
        user_id=str(test_user.id),
        content="Updated content",
    )

    assert updated is not None
    assert updated["content"] == "Updated content"
    assert updated["is_edited"] is True
    assert updated["updated_at"] is not None


def test_update_comment_not_owner_orm(db_session, test_user, test_user2, test_project):
    """Test: update_comment_orm retorna None si no es el autor"""
    entity_id = str(uuid4())

    # Crear comentario como user1
    comment = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="table",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Original content",
    )

    # Intentar actualizar como user2 (no owner)
    updated = update_comment_orm(
        db=db_session,
        comment_id=comment["id"],
        user_id=str(test_user2.id),  # Diferente usuario
        content="Malicious update",
    )

    assert updated is None


def test_delete_comment_orm(db_session, test_user, test_project):
    """Test: delete_comment_orm elimina comentario (solo autor)"""
    entity_id = str(uuid4())

    # Crear comentario
    comment = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="column",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="To be deleted",
    )

    # Verificar que existe
    found = get_comment_by_id_orm(db_session, comment["id"])
    assert found is not None

    # Eliminar como autor
    deleted = delete_comment_orm(db=db_session, comment_id=comment["id"], user_id=str(test_user.id))

    assert deleted is True

    # Verificar que no existe
    not_found = get_comment_by_id_orm(db_session, comment["id"])
    assert not_found is None


def test_delete_comment_not_owner_orm(db_session, test_user, test_user2, test_project):
    """Test: delete_comment_orm retorna False si no es el autor"""
    entity_id = str(uuid4())

    # Crear comentario como user1
    comment = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Protected comment",
    )

    # Intentar eliminar como user2 (no owner)
    deleted = delete_comment_orm(
        db=db_session, comment_id=comment["id"], user_id=str(test_user2.id)  # Diferente usuario
    )

    assert deleted is False

    # Verificar que todavía existe
    found = get_comment_by_id_orm(db_session, comment["id"])
    assert found is not None


def test_resolve_comment_orm(db_session, test_user, test_user2, test_project):
    """Test: resolve_comment_orm marca como resuelto"""
    entity_id = str(uuid4())

    # Crear comentario
    comment = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="table",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Issue to resolve",
    )

    # Marcar como resuelto
    resolved = resolve_comment_orm(
        db=db_session, comment_id=comment["id"], resolved=True, resolved_by=str(test_user2.id)
    )

    assert resolved is not None
    assert resolved["is_resolved"] is True
    assert resolved["resolved_by"] == str(test_user2.id)
    assert resolved["resolved_at"] is not None


def test_unresolve_comment_orm(db_session, test_user, test_user2, test_project):
    """Test: resolve_comment_orm puede desmarcar como resuelto"""
    entity_id = str(uuid4())

    # Crear comentario
    comment = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="column",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Issue",
    )

    # Marcar como resuelto
    resolve_comment_orm(
        db=db_session, comment_id=comment["id"], resolved=True, resolved_by=str(test_user2.id)
    )

    # Desmarcar
    unresolved = resolve_comment_orm(
        db=db_session, comment_id=comment["id"], resolved=False, resolved_by=str(test_user.id)
    )

    assert unresolved is not None
    assert unresolved["is_resolved"] is False
    assert unresolved["resolved_by"] is None
    assert unresolved["resolved_at"] is None


def test_get_comment_by_id_orm(db_session, test_user, test_project):
    """Test: get_comment_by_id_orm devuelve comentario con datos de usuario"""
    entity_id = str(uuid4())

    # Crear comentario
    created = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Test comment",
    )

    # Obtener por ID
    result = get_comment_by_id_orm(db_session, created["id"])

    assert result is not None
    assert result["id"] == created["id"]
    assert result["content"] == "Test comment"
    assert result["username"] == test_user.username
    assert result["user_email"] == test_user.email
    assert result["reactions_count"] == 0
    assert result["replies_count"] == 0


def test_get_comment_by_id_not_found_orm(db_session):
    """Test: get_comment_by_id_orm retorna None si no existe"""
    result = get_comment_by_id_orm(db_session, str(uuid4()))
    assert result is None


def test_get_comments_orm(db_session, test_user, test_project):
    """Test: get_comments_orm devuelve lista de comentarios"""
    entity_id = str(uuid4())

    # Crear 3 comentarios
    for i in range(3):
        create_comment_orm(
            db=db_session,
            entity_id=entity_id,
            entity_type="table",
            project_id=str(test_project.id),
            user_id=str(test_user.id),
            content=f"Comment {i+1}",
        )

    # Obtener todos
    result = get_comments_orm(db=db_session, entity_id=entity_id, entity_type="table")

    assert len(result) == 3
    # Debe estar ordenado por created_at ASC
    assert result[0]["content"] == "Comment 1"
    assert result[1]["content"] == "Comment 2"
    assert result[2]["content"] == "Comment 3"


def test_get_comments_filter_resolved_orm(db_session, test_user, test_user2, test_project):
    """Test: get_comments_orm con filtro include_resolved"""
    entity_id = str(uuid4())

    # Crear comentario sin resolver
    create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="column",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Unresolved",
    )

    # Crear comentario resuelto
    resolved_comment = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="column",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Resolved",
    )

    resolve_comment_orm(
        db=db_session,
        comment_id=resolved_comment["id"],
        resolved=True,
        resolved_by=str(test_user2.id),
    )

    # Filtrar solo no resueltos
    unresolved_only = get_comments_orm(
        db=db_session, entity_id=entity_id, entity_type="column", include_resolved=False
    )

    assert len(unresolved_only) == 1
    assert unresolved_only[0]["content"] == "Unresolved"


def test_get_comments_filter_replies_orm(db_session, test_user, test_project):
    """Test: get_comments_orm con filtro include_replies"""
    entity_id = str(uuid4())

    # Crear comentario padre
    parent = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Parent",
    )

    # Crear reply
    create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Reply",
        parent_id=parent["id"],
    )

    # Obtener solo comentarios raíz (sin replies)
    root_only = get_comments_orm(
        db=db_session, entity_id=entity_id, entity_type="mapping", include_replies=False
    )

    assert len(root_only) == 1
    assert root_only[0]["content"] == "Parent"


def test_get_comments_filter_by_parent_orm(db_session, test_user, test_project):
    """Test: get_comments_orm filtrando por parent_id específico"""
    entity_id = str(uuid4())

    # Crear comentario padre
    parent = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="table",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Parent",
    )

    # Crear 2 replies
    create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="table",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Reply 1",
        parent_id=parent["id"],
    )

    create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="table",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Reply 2",
        parent_id=parent["id"],
    )

    # Obtener replies del parent
    replies = get_comments_orm(
        db=db_session, entity_id=entity_id, entity_type="table", parent_id=parent["id"]
    )

    assert len(replies) == 2


def test_mark_as_read_orm(db_session, test_user, test_user2, test_project):
    """Test: mark_as_read_orm marca comentarios como leídos"""
    entity_id = str(uuid4())

    # Crear 3 comentarios
    comment_ids = []
    for i in range(3):
        comment = create_comment_orm(
            db=db_session,
            entity_id=entity_id,
            entity_type="column",
            project_id=str(test_project.id),
            user_id=str(test_user.id),
            content=f"Comment {i+1}",
        )
        comment_ids.append(comment["id"])

    # Marcar como leído para user2
    count = mark_as_read_orm(db=db_session, comment_ids=comment_ids, user_id=str(test_user2.id))

    assert count == 3


def test_mark_as_read_duplicate_orm(db_session, test_user, test_user2, test_project):
    """Test: mark_as_read_orm con ON CONFLICT (duplicado)"""
    entity_id = str(uuid4())

    # Crear comentario
    comment = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Test",
    )

    # Primera vez
    count1 = mark_as_read_orm(
        db=db_session, comment_ids=[comment["id"]], user_id=str(test_user2.id)
    )

    # Segunda vez (duplicado - debe ignorar)
    count2 = mark_as_read_orm(
        db=db_session, comment_ids=[comment["id"]], user_id=str(test_user2.id)
    )

    assert count1 == 1
    assert count2 == 0  # ON CONFLICT DO NOTHING


def test_get_unread_count_orm(db_session, test_user, test_user2, test_project):
    """Test: get_unread_count_orm cuenta comentarios no leídos"""
    entity_id = str(uuid4())

    # Crear 3 comentarios de user1
    comment_ids = []
    for i in range(3):
        comment = create_comment_orm(
            db=db_session,
            entity_id=entity_id,
            entity_type="table",
            project_id=str(test_project.id),
            user_id=str(test_user.id),
            content=f"Comment {i+1}",
        )
        comment_ids.append(comment["id"])

    # User2 no ha leído ninguno
    unread = get_unread_count_orm(
        db=db_session, project_id=str(test_project.id), user_id=str(test_user2.id)
    )

    assert unread == 3

    # Marcar 1 como leído
    mark_as_read_orm(db=db_session, comment_ids=[comment_ids[0]], user_id=str(test_user2.id))

    # Ahora solo 2 no leídos
    unread_after = get_unread_count_orm(
        db=db_session, project_id=str(test_project.id), user_id=str(test_user2.id)
    )

    assert unread_after == 2


def test_get_unread_count_excludes_own_comments_orm(db_session, test_user, test_project):
    """Test: get_unread_count_orm excluye comentarios propios"""
    entity_id = str(uuid4())

    # Crear 3 comentarios del mismo usuario
    for i in range(3):
        create_comment_orm(
            db=db_session,
            entity_id=entity_id,
            entity_type="column",
            project_id=str(test_project.id),
            user_id=str(test_user.id),
            content=f"Own comment {i+1}",
        )

    # No debe contar sus propios comentarios
    unread = get_unread_count_orm(
        db=db_session, project_id=str(test_project.id), user_id=str(test_user.id)
    )

    assert unread == 0


def test_check_comment_owner_orm(db_session, test_user, test_user2, test_project):
    """Test: check_comment_owner_orm verifica ownership correctamente"""
    entity_id = str(uuid4())

    # Crear comentario
    comment = create_comment_orm(
        db=db_session,
        entity_id=entity_id,
        entity_type="mapping",
        project_id=str(test_project.id),
        user_id=str(test_user.id),
        content="Test",
    )

    # Verificar owner
    is_owner = check_comment_owner_orm(
        db=db_session, comment_id=comment["id"], user_id=str(test_user.id)
    )

    # Verificar no owner
    is_not_owner = check_comment_owner_orm(
        db=db_session, comment_id=comment["id"], user_id=str(test_user2.id)
    )

    assert is_owner is True
    assert is_not_owner is False


def test_check_comment_owner_not_exists_orm(db_session, test_user):
    """Test: check_comment_owner_orm retorna False si comentario no existe"""
    is_owner = check_comment_owner_orm(
        db=db_session, comment_id=str(uuid4()), user_id=str(test_user.id)
    )

    assert is_owner is False
