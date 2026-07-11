"""
Tests para notification_crud.py (versión ORM)
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.crud import notification_crud
from app.models.orm.notification import Notification
from app.models.orm.project import Project
from app.models.orm.user import User

# ============================================================================
# Helpers para crear datos de prueba
# ============================================================================


def create_test_user(db_session: Session, user_id: uuid.UUID = None) -> uuid.UUID:
    """Crea un usuario de prueba y retorna su ID"""
    if user_id is None:
        user_id = uuid.uuid4()

    user = User(
        id=user_id,
        username=f"testuser_{str(user_id)[:8]}",
        email=f"{str(user_id)[:8]}@test.com",
        password_hash="hashed_password_test",
        is_verified=True,
        is_deleted=False,
    )
    db_session.add(user)
    db_session.commit()

    return user_id


def create_test_project(
    db_session: Session, owner_id: uuid.UUID, project_id: uuid.UUID = None
) -> uuid.UUID:
    """Crea un proyecto de prueba y retorna su ID"""
    if project_id is None:
        project_id = uuid.uuid4()

    project = Project(id=project_id, name=f"Test Project {str(project_id)[:8]}", owner_id=owner_id)
    db_session.add(project)
    db_session.commit()

    return project_id


# ============================================================================
# Tests de create_notification_orm
# ============================================================================


def test_create_notification_orm_basic(db_session: Session):
    """Test: crear notificación básica"""
    user_id = create_test_user(db_session)

    result = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="system",
        title="Test Notification",
        body="This is a test notification",
    )

    assert result is not None
    assert result["recipient_id"] == str(user_id)
    assert result["notification_kind"] == "system"
    assert result["title"] == "Test Notification"
    assert result["body"] == "This is a test notification"
    assert result["read_at"] is None  # No leída por defecto
    assert result["created_at"] is not None

    # Verificar en BD
    notif_db = db_session.query(Notification).filter(Notification.id == result["id"]).first()
    assert notif_db is not None
    assert notif_db.title == "Test Notification"


def test_create_notification_orm_with_project(db_session: Session):
    """Test: crear notificación asociada a un proyecto"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    result = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="invitation",
        title="Project Invitation",
        body="You've been invited to a project",
        project_id=str(project_id),
    )

    assert result["project_id"] == str(project_id)
    assert result["notification_kind"] == "invitation"


def test_create_notification_orm_with_actions(db_session: Session):
    """Test: crear notificación con acciones"""
    user_id = create_test_user(db_session)

    actions = [
        {"label": "Accept", "action": "accept_invite"},
        {"label": "Reject", "action": "reject_invite"},
    ]

    result = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="invite",
        title="Invitation",
        body="You have been invited",
        actions=actions,
    )

    assert result["actions"] is not None
    assert len(result["actions"]) == 2
    assert result["actions"][0]["label"] == "Accept"


def test_create_notification_orm_with_expiration(db_session: Session):
    """Test: crear notificación con fecha de expiración"""
    user_id = create_test_user(db_session)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    result = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="system",
        title="Expiring Notification",
        body="This notification will expire",
        expires_at=expires_at,
    )

    assert result["expires_at"] is not None


# ============================================================================
# Tests de get_user_notifications_orm
# ============================================================================


def test_get_user_notifications_orm_empty(db_session: Session):
    """Test: obtener notificaciones cuando no hay ninguna"""
    user_id = create_test_user(db_session)

    result = notification_crud.get_user_notifications_orm(db_session, str(user_id))

    assert result == []


def test_get_user_notifications_orm_multiple(db_session: Session):
    """Test: obtener múltiples notificaciones"""
    user_id = create_test_user(db_session)

    # Crear 3 notificaciones
    for i in range(3):
        notification_crud.create_notification_orm(
            db_session,
            recipient_id=str(user_id),
            notification_kind="system",
            title=f"Notification {i}",
            body=f"Body {i}",
        )

    result = notification_crud.get_user_notifications_orm(db_session, str(user_id))

    assert len(result) == 3


def test_get_user_notifications_orm_ordering(db_session: Session):
    """Test: verificar orden (no leídas primero, luego por fecha desc)"""
    user_id = create_test_user(db_session)

    # Crear notificación leída (antigua)
    notif1 = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="system",
        title="Old Read",
        body="This is old and read",
    )
    # Marcar como leída
    db_session.query(Notification).filter(Notification.id == notif1["id"]).update(
        {"read_at": datetime.now(timezone.utc) - timedelta(days=1)}
    )
    db_session.commit()

    # Crear notificación no leída (nueva)
    notif2 = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="system",
        title="New Unread",
        body="This is new and unread",
    )

    result = notification_crud.get_user_notifications_orm(db_session, str(user_id))

    # La no leída debe estar primero
    assert result[0]["id"] == notif2["id"]
    assert result[1]["id"] == notif1["id"]


