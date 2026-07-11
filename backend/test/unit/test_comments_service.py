"""
Tests unitarios para Comments Service

Módulo: app.services.comments_service
Propósito: Tests para lógica de negocio de comentarios y reacciones

Seguridad crítica:
- Validación de permisos (solo autor puede editar/eliminar)
- Extracción segura de @menciones con regex
- Prevención de SQL injection en resolución de menciones

Autor: DataMap Testing Team
Última actualización: 2025-01-15
"""

import json
from unittest.mock import MagicMock, call, patch

import pytest

from app.services import comments_service

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_db():
    """Mock de sesión SQLAlchemy"""
    mock = MagicMock()
    mock.query = MagicMock()
    mock.commit = MagicMock()
    mock.rollback = MagicMock()
    return mock


@pytest.fixture
def comment_data():
    """Datos de comentario de prueba"""
    return {
        "id": "comment-123",
        "entity_id": "entity-456",
        "entity_type": "table",
        "project_id": "project-789",
        "user_id": "user-abc",
        "content": "Test comment with @john mention",
        "mentions": ["user-john-id"],
        "created_at": "2025-01-15T10:00:00Z",
    }


# ============================================================================
# TESTS: extract_mentions()
# ============================================================================


class TestExtractMentions:
    """Tests para extracción de @menciones"""

    def test_extract_mentions_single_mention(self):
        """Extrae mención única"""
        # Arrange
        content = "Hello @john how are you?"

        # Act
        mentions = comments_service.extract_mentions(content)

        # Assert
        assert mentions == ["john"]

    def test_extract_mentions_multiple_mentions(self):
        """Extrae múltiples menciones"""
        # Arrange
        content = "@alice and @bob please review this @charlie"

        # Act
        mentions = comments_service.extract_mentions(content)

        # Assert
        assert set(mentions) == {"alice", "bob", "charlie"}

    def test_extract_mentions_duplicate_mentions(self):
        """Elimina menciones duplicadas"""
        # Arrange
        content = "@john @john @john mentioned three times"

        # Act
        mentions = comments_service.extract_mentions(content)

        # Assert
        assert mentions == ["john"]

    def test_extract_mentions_no_mentions(self):
        """Retorna lista vacía sin menciones"""
        # Arrange
        content = "This is a comment without any mentions"

        # Act
        mentions = comments_service.extract_mentions(content)

        # Assert
        assert mentions == []

    def test_extract_mentions_with_underscores(self):
        """Extrae menciones con underscores"""
        # Arrange
        content = "Hey @john_doe and @alice_smith"

        # Act
        mentions = comments_service.extract_mentions(content)

        # Assert
        assert set(mentions) == {"john_doe", "alice_smith"}

    def test_extract_mentions_with_numbers(self):
        """Extrae menciones con números"""
        # Arrange
        content = "@user123 and @test456"

        # Act
        mentions = comments_service.extract_mentions(content)

        # Assert
        assert set(mentions) == {"user123", "test456"}

    def test_extract_mentions_at_start_of_line(self):
        """Extrae mención al inicio de línea"""
        # Arrange
        content = "@john this is important"

        # Act
        mentions = comments_service.extract_mentions(content)

        # Assert
        assert mentions == ["john"]

    def test_extract_mentions_at_end_of_line(self):
        """Extrae mención al final de línea"""
        # Arrange
        content = "Please review @john"

        # Act
        mentions = comments_service.extract_mentions(content)

        # Assert
        assert mentions == ["john"]

    def test_extract_mentions_empty_string(self):
        """Maneja string vacío"""
        # Arrange
        content = ""

        # Act
        mentions = comments_service.extract_mentions(content)

        # Assert
        assert mentions == []


# ============================================================================
# TESTS: resolve_mentions_to_user_ids()
# ============================================================================


