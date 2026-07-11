"""
Tests para email_otp_crud.py (versión ORM)
"""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from sqlalchemy.orm import Session

from app.crud import email_otp_crud
from app.models.orm import EmailOTP, User

# ============================================================================
# Helper para crear usuarios de prueba
# ============================================================================


def create_test_user(session: Session, user_id: uuid.UUID = None) -> uuid.UUID:
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
    session.add(user)
    session.commit()

    return user_id


# ============================================================================
# Tests de create_otp_orm
# ============================================================================


def test_create_otp_orm(clean_db_session: Session):
    """Test básico: crear OTP para usuario"""
    user_id = create_test_user(clean_db_session)
    otp_code = "12345678"

    result = email_otp_crud.create_otp_orm(clean_db_session, user_id, otp_code)

    assert result is not None
    assert result["user_id"] == str(user_id)
    assert result["otp_code"] != otp_code  # Debe estar hasheado
    assert result["expires_at"] is not None

    # Verificar que existe en BD
    otp_db = clean_db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()
    assert otp_db is not None
    assert otp_db.otp_code != otp_code  # Hash, no texto plano


def test_create_otp_orm_custom_expiry(clean_db_session: Session):
    """Test: crear OTP con expiración custom"""
    user_id = create_test_user(clean_db_session)
    otp_code = "87654321"
    expires_in = 30  # 30 minutos

    before = datetime.now(timezone.utc)
    result = email_otp_crud.create_otp_orm(
        clean_db_session, user_id, otp_code, expires_in_minutes=expires_in
    )
    after = datetime.now(timezone.utc)

    # Verificar que expira_at está aproximadamente en 30 minutos
    expected_expiry_min = before + timedelta(minutes=expires_in)
    expected_expiry_max = after + timedelta(minutes=expires_in)

    expires_at = result["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

    assert expected_expiry_min <= expires_at <= expected_expiry_max


def test_create_otp_orm_update_existing(clean_db_session: Session):
    """Test: actualizar OTP existente (user_id es PK - solo 1 OTP por usuario)"""
    user_id = create_test_user(clean_db_session)
    otp_code_1 = "11111111"
    otp_code_2 = "22222222"

    # Crear primer OTP
    result1 = email_otp_crud.create_otp_orm(clean_db_session, user_id, otp_code_1)
    hash1 = result1["otp_code"]

    # Crear segundo OTP (debe actualizar el primero)
    result2 = email_otp_crud.create_otp_orm(clean_db_session, user_id, otp_code_2)
    hash2 = result2["otp_code"]

    # Verificar que el hash cambió
    assert hash1 != hash2

    # Verificar que solo hay 1 OTP en BD
    count = clean_db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).count()
    assert count == 1

    # Verificar que el código actual es el segundo
    otp_db = clean_db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()
    assert bcrypt.checkpw(otp_code_2.encode("utf-8"), otp_db.otp_code.encode("utf-8"))


def test_create_otp_orm_encrypted(clean_db_session: Session):
    """Test: verificar que OTP está cifrado con bcrypt"""
    user_id = create_test_user(clean_db_session)
    otp_code = "ABCD1234"

    result = email_otp_crud.create_otp_orm(clean_db_session, user_id, otp_code)

    # Verificar que el hash es válido para bcrypt
    hash_bytes = result["otp_code"].encode("utf-8")
    assert hash_bytes.startswith(b"$2b$")  # bcrypt hash prefix

    # Verificar que se puede verificar con bcrypt
    assert bcrypt.checkpw(otp_code.encode("utf-8"), hash_bytes)
    # Verificar que código incorrecto falla
    assert not bcrypt.checkpw("WRONG".encode("utf-8"), hash_bytes)


# ============================================================================
# Tests de verify_otp_orm
# ============================================================================


def test_verify_otp_orm_valid(clean_db_session: Session):
    """Test: verificar OTP válido"""
    user_id = create_test_user(clean_db_session)
    otp_code = "99887766"

    # Crear OTP
    email_otp_crud.create_otp_orm(clean_db_session, user_id, otp_code)

    # Verificar OTP
    is_valid = email_otp_crud.verify_otp_orm(clean_db_session, user_id, otp_code)

    assert is_valid is True


def test_verify_otp_orm_invalid_code(clean_db_session: Session):
    """Test: verificar OTP con código incorrecto"""
    user_id = create_test_user(clean_db_session)
    otp_code = "11112222"

    # Crear OTP
    email_otp_crud.create_otp_orm(clean_db_session, user_id, otp_code)

    # Verificar con código incorrecto
    is_valid = email_otp_crud.verify_otp_orm(clean_db_session, user_id, "33334444")

    assert is_valid is False

    # OTP NO debe haberse eliminado (código incorrecto)
    otp_db = clean_db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()
    assert otp_db is not None