def test_get_user_notifications_orm_pagination(db_session: Session):
    """Test: paginación de notificaciones"""
    user_id = create_test_user(db_session)

    # Crear 10 notificaciones
    for i in range(10):
        notification_crud.create_notification_orm(
            db_session,
            recipient_id=str(user_id),
            notification_kind="system",
            title=f"Notification {i}",
            body=f"Body {i}",
        )

    # Obtener primera página (5 elementos)
    page1 = notification_crud.get_user_notifications_orm(
        db_session, str(user_id), limit=5, offset=0
    )
    assert len(page1) == 5

    # Obtener segunda página (5 elementos)
    page2 = notification_crud.get_user_notifications_orm(
        db_session, str(user_id), limit=5, offset=5
    )
    assert len(page2) == 5

    # Verificar que son diferentes
    assert page1[0]["id"] != page2[0]["id"]


def test_get_user_notifications_orm_unread_only(db_session: Session):
    """Test: filtrar solo notificaciones no leídas"""
    user_id = create_test_user(db_session)

    # Crear 3 notificaciones
    for i in range(3):
        notification_crud.create_notification_orm(
            db_session,
            recipient_id=str(user_id),
            notification_kind="system",
            title=f"Notification {i}",
            body=f"Body {i}",
        )

    # Marcar la primera como leída
    notifications = (
        db_session.query(Notification).filter(Notification.recipient_id == user_id).all()
    )
    notifications[0].read_at = datetime.now(timezone.utc)
    db_session.commit()

    # Obtener solo no leídas
    result = notification_crud.get_user_notifications_orm(
        db_session, str(user_id), unread_only=True
    )

    assert len(result) == 2


def test_get_user_notifications_orm_isolation(db_session: Session):
    """Test: un usuario no ve notificaciones de otro"""
    user1_id = create_test_user(db_session)
    user2_id = create_test_user(db_session)

    # Crear notificación para user1
    notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user1_id),
        notification_kind="system",
        title="For User 1",
        body="This is for user 1",
    )

    # Crear notificación para user2
    notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user2_id),
        notification_kind="system",
        title="For User 2",
        body="This is for user 2",
    )

    # Verificar aislamiento
    user1_notifs = notification_crud.get_user_notifications_orm(db_session, str(user1_id))
    user2_notifs = notification_crud.get_user_notifications_orm(db_session, str(user2_id))

    assert len(user1_notifs) == 1
    assert len(user2_notifs) == 1
    assert user1_notifs[0]["title"] == "For User 1"
    assert user2_notifs[0]["title"] == "For User 2"


# ============================================================================
# Tests de get_notification_by_id_orm
# ============================================================================


def test_get_notification_by_id_orm_success(db_session: Session):
    """Test: obtener notificación por ID"""
    user_id = create_test_user(db_session)

    created = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="system",
        title="Test",
        body="Test body",
    )

    result = notification_crud.get_notification_by_id_orm(db_session, created["id"], str(user_id))

    assert result is not None
    assert result["id"] == created["id"]
    assert result["title"] == "Test"


def test_get_notification_by_id_orm_not_found(db_session: Session):
    """Test: obtener notificación inexistente"""
    user_id = create_test_user(db_session)
    fake_id = str(uuid.uuid4())

    result = notification_crud.get_notification_by_id_orm(db_session, fake_id, str(user_id))

    assert result is None


def test_get_notification_by_id_orm_wrong_user(db_session: Session):
    """Test: no se puede obtener notificación de otro usuario"""
    user1_id = create_test_user(db_session)
    user2_id = create_test_user(db_session)

    # Crear notificación para user1
    created = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user1_id),
        notification_kind="system",
        title="Private",
        body="This is private",
    )

    # Intentar obtener como user2
    result = notification_crud.get_notification_by_id_orm(db_session, created["id"], str(user2_id))

    assert result is None


# ============================================================================
# Tests de mark_as_read_orm
# ============================================================================