class TestResolveMentionsToUserIds:
    """Tests para resolución de menciones a IDs de usuario (SQLAlchemy ORM)"""

    def test_resolve_mentions_to_user_ids_single_user(self, mock_db):
        """Resuelve mención única a user_id"""
        # Arrange - mock SQLAlchemy query chain
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_user]

        # Act
        user_ids = comments_service.resolve_mentions_to_user_ids(mock_db, ["john"])

        # Assert
        assert user_ids == ["user-123"]
        mock_db.query.assert_called_once()

    def test_resolve_mentions_to_user_ids_multiple_users(self, mock_db):
        """Resuelve múltiples menciones a user_ids"""
        # Arrange
        mock_user1 = MagicMock()
        mock_user1.id = "user-123"
        mock_user2 = MagicMock()
        mock_user2.id = "user-456"
        mock_user3 = MagicMock()
        mock_user3.id = "user-789"
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_user1,
            mock_user2,
            mock_user3,
        ]

        # Act
        user_ids = comments_service.resolve_mentions_to_user_ids(mock_db, ["john", "alice", "bob"])

        # Assert
        assert user_ids == ["user-123", "user-456", "user-789"]

    def test_resolve_mentions_to_user_ids_empty_list(self, mock_db):
        """Retorna lista vacía para usernames vacíos"""
        # Arrange & Act
        user_ids = comments_service.resolve_mentions_to_user_ids(mock_db, [])

        # Assert
        assert user_ids == []

    def test_resolve_mentions_to_user_ids_no_matches(self, mock_db):
        """Retorna lista vacía cuando no hay matches"""
        # Arrange
        mock_db.query.return_value.filter.return_value.all.return_value = []

        # Act
        user_ids = comments_service.resolve_mentions_to_user_ids(mock_db, ["nonexistent_user"])

        # Assert
        assert user_ids == []

    def test_resolve_mentions_to_user_ids_sql_injection_safe(self, mock_db):
        """SQLAlchemy usa parámetros para prevenir SQL injection"""
        # Arrange
        mock_db.query.return_value.filter.return_value.all.return_value = []

        # Act
        comments_service.resolve_mentions_to_user_ids(mock_db, ["user1", "user2", "user3"])

        # Assert - SQLAlchemy usa parametrización automática
        # Verificamos que se usó filter con in_()
        mock_db.query.return_value.filter.assert_called_once()


# ============================================================================
# TESTS: create_comment()
# ============================================================================


