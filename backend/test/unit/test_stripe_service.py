"""
Unit tests for app.services.stripe_service module

Tests for StripeService:
- Customer creation and retrieval
- Checkout session creation
- Subscription management (get, cancel, update)
- Webhook handling (checkout, subscription events, payment failures)
- Database updates
- Error handling with Stripe API
- Configuration management per plan
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import stripe

from app.services.stripe_service import StripeConfig, StripeService

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_db():
    """Provide a mock SQLAlchemy session"""
    db = MagicMock()
    db.query = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.close = MagicMock()
    return db


@pytest.fixture
def stripe_service():
    """Provide a StripeService instance"""
    with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_fake_key"}):
        return StripeService()


@pytest.fixture
def mock_stripe_customer():
    """Mock Stripe customer object"""
    customer = MagicMock()
    customer.id = "cus_test123"
    customer.email = "test@example.com"
    customer.name = "Test User"
    customer.metadata = {"user_id": "user_123"}
    return customer


@pytest.fixture
def mock_stripe_subscription():
    """Mock Stripe subscription object"""
    subscription = MagicMock()
    subscription.id = "sub_test123"
    subscription.customer = "cus_test123"
    subscription.status = "active"
    subscription.current_period_start = int(datetime.now(timezone.utc).timestamp())
    subscription.current_period_end = int(
        (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
    )
    subscription.cancel_at_period_end = False
    subscription.cancel_at = None
    subscription.trial_end = None
    subscription.default_payment_method = "pm_test123"
    subscription.latest_invoice = "in_test123"
    subscription.quantity = 1
    subscription.metadata = {"project_id": "proj_123", "user_id": "user_123", "plan_id": "plan_123"}
    return subscription


@pytest.fixture
def mock_stripe_session():
    """Mock Stripe checkout session object"""
    session = MagicMock()
    session.id = "cs_test123"
    session.url = "https://checkout.stripe.com/pay/cs_test123"
    session.customer = "cus_test123"
    session.subscription = "sub_test123"
    session.metadata = {
        "project_id": "proj_123",
        "user_id": "user_123",
        "plan_id": "plan_123",
        "billing_cycle": "monthly",
    }
    return session


@pytest.fixture
def mock_plan_config():
    """Mock Stripe configuration for a plan"""
    return {
        "secret_key": "sk_test_plan_key",
        "publishable_key": "pk_test_plan_key",
        "webhook_secret": "whsec_test_secret",
    }


@pytest.fixture
def mock_subscription_plan():
    """Mock subscription plan from database"""
    return {
        "id": "plan_123",
        "name": "Pro Plan",
        "stripe_price_id_monthly": "price_monthly_123",
        "stripe_price_id_yearly": "price_yearly_123",
        "stripe_secret_key": "sk_test_plan_key",
        "stripe_publishable_key": "pk_test_plan_key",
        "stripe_webhook_secret": "whsec_test_secret",
    }


# ============================================================================
# STRIPE CONFIG TESTS
# ============================================================================


class TestStripeConfig:
    """Tests for StripeConfig class"""

    @patch("app.services.stripe_service.get_db")
    @patch("app.services.stripe_service.get_subscription_plan_by_id")
    def test_get_stripe_config_success(self, mock_get_plan, mock_get_db, mock_subscription_plan):
        """Test successful retrieval of Stripe configuration for a plan"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_plan.return_value = mock_subscription_plan

        config = StripeConfig.get_stripe_config("plan_123")

        assert config is not None
        assert config["secret_key"] == "sk_test_plan_key"
        assert config["publishable_key"] == "pk_test_plan_key"
        assert config["webhook_secret"] == "whsec_test_secret"
        mock_get_plan.assert_called_once_with(mock_db, "plan_123")
        mock_db.close.assert_called_once()

    @patch("app.services.stripe_service.get_db")
    @patch("app.services.stripe_service.get_subscription_plan_by_id")
    def test_get_stripe_config_plan_not_found(self, mock_get_plan, mock_get_db):
        """Test Stripe config retrieval when plan doesn't exist"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_plan.return_value = None

        config = StripeConfig.get_stripe_config("nonexistent_plan")

        assert config is None

    @patch("app.services.stripe_service.get_db")
    @patch("app.services.stripe_service.get_subscription_plan_by_id")
    def test_get_stripe_config_no_stripe_keys(self, mock_get_plan, mock_get_db):
        """Test Stripe config retrieval when plan has no Stripe keys"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_plan.return_value = {"id": "plan_123", "stripe_secret_key": None}

        config = StripeConfig.get_stripe_config("plan_123")

        assert config is None

    @patch("app.services.stripe_service.get_db")
    def test_get_stripe_config_database_error(self, mock_get_db):
        """Test Stripe config retrieval with database error"""
        mock_get_db.side_effect = Exception("Database connection failed")

        config = StripeConfig.get_stripe_config("plan_123")

        assert config is None

    def test_get_stripe_client(self):
        """Test Stripe client creation with secret key"""
        with patch("stripe.api_key") as mock_api_key:
            client = StripeConfig.get_stripe_client("sk_test_key")

            assert client == stripe


