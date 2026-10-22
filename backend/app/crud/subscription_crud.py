# app/database/subscription_crud.py
"""
Operaciones CRUD para las tablas de suscripciones.
Maneja las tablas SUBSCRIPTION_PLANS y SUBSCRIPTIONS.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

import stripe

logger = logging.getLogger(__name__)


# ========================================================================
# SQLALCHEMY ORM VERSIONS - Funciones con sufijo _orm
# ========================================================================


def get_subscription_plan_by_id_orm(db, plan_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene un plan de suscripción por su ID (ORM version).

    Args:
        db: SQLAlchemy Session
        plan_id: ID del plan de suscripción

    Returns:
        Dict con los datos del plan o None si no existe
    """
    from app.models.orm import SubscriptionPlan
    from app.utils.orm_helpers import model_to_dict

    try:
        plan = (
            db.query(SubscriptionPlan)
            .filter(SubscriptionPlan.id == plan_id, SubscriptionPlan.is_active == True)
            .first()
        )

        return model_to_dict(plan) if plan else None

    except Exception as e:
        logger.error(f"Error al obtener plan de suscripción {plan_id}: {str(e)}")
        return None


def get_subscription_plans_orm(db) -> list:
    """
    Obtiene todos los planes de suscripción activos (ORM version).

    Args:
        db: SQLAlchemy Session

    Returns:
        Lista de planes de suscripción
    """
    from app.models.orm import SubscriptionPlan
    from app.utils.orm_helpers import models_to_dict_list

    try:
        plans = (
            db.query(SubscriptionPlan)
            .filter(SubscriptionPlan.is_active == True)
            .order_by(SubscriptionPlan.sort_order, SubscriptionPlan.created_at)
            .all()
        )

        return models_to_dict_list(plans)

    except Exception as e:
        logger.error(f"Error al obtener planes de suscripción: {str(e)}")
        return []