class TestCreateComment:
    """Tests para creación de comentarios"""

    @patch("app.services.comments_service.comments_crud")
    @patch("app.services.comments_service.resolve_mentions_to_user_ids")
    def test_create_comment_success(self, mock_resolve, mock_crud, mock_db, comment_data):
        """Crea comentario exitosamente"""
        # Arrange
        mock_resolve.return_value = ["user-john-id"]
        mock_crud.create_comment_orm.return_value = comment_data

        # Act
        result = comments_service.create_comment(
            db=mock_db,
            entity_id="entity-456",
            entity_type="table",
            project_id="project-789",
            user_id="user-abc",
            content="Test comment with @john mention",
        )

        # Assert
        assert result == comment_data
        mock_crud.create_comment_orm.assert_called_once()

    @patch("app.services.comments_service.comments_crud")
    @patch("app.services.comments_service.extract_mentions")
    @patch("app.services.comments_service.resolve_mentions_to_user_ids")
    def test_create_comment_extracts_mentions(
        self, mock_resolve, mock_extract, mock_crud, mock_db, comment_data
    ):
        """Extrae menciones del contenido"""
        # Arrange
        mock_extract.return_value = ["john", "alice"]
        mock_resolve.return_value = ["user-john-id", "user-alice-id"]
        mock_crud.create_comment_orm.return_value = comment_data

        # Act
        comments_service.create_comment(
            db=mock_db,
            entity_id="entity-456",
            entity_type="table",
            project_id="project-789",
            user_id="user-abc",
            content="Test @john and @alice",
        )

        # Assert
        mock_extract.assert_called_once_with("Test @john and @alice")
        mock_resolve.assert_called_once_with(mock_db, ["john", "alice"])

    @patch("app.services.comments_service.comments_crud")
    @patch("app.services.comments_service.resolve_mentions_to_user_ids")
    def test_create_comment_with_parent_id(self, mock_resolve, mock_crud, mock_db, comment_data):
        """Crea comentario con parent_id (respuesta)"""
        # Arrange
        mock_resolve.return_value = []
        mock_crud.create_comment_orm.return_value = comment_data

        # Act
        comments_service.create_comment(
            db=mock_db,
            entity_id="entity-456",
            entity_type="table",
            project_id="project-789",
            user_id="user-abc",
            content="Reply comment",
            parent_id="parent-comment-123",
        )

        # Assert
        call_args = mock_crud.create_comment_orm.call_args
        assert call_args[1]["parent_id"] == "parent-comment-123"

    @patch("app.services.comments_service.comments_crud")
    @patch("app.services.comments_service.resolve_mentions_to_user_ids")
    def test_create_comment_without_mentions(self, mock_resolve, mock_crud, mock_db, comment_data):
        """Crea comentario sin menciones"""
        # Arrange
        mock_resolve.return_value = []
        mock_crud.create_comment_orm.return_value = comment_data

        # Act
        comments_service.create_comment(
            db=mock_db,
            entity_id="entity-456",
            entity_type="table",
            project_id="project-789",
            user_id="user-abc",
            content="Comment without mentions",
        )

        # Assert
        call_args = mock_crud.create_comment_orm.call_args
        assert call_args[1]["mentions"] is None

    @patch("app.services.comments_service.comments_crud")
    @patch("app.services.comments_service.resolve_mentions_to_user_ids")
    def test_create_comment_passes_mentions_to_crud(
        self, mock_resolve, mock_crud, mock_db, comment_data
    ):
        """Pasa menciones resueltas a CRUD"""
        # Arrange
        mock_resolve.return_value = ["user-1", "user-2"]
        mock_crud.create_comment_orm.return_value = comment_data

        # Act
        comments_service.create_comment(
            db=mock_db,
            entity_id="entity-456",
            entity_type="table",
            project_id="project-789",
            user_id="user-abc",
            content="Test @john @alice",
        )

        # Assert
        call_args = mock_crud.create_comment_orm.call_args
        assert call_args[1]["mentions"] == ["user-1", "user-2"]


# ============================================================================
# TESTS: edit_comment()
# ============================================================================


class TestEditComment:
    """Tests para edición de comentarios (SQLAlchemy ORM)"""

    @patch("app.services.comments_service.comments_crud")
    @patch("app.services.comments_service.resolve_mentions_to_user_ids")
    def test_edit_comment_success(self, mock_resolve, mock_crud, mock_db, comment_data):
        """Edita comentario exitosamente"""
        # Arrange
        mock_resolve.return_value = ["user-john-id"]
        mock_crud.update_comment_orm.return_value = comment_data
        mock_db.query.return_value.filter.return_value.update.return_value = 1

        # Act
        result = comments_service.edit_comment(
            db=mock_db,
            comment_id="comment-123",
            user_id="user-abc",
            content="Updated content with @john",
        )

        # Assert
        assert result == comment_data
        mock_crud.update_comment_orm.assert_called_once_with(
            mock_db, "comment-123", "user-abc", "Updated content with @john"
        )

    @patch("app.services.comments_service.comments_crud")
    @patch("app.services.comments_service.extract_mentions")
    @patch("app.services.comments_service.resolve_mentions_to_user_ids")
    def test_edit_comment_updates_mentions(
        self, mock_resolve, mock_extract, mock_crud, mock_db, comment_data
    ):
        """Actualiza menciones al editar usando SQLAlchemy ORM"""
        # Arrange
        mock_extract.return_value = ["alice"]
        mock_resolve.return_value = ["user-alice-id"]
        mock_crud.update_comment_orm.return_value = comment_data
        mock_db.query.return_value.filter.return_value.update.return_value = 1

        # Act
        comments_service.edit_comment(
            db=mock_db, comment_id="comment-123", user_id="user-abc", content="Updated with @alice"
        )

        # Assert
        # Verifica que se usa SQLAlchemy query para actualizar mentions
        mock_db.query.assert_called()
        mock_db.commit.assert_called()

    @patch("app.services.comments_service.comments_crud")
    @patch("app.services.comments_service.resolve_mentions_to_user_ids")
    def test_edit_comment_not_author_returns_none(self, mock_resolve, mock_crud, mock_db):
        """Retorna None si usuario no es autor"""
        # Arrange
        mock_resolve.return_value = []
        mock_crud.update_comment_orm.return_value = None  # CRUD retorna None (no es autor)

        # Act
        result = comments_service.edit_comment(
            db=mock_db, comment_id="comment-123", user_id="other-user", content="Try to edit"
        )

        # Assert
        assert result is None

    @patch("app.services.comments_service.comments_crud")
    @patch("app.services.comments_service.resolve_mentions_to_user_ids")
    def test_edit_comment_commits_transaction(self, mock_resolve, mock_crud, mock_db, comment_data):
        """Hace commit de la transacción"""
        # Arrange
        mock_resolve.return_value = []
        mock_crud.update_comment_orm.return_value = comment_data
        mock_db.query.return_value.filter.return_value.update.return_value = 1

        # Act
        comments_service.edit_comment(
            db=mock_db, comment_id="comment-123", user_id="user-abc", content="Updated"
        )

        # Assert
        mock_db.commit.assert_called()


