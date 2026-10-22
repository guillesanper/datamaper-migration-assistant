import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import stripe

from app.crud.subscription_crud import create_subscription_orm as create_subscription
from app.crud.subscription_crud import get_customer_by_stripe_id_orm as get_customer_by_stripe_id
from app.crud.subscription_crud import (
    get_plan_by_price_id_orm,
)
from app.crud.subscription_crud import (
    get_subscription_by_stripe_id_orm as get_subscription_by_stripe_id,
)
from app.crud.subscription_crud import (
    get_subscription_plan_by_id_orm as get_subscription_plan_by_id,
)
from app.crud.subscription_crud import get_subscription_plans_orm as get_subscription_plans
from app.crud.subscription_crud import get_user_subscription_orm as get_user_subscription
from app.crud.subscription_crud import update_subscription_orm as update_subscription
from app.database import session as db_session_module

# Configurar logging
logger = logging.getLogger(__name__)


def get_db():
    """Abre una sesión SQLAlchemy nueva; quien la llama debe cerrarla (db.close())."""
    return db_session_module.SessionLocal()


# URL base para redirects
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


class StripeConfig:
    """
    Clase para manejar la configuración dinámica de Stripe por plan(por ahora no habra pagos)
    """

    @staticmethod
    def get_stripe_config(plan_id: str) -> Optional[Dict[str, str]]:
        """
        Obtiene la configuración de Stripe para un plan específico (síncrono)
        """
        try:
            db = get_db()
            plan = get_subscription_plan_by_id(db, plan_id)
            if plan and plan.get("stripe_secret_key"):
                return {
                    "secret_key": plan["stripe_secret_key"],
                    "publishable_key": plan["stripe_publishable_key"],
                    "webhook_secret": plan["stripe_webhook_secret"],
                }
            return None
        except Exception as e:
            logger.error(f"Error obteniendo configuración de Stripe para plan {plan_id}: {e}")
            return None
        finally:
            if "db" in locals():
                db.close()

    @staticmethod
    def get_stripe_client(secret_key: str):
        """
        Crea y retorna un cliente de Stripe configurado con la clave secreta específica
        """
        # Configurar la clave API de stripe y retornar el módulo
        stripe.api_key = secret_key
        return stripe