# ============================================================================
# CUSTOMER MANAGEMENT TESTS
# ============================================================================


class TestCreateOrGetCustomer:
    """Tests for create_or_get_customer method"""

    @patch("stripe.Customer.list")
    def test_create_or_get_customer_existing(self, mock_list, stripe_service, mock_stripe_customer):
        """Test getting existing Stripe customer"""
        mock_list.return_value.data = [mock_stripe_customer]

        customer = stripe_service.create_or_get_customer(
            "test@example.com", "Test User", "user_123"
        )

        assert customer.id == "cus_test123"
        mock_list.assert_called_once_with(email="test@example.com", limit=1)

    @patch("stripe.Customer.create")
    @patch("stripe.Customer.list")
    def test_create_or_get_customer_new(
        self, mock_list, mock_create, stripe_service, mock_stripe_customer
    ):
        """Test creating new Stripe customer"""
        mock_list.return_value.data = []
        mock_create.return_value = mock_stripe_customer

        customer = stripe_service.create_or_get_customer(
            "test@example.com", "Test User", "user_123"
        )

        assert customer.id == "cus_test123"
        mock_create.assert_called_once_with(
            email="test@example.com", name="Test User", metadata={"user_id": "user_123"}
        )

    @patch("stripe.Customer.create")
    @patch("stripe.Customer.list")
    def test_create_or_get_customer_no_name(
        self, mock_list, mock_create, stripe_service, mock_stripe_customer
    ):
        """Test creating customer without name"""
        mock_list.return_value.data = []
        mock_create.return_value = mock_stripe_customer

        customer = stripe_service.create_or_get_customer("test@example.com")

        assert customer.id == "cus_test123"
        mock_create.assert_called_once()
        call_args = mock_create.call_args[1]
        assert "name" not in call_args

    @patch("stripe.Customer.list")
    def test_create_or_get_customer_stripe_error(self, mock_list, stripe_service):
        """Test customer creation with Stripe API error"""
        mock_list.side_effect = stripe.error.StripeError("API Error")

        customer = stripe_service.create_or_get_customer("test@example.com")

        assert customer is None

    @patch("stripe.Customer.list")
    def test_create_or_get_customer_unexpected_error(self, mock_list, stripe_service):
        """Test customer creation with unexpected error"""
        mock_list.side_effect = Exception("Unexpected error")

        customer = stripe_service.create_or_get_customer("test@example.com")

        assert customer is None


# ============================================================================
# CHECKOUT SESSION TESTS
# ============================================================================


