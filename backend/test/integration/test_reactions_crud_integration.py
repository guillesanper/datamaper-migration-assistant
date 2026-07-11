# test/integration/test_reactions_crud_integration.py
"""
Tests de integración para app.crud.reactions_crud
Usa base de datos real de PostgreSQL para testing
"""

import os
import sys
import uuid
from datetime import datetime

import pytest

# Import functions to test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from app.crud import comments_crud, reactions_crud

# ============================================================================
# LOCAL FIXTURES - Usan clean_db_session consistentemente
# ============================================================================


@pytest.fixture
def local_test_user(clean_db_session, worker_id):
    """
    Usuario de prueba local que usa clean_db_session.
    Necesario porque el fixture global test_user usa db_session diferente,
    y clean_db_session hace TRUNCATE que borra los datos.
    """
    from app.models.orm import User
    from app.services.auth_service import AuthService

    if worker_id == "master":
        suffix = ""
    else:
        suffix = f"_{worker_id}"

    email = f"test_reactions{suffix}@example.com"
    username = f"test_reactions_user{suffix}"
    password = "Test123!@#"

    # Verificar si ya existe
    existing_user = clean_db_session.query(User).filter(User.email == email).first()
    if existing_user:
        existing_user.is_verified = True
        clean_db_session.commit()
        return {
            "id": str(existing_user.id),
            "username": username,
            "email": email,
            "password": password,
        }

    # Crear usuario usando AuthService con la sesión correcta
    auth_service = AuthService(clean_db_session)
    user = auth_service.create_user(username=username, email=email, password=password)

    # Marcar como verificado
    created_user = clean_db_session.query(User).filter(User.id == user["user_id"]).first()
    if created_user:
        created_user.is_verified = True
        clean_db_session.commit()

    return {"id": user["user_id"], "username": username, "email": email, "password": password}


@pytest.fixture
def local_test_project(clean_db_session, local_test_user):
    """
    Proyecto de prueba local que usa clean_db_session.
    Necesario porque el fixture global test_project usa db (psycopg2),
    y clean_db_session hace TRUNCATE que borra los datos.
    """
    from app.crud.project_crud import ProjectCRUD

    return ProjectCRUD.create_project_orm(
        db=clean_db_session,
        owner_id=local_test_user["id"],
        name="Test Reactions Project",
        description="A test project for reactions",
        origin_db="PostgreSQL",
        destination_db="MySQL",
        status="active",
    )


@pytest.fixture
def test_comment(clean_db_session, local_test_user, local_test_project):
    """Fixture para crear un comentario de prueba"""
    from app.crud import schemas_crud

    # Crear una tabla primero usando ORM
    table = schemas_crud.create_table_orm(
        clean_db_session,
        local_test_project["id"],
        "test_table",
        "origin",
        local_test_user["id"],
        encryption_key=None,
    )

    # Crear comentario usando ORM
    comment = comments_crud.create_comment_orm(
        db=clean_db_session,
        entity_id=table["id"],
        entity_type="table",
        project_id=local_test_project["id"],
        user_id=local_test_user["id"],
        content="This is a test comment",
    )

    return comment


