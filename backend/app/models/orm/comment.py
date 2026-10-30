"""
Modelos ORM para Comments System

Este módulo contiene los modelos para el sistema de comentarios:
- Comment: Comentarios en entidades (mappings, tables, columns, projects)
- CommentReaction: Reacciones emoji a comentarios
- CommentRead: Tracking de comentarios leídos por usuario

Características:
- Comentarios con soporte de replies (parent_id)
- Menciones a usuarios (@username)
- Estado de resolución (is_resolved)
- Soporte de encriptación para contenido
- Reacciones emoji
- Tracking de lectura
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Comment(Base):
    """
    Comentario en una entidad del proyecto.

    Soporta:
    - Comentarios en cualquier entidad (mapping, table, column, project)
    - Replies anidados (parent_id)
    - Menciones a usuarios en el contenido
    - Resolución de comentarios
    - Encriptación del contenido

    Constraint: content no puede estar vacío (TRIM(content) > 0)
    """

    __tablename__ = "comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Entidad a la que pertenece el comentario
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)  # 'mapping', 'table', 'column', 'project'

    # Relación con proyecto
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Usuario que creó el comentario
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )

    # Parent comment (para replies)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"))

    # Contenido (plaintext, nullable cuando está encriptado)
    content = Column(Text)

    # Contenido cifrado
    content_encrypted = Column(Text)
    content_nonce = Column(Text)

    # Flag de cifrado
    is_encrypted = Column(
        Boolean, default=False, server_default=text("false"), nullable=False, index=True
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    updated_at = Column(DateTime(timezone=True))

    # Estado
    is_edited = Column(Boolean, default=False, server_default=text("false"), nullable=False)
    is_resolved = Column(
        Boolean, default=False, server_default=text("false"), nullable=False, index=True
    )

    # Resolución
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at = Column(DateTime(timezone=True))

    # Menciones (array JSON de user_ids)
    mentions = Column(JSONB)  # ["uuid1", "uuid2", ...]

    # Relationships
    project = relationship("Project", back_populates="comments")
    user = relationship("User", back_populates="comments", foreign_keys=[user_id])
    resolver = relationship("User", back_populates="resolved_comments", foreign_keys=[resolved_by])
    parent_comment = relationship("Comment", remote_side=[id], backref="replies")
    reactions = relationship(
        "CommentReaction", back_populates="comment", cascade="all, delete-orphan"
    )
    reads = relationship("CommentRead", back_populates="comment", cascade="all, delete-orphan")

    # Constraints e índices
    __table_args__ = (
        # Check constraint: content no puede estar vacío (cuando no está encriptado)
        CheckConstraint(
            """
            (content IS NOT NULL AND LENGTH(TRIM(content)) > 0 AND (is_encrypted IS NULL OR is_encrypted = FALSE))
            OR
            (content_encrypted IS NOT NULL AND content_nonce IS NOT NULL AND is_encrypted = TRUE)
            """,
            name="check_comment_not_empty",
        ),
        # Índices compuestos
        Index("idx_comments_entity", "entity_id", "entity_type", "created_at"),
        Index("idx_comments_parent", "parent_id", postgresql_where=(parent_id.isnot(None))),
        Index("idx_comments_encrypted", "is_encrypted", postgresql_where=(is_encrypted == True)),
        Index("idx_comments_project_encrypted", "project_id", "is_encrypted"),
        Index(
            "idx_comments_unresolved",
            "project_id",
            "is_resolved",
            postgresql_where=(is_resolved == False),
        ),
    )

    def __repr__(self):
        preview = self.content[:50] if self.content and not self.is_encrypted else "[ENCRYPTED]"
        return f"<Comment(id={self.id}, entity_type='{self.entity_type}', preview='{preview}...')>"


class CommentReaction(Base):
    """
    Reacción emoji a un comentario.

    Un usuario solo puede reaccionar una vez con el mismo emoji
    a un comentario específico.

    Constraint UNIQUE(comment_id, user_id, emoji)
    """

    __tablename__ = "comment_reactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relaciones
    comment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Emoji unicode
    emoji = Column(String(10), nullable=False)

    # Timestamp
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    comment = relationship("Comment", back_populates="reactions")
    user = relationship("User", back_populates="comment_reactions")

    # Constraints e índices
    __table_args__ = (
        # UNIQUE: Un usuario solo puede reaccionar una vez con el mismo emoji
        Index(
            "uq_comment_reactions_comment_user_emoji", "comment_id", "user_id", "emoji", unique=True
        ),
    )

    def __repr__(self):
        return (
            f"<CommentReaction(id={self.id}, comment_id={self.comment_id}, emoji='{self.emoji}')>"
        )


class CommentRead(Base):
    """
    Tracking de comentarios leídos por usuario.

    Permite marcar comentarios como leídos para notificaciones.

    Un usuario solo puede marcar un comentario como leído una vez.
    Constraint UNIQUE(comment_id, user_id)
    """

    __tablename__ = "comment_reads"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # Relaciones
    comment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Timestamp
    read_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    # Relationships
    comment = relationship("Comment", back_populates="reads")
    user = relationship("User", back_populates="comment_reads")

    # Constraints e índices
    __table_args__ = (
        # UNIQUE: Un usuario solo puede marcar un comentario como leído una vez
        Index("uq_comment_reads_comment_user", "comment_id", "user_id", unique=True),
        Index("idx_comment_reads_user_read", "user_id", "read_at"),
    )

    def __repr__(self):
        return f"<CommentRead(id={self.id}, comment_id={self.comment_id}, user_id={self.user_id})>"