class TestCreateCheckoutSession:
    """Tests for create_checkout_session method"""

    @pytest.mark.asyncio
    @patch("app.services.stripe_service.get_db")
    @patch("app.services.stripe_service.get_subscription_plan_by_id")
    @patch("app.services.stripe_service.StripeConfig.get_stripe_config")
    @patch("stripe.checkout.Session.create")
    async def test_create_checkout_session_monthly(
        self,
        mock_session_create,
        mock_get_config,
        mock_get_plan,
        mock_get_db,
        stripe_service,
        mock_subscription_plan,
        mock_plan_config,
        mock_stripe_session,
    ):
        """Test successful checkout session creation for monthly billing"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_config.return_value = mock_plan_config
        mock_get_plan.return_value = mock_subscription_plan
        mock_session_create.return_value = mock_stripe_session

        with patch.object(stripe_service, "create_or_get_customer") as mock_create_customer:
            mock_customer = MagicMock()
            mock_customer.id = "cus_test123"
            mock_create_customer.return_value = mock_customer

            session = await stripe_service.create_checkout_session(
                user_id="user_123",
                project_id="proj_123",
                plan_id="plan_123",
                user_email="test@example.com",
                billing_cycle="monthly",
            )

        assert session.id == "cs_test123"
        mock_session_create.assert_called_once()
        call_args = mock_session_create.call_args[1]
        assert call_args["line_items"][0]["price"] == "price_monthly_123"
        assert call_args["mode"] == "subscription"
        assert call_args["metadata"]["billing_cycle"] == "monthly"

    @pytest.mark.asyncio
    @patch("app.services.stripe_service.get_db")
    @patch("app.services.stripe_service.get_subscription_plan_by_id")
    @patch("app.services.stripe_service.StripeConfig.get_stripe_config")
    @patch("stripe.checkout.Session.create")
    async def test_create_checkout_session_yearly(
        self,
        mock_session_create,
        mock_get_config,
        mock_get_plan,
        mock_get_db,
        stripe_service,
        mock_subscription_plan,
        mock_plan_config,
        mock_stripe_session,
    ):
        """Test successful checkout session creation for yearly billing"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_config.return_value = mock_plan_config
        mock_get_plan.return_value = mock_subscription_plan
        mock_session_create.return_value = mock_stripe_session

        with patch.object(stripe_service, "create_or_get_customer") as mock_create_customer:
            mock_customer = MagicMock()
            mock_customer.id = "cus_test123"
            mock_create_customer.return_value = mock_customer

            session = await stripe_service.create_checkout_session(
                user_id="user_123",
                project_id="proj_123",
                plan_id="plan_123",
                user_email="test@example.com",
                billing_cycle="yearly",
            )

        call_args = mock_session_create.call_args[1]
        assert call_args["line_items"][0]["price"] == "price_yearly_123"

    @pytest.mark.asyncio
    @patch("app.services.stripe_service.StripeConfig.get_stripe_config")
    async def test_create_checkout_session_no_config(self, mock_get_config, stripe_service):
        """Test checkout session creation when Stripe config not found"""
        mock_get_config.return_value = None

        session = await stripe_service.create_checkout_session(
            user_id="user_123",
            project_id="proj_123",
            plan_id="plan_123",
            user_email="test@example.com",
        )

        assert session is None

    @pytest.mark.asyncio
    @patch("app.services.stripe_service.get_db")
    @patch("app.services.stripe_service.get_subscription_plan_by_id")
    @patch("app.services.stripe_service.StripeConfig.get_stripe_config")
    async def test_create_checkout_session_plan_not_found(
        self, mock_get_config, mock_get_plan, mock_get_db, stripe_service, mock_plan_config
    ):
        """Test checkout session creation when plan not found"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_config.return_value = mock_plan_config
        mock_get_plan.return_value = None

        session = await stripe_service.create_checkout_session(
            user_id="user_123",
            project_id="proj_123",
            plan_id="plan_123",
            user_email="test@example.com",
        )

        assert session is None

    @pytest.mark.asyncio
    @patch("app.services.stripe_service.get_db")
    @patch("app.services.stripe_service.get_subscription_plan_by_id")
    @patch("app.services.stripe_service.StripeConfig.get_stripe_config")
    async def test_create_checkout_session_customer_creation_failed(
        self,
        mock_get_config,
        mock_get_plan,
        mock_get_db,
        stripe_service,
        mock_subscription_plan,
        mock_plan_config,
    ):
        """Test checkout session creation when customer creation fails"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_config.return_value = mock_plan_config
        mock_get_plan.return_value = mock_subscription_plan

        with patch.object(stripe_service, "create_or_get_customer", return_value=None):
            session = await stripe_service.create_checkout_session(
                user_id="user_123",
                project_id="proj_123",
                plan_id="plan_123",
                user_email="test@example.com",
            )

        assert session is None