# ============================================================================
# TESTS: delete_comment()
# ============================================================================


class TestDeleteComment:
    """Tests para eliminación de comentarios"""

    @patch("app.services.comments_service.comments_crud")
    def test_delete_comment_success(self, mock_crud, mock_db):
        """Elimina comentario exitosamente"""
        # Arrange
        mock_crud.delete_comment_orm.return_value = True

        # Act
        result = comments_service.delete_comment(
            db=mock_db, comment_id="comment-123", user_id="user-abc"
        )

        # Assert
        assert result is True
        mock_crud.delete_comment_orm.assert_called_once_with(mock_db, "comment-123", "user-abc")

    @patch("app.services.comments_service.comments_crud")
    def test_delete_comment_not_author_returns_false(self, mock_crud, mock_db):
        """Retorna False si usuario no es autor"""
        # Arrange
        mock_crud.delete_comment_orm.return_value = False

        # Act
        result = comments_service.delete_comment(
            db=mock_db, comment_id="comment-123", user_id="other-user"
        )

        # Assert
        assert result is False

    @patch("app.services.comments_service.comments_crud")
    def test_delete_comment_delegates_to_crud(self, mock_crud, mock_db):
        """Delega a CRUD para validación de autor"""
        # Arrange
        mock_crud.delete_comment_orm.return_value = True

        # Act
        comments_service.delete_comment(db=mock_db, comment_id="comment-123", user_id="user-abc")

        # Assert
        # CRUD debe manejar la validación de ownership
        mock_crud.delete_comment_orm.assert_called_once()


# ============================================================================
# TESTS: resolve_comment()
# ============================================================================


