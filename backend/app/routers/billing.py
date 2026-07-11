# app/routers/billing.py
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import text

from app.crud.subscription_crud import (
    get_subscription_plan_by_id_orm,
    get_user_subscription_orm,
    update_subscription_orm,
)
from app.database.session import get_db_session
from app.routers.dependencies import get_current_user
from app.services.stripe_service import StripeConfig, stripe_service
from app.utils.error_codes import ErrorCode, make_error
from config import make_translator

router = APIRouter()
logger = logging.getLogger(__name__)

# Stripe config
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID_MONTHLY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


def utcnow():
    return datetime.now(timezone.utc)


@router.post("/billing/upgradeSubscription")
async def upgrade_subscription(
    request: Request,
    project_id: str = Form(...),
    plan_id: str = Form(default="pro"),
    billing_cycle: str = Form(default="monthly"),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Endpoint llamado desde el botón 'Switch to Pro'.
    Reglas:
      - Solo el owner del proyecto puede hacerlo.
      - El proyecto debe estar en plan 'free'.
      - Aquí se crea la Checkout Session de Stripe usando plan_id.
      - NO marcamos el plan en BD aquí: se hará en el webhook al confirmar.
    """
    # 1) Validar que el proyecto existe y eres owner
    proj = (
        db.execute(
            text("SELECT id, owner_id, name FROM projects WHERE id = :pid"),
            {"pid": project_id},
        )
        .mappings()
        .fetchone()
    )
    if not proj:
        raise HTTPException(status_code=404, detail=make_error(ErrorCode.PROJECT_NOT_FOUND))
    if str(proj["owner_id"]) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail=make_error(ErrorCode.BILLING_NOT_OWNER))

    # 2) Verificar plan actual (si ya tiene suscripción activa/trialing → error)
    already_pro = db.execute(
        text("""
        SELECT 1
          FROM subscriptions
         WHERE project_id = :pid
           AND LOWER(status) IN ('active','trialing')
         LIMIT 1
        """),
        {"pid": project_id},
    ).fetchone()
    if already_pro:
        r = RedirectResponse(url=f"/billing?project_id={project_id}", status_code=303)
        r.set_cookie(
            "flash", "El proyecto ya está en PRO o tiene una suscripción activa.", max_age=4
        )
        return r

    user_email = current_user.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail=make_error(ErrorCode.BILLING_INVALID_EMAIL))

    # Validar formato de email antes de enviarlo a Stripe
    from email_validator import EmailNotValidError, validate_email

    try:
        valid = validate_email(user_email, check_deliverability=False)
        user_email = valid.email  # normalizado
    except EmailNotValidError as e:
        r = RedirectResponse(url=f"/billing?project_id={project_id}", status_code=303)
        r.set_cookie(
            "flash",
            f"Email inválido: {str(e)}. Por favor actualiza tu perfil con un email válido.",
            max_age=8,
        )
        return r

    # 3) Crear Checkout Session en Stripe
    # --------------------------------------------------------
    # Obtener plan usando CRUD ORM
    plan = get_subscription_plan_by_id_orm(db, plan_id)

    if not plan:
        r = RedirectResponse(url=f"/billing?project_id={project_id}", status_code=303)
        r.set_cookie("flash", f"Plan {plan_id} no disponible en este momento.", max_age=4)
        return r

    # Validar que el plan está activo
    if not plan.get("is_active", True):
        r = RedirectResponse(url=f"/billing?project_id={project_id}", status_code=303)
        r.set_cookie("flash", f"Plan {plan_id} no está activo.", max_age=4)
        return r

    # Obtener price_id según el ciclo de facturación
    if billing_cycle == "yearly":
        price_id = plan.get("stripe_price_id_yearly")
    else:
        price_id = plan.get("stripe_price_id_monthly")
        billing_cycle = "monthly"  # Normalizar valor

    if not price_id:
        r = RedirectResponse(url=f"/billing?project_id={project_id}", status_code=303)
        r.set_cookie(
            "flash", f"Configuración de precios incompleta para {billing_cycle}.", max_age=4
        )
        return r

    # Crear o obtener cliente de Stripe
    user_name = (
        current_user.get("name")
        or current_user.get("full_name")
        or current_user.get("username")
        or user_email.split("@")[0]
    ).strip()

    # Obtener configuración de Stripe para el plan
    stripe_config = StripeConfig.get_stripe_config(plan_id)
    if not stripe_config:
        r = RedirectResponse(url=f"/billing?project_id={project_id}", status_code=303)
        r.set_cookie(
            "flash", f"Configuración de Stripe no disponible para el plan {plan_id}.", max_age=4
        )
        return r

    # Crear cliente Stripe independiente para este plan
    customer = stripe_service.create_or_get_customer(
        user_email=user_email,
        user_name=user_name,
        user_id=str(current_user["id"]),
    )

    if not customer:
        r = RedirectResponse(url=f"/billing?project_id={project_id}", status_code=303)
        r.set_cookie("flash", "Error al configurar el cliente en Stripe.", max_age=4)
        return r

    # Crear sesión de checkout usando el cliente específico
    session = await stripe_service.create_checkout_session(
        user_id=str(current_user["id"]),
        project_id=project_id,
        plan_id=plan_id,
        user_email=user_email,
        billing_cycle=billing_cycle,
        success_url=f"{BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{BASE_URL}/billing?project_id={project_id}",
    )

    checkout_url = session.url if session else None

    # 4) Si Stripe aún no está integrado, mostramos aviso
    if not checkout_url:
        r = RedirectResponse(url=f"/billing?project_id={project_id}", status_code=303)
        r.set_cookie("flash", "Integración de Stripe pendiente: validaciones correctas.", max_age=4)
        return r

    # 5) Redirigir a Stripe Checkout
    return RedirectResponse(url=checkout_url, status_code=303)


@router.post("/billing/cancel_subscription")
def cancel_subscription(
    request: Request,
    project_id: str = Form(...),
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """
    Cancela la suscripción PRO de un proyecto (downgrade a FREE) usando configuración dinámica de Stripe.
    Reglas:
      - Solo el owner del proyecto puede cancelar.
      - Debe existir una suscripción activa/trialing en 'subscriptions'.
      - Usa configuración dinámica de Stripe basada en el plan_id.
      - NO modificamos la BD aquí; el webhook de Stripe actualizará 'subscriptions'
        a 'canceled' y fechas cuando corresponda.
    """
    _ = make_translator(request)

    # 1) Validar proyecto y ownership
    proj = (
        db.execute(
            text("SELECT id, owner_id, name FROM projects WHERE id = :pid"),
            {"pid": project_id},
        )
        .mappings()
        .fetchone()
    )
    if not proj:
        raise HTTPException(status_code=404, detail=make_error(ErrorCode.PROJECT_NOT_FOUND))
    if str(proj["owner_id"]) != str(current_user["id"]):
        raise HTTPException(
            status_code=403, detail=make_error(ErrorCode.BILLING_NOT_OWNER)
        )

    # 2) Buscar suscripción activa/trialing usando CRUD ORM
    sub = get_user_subscription_orm(db, current_user["id"], project_id)

    if not sub:
        r = RedirectResponse(url="/billing/active", status_code=303)
        r.set_cookie("flash", "No hay suscripción activa para este proyecto.", max_age=5)
        return r

    stripe_sub_id = (sub.get("stripe_subscription_id") or "").strip()
    plan_id = sub.get("plan_id")

    # 3) Configurar Stripe dinámicamente basado en el plan
    # -------------------------------------------------------------------------
    try:
        if not plan_id:
            r = RedirectResponse(url="/billing/active", status_code=303)
            r.set_cookie("flash", "Suscripción no tiene plan_id asociado.", max_age=5)
            return r

        # Obtener configuración de Stripe para el plan
        plan = get_subscription_plan_by_id_orm(db, plan_id)
        if not plan:
            r = RedirectResponse(url="/billing/active", status_code=303)
            r.set_cookie(
                "flash", f"No se encontró configuración para el plan {plan_id}.", max_age=5
            )
            return r

        # Obtener configuración de Stripe para el plan
        stripe_config = StripeConfig.get_stripe_config(plan_id)
        if not stripe_config:
            r = RedirectResponse(url="/billing/active", status_code=303)
            r.set_cookie(
                "flash", f"Configuración de Stripe no disponible para el plan {plan_id}.", max_age=5
            )
            return r

        # Crear cliente Stripe independiente para este plan
        stripe_client = StripeConfig.get_stripe_client(stripe_config["secret_key"])

        if not stripe_sub_id:
            # No hay stripe_subscription_id en la BD
            requested = False
            logger.warning(f"Suscripción sin stripe_subscription_id: {sub['id']}")
        else:
            # Cancelar suscripción usando el cliente específico
            try:
                # Primero obtener current_period_end de la base de datos local (más confiable)
                current_period_end = None
                local_subscription = None
                current_period_end_dt = None

                try:
                    local_subscription = get_user_subscription_orm(
                        db, current_user["id"], project_id
                    )
                    if local_subscription and local_subscription.get("current_period_end"):
                        # Ya es un datetime, no necesita conversión
                        current_period_end_dt = local_subscription["current_period_end"]
                        # Convertir a timestamp para logging
                        current_period_end = (
                            int(current_period_end_dt.timestamp())
                            if current_period_end_dt
                            else None
                        )
                        logger.info(
                            f"Current period end obtenido de BD local: {current_period_end_dt} (timestamp: {current_period_end})"
                        )
                    else:
                        logger.warning("No se encontró current_period_end en la BD local")
                except Exception as e:
                    logger.error(f"Error obteniendo current_period_end de BD local: {str(e)}")

                # Si no se obtuvo de BD local, intentar de Stripe
                if current_period_end is None:
                    try:
                        current_subscription = stripe_client.Subscription.retrieve(stripe_sub_id)
                        current_period_end = getattr(
                            current_subscription, "current_period_end", None
                        )
                        logger.info(f"Current period end obtenido de Stripe: {current_period_end}")
                    except Exception as e:
                        logger.error(f"Error obteniendo suscripción de Stripe: {str(e)}")
                        current_period_end = None

                # Cancelar al final del período actual (más amigable para el usuario)
                subscription = stripe_client.Subscription.modify(
                    stripe_sub_id, cancel_at_period_end=True
                )

                # Si no obtuvimos current_period_end antes, intentar de la suscripción modificada
                if current_period_end is None:
                    current_period_end = getattr(subscription, "current_period_end", None)
                    logger.info(
                        f"Current period end de suscripción programada para cancelar: {current_period_end}"
                    )

                if current_period_end is None:
                    logger.warning("No se pudo obtener current_period_end de ninguna fuente")

                if subscription:
                    requested = True
                    logger.info(
                        f"Suscripción {stripe_sub_id} cancelada exitosamente para plan {plan_id}"
                    )

                    # Actualizar la suscripción en la base de datos para reflejar la cancelación
                    try:
                        from datetime import datetime

                        # Preparar period_end_dt para la base de datos
                        period_end_dt = None
                        if current_period_end_dt:
                            # Si obtuvimos de BD local, ya tenemos el datetime
                            period_end_dt = current_period_end_dt
                            logger.info(f"Usando period_end_dt de BD local: {period_end_dt}")
                        elif current_period_end:
                            try:
                                # Si obtuvimos de Stripe, convertir timestamp a datetime
                                period_end_dt = datetime.fromtimestamp(current_period_end)
                                logger.info(
                                    f"Period end convertido de Stripe timestamp: {period_end_dt}"
                                )
                            except (ValueError, TypeError, OSError) as e:
                                logger.error(
                                    f"Error convirtiendo current_period_end {current_period_end}: {str(e)}"
                                )
                                period_end_dt = None

                        update_data = {
                            "status": "canceled",
                            "cancel_at": datetime.now(),
                            "current_period_end": period_end_dt,  # Mantener hasta cuándo tiene beneficios
                        }

                        success = update_subscription_orm(db, stripe_sub_id, update_data)
                        if success:
                            logger.info(
                                f"Suscripción {stripe_sub_id} actualizada en BD como cancelada"
                            )
                        else:
                            logger.warning(
                                f"No se pudo actualizar la suscripción {stripe_sub_id} en BD"
                            )

                    except Exception as db_error:
                        logger.error(f"Error actualizando suscripción en BD: {str(db_error)}")

                else:
                    requested = False
                    logger.error(
                        f"Error al cancelar suscripción {stripe_sub_id} para plan {plan_id}"
                    )
            except stripe.StripeError as e:  # type: ignore[attr-defined]
                requested = False
                logger.error(f"Error de Stripe al cancelar suscripción {stripe_sub_id}: {str(e)}")
                r = RedirectResponse(url="/billing/active", status_code=303)
                r.set_cookie("flash", f"Error al cancelar suscripción: {str(e)}", max_age=6)
                return r

    except Exception as e:
        logger.error(f"Error inesperado al cancelar suscripción: {str(e)}")
        r = RedirectResponse(url="/billing/active", status_code=303)
        r.set_cookie("flash", f"Error al solicitar la cancelación: {str(e)}", max_age=6)
        return r

    # 4) Respuesta (feedback por flash)
    ok_msg = "Suscripción programada para cancelar al final del período actual. Mantienes acceso completo hasta entonces."
    if not stripe_sub_id:
        ok_msg = (
            "Solicitud de cancelación enviada, pero no se encontró 'stripe_subscription_id' en la BD. "
            "Revisa la configuración antes de producción."
        )

    r = RedirectResponse(url="/billing/active", status_code=303)
    if not requested:
        r.set_cookie("flash", "No se pudo procesar la cancelación. Contacta soporte.", max_age=6)
    else:
        r.set_cookie("flash_success", ok_msg, max_age=6)
    return r


@router.get("/billing/success")
async def billing_success(
    request: Request,
    session_id: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    """
    Página de éxito después del checkout de Stripe.
    Muestra información de la suscripción creada y activa la suscripción como respaldo.
    """
    if not session_id:
        return RedirectResponse(url="/billing", status_code=303)

    try:
        # Obtener información de la sesión de checkout
        session = stripe.checkout.Session.retrieve(session_id)

        if session.payment_status == "paid":
            # Procesar la activación de la suscripción como respaldo al webhook
            try:
                # Obtener la suscripción de Stripe
                if session.subscription:
                    subscription = stripe.Subscription.retrieve(str(session.subscription))

                    # Procesar la suscripción usando el mismo método que el webhook
                    success = await stripe_service.update_subscription_in_db(
                        subscription, (session.metadata or {}).get("project_id")
                    )

                    if success:
                        logger.info(
                            f"Suscripción activada exitosamente desde /billing/success: {subscription.id}"
                        )
                        message = (
                            "¡Suscripción activada exitosamente! Tu plan PRO ya está disponible."
                        )
                    else:
                        logger.error(
                            f"Error al activar suscripción desde /billing/success: {subscription.id}"
                        )
                        message = "Pago procesado, pero hubo un problema al activar la suscripción. Contacta soporte."
                else:
                    logger.warning(f"Sesión de checkout sin suscripción: {session_id}")
                    message = "Pago procesado, pero no se encontró información de suscripción. Contacta soporte."

            except Exception as e:
                logger.error(f"Error al procesar suscripción en /billing/success: {str(e)}")
                message = "¡Pago exitoso! La suscripción se activará en unos minutos."

            success = True
        else:
            message = "El pago está siendo procesado. Te notificaremos cuando esté completo."
            success = False

    except Exception as e:
        logger.error(f"Error al obtener sesión de checkout: {str(e)}")
        message = "Hubo un problema al verificar tu pago. Contacta soporte si no ves tu suscripción activa."
        success = False

    r = RedirectResponse(url="/billing", status_code=303)
    if success:
        r.set_cookie("flash_success", message, max_age=8)
    else:
        r.set_cookie("flash", message, max_age=8)
    return r


@router.post("/billing/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    plan_id: Optional[str] = None,
):
    """
    Endpoint para recibir webhooks de Stripe con configuración dinámica por plan
    """
    try:
        payload = await request.body()

        if not stripe_signature:
            raise HTTPException(status_code=400, detail=make_error(ErrorCode.BILLING_MISSING_SIG))

        # Procesar webhook con configuración dinámica
        success = await stripe_service.handle_webhook(payload, stripe_signature, plan_id)

        if not success:
            raise HTTPException(status_code=400, detail=make_error(ErrorCode.BILLING_WEBHOOK_ERROR))

        return {"status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en webhook de Stripe: {e}")
        raise HTTPException(status_code=500, detail=make_error(ErrorCode.INTERNAL_ERROR))


async def handle_checkout_completed(session):
    """
    Maneja el evento checkout.session.completed.
    Se ejecuta cuando un usuario completa el pago.
    """
    try:
        logger.info(f"Checkout completado: {session['id']}")

        # Si es una suscripción, la información se manejará en subscription.created
        if session.get("mode") == "subscription":
            logger.info("Checkout de suscripción completado, esperando evento de suscripción")
            return

    except Exception as e:
        logger.error(f"Error al manejar checkout completado: {str(e)}")


async def handle_subscription_created(subscription):
    """
    Maneja el evento customer.subscription.created.
    Crea la suscripción en la base de datos.
    """
    try:
        logger.info(f"Suscripción creada: {subscription['id']}")

        # Actualizar la base de datos
        success = await stripe_service.update_subscription_in_db(subscription)

        if success:
            logger.info(f"Suscripción {subscription['id']} guardada en BD")
        else:
            logger.error(f"Error al guardar suscripción {subscription['id']} en BD")

    except Exception as e:
        logger.error(f"Error al manejar suscripción creada: {str(e)}")


async def handle_subscription_updated(subscription):
    """
    Maneja el evento customer.subscription.updated.
    Actualiza la suscripción en la base de datos.
    """
    try:
        logger.info(f"Suscripción actualizada: {subscription['id']}")

        # Actualizar la base de datos
        success = await stripe_service.update_subscription_in_db(subscription)

        if success:
            logger.info(f"Suscripción {subscription['id']} actualizada en BD")
        else:
            logger.error(f"Error al actualizar suscripción {subscription['id']} en BD")

    except Exception as e:
        logger.error(f"Error al manejar suscripción actualizada: {str(e)}")


async def handle_subscription_deleted(subscription):
    """
    Maneja el evento customer.subscription.deleted.
    Marca la suscripción como cancelada en la base de datos.
    """
    try:
        logger.info(f"Suscripción eliminada: {subscription['id']}")

        # Actualizar la base de datos
        success = await stripe_service.update_subscription_in_db(subscription)

        if success:
            logger.info(f"Suscripción {subscription['id']} marcada como cancelada en BD")
        else:
            logger.error(f"Error al cancelar suscripción {subscription['id']} en BD")

    except Exception as e:
        logger.error(f"Error al manejar suscripción eliminada: {str(e)}")


async def handle_payment_failed(invoice):
    """
    Maneja el evento invoice.payment_failed.
    Registra el fallo de pago y puede enviar notificaciones.
    """
    try:
        logger.warning(f"Pago fallido para factura: {invoice['id']}")

        subscription_id = invoice.get("subscription")
        if subscription_id:
            logger.warning(f"Pago fallido para suscripción: {subscription_id}")

    except Exception as e:
        logger.error(f"Error al manejar pago fallido: {str(e)}")