@pytest.mark.integration
@pytest.mark.database
class TestReactionsCrudIntegration:
    """Tests de integración para reactions_crud con BD real"""

    def test_add_and_check_reaction(self, clean_db_session, local_test_user, test_comment):
        """
        Test: Agregar una reacción y verificar que existe
        Verifica el flujo completo de add -> check
        """
        # Agregar reacción
        reaction = reactions_crud.add_reaction_orm(
            db=clean_db_session,
            comment_id=test_comment["id"],
            user_id=local_test_user["id"],
            emoji="👍",
        )

        # Verificar que se creó
        assert reaction is not None
        assert reaction["comment_id"] == test_comment["id"]
        assert reaction["user_id"] == local_test_user["id"]
        assert reaction["emoji"] == "👍"

        # Verificar que el usuario ha reaccionado
        has_reacted = reactions_crud.check_user_reacted_orm(
            db=clean_db_session,
            comment_id=test_comment["id"],
            user_id=local_test_user["id"],
            emoji="👍",
        )

        assert has_reacted is True

    def test_add_duplicate_reaction_returns_none(
        self, clean_db_session, local_test_user, test_comment
    ):
        """
        Test: Intentar agregar una reacción duplicada
        Verifica que ON CONFLICT DO NOTHING funciona correctamente
        """
        # Primera reacción
        reaction1 = reactions_crud.add_reaction_orm(
            db=clean_db_session,
            comment_id=test_comment["id"],
            user_id=local_test_user["id"],
            emoji="❤️",
        )

        assert reaction1 is not None

        # Intentar agregar la misma reacción otra vez
        reaction2 = reactions_crud.add_reaction_orm(
            db=clean_db_session,
            comment_id=test_comment["id"],
            user_id=local_test_user["id"],
            emoji="❤️",
        )

        # Debe retornar None debido al conflicto
        assert reaction2 is None

    def test_remove_reaction(self, clean_db_session, local_test_user, test_comment):
        """
        Test: Agregar y luego eliminar una reacción
        Verifica el flujo completo de add -> remove -> check
        """
        # Agregar reacción
        reactions_crud.add_reaction_orm(
            db=clean_db_session,
            comment_id=test_comment["id"],
            user_id=local_test_user["id"],
            emoji="😂",
        )

        # Verificar que existe
        has_reacted = reactions_crud.check_user_reacted_orm(
            db=clean_db_session,
            comment_id=test_comment["id"],
            user_id=local_test_user["id"],
            emoji="😂",
        )
        assert has_reacted is True

        # Eliminar reacción
        deleted = reactions_crud.remove_reaction_orm(
            db=clean_db_session,
            comment_id=test_comment["id"],
            user_id=local_test_user["id"],
            emoji="😂",
        )

        assert deleted is True

        # Verificar que ya no existe
        has_reacted_after = reactions_crud.check_user_reacted_orm(
            db=clean_db_session,
            comment_id=test_comment["id"],
            user_id=local_test_user["id"],
            emoji="😂",
        )
        assert has_reacted_after is False

    def test_remove_nonexistent_reaction(self, clean_db_session, local_test_user, test_comment):
        """
        Test: Intentar eliminar una reacción que no existe
        Verifica que retorna False cuando no hay nada que eliminar
        """
        deleted = reactions_crud.remove_reaction_orm(
            db=clean_db_session,
            comment_id=test_comment["id"],
            user_id=local_test_user["id"],
            emoji="🎉",
        )

        assert deleted is False

    def test_get_reactions_by_comment_multiple_users(
        self, clean_db_session, local_test_user, test_comment
    ):
        """
        Test: Obtener reacciones de múltiples usuarios
        Verifica que se incluyen los nombres de usuario
        """
        from app.models.orm import User

        # Crear segundo usuario usando ORM
        user_2_id = uuid.uuid4()
        user_2 = User(
            id=user_2_id,
            username=f"testuser2_{str(user_2_id)[:8]}",
            email=f"test2_{str(user_2_id)[:8]}@example.com",
            password_hash="hash",
            is_verified=True,
            is_deleted=False,
        )
        clean_db_session.add(user_2)
        clean_db_session.commit()

        # Agregar reacciones de diferentes usuarios
        reactions_crud.add_reaction_orm(
            db=clean_db_session,
            comment_id=test_comment["id"],
            user_id=local_test_user["id"],
            emoji="👍",
        )

        reactions_crud.add_reaction_orm(
            db=clean_db_session, comment_id=test_comment["id"], user_id=str(user_2_id), emoji="❤️"
        )

        reactions_crud.add_reaction_orm(
            db=clean_db_session, comment_id=test_comment["id"], user_id=str(user_2_id), emoji="👍"
        )

        # Obtener todas las reacciones
        reactions = reactions_crud.get_reactions_by_comment_orm(
            db=clean_db_session, comment_id=test_comment["id"]
        )

        # Verificar resultados
        assert len(reactions) == 3

        # Verificar que incluyen username
        assert all("username" in r for r in reactions)

        # Verificar orden por created_at ASC
        assert reactions[0]["emoji"] == "👍"
        assert reactions[0]["username"] == local_test_user["username"]

    def test_get_reactions_empty_comment(self, clean_db_session, test_comment):
        """
        Test: Obtener reacciones de un comentario sin reacciones
        Verifica que retorna lista vacía
        """
        reactions = reactions_crud.get_reactions_by_comment_orm(
            db=clean_db_session, comment_id=test_comment["id"]
        )

        assert reactions == []

    def test_get_reaction_counts(self, clean_db_session, local_test_user, test_comment):
        """
        Test: Obtener conteos de reacciones agrupados por emoji
        Verifica que los conteos son correctos
        """
        from app.models.orm import User

        # Crear usuarios adicionales usando ORM
        user_2_id = uuid.uuid4()
        user_3_id = uuid.uuid4()

        user_2 = User(
            id=user_2_id,
            username=f"testuser2_{str(user_2_id)[:8]}",
            email=f"test2_{str(user_2_id)[:8]}@example.com",
            password_hash="hash",
            is_verified=True,
            is_deleted=False,
        )
        user_3 = User(
            id=user_3_id,
            username=f"testuser3_{str(user_3_id)[:8]}",
            email=f"test3_{str(user_3_id)[:8]}@example.com",
            password_hash="hash",
            is_verified=True,
            is_deleted=False,
        )
        clean_db_session.add(user_2)
        clean_db_session.add(user_3)
        clean_db_session.commit()

        # Agregar varias reacciones
        reactions_crud.add_reaction_orm(
            clean_db_session, test_comment["id"], local_test_user["id"], "👍"
        )
        reactions_crud.add_reaction_orm(clean_db_session, test_comment["id"], str(user_2_id), "👍")
        reactions_crud.add_reaction_orm(clean_db_session, test_comment["id"], str(user_3_id), "👍")
        reactions_crud.add_reaction_orm(clean_db_session, test_comment["id"], str(user_2_id), "❤️")
        reactions_crud.add_reaction_orm(clean_db_session, test_comment["id"], str(user_3_id), "❤️")
        reactions_crud.add_reaction_orm(
            clean_db_session, test_comment["id"], local_test_user["id"], "😂"
        )

        # Obtener conteos
        counts = reactions_crud.get_reaction_counts_orm(
            db=clean_db_session, comment_id=test_comment["id"]
        )

        # Verificar conteos
        assert counts["👍"] == 3
        assert counts["❤️"] == 2
        assert counts["😂"] == 1

    def test_get_reaction_counts_empty(self, clean_db_session, test_comment):
        """
        Test: Obtener conteos de un comentario sin reacciones
        Verifica que retorna diccionario vacío
        """
        counts = reactions_crud.get_reaction_counts_orm(
            db=clean_db_session, comment_id=test_comment["id"]
        )

        assert counts == {}

    def test_check_user_not_reacted(self, clean_db_session, local_test_user, test_comment):
        """
        Test: Verificar que un usuario no ha reaccionado
        Verifica que retorna False cuando no existe la reacción
        """
        has_reacted = reactions_crud.check_user_reacted_orm(
            db=clean_db_session,
            comment_id=test_comment["id"],
            user_id=local_test_user["id"],
            emoji="🚀",
        )

        assert has_reacted is False

    def test_multiple_emojis_same_user(self, clean_db_session, local_test_user, test_comment):
        """
        Test: Un usuario puede reaccionar con múltiples emojis diferentes
        Verifica que el mismo usuario puede tener varias reacciones diferentes
        """
        # Agregar varias reacciones del mismo usuario
        reactions_crud.add_reaction_orm(
            clean_db_session, test_comment["id"], local_test_user["id"], "👍"
        )
        reactions_crud.add_reaction_orm(
            clean_db_session, test_comment["id"], local_test_user["id"], "❤️"
        )
        reactions_crud.add_reaction_orm(
            clean_db_session, test_comment["id"], local_test_user["id"], "😂"
        )

        # Obtener reacciones
        reactions = reactions_crud.get_reactions_by_comment_orm(
            db=clean_db_session, comment_id=test_comment["id"]
        )

        # Verificar que tiene 3 reacciones
        assert len(reactions) == 3

        # Verificar que todas son del mismo usuario
        assert all(r["user_id"] == local_test_user["id"] for r in reactions)

        # Verificar que son emojis diferentes
        emojis = {r["emoji"] for r in reactions}
        assert emojis == {"👍", "❤️", "😂"}
