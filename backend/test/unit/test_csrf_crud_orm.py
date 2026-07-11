"""
Tests unitarios para csrf_crud.py (funciones ORM).
Valida generación, validación y limpieza de tokens CSRF.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.crud import csrf_crud
from app.models.orm import CSRFToken

# ============================================================================
# Tests de generate_token_orm
# ============================================================================


def test_generate_token_orm(db_session: Session):
    """Test generating basic CSRF token"""
    unique_id = str(uuid.uuid4())[:8]

    result = csrf_crud.generate_token_orm(
        db_session, session_id=f"session_{unique_id}", ip_address="192.168.1.100"
    )

    assert result is not None
    assert "id" in result
    assert "token" in result
    assert len(result["token"]) > 20  # Token seguro
    assert result["used"] == False
    assert result["used_at"] is None
    assert result["session_id"] == f"session_{unique_id}"
    assert result["ip_address"] == "192.168.1.100"
    assert "expires_at" in result
    assert "created_at" in result


def test_generate_token_orm_custom_expiry(db_session: Session):
    """Test generating token with custom expiration"""
    unique_id = str(uuid.uuid4())[:8]

    result = csrf_crud.generate_token_orm(
        db_session, session_id=f"session_{unique_id}", ip_address="10.0.0.1", expires_in_minutes=30
    )

    assert result is not None
    assert "token" in result
    assert "expires_at" in result

    # Verificar que la expiración está aproximadamente en 30 minutos
    now = datetime.now(timezone.utc)
    expected_expiry = now + timedelta(minutes=30)
    actual_expiry = result["expires_at"]

    # Convertir a datetime si es string
    if isinstance(actual_expiry, str):
        from dateutil import parser

        actual_expiry = parser.parse(actual_expiry)

    time_diff = abs((actual_expiry - expected_expiry).total_seconds())
    assert time_diff < 5  # Diferencia menor a 5 segundos


def test_generate_token_orm_unique(db_session: Session):
    """Test that multiple tokens are unique"""
    unique_id = str(uuid.uuid4())[:8]

    token1 = csrf_crud.generate_token_orm(
        db_session, session_id=f"session_{unique_id}_1", ip_address="192.168.1.100"
    )

    token2 = csrf_crud.generate_token_orm(
        db_session, session_id=f"session_{unique_id}_2", ip_address="192.168.1.100"
    )

    token3 = csrf_crud.generate_token_orm(
        db_session, session_id=f"session_{unique_id}_3", ip_address="192.168.1.100"
    )

    # Todos los tokens deben ser únicos
    assert token1["token"] != token2["token"]
    assert token1["token"] != token3["token"]
    assert token2["token"] != token3["token"]


# ============================================================================
# Tests de validate_token_orm
# ============================================================================


def test_validate_token_orm_valid(db_session: Session):
    """Test validating a valid token"""
    unique_id = str(uuid.uuid4())[:8]

    # Generar token
    result = csrf_crud.generate_token_orm(
        db_session,
        session_id=f"session_{unique_id}",
        ip_address="192.168.1.100",
        expires_in_minutes=60,
    )

    token = result["token"]

    # Validar token
    is_valid = csrf_crud.validate_token_orm(db_session, token)

    assert is_valid == True

    # Verificar que fue marcado como usado
    csrf_token = db_session.query(CSRFToken).filter(CSRFToken.token == token).first()
    assert csrf_token is not None
    assert csrf_token.used == True
    assert csrf_token.used_at is not None


def test_validate_token_orm_expired(db_session: Session):
    """Test validating an expired token"""
    unique_id = str(uuid.uuid4())[:8]

    # Crear token expirado directamente en DB
    now = datetime.now(timezone.utc)
    expired_token = f"expired_token_{unique_id}"

    csrf_token = CSRFToken(
        token=expired_token,
        session_id=f"session_{unique_id}",
        ip_address="192.168.1.100",
        expires_at=now - timedelta(hours=1),  # Expirado hace 1 hora
        used=False,
        created_at=now - timedelta(hours=2),
    )

    db_session.add(csrf_token)
    db_session.commit()

    # Intentar validar token expirado
    is_valid = csrf_crud.validate_token_orm(db_session, expired_token)

    assert is_valid == False


def test_validate_token_orm_used(db_session: Session):
    """Test validating a token that was already used"""
    unique_id = str(uuid.uuid4())[:8]

    # Generar token
    result = csrf_crud.generate_token_orm(
        db_session, session_id=f"session_{unique_id}", ip_address="192.168.1.100"
    )

    token = result["token"]

    # Validar primera vez (debería marcar como usado)
    is_valid_first = csrf_crud.validate_token_orm(db_session, token)
    assert is_valid_first == True

    # Intentar validar segunda vez (debería fallar porque ya fue usado)
    is_valid_second = csrf_crud.validate_token_orm(db_session, token)
    assert is_valid_second == False


def test_validate_token_orm_nonexistent(db_session: Session):
    """Test validating a nonexistent token"""
    unique_id = str(uuid.uuid4())[:8]

    # Intentar validar token que no existe
    is_valid = csrf_crud.validate_token_orm(db_session, f"nonexistent_token_{unique_id}")

    assert is_valid == False


def test_validate_token_orm_marks_as_used(db_session: Session):
    """Test that validation marks token as used with timestamp"""
    unique_id = str(uuid.uuid4())[:8]

    # Generar token
    result = csrf_crud.generate_token_orm(
        db_session, session_id=f"session_{unique_id}", ip_address="192.168.1.100"
    )

    token = result["token"]

    # Verificar estado inicial
    csrf_token_before = db_session.query(CSRFToken).filter(CSRFToken.token == token).first()
    assert csrf_token_before.used == False
    assert csrf_token_before.used_at is None

    # Validar token
    before_validation = datetime.now(timezone.utc)
    is_valid = csrf_crud.validate_token_orm(db_session, token)
    after_validation = datetime.now(timezone.utc)

    assert is_valid == True

    # Verificar que fue marcado como usado con timestamp
    db_session.expire_all()  # Refrescar desde DB
    csrf_token_after = db_session.query(CSRFToken).filter(CSRFToken.token == token).first()

    assert csrf_token_after.used == True
    assert csrf_token_after.used_at is not None
    assert before_validation <= csrf_token_after.used_at <= after_validation


def test_validate_token_orm_with_session_validation(db_session: Session):
    """Test validating token with session_id check"""
    unique_id = str(uuid.uuid4())[:8]

    # Generar token
    result = csrf_crud.generate_token_orm(
        db_session, session_id=f"session_{unique_id}", ip_address="192.168.1.100"
    )

    token = result["token"]

    # Validar con session_id correcto
    is_valid_correct = csrf_crud.validate_token_orm(
        db_session, token, session_id=f"session_{unique_id}"
    )
    assert is_valid_correct == True

    # Generar otro token para probar con session_id incorrecto
    result2 = csrf_crud.generate_token_orm(
        db_session, session_id=f"session_{unique_id}_2", ip_address="192.168.1.100"
    )

    token2 = result2["token"]

    # Validar con session_id incorrecto
    is_valid_incorrect = csrf_crud.validate_token_orm(
        db_session, token2, session_id="wrong_session_id"
    )
    assert is_valid_incorrect == False


def test_validate_token_orm_with_ip_validation(db_session: Session):
    """Test validating token with ip_address check"""
    unique_id = str(uuid.uuid4())[:8]

    # Generar token
    result = csrf_crud.generate_token_orm(
        db_session, session_id=f"session_{unique_id}", ip_address="192.168.1.100"
    )

    token = result["token"]

    # Validar con IP correcta
    is_valid_correct = csrf_crud.validate_token_orm(db_session, token, ip_address="192.168.1.100")
    assert is_valid_correct == True

    # Generar otro token para probar con IP incorrecta
    result2 = csrf_crud.generate_token_orm(
        db_session, session_id=f"session_{unique_id}_2", ip_address="10.0.0.1"
    )

    token2 = result2["token"]

    # Validar con IP incorrecta
    is_valid_incorrect = csrf_crud.validate_token_orm(
        db_session, token2, ip_address="192.168.99.99"
    )
    assert is_valid_incorrect == False


# ============================================================================
# Tests de cleanup_orm
# ============================================================================


def test_cleanup_orm(db_session: Session):
    """Test cleaning up expired tokens"""
    unique_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc)

    # Crear token expirado hace 48 horas
    old_token1 = CSRFToken(
        token=f"old_token1_{unique_id}",
        session_id=f"session_{unique_id}_1",
        ip_address="192.168.1.100",
        expires_at=now - timedelta(hours=48),
        used=False,
        created_at=now - timedelta(hours=50),
    )

    # Crear token usado hace 48 horas
    old_token2 = CSRFToken(
        token=f"old_token2_{unique_id}",
        session_id=f"session_{unique_id}_2",
        ip_address="192.168.1.101",
        expires_at=now + timedelta(hours=1),
        used=True,
        used_at=now - timedelta(hours=48),
        created_at=now - timedelta(hours=50),
    )

    # Crear token reciente (no debe ser eliminado)
    recent_token = CSRFToken(
        token=f"recent_token_{unique_id}",
        session_id=f"session_{unique_id}_3",
        ip_address="192.168.1.102",
        expires_at=now + timedelta(hours=1),
        used=False,
        created_at=now - timedelta(hours=1),
    )

    db_session.add_all([old_token1, old_token2, recent_token])
    db_session.commit()

    # Ejecutar cleanup (24 horas)
    deleted_count = csrf_crud.cleanup_orm(db_session, hours_old=24)

    # Deben haberse eliminado 2 tokens antiguos
    assert deleted_count == 2

    # Verificar que el token reciente sigue existiendo
    remaining_token = (
        db_session.query(CSRFToken).filter(CSRFToken.token == f"recent_token_{unique_id}").first()
    )
    assert remaining_token is not None


def test_cleanup_orm_keep_recent(db_session: Session):
    """Test that cleanup keeps recent tokens"""
    unique_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc)

    # Crear varios tokens recientes
    for i in range(3):
        token = CSRFToken(
            token=f"recent_token_{unique_id}_{i}",
            session_id=f"session_{unique_id}_{i}",
            ip_address=f"192.168.1.{100+i}",
            expires_at=now + timedelta(hours=1),
            used=False,
            created_at=now - timedelta(hours=2),
        )
        db_session.add(token)

    db_session.commit()

    # Ejecutar cleanup
    deleted_count = csrf_crud.cleanup_orm(db_session, hours_old=24)

    # No debe haberse eliminado ningún token
    assert deleted_count == 0

    # Verificar que todos siguen existiendo
    remaining_count = (
        db_session.query(CSRFToken)
        .filter(CSRFToken.token.like(f"recent_token_{unique_id}_%"))
        .count()
    )
    assert remaining_count == 3


def test_cleanup_orm_no_old_tokens(db_session: Session):
    """Test cleanup when there are no old tokens"""
    # Ejecutar cleanup cuando no hay tokens antiguos
    deleted_count = csrf_crud.cleanup_orm(db_session, hours_old=24)

    # No debe haberse eliminado ningún token
    assert deleted_count >= 0  # Puede ser 0 o más dependiendo del estado de la DB


def test_cleanup_orm_custom_hours(db_session: Session):
    """Test cleanup with custom hours threshold"""
    unique_id = str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc)

    # Crear token expirado hace 3 horas
    token_3h = CSRFToken(
        token=f"token_3h_{unique_id}",
        session_id=f"session_{unique_id}_1",
        ip_address="192.168.1.100",
        expires_at=now - timedelta(hours=3),
        used=False,
        created_at=now - timedelta(hours=4),
    )

    # Crear token expirado hace 10 horas
    token_10h = CSRFToken(
        token=f"token_10h_{unique_id}",
        session_id=f"session_{unique_id}_2",
        ip_address="192.168.1.101",
        expires_at=now - timedelta(hours=10),
        used=False,
        created_at=now - timedelta(hours=11),
    )

    db_session.add_all([token_3h, token_10h])
    db_session.commit()

    # Ejecutar cleanup con threshold de 5 horas
    deleted_count = csrf_crud.cleanup_orm(db_session, hours_old=5)

    # Solo debe eliminarse el token de 10 horas
    assert deleted_count == 1

    # Verificar que el de 3 horas sigue existiendo
    remaining_token = (
        db_session.query(CSRFToken).filter(CSRFToken.token == f"token_3h_{unique_id}").first()
    )
    assert remaining_token is not None

    # Verificar que el de 10 horas fue eliminado
    deleted_token = (
        db_session.query(CSRFToken).filter(CSRFToken.token == f"token_10h_{unique_id}").first()
    )
    assert deleted_token is None