def get_user_subscription_orm(db, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene la suscripción activa de un usuario para un proyecto (ORM version).

    Args:
        db: SQLAlchemy Session
        user_id: ID del usuario
        project_id: ID del proyecto

    Returns:
        Dict con los datos de la suscripción o None si no existe
    """
    from app.models.orm import Subscription, SubscriptionPlan

    try:
        result = (
            db.query(
                Subscription,
                SubscriptionPlan.name.label("plan_name"),
                SubscriptionPlan.max_projects,
                SubscriptionPlan.max_tables,
                SubscriptionPlan.max_columns_per_table,
            )
            .join(SubscriptionPlan, Subscription.plan_id == SubscriptionPlan.id)
            .filter(
                Subscription.user_id == user_id,
                Subscription.project_id == project_id,
                Subscription.status.in_(["active", "trialing"]),
            )
            .order_by(Subscription.created_at.desc())
            .first()
        )

        if not result:
            return None

        subscription, plan_name, max_projects, max_tables, max_columns_per_table = result

        # Convert subscription to dict
        from app.utils.orm_helpers import model_to_dict

        subscription_dict = model_to_dict(subscription)

        if subscription_dict is None:
            return None

        # Add plan fields
        subscription_dict["plan_name"] = plan_name
        subscription_dict["max_projects"] = max_projects
        subscription_dict["max_tables"] = max_tables
        subscription_dict["max_columns_per_table"] = max_columns_per_table

        return subscription_dict

    except Exception as e:
        logger.error(f"Error al obtener suscripción del usuario {user_id}: {str(e)}")
        return None


def get_subscription_by_stripe_id_orm(db, stripe_subscription_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene una suscripción por su ID de Stripe (ORM version).

    Args:
        db: SQLAlchemy Session
        stripe_subscription_id: ID de la suscripción en Stripe

    Returns:
        Dict con los datos de la suscripción o None si no existe
    """
    from app.models.orm import Subscription
    from app.utils.orm_helpers import model_to_dict

    try:
        subscription = (
            db.query(Subscription)
            .filter(Subscription.stripe_subscription_id == stripe_subscription_id)
            .first()
        )

        return model_to_dict(subscription) if subscription else None

    except Exception as e:
        logger.error(
            f"Error al obtener suscripción por Stripe ID {stripe_subscription_id}: {str(e)}"
        )
        return None


def create_subscription_orm(db, subscription_data: Dict[str, Any]) -> bool:
    """
    Crea una nueva suscripción en la base de datos (ORM version).

    Args:
        db: SQLAlchemy Session
        subscription_data: Datos de la suscripción

    Returns:
        True si se creó exitosamente, False en caso contrario
    """
    from app.models.orm import Subscription

    try:
        new_subscription = Subscription(
            user_id=subscription_data.get("user_id"),
            project_id=subscription_data.get("project_id"),
            stripe_customer_id=subscription_data.get("stripe_customer_id"),
            stripe_subscription_id=subscription_data.get("stripe_subscription_id"),
            plan_id=subscription_data.get("plan_id"),
            price_id=subscription_data.get("price_id"),
            status=subscription_data.get("status"),
            current_period_start=subscription_data.get("current_period_start"),
            current_period_end=subscription_data.get("current_period_end"),
            cancel_at_period_end=subscription_data.get("cancel_at_period_end", False),
            cancel_at=subscription_data.get("cancel_at"),
            trial_end=subscription_data.get("trial_end"),
            currency=subscription_data.get("currency"),
            unit_amount=subscription_data.get("unit_amount"),
            quantity=subscription_data.get("quantity", 1),
            default_payment_method=subscription_data.get("default_payment_method"),
            latest_invoice_id=subscription_data.get("latest_invoice_id"),
        )

        db.add(new_subscription)
        db.commit()

        logger.info(f"Suscripción creada: {subscription_data.get('stripe_subscription_id')}")
        return True

    except Exception as e:
        logger.error(f"Error al crear suscripción: {str(e)}")
        db.rollback()
        return False


def update_subscription_orm(db, stripe_subscription_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Actualiza una suscripción existente (ORM version).

    Args:
        db: SQLAlchemy Session
        stripe_subscription_id: ID de la suscripción en Stripe
        update_data: Datos a actualizar

    Returns:
        True si se actualizó exitosamente, False en caso contrario
    """
    from datetime import datetime

    from app.models.orm import Subscription

    try:
        logger.info(f"Actualizando suscripción {stripe_subscription_id} con datos: {update_data}")

        # Remove stripe_subscription_id from update data if present
        update_dict = {k: v for k, v in update_data.items() if k != "stripe_subscription_id"}

        if not update_dict:
            return True  # No hay nada que actualizar

        # Add updated_at
        update_dict["updated_at"] = datetime.now()

        # Execute update
        result = (
            db.query(Subscription)
            .filter(Subscription.stripe_subscription_id == stripe_subscription_id)
            .update(update_dict, synchronize_session="fetch")
        )

        db.commit()

        if result > 0:
            logger.info(f"Suscripción actualizada: {stripe_subscription_id}")
            return True
        else:
            logger.warning(f"No se encontró suscripción para actualizar: {stripe_subscription_id}")
            return False

    except Exception as e:
        logger.error(f"Error al actualizar suscripción {stripe_subscription_id}: {str(e)}")
        logger.error(f"Tipo de error: {type(e).__name__}")

        if hasattr(e, "orig"):
            logger.error(f"Error original: {e.orig}")

        db.rollback()
        return False


def get_customer_by_stripe_id_orm(db, stripe_customer_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene información del usuario por su ID de cliente de Stripe (ORM version).
    Primero intenta obtener desde metadatos del cliente de Stripe,
    luego como fallback busca en la tabla de suscripciones.

    Args:
        db: SQLAlchemy Session
        stripe_customer_id: ID del cliente en Stripe

    Returns:
        Dict con los datos del usuario o None si no existe
    """
    from app.models.orm import Subscription, User

    try:
        # Primero intentar obtener el user_id desde los metadatos del cliente de Stripe
        try:
            customer = stripe.Customer.retrieve(stripe_customer_id)
            metadata = customer.metadata if customer.metadata else {}
            user_id = metadata.get("user_id")

            if user_id:
                # Obtener información del usuario desde la base de datos
                user = (
                    db.query(User.id.label("user_id"), User.email, User.username)
                    .filter(User.id == user_id)
                    .first()
                )

                if user:
                    return {
                        "user_id": str(user.user_id),
                        "email": user.email,
                        "username": user.username,
                    }
        except Exception as e:
            logger.warning(f"No se pudo obtener user_id desde metadatos de Stripe: {str(e)}")

        # Fallback: buscar en la tabla de suscripciones (método anterior)
        result = (
            db.query(Subscription.user_id, Subscription.project_id, User.email, User.username)
            .join(User, Subscription.user_id == User.id)
            .filter(Subscription.stripe_customer_id == stripe_customer_id)
            .first()
        )

        if result:
            return {
                "user_id": str(result.user_id),
                "project_id": str(result.project_id),
                "email": result.email,
                "username": result.username,
            }

        return None

    except Exception as e:
        logger.error(f"Error al obtener cliente por Stripe ID {stripe_customer_id}: {str(e)}")
        return None


def get_plan_by_price_id_orm(db, price_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene plan de suscripción por price_id de Stripe (ORM version)

    Busca tanto en stripe_price_id_monthly como stripe_price_id_yearly

    Args:
        db: SQLAlchemy session
        price_id: Price ID de Stripe

    Returns:
        Dict con datos del plan o None si no existe
    """
    import logging

    from sqlalchemy import or_

    from app.models.orm.subscription import SubscriptionPlan
    from app.utils.orm_helpers import model_to_dict

    logger = logging.getLogger(__name__)

    try:
        plan = (
            db.query(SubscriptionPlan)
            .filter(
                or_(
                    SubscriptionPlan.stripe_price_id_monthly == price_id,
                    SubscriptionPlan.stripe_price_id_yearly == price_id,
                ),
                SubscriptionPlan.is_active == True,
            )
            .first()
        )

        if not plan:
            return None

        return model_to_dict(plan)

    except Exception as e:
        logger.error(f"Error getting plan by price_id {price_id}: {e}")
        raise