class StripeService:
    """
    Servicio para manejar todas las operaciones de Stripe
    """

    def __init__(self):
        # Configurar la clave de API de Stripe desde las variables de entorno
        stripe_secret_key = os.getenv("STRIPE_SECRET_KEY")
        if stripe_secret_key:
            stripe.api_key = stripe_secret_key
            logger.info("Stripe API key configurada desde variables de entorno")
        else:
            logger.warning("STRIPE_SECRET_KEY no encontrada en variables de entorno")

    def create_or_get_customer(
        self, user_email: str, user_name: Optional[str] = None, user_id: Optional[str] = None
    ) -> Optional[stripe.Customer]:
        """
        Crea o obtiene un cliente de Stripe - para Stripe 12.4.0
        """
        try:
            # Buscar cliente existente por email
            customers = stripe.Customer.list(email=user_email, limit=1)

            if customers.data:
                customer = customers.data[0]
                logger.info(f"Cliente existente encontrado: {customer.id}")
                return customer

            # Crear nuevo cliente
            customer_data: Dict[str, Any] = {
                "email": user_email,
            }

            if user_name:
                customer_data["name"] = user_name

            if user_id:
                customer_data["metadata"] = {"user_id": user_id}

            customer = stripe.Customer.create(**customer_data)  # type: ignore[call-arg]
            logger.info(f"Nuevo cliente creado: {customer.id}")
            return customer

        except stripe.error.StripeError as e:  # type: ignore[attr-defined]
            logger.error(f"Error al crear/obtener cliente de Stripe: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado al manejar cliente: {str(e)}")
            return None

    async def create_checkout_session(
        self,
        user_id: str,
        project_id: str,
        plan_id: str,
        user_email: str,
        billing_cycle: str = "monthly",
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Optional[stripe.checkout.Session]:
        """
        Crea una sesión de checkout de Stripe - versión simplificada para testing
        """
        try:
            # Obtener configuración de Stripe para el plan
            stripe_config = StripeConfig.get_stripe_config(plan_id)
            if not stripe_config:
                logger.error(f"No se encontró configuración de Stripe para el plan {plan_id}")
                return None

            # Configurar Stripe globalmente para esta operación
            original_api_key = stripe.api_key
            stripe.api_key = stripe_config["secret_key"]

            try:
                # Obtener el plan para obtener el price_id
                db = get_db()
                plan = get_subscription_plan_by_id(db, plan_id)
                if not plan:
                    logger.error(f"Plan {plan_id} no encontrado")
                    return None

                # Seleccionar price_id según el ciclo de facturación
                if billing_cycle == "yearly":
                    price_id = plan.get("stripe_price_id_yearly")
                else:
                    price_id = plan.get("stripe_price_id_monthly")

                if not price_id:
                    logger.error(
                        f"Plan {plan_id} no tiene price_id configurado para {billing_cycle}"
                    )
                    return None

                # Crear o obtener cliente
                user_name = f"User {user_id}"
                customer = self.create_or_get_customer(
                    user_email=user_email, user_name=user_name, user_id=user_id
                )
                if not customer:
                    logger.error(f"No se pudo crear/obtener cliente para usuario {user_id}")
                    return None

                # URLs por defecto si no se proporcionan
                if not success_url:
                    success_url = f"{BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
                if not cancel_url:
                    cancel_url = f"{BASE_URL}/billing?project_id={project_id}"

                # CONFIGURACIÓN SIMPLIFICADA PARA TESTING
                session = stripe.checkout.Session.create(
                    customer=customer.id,
                    payment_method_types=["card"],
                    mode="subscription",
                    line_items=[
                        {
                            "price": price_id,
                            "quantity": 1,
                        }
                    ],
                    metadata={
                        "project_id": project_id,
                        "user_id": user_id,
                        "plan_id": plan_id,
                        "billing_cycle": billing_cycle,
                    },
                    success_url=success_url,
                    cancel_url=cancel_url,
                    allow_promotion_codes=True,
                    # Configuración simplificada
                    billing_address_collection="auto",
                    automatic_tax={"enabled": False},  # Deshabilitar impuestos para testing
                )

                logger.info(
                    f"Sesión de checkout creada: {session.id} para usuario {user_id}, plan {plan_id}"
                )
                return session

            finally:
                if "db" in locals():
                    db.close()
                # Restaurar API key original
                stripe.api_key = original_api_key

        except stripe.error.StripeError as e:  # type: ignore[attr-defined]
            logger.error(f"Error al crear sesión de checkout: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado al crear checkout: {str(e)}")
            return None

    def get_subscription(self, subscription_id: str) -> Optional[stripe.Subscription]:
        """
        Obtiene una suscripción de Stripe por su ID.

        Args:
            subscription_id: ID de la suscripción en Stripe

        Returns:
            stripe.Subscription: Suscripción o None si hay error
        """
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return subscription
        except stripe.error.StripeError as e:  # type: ignore[attr-defined]
            logger.error(f"Error al obtener suscripción {subscription_id}: {str(e)}")
            return None

    def cancel_subscription(
        self, subscription_id: str, cancel_at_period_end: bool = True
    ) -> Optional[stripe.Subscription]:
        """
        Cancela una suscripción de Stripe.

        Args:
            subscription_id: ID de la suscripción en Stripe
            cancel_at_period_end: Si True, cancela al final del período actual

        Returns:
            stripe.Subscription: Suscripción cancelada o None si hay error
        """
        try:
            if cancel_at_period_end:
                # Cancelar al final del período
                subscription = stripe.Subscription.modify(
                    subscription_id, cancel_at_period_end=True
                )
                logger.info(
                    f"Suscripción {subscription_id} marcada para cancelar al final del período"
                )
            else:
                # Cancelar inmediatamente
                subscription = stripe.Subscription.delete(subscription_id)  # type: ignore[arg-type]
                logger.info(f"Suscripción {subscription_id} cancelada inmediatamente")

            return subscription

        except stripe.error.StripeError as e:  # type: ignore[attr-defined]
            logger.error(f"Error al cancelar suscripción {subscription_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado al cancelar suscripción: {str(e)}")
            return None

    async def update_subscription_in_db(
        self, subscription_data: stripe.Subscription, project_id: Optional[str] = None
    ) -> bool:
        """
        Actualiza o crea una suscripción en la base de datos basada en datos de Stripe.

        Args:
            subscription_data: Datos de la suscripción de Stripe
            project_id: ID del proyecto (opcional, se puede obtener de metadata)

        Returns:
            bool: True si la operación fue exitosa
        """
        try:
            db = get_db()

            # Obtener project_id de metadata si no se proporciona
            if not project_id:
                project_id = subscription_data.metadata.get("project_id")

            if not project_id:
                logger.error("No se pudo obtener project_id para la suscripción")
                return False

            # Obtener información del precio para determinar el plan
            logger.info(f"Subscription data type: {type(subscription_data)}")

            # Usar la API de Stripe para obtener los items de la suscripción
            try:
                # Obtener los items de la suscripción usando la API
                subscription_items = stripe.SubscriptionItem.list(
                    subscription=subscription_data.id, limit=1
                )

                logger.info(f"Subscription items type: {type(subscription_items)}")
                logger.info(f"Subscription items data: {subscription_items.data}")

                if subscription_items.data and len(subscription_items.data) > 0:
                    price_id = subscription_items.data[0].price.id
                    logger.info(f"Price ID obtenido: {price_id}")
                else:
                    logger.error("No se encontraron items en la suscripción")
                    return False
            except Exception as e:
                logger.error(f"Error accediendo a price_id: {e}")
                return False

            # Buscar el plan correspondiente al price_id
            plan = self.get_plan_by_price_id(price_id)

            if not plan:
                logger.error(f"No se encontró plan para price_id: {price_id}")
                return False

            plan_id = plan["id"]

            # Preparar datos de la suscripción
            print(f"DEBUG: Tipo de subscription_data: {type(subscription_data)}")
            print(f"DEBUG: Atributos disponibles en subscription_data: {dir(subscription_data)}")
            print(
                f"DEBUG: subscription_data como dict: {dict(subscription_data) if hasattr(subscription_data, '__iter__') else 'No es iterable'}"
            )

            # Verificar si los atributos existen antes de acceder
            if hasattr(subscription_data, "current_period_start"):
                print(
                    f"DEBUG: current_period_start existe: {subscription_data.current_period_start}"
                )
                logger.info(
                    f"Raw current_period_start: {subscription_data.current_period_start} (tipo: {type(subscription_data.current_period_start)})"
                )
            else:
                print(f"DEBUG: current_period_start NO existe en subscription_data")

            if hasattr(subscription_data, "current_period_end"):
                print(f"DEBUG: current_period_end existe: {subscription_data.current_period_end}")
                logger.info(
                    f"Raw current_period_end: {subscription_data.current_period_end} (tipo: {type(subscription_data.current_period_end)})"
                )
            else:
                print(f"DEBUG: current_period_end NO existe en subscription_data")

            try:
                # Usar los campos correctos del objeto Stripe
                # Verificar qué campos están disponibles para fechas
                print(f"DEBUG: start_date disponible: {hasattr(subscription_data, 'start_date')}")
                print(f"DEBUG: created disponible: {hasattr(subscription_data, 'created')}")

                if hasattr(subscription_data, "start_date") and subscription_data.start_date:
                    current_period_start = datetime.fromtimestamp(
                        subscription_data.start_date, tz=timezone.utc
                    )
                    print(f"DEBUG: Usando start_date: {current_period_start}")
                elif hasattr(subscription_data, "created") and subscription_data.created:
                    current_period_start = datetime.fromtimestamp(
                        subscription_data.created, tz=timezone.utc
                    )
                    print(f"DEBUG: Usando created: {current_period_start}")
                else:
                    # Usar fecha actual como fallback
                    current_period_start = datetime.now(tz=timezone.utc)
                    print(f"DEBUG: Usando fecha actual como fallback: {current_period_start}")

                # Para current_period_end, calcular basado en el plan (mensual = +1 mes)
                # Por ahora usar start + 30 días como aproximación
                from datetime import timedelta

                current_period_end = current_period_start + timedelta(days=30)

                logger.info(f"Converted current_period_start: {current_period_start}")
                logger.info(f"Converted current_period_end: {current_period_end}")
            except Exception as e:
                logger.error(f"Error convirtiendo timestamps: {e}")
                return False

            # Verificar si ya existe la suscripción
            existing = get_subscription_by_stripe_id(db, subscription_data.id)

            if existing:
                # Actualizar suscripción existente
                update_data = {
                    "status": subscription_data.status,
                    "current_period_start": current_period_start,
                    "current_period_end": current_period_end,
                    "cancel_at_period_end": subscription_data.cancel_at_period_end,
                    "cancel_at": (
                        datetime.fromtimestamp(subscription_data.cancel_at, tz=timezone.utc)
                        if subscription_data.cancel_at
                        else None
                    ),
                    "trial_end": (
                        datetime.fromtimestamp(subscription_data.trial_end, tz=timezone.utc)
                        if subscription_data.trial_end
                        else None
                    ),
                    "currency": subscription_items.data[0].price.currency,
                    "unit_amount": subscription_items.data[0].price.unit_amount,
                    "default_payment_method": subscription_data.default_payment_method,
                    "latest_invoice_id": subscription_data.latest_invoice,
                }

                success = update_subscription(db, subscription_data.id, update_data)
                logger.info(f"Suscripción {subscription_data.id} actualizada en BD")
                return success
            else:
                # Crear nueva suscripción
                # Obtener información del customer para user_id
                customer_info = get_customer_by_stripe_id(db, subscription_data.customer)  # type: ignore[arg-type]

                if not customer_info:
                    logger.error(
                        f"No se encontró información del cliente: {subscription_data.customer}"
                    )
                    return False

                create_data = {
                    "user_id": customer_info["user_id"],
                    "project_id": project_id,
                    "stripe_customer_id": subscription_data.customer,
                    "stripe_subscription_id": subscription_data.id,
                    "plan_id": plan_id,
                    "price_id": price_id,
                    "status": subscription_data.status,
                    "current_period_start": current_period_start,
                    "current_period_end": current_period_end,
                    "cancel_at_period_end": subscription_data.cancel_at_period_end,
                    "cancel_at": (
                        datetime.fromtimestamp(subscription_data.cancel_at, tz=timezone.utc)
                        if subscription_data.cancel_at
                        else None
                    ),
                    "trial_end": (
                        datetime.fromtimestamp(subscription_data.trial_end, tz=timezone.utc)
                        if subscription_data.trial_end
                        else None
                    ),
                    "currency": subscription_items.data[0].price.currency,
                    "unit_amount": subscription_items.data[0].price.unit_amount,
                    "quantity": (
                        subscription_data.quantity if hasattr(subscription_data, "quantity") else 1
                    ),
                    "default_payment_method": subscription_data.default_payment_method,
                    "latest_invoice_id": subscription_data.latest_invoice,
                }

                success = create_subscription(db, create_data)
                logger.info(f"Nueva suscripción {subscription_data.id} creada en BD")
                return success

        except Exception as e:
            print(f"DEBUG STRIPE ERROR: Error al actualizar suscripción en BD: {str(e)}")
            print(f"DEBUG STRIPE ERROR: Tipo de error: {type(e).__name__}")
            print(f"DEBUG STRIPE ERROR: Detalles del error: {repr(e)}")

            # Información adicional del error de PostgreSQL si aplica
            if hasattr(e, "pgcode"):
                print(f"DEBUG STRIPE ERROR: PostgreSQL error code: {e.pgcode}")
            if hasattr(e, "pgerror"):
                print(f"DEBUG STRIPE ERROR: PostgreSQL error message: {e.pgerror}")
            if hasattr(e, "diag"):
                print(f"DEBUG STRIPE ERROR: PostgreSQL diagnostic: {e.diag}")

            logger.error(f"Error al actualizar suscripción en BD: {str(e)}")
            logger.error(f"Tipo de error: {type(e).__name__}")
            logger.error(f"Detalles del error: {repr(e)}")
            return False
        finally:
            if "db" in locals():
                db.close()

    def get_subscription_plans(self) -> List[Dict[str, Any]]:
        """
        Obtiene todos los planes de suscripción activos de la base de datos.

        Returns:
            List[Dict]: Lista de planes de suscripción
        """
        db = get_db()
        try:
            return get_subscription_plans(db)
        finally:
            db.close()

    def get_plan_by_price_id(self, price_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un plan de suscripción por su price_id de Stripe.

        Args:
            price_id: ID del precio en Stripe

        Returns:
            Dict con los datos del plan o None si no existe
        """
        try:
            db = get_db()
            plan = get_plan_by_price_id_orm(db, price_id)
            return plan

        except Exception as e:
            logger.error(f"Error al obtener plan por price_id {price_id}: {str(e)}")
            return None
        finally:
            if "db" in locals():
                db.close()

    async def handle_webhook(
        self, payload: bytes, sig_header: str, plan_id: Optional[str] = None
    ) -> bool:
        """
        Maneja los webhooks de Stripe usando configuración dinámica
        """
        try:
            # Si no se proporciona plan_id, intentar extraerlo del payload
            if not plan_id:
                # Parsear el payload para obtener metadata
                import json

                try:
                    event_data = json.loads(payload.decode("utf-8"))
                    metadata = event_data.get("data", {}).get("object", {}).get("metadata", {})
                    plan_id = metadata.get("plan_id")
                except:
                    logger.warning("No se pudo extraer plan_id del webhook payload")

            # Obtener configuración de Stripe para el plan
            webhook_secret = None
            stripe_client = None
            if plan_id:
                stripe_config = StripeConfig.get_stripe_config(plan_id)
                if stripe_config:
                    webhook_secret = stripe_config["webhook_secret"]
                    # Crear cliente Stripe independiente para este plan
                    stripe_client = StripeConfig.get_stripe_client(stripe_config["secret_key"])

            # Si no tenemos webhook_secret específico, usar uno por defecto (fallback)
            if not webhook_secret:
                webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
                logger.warning(f"Usando webhook secret por defecto para plan {plan_id}")

            if not webhook_secret:
                logger.error("No se encontró webhook secret")
                return False

            # Construir evento (el API key ya está configurado en stripe.api_key si hay stripe_client)
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)

            logger.info(f"Webhook recibido: {event['type']} para plan {plan_id}")

            if event["type"] == "checkout.session.completed":
                session = event["data"]["object"]
                await self.handle_checkout_completed(session)
            elif event["type"] == "customer.subscription.created":
                subscription = event["data"]["object"]
                await self.handle_subscription_created(subscription)
            elif event["type"] == "customer.subscription.updated":
                subscription = event["data"]["object"]
                await self.handle_subscription_updated(subscription)
            elif event["type"] == "customer.subscription.deleted":
                subscription = event["data"]["object"]
                await self.handle_subscription_deleted(subscription)
            elif event["type"] == "invoice.payment_failed":
                invoice = event["data"]["object"]
                await self.handle_payment_failed(invoice)

            return True

        except ValueError as e:
            logger.error(f"Payload inválido en webhook: {e}")
            return False
        except stripe.error.SignatureVerificationError as e:  # type: ignore[attr-defined]
            logger.error(f"Firma inválida en webhook: {e}")
            return False
        except Exception as e:
            logger.error(f"Error procesando webhook: {e}")
            return False

    async def handle_checkout_completed(self, session):
        """
        Maneja el evento de checkout completado
        """
        try:
            user_id = session["metadata"].get("user_id")
            project_id = session["metadata"].get("project_id")
            plan_id = session["metadata"].get("plan_id")

            logger.info(
                f"Checkout completado para usuario {user_id}, proyecto {project_id}, plan {plan_id}"
            )

            # Obtener la suscripción de Stripe
            subscription_id = session.get("subscription")
            if subscription_id:
                # Obtener configuración de Stripe para el plan
                stripe_config = StripeConfig.get_stripe_config(plan_id)
                if stripe_config:
                    # Crear cliente Stripe independiente para este plan
                    stripe_client = StripeConfig.get_stripe_client(stripe_config["secret_key"])

                    # Obtener detalles de la suscripción usando el cliente específico
                    subscription = stripe_client.Subscription.retrieve(subscription_id)
                    await self.update_subscription_in_db(subscription, project_id)

            # Aquí puedes agregar lógica adicional como:
            # - Enviar email de confirmación
            # - Actualizar estado del proyecto
            # - Registrar en analytics

        except Exception as e:
            logger.error(f"Error manejando checkout completado: {e}")

    async def handle_subscription_created(self, subscription):
        """
        Maneja el evento de suscripción creada
        """
        try:
            logger.info(f"Suscripción creada: {subscription['id']}")

            # Obtener plan_id de metadata
            plan_id = subscription["metadata"].get("plan_id")
            if plan_id:
                # Configurar Stripe con las claves del plan
                stripe_config = StripeConfig.get_stripe_config(plan_id)
                if stripe_config:
                    # Configurar Stripe con la clave del plan
                    StripeConfig.get_stripe_client(stripe_config["secret_key"])

            # Actualizar en base de datos
            await self.update_subscription_in_db(subscription)

        except Exception as e:
            logger.error(f"Error manejando suscripción creada: {e}")

    async def handle_subscription_updated(self, subscription):
        """
        Maneja el evento de suscripción actualizada
        """
        try:
            logger.info(f"Suscripción actualizada: {subscription['id']}")

            # Obtener plan_id de metadata
            plan_id = subscription["metadata"].get("plan_id")
            if plan_id:
                # Configurar Stripe con las claves del plan
                stripe_config = StripeConfig.get_stripe_config(plan_id)
                if stripe_config:
                    # Configurar Stripe con la clave del plan
                    StripeConfig.get_stripe_client(stripe_config["secret_key"])

            # Actualizar en base de datos
            await self.update_subscription_in_db(subscription)

        except Exception as e:
            logger.error(f"Error manejando suscripción actualizada: {e}")

    async def handle_subscription_deleted(self, subscription):
        """
        Maneja el evento de suscripción eliminada
        """
        try:
            logger.info(f"Suscripción eliminada: {subscription['id']}")

            # Obtener plan_id de metadata
            plan_id = subscription["metadata"].get("plan_id")
            if plan_id:
                # Configurar Stripe con las claves del plan
                stripe_config = StripeConfig.get_stripe_config(plan_id)
                if stripe_config:
                    # Configurar Stripe con la clave del plan
                    StripeConfig.get_stripe_client(stripe_config["secret_key"])

            # Actualizar en base de datos
            await self.update_subscription_in_db(subscription)

        except Exception as e:
            logger.error(f"Error manejando suscripción eliminada: {e}")

    async def handle_payment_failed(self, invoice):
        """
        Maneja el evento de pago fallido
        """
        try:
            subscription_id = invoice.get("subscription")
            logger.warning(f"Pago fallido para suscripción: {subscription_id}")

            # Obtener información de la suscripción
            if subscription_id:
                subscription = stripe.Subscription.retrieve(subscription_id)
                plan_id = subscription["metadata"].get("plan_id")

                if plan_id:
                    # Configurar Stripe con las claves del plan
                    stripe_config = StripeConfig.get_stripe_config(plan_id)
                    if stripe_config:
                        # Configurar Stripe con la clave del plan
                        StripeConfig.get_stripe_client(stripe_config["secret_key"])

                # Actualizar estado en base de datos
                await self.update_subscription_in_db(subscription)

            # Aquí puedes agregar lógica adicional como:
            # - Enviar notificación al usuario
            # - Suspender acceso al servicio
            # - Registrar en sistema de alertas

        except Exception as e:
            logger.error(f"Error manejando pago fallido: {e}")

    def construct_webhook_event(self, payload: bytes, sig_header: str) -> Optional[stripe.Event]:
        """
        Construye y verifica un evento de webhook de Stripe.

        Args:
            payload: Payload del webhook
            sig_header: Header de firma del webhook

        Returns:
            stripe.Event: Evento verificado o None si hay error
        """
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

        if not webhook_secret:
            logger.error("STRIPE_WEBHOOK_SECRET no está configurado")
            return None

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
            return event  # type: ignore[no-any-return]
        except ValueError as e:
            logger.error(f"Payload inválido en webhook: {str(e)}")
            return None
        except stripe.error.SignatureVerificationError as e:  # type: ignore[attr-defined]
            logger.error(f"Firma inválida en webhook: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado en webhook: {str(e)}")
            return None


# Instancia global del servicio
stripe_service = StripeService()