class TestResolveComment:
    """Tests para marcar comentarios como resueltos"""

    @patch("app.services.comments_service.activity_crud")
    @patch("app.services.comments_service.comments_crud")
    def test_resolve_comment_marks_as_resolved(
        self, mock_crud, mock_activity, mock_db, comment_data
    ):
        """Marca comentario como resuelto"""
        # Arrange
        mock_crud.resolve_comment_orm.return_value = comment_data

        # Act
        result = comments_service.resolve_comment(
            db=mock_db,
            comment_id="comment-123",
            resolved=True,
            resolved_by="user-abc",
            project_id="project-789",
        )

        # Assert
        assert result == comment_data
        mock_crud.resolve_comment_orm.assert_called_once_with(
            mock_db, "comment-123", True, "user-abc"
        )

    @patch("app.services.comments_service.activity_crud")
    @patch("app.services.comments_service.comments_crud")
    def test_resolve_comment_logs_activity(self, mock_crud, mock_activity, mock_db, comment_data):
        """Registra actividad al resolver"""
        # Arrange
        mock_crud.resolve_comment_orm.return_value = comment_data

        # Act
        comments_service.resolve_comment(
            db=mock_db,
            comment_id="comment-123",
            resolved=True,
            resolved_by="user-abc",
            project_id="project-789",
        )

        # Assert
        mock_activity.create_activity_log_orm.assert_called_once()
        call_args = mock_activity.create_activity_log_orm.call_args[1]
        assert call_args["activity_type"] == "comment_resolved"
        assert call_args["user_id"] == "user-abc"

    @patch("app.services.comments_service.activity_crud")
    @patch("app.services.comments_service.comments_crud")
    def test_unresolve_comment_logs_activity(self, mock_crud, mock_activity, mock_db, comment_data):
        """Registra actividad al desmarcar resolución"""
        # Arrange
        mock_crud.resolve_comment_orm.return_value = comment_data

        # Act
        comments_service.resolve_comment(
            db=mock_db,
            comment_id="comment-123",
            resolved=False,
            resolved_by="user-abc",
            project_id="project-789",
        )

        # Assert
        call_args = mock_activity.create_activity_log_orm.call_args[1]
        assert call_args["activity_type"] == "comment_unresolved"

    @patch("app.services.comments_service.activity_crud")
    @patch("app.services.comments_service.comments_crud")
    def test_resolve_comment_not_found_returns_none(self, mock_crud, mock_activity, mock_db):
        """Retorna None si comentario no existe"""
        # Arrange
        mock_crud.resolve_comment_orm.return_value = None

        # Act
        result = comments_service.resolve_comment(
            db=mock_db,
            comment_id="nonexistent",
            resolved=True,
            resolved_by="user-abc",
            project_id="project-789",
        )

        # Assert
        assert result is None
        # No debe registrar actividad
        mock_activity.create_activity_log_orm.assert_not_called()


# ============================================================================
# TESTS: add_reaction()
# ============================================================================


class TestAddReaction:
    """Tests para añadir reacciones"""

    @patch("app.services.comments_service.reactions_crud")
    def test_add_reaction_success(self, mock_crud, mock_db):
        """Añade reacción exitosamente"""
        # Arrange
        reaction = {"id": "reaction-123", "emoji": "👍", "user_id": "user-abc"}
        mock_crud.add_reaction_orm.return_value = reaction

        # Act
        result = comments_service.add_reaction(
            db=mock_db, comment_id="comment-123", user_id="user-abc", emoji="👍"
        )

        # Assert
        assert result == reaction
        mock_crud.add_reaction_orm.assert_called_once_with(mock_db, "comment-123", "user-abc", "👍")

    @patch("app.services.comments_service.reactions_crud")
    def test_add_reaction_delegates_to_crud(self, mock_crud, mock_db):
        """Delega a CRUD para lógica de reacciones"""
        # Arrange
        mock_crud.add_reaction_orm.return_value = {"id": "reaction-123"}

        # Act
        comments_service.add_reaction(
            db=mock_db, comment_id="comment-123", user_id="user-abc", emoji="❤️"
        )

        # Assert
        mock_crud.add_reaction_orm.assert_called_once()


# ============================================================================
# TESTS: remove_reaction()
# ============================================================================


