"""
Modelo ORM para Project Metrics History

Este módulo contiene el modelo para el historial de métricas de proyectos.

Características:
- Snapshot diario de métricas por usuario
- Tracking de proyectos por estado
- Métricas de presupuesto y progreso
- Útil para dashboards y reportes
"""

from typing import Any

from sqlalchemy import DECIMAL, Column, Date, DateTime, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class ProjectMetricsHistory(Base):
    """
    Historial de métricas de proyectos por usuario.

    Almacena snapshots diarios de estadísticas de proyectos:
    - Conteo de proyectos por estado (activos, pausados, completados)
    - Métricas financieras (presupuesto total)
    - Métricas de progreso (promedio)

    Útil para generar gráficos históricos y reportes.

    Constraint UNIQUE(user_id, date) asegura un snapshot por día.
    """

    __tablename__ = "project_metrics_history"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Usuario al que pertenecen las métricas
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Fecha del snapshot
    date = Column(Date, nullable=False, server_default=func.current_date(), index=True)

    # Contadores de proyectos
    total_projects = Column(Integer, default=0, nullable=False)
    active_projects = Column(Integer, default=0, nullable=False)
    paused_projects = Column(Integer, default=0, nullable=False)
    completed_projects = Column(Integer, default=0, nullable=False)

    # Métricas financieras
    total_budget: Any = Column(DECIMAL(10, 2), default=0.00, nullable=False)

    # Métricas de progreso
    avg_progress: Any = Column(DECIMAL(5, 2), default=0.00, nullable=False)

    # Timestamp de creación
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    user = relationship("User", backref="metrics_history")

    # Índices y constraints
    __table_args__ = (
        # UNIQUE: Solo un snapshot por usuario por día
        Index("uq_metrics_user_date", "user_id", "date", unique=True),
        # Índice para consultas por rango de fechas
        Index("idx_metrics_date_range", "user_id", "date"),
    )

    def __repr__(self):
        return f"<ProjectMetricsHistory(id={self.id}, user_id={self.user_id}, date={self.date}, total={self.total_projects})>"