def test_verify_otp_orm_expired(clean_db_session: Session):
    """Test: verificar OTP expirado (debe retornar False y eliminar)"""
    user_id = create_test_user(clean_db_session)
    otp_code = "55556666"

    # Crear OTP que expira en 0 minutos (expirado inmediatamente)
    email_otp_crud.create_otp_orm(clean_db_session, user_id, otp_code, expires_in_minutes=0)

    # Esperar un poco para asegurar que expire
    import time

    time.sleep(0.1)

    # Verificar OTP expirado
    is_valid = email_otp_crud.verify_otp_orm(clean_db_session, user_id, otp_code)

    assert is_valid is False

    # OTP debe haberse eliminado automáticamente
    otp_db = clean_db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()
    assert otp_db is None


def test_verify_otp_orm_nonexistent(clean_db_session: Session):
    """Test: verificar OTP inexistente"""
    user_id = create_test_user(clean_db_session)  # Usuario existe, pero OTP no
    otp_code = "77778888"

    # NO crear OTP, solo intentar verificar
    is_valid = email_otp_crud.verify_otp_orm(clean_db_session, user_id, otp_code)

    assert is_valid is False


def test_verify_otp_orm_deletes_after_use(clean_db_session: Session):
    """Test: OTP se elimina después de verificación exitosa"""
    user_id = create_test_user(clean_db_session)
    otp_code = "44445555"

    # Crear OTP
    email_otp_crud.create_otp_orm(clean_db_session, user_id, otp_code)

    # Verificar que existe antes de verificar
    otp_before = clean_db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()
    assert otp_before is not None

    # Verificar OTP
    is_valid = email_otp_crud.verify_otp_orm(clean_db_session, user_id, otp_code)
    assert is_valid is True

    # Verificar que se eliminó después de uso
    otp_after = clean_db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()
    assert otp_after is None


def test_verify_otp_orm_cannot_reuse(clean_db_session: Session):
    """Test: no se puede reusar OTP después de verificación exitosa"""
    user_id = create_test_user(clean_db_session)
    otp_code = "66667777"

    # Crear OTP
    email_otp_crud.create_otp_orm(clean_db_session, user_id, otp_code)

    # Primera verificación (exitosa)
    is_valid_1 = email_otp_crud.verify_otp_orm(clean_db_session, user_id, otp_code)
    assert is_valid_1 is True

    # Segunda verificación (debe fallar - OTP ya usado y eliminado)
    is_valid_2 = email_otp_crud.verify_otp_orm(clean_db_session, user_id, otp_code)
    assert is_valid_2 is False


# ============================================================================
# Tests de delete_otp_orm
# ============================================================================


def test_delete_otp_orm(clean_db_session: Session):
    """Test: eliminar OTP existente"""
    user_id = create_test_user(clean_db_session)
    otp_code = "12341234"

    # Crear OTP
    email_otp_crud.create_otp_orm(clean_db_session, user_id, otp_code)

    # Eliminar OTP
    deleted = email_otp_crud.delete_otp_orm(clean_db_session, user_id)

    assert deleted is True

    # Verificar que no existe en BD
    otp_db = clean_db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()
    assert otp_db is None


def test_delete_otp_orm_nonexistent(clean_db_session: Session):
    """Test: eliminar OTP inexistente retorna False"""
    user_id = create_test_user(clean_db_session)  # Usuario existe, pero OTP no

    # NO crear OTP, solo intentar eliminar
    deleted = email_otp_crud.delete_otp_orm(clean_db_session, user_id)

    assert deleted is False


def test_delete_otp_orm_after_create(clean_db_session: Session):
    """Test: crear y eliminar OTP"""
    user_id = create_test_user(clean_db_session)
    otp_code = "ABCDEFGH"

    # Crear OTP
    result = email_otp_crud.create_otp_orm(clean_db_session, user_id, otp_code)
    assert result is not None

    # Verificar que existe
    otp_db = clean_db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()
    assert otp_db is not None

    # Eliminar OTP
    deleted = email_otp_crud.delete_otp_orm(clean_db_session, user_id)
    assert deleted is True

    # Verificar que ya no existe
    otp_db_after = clean_db_session.query(EmailOTP).filter(EmailOTP.user_id == user_id).first()
    assert otp_db_after is None