def test_mark_as_read_orm_success(db_session: Session):
    """Test: marcar notificación como leída"""
    user_id = create_test_user(db_session)

    created = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="system",
        title="Unread",
        body="This is unread",
    )

    # Verificar que está no leída
    assert created["read_at"] is None

    # Marcar como leída
    result = notification_crud.mark_as_read_orm(db_session, created["id"], str(user_id))

    assert result is not None
    assert result["id"] == created["id"]
    assert result["read_at"] is not None


def test_mark_as_read_orm_already_read(db_session: Session):
    """Test: marcar notificación ya leída (debe retornar None)"""
    user_id = create_test_user(db_session)

    created = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="system",
        title="Read",
        body="This will be read",
    )

    # Marcar como leída primera vez
    notification_crud.mark_as_read_orm(db_session, created["id"], str(user_id))

    # Intentar marcar como leída segunda vez
    result = notification_crud.mark_as_read_orm(db_session, created["id"], str(user_id))

    assert result is None


def test_mark_as_read_orm_wrong_user(db_session: Session):
    """Test: no se puede marcar notificación de otro usuario"""
    user1_id = create_test_user(db_session)
    user2_id = create_test_user(db_session)

    created = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user1_id),
        notification_kind="system",
        title="Private",
        body="This is private",
    )

    # Intentar marcar como leída como user2
    result = notification_crud.mark_as_read_orm(db_session, created["id"], str(user2_id))

    assert result is None


# ============================================================================
# Tests de mark_all_as_read_orm
# ============================================================================


def test_mark_all_as_read_orm_success(db_session: Session):
    """Test: marcar todas las notificaciones como leídas"""
    user_id = create_test_user(db_session)

    # Crear 5 notificaciones no leídas
    for i in range(5):
        notification_crud.create_notification_orm(
            db_session,
            recipient_id=str(user_id),
            notification_kind="system",
            title=f"Unread {i}",
            body=f"Body {i}",
        )

    # Marcar todas como leídas
    count = notification_crud.mark_all_as_read_orm(db_session, str(user_id))

    assert count == 5

    # Verificar que todas están leídas
    unread_count = notification_crud.get_unread_count_orm(db_session, str(user_id))
    assert unread_count == 0


def test_mark_all_as_read_orm_partial(db_session: Session):
    """Test: marcar todas (algunas ya leídas)"""
    user_id = create_test_user(db_session)

    # Crear 3 notificaciones
    for i in range(3):
        notification_crud.create_notification_orm(
            db_session,
            recipient_id=str(user_id),
            notification_kind="system",
            title=f"Notification {i}",
            body=f"Body {i}",
        )

    # Marcar la primera como leída manualmente
    notifications = (
        db_session.query(Notification).filter(Notification.recipient_id == user_id).all()
    )
    notifications[0].read_at = datetime.now(timezone.utc)
    db_session.commit()

    # Marcar todas como leídas (solo 2 pendientes)
    count = notification_crud.mark_all_as_read_orm(db_session, str(user_id))

    assert count == 2


def test_mark_all_as_read_orm_none_unread(db_session: Session):
    """Test: marcar todas cuando no hay pendientes"""
    user_id = create_test_user(db_session)

    # No crear notificaciones, o crear pero marcar todas como leídas
    count = notification_crud.mark_all_as_read_orm(db_session, str(user_id))

    assert count == 0


def test_mark_all_as_read_orm_isolation(db_session: Session):
    """Test: marcar todas solo afecta al usuario correcto"""
    user1_id = create_test_user(db_session)
    user2_id = create_test_user(db_session)

    # Crear notificaciones para ambos usuarios
    notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user1_id),
        notification_kind="system",
        title="For User 1",
        body="Body",
    )
    notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user2_id),
        notification_kind="system",
        title="For User 2",
        body="Body",
    )

    # Marcar todas de user1 como leídas
    notification_crud.mark_all_as_read_orm(db_session, str(user1_id))

    # Verificar que user2 aún tiene notificaciones no leídas
    user2_unread = notification_crud.get_unread_count_orm(db_session, str(user2_id))
    assert user2_unread == 1


# ============================================================================
# Tests de delete_notification_orm
# ============================================================================


def test_delete_notification_orm_success(db_session: Session):
    """Test: eliminar notificación"""
    user_id = create_test_user(db_session)

    created = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="system",
        title="To Delete",
        body="This will be deleted",
    )

    # Eliminar
    deleted = notification_crud.delete_notification_orm(db_session, created["id"], str(user_id))

    assert deleted is True

    # Verificar que no existe
    result = notification_crud.get_notification_by_id_orm(db_session, created["id"], str(user_id))
    assert result is None