# ============================================================================
# SUBSCRIPTION MANAGEMENT TESTS
# ============================================================================


class TestGetSubscription:
    """Tests for get_subscription method"""

    @patch("stripe.Subscription.retrieve")
    def test_get_subscription_success(
        self, mock_retrieve, stripe_service, mock_stripe_subscription
    ):
        """Test successful subscription retrieval"""
        mock_retrieve.return_value = mock_stripe_subscription

        subscription = stripe_service.get_subscription("sub_test123")

        assert subscription.id == "sub_test123"
        mock_retrieve.assert_called_once_with("sub_test123")

    @patch("stripe.Subscription.retrieve")
    def test_get_subscription_stripe_error(self, mock_retrieve, stripe_service):
        """Test subscription retrieval with Stripe error"""
        mock_retrieve.side_effect = stripe.error.StripeError("Not found")

        subscription = stripe_service.get_subscription("sub_test123")

        assert subscription is None


class TestCancelSubscription:
    """Tests for cancel_subscription method"""

    @patch("stripe.Subscription.modify")
    def test_cancel_subscription_at_period_end(
        self, mock_modify, stripe_service, mock_stripe_subscription
    ):
        """Test canceling subscription at period end"""
        mock_modify.return_value = mock_stripe_subscription

        subscription = stripe_service.cancel_subscription("sub_test123", cancel_at_period_end=True)

        assert subscription is not None
        mock_modify.assert_called_once_with("sub_test123", cancel_at_period_end=True)

    @patch("stripe.Subscription.delete")
    def test_cancel_subscription_immediately(
        self, mock_delete, stripe_service, mock_stripe_subscription
    ):
        """Test canceling subscription immediately"""
        mock_delete.return_value = mock_stripe_subscription

        subscription = stripe_service.cancel_subscription("sub_test123", cancel_at_period_end=False)

        assert subscription is not None
        mock_delete.assert_called_once_with("sub_test123")

    @patch("stripe.Subscription.modify")
    def test_cancel_subscription_stripe_error(self, mock_modify, stripe_service):
        """Test subscription cancellation with Stripe error"""
        mock_modify.side_effect = stripe.error.StripeError("Error")

        subscription = stripe_service.cancel_subscription("sub_test123")

        assert subscription is None


# ============================================================================
# WEBHOOK HANDLING TESTS
# ============================================================================