class TestRemoveReaction:
    """Tests para eliminar reacciones"""

    @patch("app.services.comments_service.reactions_crud")
    def test_remove_reaction_success(self, mock_crud, mock_db):
        """Elimina reacción exitosamente"""
        # Arrange
        mock_crud.remove_reaction_orm.return_value = True

        # Act
        result = comments_service.remove_reaction(
            db=mock_db, comment_id="comment-123", user_id="user-abc", emoji="👍"
        )

        # Assert
        assert result is True
        mock_crud.remove_reaction_orm.assert_called_once_with(
            mock_db, "comment-123", "user-abc", "👍"
        )

    @patch("app.services.comments_service.reactions_crud")
    def test_remove_reaction_not_found_returns_false(self, mock_crud, mock_db):
        """Retorna False si reacción no existe"""
        # Arrange
        mock_crud.remove_reaction_orm.return_value = False

        # Act
        result = comments_service.remove_reaction(
            db=mock_db, comment_id="comment-123", user_id="user-abc", emoji="👍"
        )

        # Assert
        assert result is False


# ============================================================================
# TESTS: get_comments()
# ============================================================================


class TestGetComments:
    """Tests para obtener comentarios"""

    @patch("app.services.comments_service.reactions_crud")
    @patch("app.services.comments_service.comments_crud")
    def test_get_comments_returns_comments_with_reactions(self, mock_crud, mock_reactions, mock_db):
        """Retorna comentarios con sus reacciones"""
        # Arrange
        comments = [
            {"id": "comment-1", "content": "Test 1"},
            {"id": "comment-2", "content": "Test 2"},
        ]
        mock_crud.get_comments_orm.return_value = comments
        mock_reactions.get_reactions_by_comment_orm.return_value = [{"emoji": "👍"}]
        mock_reactions.get_reaction_counts_orm.return_value = {"👍": 5}

        # Act
        result = comments_service.get_comments(
            db=mock_db, entity_id="entity-123", entity_type="table"
        )

        # Assert
        assert len(result) == 2
        assert all("reactions" in comment for comment in result)
        assert all("reaction_counts" in comment for comment in result)

    @patch("app.services.comments_service.reactions_crud")
    @patch("app.services.comments_service.comments_crud")
    def test_get_comments_with_filters(self, mock_crud, mock_reactions, mock_db):
        """Pasa filtros a CRUD"""
        # Arrange
        mock_crud.get_comments_orm.return_value = []
        mock_reactions.get_reactions_by_comment_orm.return_value = []
        mock_reactions.get_reaction_counts_orm.return_value = {}

        filters = {"include_resolved": False, "include_replies": True, "parent_id": "parent-123"}

        # Act
        comments_service.get_comments(
            db=mock_db, entity_id="entity-123", entity_type="table", filters=filters
        )

        # Assert
        call_args = mock_crud.get_comments_orm.call_args[1]
        assert call_args["include_resolved"] is False
        assert call_args["include_replies"] is True
        assert call_args["parent_id"] == "parent-123"

    @patch("app.services.comments_service.reactions_crud")
    @patch("app.services.comments_service.comments_crud")
    def test_get_comments_default_filters(self, mock_crud, mock_reactions, mock_db):
        """Usa filtros por defecto si no se especifican"""
        # Arrange
        mock_crud.get_comments_orm.return_value = []
        mock_reactions.get_reactions_by_comment_orm.return_value = []
        mock_reactions.get_reaction_counts_orm.return_value = {}

        # Act
        comments_service.get_comments(db=mock_db, entity_id="entity-123", entity_type="table")

        # Assert
        call_args = mock_crud.get_comments_orm.call_args[1]
        assert call_args["include_resolved"] is True
        assert call_args["include_replies"] is True


# ============================================================================
# TESTS: mark_as_read()
# ============================================================================


class TestMarkAsRead:
    """Tests para marcar comentarios como leídos"""

    @patch("app.services.comments_service.comments_crud")
    def test_mark_as_read_success(self, mock_crud, mock_db):
        """Marca comentarios como leídos"""
        # Arrange
        comment_ids = ["comment-1", "comment-2", "comment-3"]
        mock_crud.mark_as_read_orm.return_value = 3

        # Act
        result = comments_service.mark_as_read(
            db=mock_db, comment_ids=comment_ids, user_id="user-abc"
        )

        # Assert
        assert result == 3
        mock_crud.mark_as_read_orm.assert_called_once_with(mock_db, comment_ids, "user-abc")

    @patch("app.services.comments_service.comments_crud")
    def test_mark_as_read_empty_list(self, mock_crud, mock_db):
        """Maneja lista vacía de comment_ids"""
        # Arrange
        mock_crud.mark_as_read_orm.return_value = 0

        # Act
        result = comments_service.mark_as_read(db=mock_db, comment_ids=[], user_id="user-abc")

        # Assert
        assert result == 0


