"""
Modelos ORM para Subscripciones y Planes

Este módulo contiene los modelos para el sistema de suscripciones:
- SubscriptionPlan: Planes de suscripción disponibles (free, pro, enterprise)
- Subscription: Suscripciones activas de usuarios a proyectos

Características:
- Integración con Stripe (customer_id, subscription_id, product_id, price_id)
- Precios mensuales y anuales
- Features en JSONB
- Límites por plan (max_projects, max_tables, etc.)
- Estados de suscripción (active, trialing, canceled, etc.)
"""

from decimal import Decimal
from typing import Any

from sqlalchemy import DECIMAL, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class SubscriptionPlan(Base):
    """
    Planes de suscripción disponibles en la plataforma.

    Ejemplos: 'free', 'pro', 'enterprise'

    Contiene configuración de Stripe (product_id, price_id) y límites
    funcionales (max_projects, max_tables, max_columns_per_table).

    Las claves de API de Stripe se almacenan por plan para soporte multi-tenant.
    """

    __tablename__ = "subscription_plans"

    id = Column(String(50), primary_key=True)  # 'free', 'pro', 'enterprise'

    # Información del plan
    name = Column(String(100), nullable=False)
    description = Column(Text)

    # Precios
    price_monthly: Any = Column(DECIMAL(10, 2))
    price_yearly: Any = Column(DECIMAL(10, 2))
    currency = Column(String(3), default="USD", nullable=False)

    # Features en JSON
    features = Column(JSONB)  # {"feature1": true, "feature2": "unlimited", ...}

    # Límites funcionales
    max_projects = Column(Integer)
    max_tables = Column(Integer)
    max_columns_per_table = Column(Integer)

    # Integración con Stripe
    stripe_product_id = Column(String(255))
    stripe_price_id_monthly = Column(String(255))
    stripe_price_id_yearly = Column(String(255))
    stripe_secret_key = Column(String(500))
    stripe_publishable_key = Column(String(500))
    stripe_webhook_secret = Column(String(500))

    # Estado
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    sort_order = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    subscriptions = relationship("Subscription", back_populates="plan")

    # Índices
    __table_args__ = (Index("idx_subscription_plans_active", "is_active", "sort_order"),)

    def __repr__(self):
        return f"<SubscriptionPlan(id='{self.id}', name='{self.name}')>"


class Subscription(Base):
    """
    Suscripción de un usuario a un plan para un proyecto específico.

    Gestiona el ciclo de vida de la suscripción:
    - Estados: active, trialing, canceled, past_due, etc.
    - Períodos: current_period_start/end
    - Cancelación: cancel_at_period_end, cancel_at
    - Trial: trial_end

    Integrada con Stripe webhooks para sincronización automática.
    """

    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())

    # Relaciones
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id = Column(String(50), ForeignKey("subscription_plans.id"), nullable=False, index=True)

    # Stripe IDs
    stripe_customer_id = Column(String(255))
    stripe_subscription_id = Column(String(255), unique=True, index=True)
    price_id = Column(String(255))

    # Estado de la suscripción
    status = Column(
        String(50)
    )  # 'active', 'trialing', 'canceled', 'past_due', 'unpaid', 'incomplete'

    # Períodos
    current_period_start = Column(DateTime(timezone=True))
    current_period_end = Column(DateTime(timezone=True))

    # Cancelación
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    cancel_at = Column(DateTime(timezone=True))

    # Trial
    trial_end = Column(DateTime(timezone=True))

    # Información de pago
    currency = Column(String(3))
    unit_amount = Column(Integer)  # En centavos
    quantity = Column(Integer, default=1, nullable=False)
    default_payment_method = Column(String(255))
    latest_invoice_id = Column(String(255))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    project = relationship("Project", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")

    # Índices
    __table_args__ = (
        Index("idx_subscriptions_user_project", "user_id", "project_id"),
        Index(
            "idx_subscriptions_status",
            "status",
            postgresql_where=(status.in_(["active", "trialing"])),
        ),
        Index("idx_subscriptions_trial", "trial_end", postgresql_where=(trial_end.isnot(None))),
    )

    def __repr__(self):
        return f"<Subscription(id={self.id}, user_id={self.user_id}, plan_id='{self.plan_id}', status='{self.status}')>"
