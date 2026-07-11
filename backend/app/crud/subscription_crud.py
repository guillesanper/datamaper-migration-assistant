# app/database/subscription_crud.py
"""
Operaciones CRUD para las tablas de suscripciones.
Maneja las tablas SUBSCRIPTION_PLANS y SUBSCRIPTIONS.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import stripe
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


def get_subscription_plan_by_id(db, plan_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene un plan de suscripción por su ID.

    Args:
        db: Conexión a la base de datos
        plan_id: ID del plan de suscripción

    Returns:
        Dict con los datos del plan o None si no existe
    """
    try:
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, name, description, price_monthly, price_yearly, currency,
                       features, max_projects, max_tables, max_columns_per_table,
                       stripe_product_id, stripe_price_id_monthly, stripe_price_id_yearly,
                       stripe_secret_key, stripe_publishable_key, stripe_webhook_secret,
                       is_active, sort_order, created_at, updated_at
                FROM subscription_plans
                WHERE id = %s AND is_active = true
                """,
                (plan_id,),
            )
            result = cursor.fetchone()
            return dict(result) if result else None

    except Exception as e:
        logger.error(f"Error al obtener plan de suscripción {plan_id}: {str(e)}")
        return None


def get_subscription_plans(db) -> list:
    """
    Obtiene todos los planes de suscripción activos.

    Args:
        db: Conexión a la base de datos

    Returns:
        Lista de planes de suscripción
    """
    try:
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT id, name, description, price_monthly, price_yearly, currency,
                       features, max_projects, max_tables, max_columns_per_table,
                       stripe_product_id, stripe_price_id_monthly, stripe_price_id_yearly,
                       stripe_secret_key, stripe_publishable_key, stripe_webhook_secret,
                       is_active, sort_order, created_at, updated_at
                FROM subscription_plans
                WHERE is_active = true
                ORDER BY sort_order, created_at
                """)
            results = cursor.fetchall()
            return [dict(row) for row in results]

    except Exception as e:
        logger.error(f"Error al obtener planes de suscripción: {str(e)}")
        return []


def get_user_subscription(db, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene la suscripción activa de un usuario para un proyecto.

    Args:
        db: Conexión a la base de datos
        user_id: ID del usuario
        project_id: ID del proyecto

    Returns:
        Dict con los datos de la suscripción o None si no existe
    """
    try:
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT s.*, sp.name as plan_name, sp.max_projects, sp.max_tables, sp.max_columns_per_table
                FROM subscriptions s
                JOIN subscription_plans sp ON s.plan_id = sp.id
                WHERE s.user_id = %s AND s.project_id = %s
                AND s.status IN ('active', 'trialing')
                ORDER BY s.created_at DESC
                LIMIT 1
                """,
                (user_id, project_id),
            )
            result = cursor.fetchone()
            return dict(result) if result else None

    except Exception as e:
        logger.error(f"Error al obtener suscripción del usuario {user_id}: {str(e)}")
        return None


def get_subscription_by_stripe_id(db, stripe_subscription_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene una suscripción por su ID de Stripe.

    Args:
        db: Conexión a la base de datos
        stripe_subscription_id: ID de la suscripción en Stripe

    Returns:
        Dict con los datos de la suscripción o None si no existe
    """
    try:
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT * FROM subscriptions
                WHERE stripe_subscription_id = %s
                """,
                (stripe_subscription_id,),
            )
            result = cursor.fetchone()
            return dict(result) if result else None

    except Exception as e:
        logger.error(
            f"Error al obtener suscripción por Stripe ID {stripe_subscription_id}: {str(e)}"
        )
        return None