# ============================================================================
# TESTS: get_unread_count()
# ============================================================================


class TestGetUnreadCount:
    """Tests para contador de comentarios no leídos"""

    @patch("app.services.comments_service.comments_crud")
    def test_get_unread_count_returns_count(self, mock_crud, mock_db):
        """Retorna contador de no leídos"""
        # Arrange
        mock_crud.get_unread_count_orm.return_value = 5

        # Act
        result = comments_service.get_unread_count(
            db=mock_db, project_id="project-123", user_id="user-abc"
        )

        # Assert
        assert result == 5
        mock_crud.get_unread_count_orm.assert_called_once_with(mock_db, "project-123", "user-abc")

    @patch("app.services.comments_service.comments_crud")
    def test_get_unread_count_no_unread(self, mock_crud, mock_db):
        """Retorna 0 cuando no hay no leídos"""
        # Arrange
        mock_crud.get_unread_count_orm.return_value = 0

        # Act
        result = comments_service.get_unread_count(
            db=mock_db, project_id="project-123", user_id="user-abc"
        )

        # Assert
        assert result == 0


# ============================================================================
# TESTS: check_comment_permission()
# ============================================================================


class TestCheckCommentPermission:
    """Tests para verificación de permisos de comentarios"""

    @patch("app.services.comments_service.comments_crud")
    def test_check_comment_permission_edit_allowed_for_owner(self, mock_crud, mock_db):
        """Permite editar al autor del comentario"""
        # Arrange
        mock_crud.check_comment_owner_orm.return_value = True

        # Act
        result = comments_service.check_comment_permission(
            db=mock_db, comment_id="comment-123", user_id="user-abc", action="edit"
        )

        # Assert
        assert result is True
        mock_crud.check_comment_owner_orm.assert_called_once_with(
            mock_db, "comment-123", "user-abc"
        )

    @patch("app.services.comments_service.comments_crud")
    def test_check_comment_permission_delete_allowed_for_owner(self, mock_crud, mock_db):
        """Permite eliminar al autor del comentario"""
        # Arrange
        mock_crud.check_comment_owner_orm.return_value = True

        # Act
        result = comments_service.check_comment_permission(
            db=mock_db, comment_id="comment-123", user_id="user-abc", action="delete"
        )

        # Assert
        assert result is True

    @patch("app.services.comments_service.comments_crud")
    def test_check_comment_permission_edit_denied_for_non_owner(self, mock_crud, mock_db):
        """Niega editar a usuario que no es autor"""
        # Arrange
        mock_crud.check_comment_owner_orm.return_value = False

        # Act
        result = comments_service.check_comment_permission(
            db=mock_db, comment_id="comment-123", user_id="other-user", action="edit"
        )

        # Assert
        assert result is False

    @patch("app.services.comments_service.comments_crud")
    def test_check_comment_permission_delete_denied_for_non_owner(self, mock_crud, mock_db):
        """Niega eliminar a usuario que no es autor"""
        # Arrange
        mock_crud.check_comment_owner_orm.return_value = False

        # Act
        result = comments_service.check_comment_permission(
            db=mock_db, comment_id="comment-123", user_id="other-user", action="delete"
        )

        # Assert
        assert result is False

    def test_check_comment_permission_unknown_action_returns_false(self, mock_db):
        """Retorna False para acción desconocida"""
        # Arrange & Act
        result = comments_service.check_comment_permission(
            db=mock_db, comment_id="comment-123", user_id="user-abc", action="unknown_action"
        )

        # Assert
        assert result is False