def test_delete_notification_orm_not_found(db_session: Session):
    """Test: eliminar notificación inexistente"""
    user_id = create_test_user(db_session)
    fake_id = str(uuid.uuid4())

    deleted = notification_crud.delete_notification_orm(db_session, fake_id, str(user_id))

    assert deleted is False


def test_delete_notification_orm_wrong_user(db_session: Session):
    """Test: no se puede eliminar notificación de otro usuario"""
    user1_id = create_test_user(db_session)
    user2_id = create_test_user(db_session)

    created = notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user1_id),
        notification_kind="system",
        title="Private",
        body="This is private",
    )

    # Intentar eliminar como user2
    deleted = notification_crud.delete_notification_orm(db_session, created["id"], str(user2_id))

    assert deleted is False

    # Verificar que aún existe para user1
    result = notification_crud.get_notification_by_id_orm(db_session, created["id"], str(user1_id))
    assert result is not None


# ============================================================================
# Tests de get_unread_count_orm
# ============================================================================


def test_get_unread_count_orm_zero(db_session: Session):
    """Test: contador cuando no hay notificaciones"""
    user_id = create_test_user(db_session)

    count = notification_crud.get_unread_count_orm(db_session, str(user_id))

    assert count == 0


def test_get_unread_count_orm_multiple(db_session: Session):
    """Test: contador con múltiples notificaciones no leídas"""
    user_id = create_test_user(db_session)

    # Crear 7 notificaciones no leídas
    for i in range(7):
        notification_crud.create_notification_orm(
            db_session,
            recipient_id=str(user_id),
            notification_kind="system",
            title=f"Unread {i}",
            body=f"Body {i}",
        )

    count = notification_crud.get_unread_count_orm(db_session, str(user_id))

    assert count == 7


def test_get_unread_count_orm_mixed(db_session: Session):
    """Test: contador con notificaciones leídas y no leídas"""
    user_id = create_test_user(db_session)

    # Crear 5 notificaciones
    for i in range(5):
        notification_crud.create_notification_orm(
            db_session,
            recipient_id=str(user_id),
            notification_kind="system",
            title=f"Notification {i}",
            body=f"Body {i}",
        )

    # Marcar 2 como leídas
    notifications = (
        db_session.query(Notification).filter(Notification.recipient_id == user_id).limit(2).all()
    )
    for notif in notifications:
        notif.read_at = datetime.now(timezone.utc)
    db_session.commit()

    count = notification_crud.get_unread_count_orm(db_session, str(user_id))

    assert count == 3


def test_get_unread_count_orm_after_mark_all_read(db_session: Session):
    """Test: contador después de marcar todas como leídas"""
    user_id = create_test_user(db_session)

    # Crear notificaciones
    for i in range(4):
        notification_crud.create_notification_orm(
            db_session,
            recipient_id=str(user_id),
            notification_kind="system",
            title=f"Unread {i}",
            body=f"Body {i}",
        )

    # Marcar todas como leídas
    notification_crud.mark_all_as_read_orm(db_session, str(user_id))

    # Verificar contador
    count = notification_crud.get_unread_count_orm(db_session, str(user_id))

    assert count == 0


# ============================================================================
# Tests de check_existing_invite_orm
# ============================================================================


def test_check_existing_invite_orm_not_exists(db_session: Session):
    """Test: verificar invitación inexistente"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    exists = notification_crud.check_existing_invite_orm(db_session, str(user_id), str(project_id))

    assert exists is False


def test_check_existing_invite_orm_exists(db_session: Session):
    """Test: verificar invitación existente"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    # Crear invitación
    notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="invite",
        title="Project Invitation",
        body="You've been invited",
        project_id=str(project_id),
    )

    exists = notification_crud.check_existing_invite_orm(db_session, str(user_id), str(project_id))

    assert exists is True


def test_check_existing_invite_orm_different_kind(db_session: Session):
    """Test: notificación de otro tipo no cuenta como invitación"""
    user_id = create_test_user(db_session)
    project_id = create_test_project(db_session, user_id)

    # Crear notificación de sistema (no invite)
    notification_crud.create_notification_orm(
        db_session,
        recipient_id=str(user_id),
        notification_kind="system",
        title="System Notification",
        body="This is a system notification",
        project_id=str(project_id),
    )

    exists = notification_crud.check_existing_invite_orm(db_session, str(user_id), str(project_id))

    assert exists is False