def create_subscription(db, subscription_data: Dict[str, Any]) -> bool:
    """
    Crea una nueva suscripción en la base de datos.

    Args:
        db: Conexión a la base de datos
        subscription_data: Datos de la suscripción

    Returns:
        True si se creó exitosamente, False en caso contrario
    """
    try:
        with db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO subscriptions (
                    user_id, project_id, stripe_customer_id, stripe_subscription_id,
                    plan_id, price_id, status, current_period_start, current_period_end,
                    cancel_at_period_end, cancel_at, trial_end, currency, unit_amount,
                    quantity, default_payment_method, latest_invoice_id
                ) VALUES (
                    %(user_id)s, %(project_id)s, %(stripe_customer_id)s, %(stripe_subscription_id)s,
                    %(plan_id)s, %(price_id)s, %(status)s, %(current_period_start)s, %(current_period_end)s,
                    %(cancel_at_period_end)s, %(cancel_at)s, %(trial_end)s, %(currency)s, %(unit_amount)s,
                    %(quantity)s, %(default_payment_method)s, %(latest_invoice_id)s
                )
                """,
                subscription_data,
            )
            db.commit()
            logger.info(f"Suscripción creada: {subscription_data.get('stripe_subscription_id')}")
            return True

    except Exception as e:
        logger.error(f"Error al crear suscripción: {str(e)}")
        db.rollback()
        return False


def update_subscription(db, stripe_subscription_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Actualiza una suscripción existente.

    Args:
        db: Conexión a la base de datos
        stripe_subscription_id: ID de la suscripción en Stripe
        update_data: Datos a actualizar

    Returns:
        True si se actualizó exitosamente, False en caso contrario
    """
    try:
        print(f"DEBUG: Actualizando suscripción {stripe_subscription_id} con datos: {update_data}")
        logger.info(f"Actualizando suscripción {stripe_subscription_id} con datos: {update_data}")

        # Construir la consulta dinámicamente basada en los campos a actualizar
        set_clauses = []
        values = []

        for key, value in update_data.items():
            if key != "stripe_subscription_id":  # No actualizar el ID
                print(f"DEBUG: Agregando campo {key} = {value} (tipo: {type(value)})")
                logger.info(f"Agregando campo {key} = {value} (tipo: {type(value)})")
                set_clauses.append(f"{key} = %s")
                values.append(value)

        if not set_clauses:
            return True  # No hay nada que actualizar

        # Agregar updated_at
        set_clauses.append("updated_at = %s")
        values.append(datetime.now())

        # Agregar el ID para la cláusula WHERE
        values.append(stripe_subscription_id)

        query = f"""
            UPDATE subscriptions
            SET {', '.join(set_clauses)}
            WHERE stripe_subscription_id = %s
        """

        print(f"DEBUG: Query SQL: {query}")
        print(f"DEBUG: Valores: {values}")
        logger.info(f"Query SQL: {query}")
        logger.info(f"Valores: {values}")

        with db.cursor() as cursor:
            cursor.execute(query, values)
            db.commit()

            if cursor.rowcount > 0:
                logger.info(f"Suscripción actualizada: {stripe_subscription_id}")
                return True
            else:
                logger.warning(
                    f"No se encontró suscripción para actualizar: {stripe_subscription_id}"
                )
                return False

    except Exception as e:
        print(f"DEBUG ERROR: Error al actualizar suscripción {stripe_subscription_id}: {str(e)}")
        print(f"DEBUG ERROR: Tipo de error: {type(e).__name__}")
        print(f"DEBUG ERROR: Query que falló: {query if 'query' in locals() else 'No query'}")
        print(
            f"DEBUG ERROR: Valores que fallaron: {values if 'values' in locals() else 'No values'}"
        )

        # Información adicional del error de PostgreSQL
        if hasattr(e, "pgcode"):
            print(f"DEBUG ERROR: PostgreSQL error code: {e.pgcode}")
        if hasattr(e, "pgerror"):
            print(f"DEBUG ERROR: PostgreSQL error message: {e.pgerror}")
        if hasattr(e, "diag"):
            print(f"DEBUG ERROR: PostgreSQL diagnostic: {e.diag}")

        logger.error(f"Error al actualizar suscripción {stripe_subscription_id}: {str(e)}")
        logger.error(f"Tipo de error: {type(e).__name__}")
        logger.error(f"Query que falló: {query if 'query' in locals() else 'No query'}")
        logger.error(f"Valores que fallaron: {values if 'values' in locals() else 'No values'}")

        if hasattr(e, "pgcode"):
            logger.error(f"PostgreSQL error code: {e.pgcode}")
        if hasattr(e, "pgerror"):
            logger.error(f"PostgreSQL error message: {e.pgerror}")

        db.rollback()
        return False


def get_customer_by_stripe_id(db, stripe_customer_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene información del usuario por su ID de cliente de Stripe.
    Primero intenta obtener desde metadatos del cliente de Stripe,
    luego como fallback busca en la tabla de suscripciones.

    Args:
        db: Conexión a la base de datos
        stripe_customer_id: ID del cliente en Stripe

    Returns:
        Dict con los datos del usuario o None si no existe
    """
    try:
        # Primero intentar obtener el user_id desde los metadatos del cliente de Stripe
        try:
            customer = stripe.Customer.retrieve(stripe_customer_id)
            metadata = customer.metadata if customer.metadata else {}
            user_id = metadata.get("user_id")

            if user_id:
                # Obtener información del usuario desde la base de datos
                with db.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        """
                        SELECT id as user_id, email, username
                        FROM users
                        WHERE id = %s
                        """,
                        (user_id,),
                    )
                    result = cursor.fetchone()
                    if result:
                        return dict(result)
        except Exception as e:
            logger.warning(f"No se pudo obtener user_id desde metadatos de Stripe: {str(e)}")

        # Fallback: buscar en la tabla de suscripciones (método anterior)
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT s.user_id, s.project_id, u.email, u.username
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.stripe_customer_id = %s
                LIMIT 1
                """,
                (stripe_customer_id,),
            )
            result = cursor.fetchone()
            return dict(result) if result else None

    except Exception as e:
        logger.error(f"Error al obtener cliente por Stripe ID {stripe_customer_id}: {str(e)}")
        return None


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