class TestHandleWebhook:
    """Tests for webhook handling"""

    @pytest.mark.asyncio
    @patch("app.services.stripe_service.StripeConfig.get_stripe_config")
    @patch("stripe.Webhook.construct_event")
    async def test_handle_webhook_checkout_completed(
        self, mock_construct, mock_get_config, stripe_service
    ):
        """Test handling checkout.session.completed webhook"""
        # Mock stripe config
        mock_get_config.return_value = {
            "secret_key": "sk_test_key",
            "publishable_key": "pk_test_key",
            "webhook_secret": "whsec_test_secret",
        }

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {
                        "user_id": "user_123",
                        "project_id": "proj_123",
                        "plan_id": "plan_123",
                    },
                    "subscription": "sub_test123",
                }
            },
        }
        mock_construct.return_value = event

        with patch.object(
            stripe_service, "handle_checkout_completed", new_callable=AsyncMock
        ) as mock_handle:
            result = await stripe_service.handle_webhook(
                b'{"test": "payload"}', "sig_header", "plan_123"
            )

        assert result is True
        mock_handle.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.stripe_service.StripeConfig.get_stripe_config")
    @patch("stripe.Webhook.construct_event")
    async def test_handle_webhook_subscription_created(
        self, mock_construct, mock_get_config, stripe_service
    ):
        """Test handling customer.subscription.created webhook"""
        # Mock stripe config
        mock_get_config.return_value = {
            "secret_key": "sk_test_key",
            "publishable_key": "pk_test_key",
            "webhook_secret": "whsec_test_secret",
        }

        event = {
            "type": "customer.subscription.created",
            "data": {"object": {"id": "sub_123", "metadata": {"plan_id": "plan_123"}}},
        }
        mock_construct.return_value = event

        with patch.object(
            stripe_service, "handle_subscription_created", new_callable=AsyncMock
        ) as mock_handle:
            result = await stripe_service.handle_webhook(
                b'{"test": "payload"}', "sig_header", "plan_123"
            )

        assert result is True

    @pytest.mark.asyncio
    @patch("app.services.stripe_service.StripeConfig.get_stripe_config")
    @patch("stripe.Webhook.construct_event")
    async def test_handle_webhook_payment_failed(
        self, mock_construct, mock_get_config, stripe_service
    ):
        """Test handling invoice.payment_failed webhook"""
        # Mock stripe config
        mock_get_config.return_value = {
            "secret_key": "sk_test_key",
            "publishable_key": "pk_test_key",
            "webhook_secret": "whsec_test_secret",
        }

        event = {"type": "invoice.payment_failed", "data": {"object": {"subscription": "sub_123"}}}
        mock_construct.return_value = event

        with patch.object(
            stripe_service, "handle_payment_failed", new_callable=AsyncMock
        ) as mock_handle:
            result = await stripe_service.handle_webhook(
                b'{"test": "payload"}', "sig_header", "plan_123"
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_handle_webhook_invalid_signature(self, stripe_service):
        """Test webhook with invalid signature"""
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe.error.SignatureVerificationError("Invalid", "sig"),
        ):
            result = await stripe_service.handle_webhook(
                b'{"test": "payload"}', "invalid_sig", "plan_123"
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_webhook_invalid_payload(self, stripe_service):
        """Test webhook with invalid payload"""
        with patch("stripe.Webhook.construct_event", side_effect=ValueError("Invalid JSON")):
            result = await stripe_service.handle_webhook(b"invalid_json", "sig_header", "plan_123")

        assert result is False


# ============================================================================
# GET PLAN BY PRICE ID TESTS
# ============================================================================


class TestGetPlanByPriceId:
    """Tests for get_plan_by_price_id method - uses ORM CRUD"""

    @patch("app.services.stripe_service.get_plan_by_price_id_orm")
    @patch("app.services.stripe_service.get_db")
    def test_get_plan_by_price_id_success(self, mock_get_db, mock_get_plan_orm, stripe_service):
        """Test successful plan retrieval by price ID"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_plan_orm.return_value = {"id": "plan_123", "name": "Pro Plan"}

        plan = stripe_service.get_plan_by_price_id("price_123")

        assert plan["id"] == "plan_123"
        mock_get_plan_orm.assert_called_once_with(mock_db, "price_123")

    @patch("app.services.stripe_service.get_plan_by_price_id_orm")
    @patch("app.services.stripe_service.get_db")
    def test_get_plan_by_price_id_not_found(self, mock_get_db, mock_get_plan_orm, stripe_service):
        """Test plan retrieval when price ID not found"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_plan_orm.return_value = None

        plan = stripe_service.get_plan_by_price_id("nonexistent")

        assert plan is None

    @patch("app.services.stripe_service.get_db")
    def test_get_plan_by_price_id_database_error(self, mock_get_db, stripe_service):
        """Test plan retrieval with database error"""
        mock_get_db.side_effect = Exception("Database error")

        plan = stripe_service.get_plan_by_price_id("price_123")

        assert plan is None


# ============================================================================
# GET SUBSCRIPTION PLANS TESTS
# ============================================================================


class TestGetSubscriptionPlans:
    """Tests for get_subscription_plans method"""

    @patch("app.services.stripe_service.get_db")
    @patch("app.services.stripe_service.get_subscription_plans")
    def test_get_subscription_plans_success(self, mock_get_plans, mock_get_db, stripe_service):
        """Test successful retrieval of all subscription plans"""
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_get_plans.return_value = [
            {"id": "plan_1", "name": "Basic"},
            {"id": "plan_2", "name": "Pro"},
        ]

        plans = stripe_service.get_subscription_plans()

        assert len(plans) == 2
        assert plans[0]["name"] == "Basic"
        mock_get_plans.assert_called_once_with(mock_db)
