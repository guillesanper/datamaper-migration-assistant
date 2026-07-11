"""
Unit tests for app.crud.subscription_crud module (ORM versions)

Tests for subscription CRUD ORM functions:
- Get subscription plan by ID
- Get subscription plans
- Get user subscription
- Get subscription by Stripe ID
- Create subscription
- Update subscription
- Get customer by Stripe ID
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.crud import subscription_crud
from app.models.orm import Project, Subscription, SubscriptionPlan, User

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def test_user(db_session: Session):
    """Create a test user"""
    unique_id = str(uuid.uuid4())[:8]
    user = User(
        id=uuid.uuid4(),
        username=f"testuser_sub_{unique_id}",
        email=f"testuser_sub_{unique_id}@example.com",
        password_hash="hashed_password",
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_project(db_session: Session, test_user):
    """Create a test project"""
    project = Project(
        id=uuid.uuid4(),
        name="Test Project Subscription",
        description="Test project for subscription testing",
        origin_db="postgres",
        destination_db="mysql",
        owner_id=test_user.id,
        status="active",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def test_subscription_plan(db_session: Session):
    """Create a test subscription plan"""
    unique_id = str(uuid.uuid4())[:8]
    plan = SubscriptionPlan(
        id=f"test_plan_{unique_id}",
        name="Test Plan",
        description="Test subscription plan",
        price_monthly=Decimal("9.99"),
        price_yearly=Decimal("99.99"),
        currency="USD",
        features={"feature1": True, "feature2": "unlimited"},
        max_projects=10,
        max_tables=50,
        max_columns_per_table=100,
        stripe_product_id="prod_test123",
        stripe_price_id_monthly="price_monthly_test123",
        stripe_price_id_yearly="price_yearly_test123",
        is_active=True,
        sort_order=1,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


@pytest.fixture
def inactive_subscription_plan(db_session: Session):
    """Create an inactive subscription plan"""
    unique_id = str(uuid.uuid4())[:8]
    plan = SubscriptionPlan(
        id=f"inactive_plan_{unique_id}",
        name="Inactive Plan",
        description="Inactive subscription plan",
        price_monthly=Decimal("19.99"),
        price_yearly=Decimal("199.99"),
        currency="USD",
        features={"feature1": True},
        max_projects=20,
        max_tables=100,
        max_columns_per_table=200,
        is_active=False,
        sort_order=2,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


@pytest.fixture
def test_subscription(db_session: Session, test_user, test_project, test_subscription_plan):
    """Create a test subscription"""
    unique_id = str(uuid.uuid4())[:8]
    subscription = Subscription(
        id=uuid.uuid4(),
        user_id=test_user.id,
        project_id=test_project.id,
        plan_id=test_subscription_plan.id,
        stripe_customer_id=f"cus_test_{unique_id}",
        stripe_subscription_id=f"sub_test_{unique_id}",
        price_id=f"price_test_{unique_id}",
        status="active",
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
        cancel_at_period_end=False,
        currency="USD",
        unit_amount=999,
        quantity=1,
    )
    db_session.add(subscription)
    db_session.commit()
    db_session.refresh(subscription)
    return subscription


# ============================================================================
# GET SUBSCRIPTION PLAN BY ID TESTS
# ============================================================================


class TestGetSubscriptionPlanByIdOrm:
    """Tests for get_subscription_plan_by_id_orm()"""

    def test_get_active_plan_exists(self, db_session: Session, test_subscription_plan):
        """Test getting an active subscription plan that exists"""
        result = subscription_crud.get_subscription_plan_by_id_orm(
            db_session, test_subscription_plan.id
        )

        assert result is not None
        assert result["id"] == test_subscription_plan.id
        assert result["name"] == "Test Plan"
        assert result["is_active"] == True
        assert float(result["price_monthly"]) == 9.99

    def test_get_inactive_plan_returns_none(self, db_session: Session, inactive_subscription_plan):
        """Test getting an inactive plan returns None"""
        result = subscription_crud.get_subscription_plan_by_id_orm(
            db_session, inactive_subscription_plan.id
        )

        assert result is None

    def test_get_nonexistent_plan(self, db_session: Session):
        """Test getting a plan that doesn't exist"""
        result = subscription_crud.get_subscription_plan_by_id_orm(db_session, "nonexistent_plan")

        assert result is None


# ============================================================================
# GET SUBSCRIPTION PLANS TESTS
# ============================================================================


class TestGetSubscriptionPlansOrm:
    """Tests for get_subscription_plans_orm()"""

    def test_get_all_active_plans(
        self, db_session: Session, test_subscription_plan, inactive_subscription_plan
    ):
        """Test getting all active subscription plans"""
        result = subscription_crud.get_subscription_plans_orm(db_session)

        assert isinstance(result, list)
        assert len(result) >= 1

        # Check that only active plans are returned
        plan_ids = [plan["id"] for plan in result]
        assert test_subscription_plan.id in plan_ids
        assert inactive_subscription_plan.id not in plan_ids

    def test_plans_ordered_correctly(self, db_session: Session, test_subscription_plan):
        """Test that plans are ordered by sort_order and created_at"""
        # Create another plan with different sort_order
        unique_id = str(uuid.uuid4())[:8]
        plan2 = SubscriptionPlan(
            id=f"plan2_{unique_id}",
            name="Plan 2",
            description="Second plan",
            price_monthly=Decimal("19.99"),
            currency="USD",
            is_active=True,
            sort_order=0,  # Lower sort_order should come first
        )
        db_session.add(plan2)
        db_session.commit()

        result = subscription_crud.get_subscription_plans_orm(db_session)

        # Find our test plans in the result
        plan_ids = [plan["id"] for plan in result]
        plan2_index = plan_ids.index(plan2.id)
        test_plan_index = plan_ids.index(test_subscription_plan.id)

        # plan2 should come before test_subscription_plan due to lower sort_order
        assert plan2_index < test_plan_index


# ============================================================================
# GET USER SUBSCRIPTION TESTS
# ============================================================================


class TestGetUserSubscriptionOrm:
    """Tests for get_user_subscription_orm()"""

    def test_get_active_subscription(
        self, db_session: Session, test_subscription, test_user, test_project
    ):
        """Test getting an active subscription for a user and project"""
        result = subscription_crud.get_user_subscription_orm(
            db_session, str(test_user.id), str(test_project.id)
        )

        assert result is not None
        assert result["user_id"] == str(test_user.id)
        assert result["project_id"] == str(test_project.id)
        assert result["status"] == "active"
        assert "plan_name" in result
        assert "max_projects" in result
        assert "max_tables" in result
        assert "max_columns_per_table" in result

    def test_get_trialing_subscription(
        self, db_session: Session, test_user, test_project, test_subscription_plan
    ):
        """Test getting a trialing subscription"""
        # Create a trialing subscription
        unique_id = str(uuid.uuid4())[:8]
        trialing_sub = Subscription(
            id=uuid.uuid4(),
            user_id=test_user.id,
            project_id=test_project.id,
            plan_id=test_subscription_plan.id,
            stripe_customer_id=f"cus_trial_{unique_id}",
            stripe_subscription_id=f"sub_trial_{unique_id}",
            status="trialing",
            current_period_start=datetime.now(timezone.utc),
            current_period_end=datetime.now(timezone.utc) + timedelta(days=14),
            trial_end=datetime.now(timezone.utc) + timedelta(days=14),
        )
        db_session.add(trialing_sub)
        db_session.commit()

        result = subscription_crud.get_user_subscription_orm(
            db_session, str(test_user.id), str(test_project.id)
        )

        assert result is not None
        assert result["status"] == "trialing"

    def test_get_canceled_subscription_returns_none(
        self, db_session: Session, test_user, test_project, test_subscription_plan
    ):
        """Test that canceled subscriptions are not returned"""
        # Create a canceled subscription
        unique_id = str(uuid.uuid4())[:8]
        canceled_sub = Subscription(
            id=uuid.uuid4(),
            user_id=test_user.id,
            project_id=test_project.id,
            plan_id=test_subscription_plan.id,
            stripe_customer_id=f"cus_canceled_{unique_id}",
            stripe_subscription_id=f"sub_canceled_{unique_id}",
            status="canceled",
            current_period_start=datetime.now(timezone.utc) - timedelta(days=30),
            current_period_end=datetime.now(timezone.utc),
        )
        db_session.add(canceled_sub)
        db_session.commit()

        result = subscription_crud.get_user_subscription_orm(
            db_session, str(test_user.id), str(test_project.id)
        )

        # Should return None because only active/trialing subscriptions are considered
        assert result is None

    def test_get_nonexistent_subscription(self, db_session: Session):
        """Test getting a subscription that doesn't exist"""
        fake_user_id = str(uuid.uuid4())
        fake_project_id = str(uuid.uuid4())

        result = subscription_crud.get_user_subscription_orm(
            db_session, fake_user_id, fake_project_id
        )

        assert result is None


# ============================================================================
# GET SUBSCRIPTION BY STRIPE ID TESTS
# ============================================================================


class TestGetSubscriptionByStripeIdOrm:
    """Tests for get_subscription_by_stripe_id_orm()"""

    def test_get_subscription_by_stripe_id(self, db_session: Session, test_subscription):
        """Test getting a subscription by Stripe ID"""
        result = subscription_crud.get_subscription_by_stripe_id_orm(
            db_session, test_subscription.stripe_subscription_id
        )

        assert result is not None
        assert result["stripe_subscription_id"] == test_subscription.stripe_subscription_id
        assert result["stripe_customer_id"] == test_subscription.stripe_customer_id

    def test_get_nonexistent_stripe_subscription(self, db_session: Session):
        """Test getting a subscription with non-existent Stripe ID"""
        result = subscription_crud.get_subscription_by_stripe_id_orm(db_session, "sub_nonexistent")

        assert result is None


# ============================================================================
# CREATE SUBSCRIPTION TESTS
# ============================================================================


class TestCreateSubscriptionOrm:
    """Tests for create_subscription_orm()"""

    def test_create_subscription_success(
        self, db_session: Session, test_user, test_project, test_subscription_plan
    ):
        """Test creating a new subscription"""
        unique_id = str(uuid.uuid4())[:8]
        subscription_data = {
            "user_id": str(test_user.id),
            "project_id": str(test_project.id),
            "plan_id": test_subscription_plan.id,
            "stripe_customer_id": f"cus_new_{unique_id}",
            "stripe_subscription_id": f"sub_new_{unique_id}",
            "price_id": f"price_new_{unique_id}",
            "status": "active",
            "current_period_start": datetime.now(timezone.utc),
            "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
            "cancel_at_period_end": False,
            "currency": "USD",
            "unit_amount": 999,
            "quantity": 1,
        }

        result = subscription_crud.create_subscription_orm(db_session, subscription_data)

        assert result is True

        # Verify subscription was created
        created_sub = subscription_crud.get_subscription_by_stripe_id_orm(
            db_session, f"sub_new_{unique_id}"
        )
        assert created_sub is not None
        assert created_sub["status"] == "active"
        assert created_sub["user_id"] == str(test_user.id)

    def test_create_subscription_with_defaults(
        self, db_session: Session, test_user, test_project, test_subscription_plan
    ):
        """Test creating a subscription with minimal data uses defaults"""
        unique_id = str(uuid.uuid4())[:8]
        subscription_data = {
            "user_id": str(test_user.id),
            "project_id": str(test_project.id),
            "plan_id": test_subscription_plan.id,
            "stripe_customer_id": f"cus_minimal_{unique_id}",
            "stripe_subscription_id": f"sub_minimal_{unique_id}",
            "status": "active",
        }

        result = subscription_crud.create_subscription_orm(db_session, subscription_data)

        assert result is True

        # Verify defaults were applied
        created_sub = subscription_crud.get_subscription_by_stripe_id_orm(
            db_session, f"sub_minimal_{unique_id}"
        )
        assert created_sub is not None
        assert created_sub["cancel_at_period_end"] == False
        assert created_sub["quantity"] == 1


# ============================================================================
# UPDATE SUBSCRIPTION TESTS
# ============================================================================


class TestUpdateSubscriptionOrm:
    """Tests for update_subscription_orm()"""

    def test_update_subscription_status(self, db_session: Session, test_subscription):
        """Test updating subscription status"""
        update_data = {"status": "past_due"}

        result = subscription_crud.update_subscription_orm(
            db_session, test_subscription.stripe_subscription_id, update_data
        )

        assert result is True

        # Verify update
        updated_sub = subscription_crud.get_subscription_by_stripe_id_orm(
            db_session, test_subscription.stripe_subscription_id
        )
        assert updated_sub["status"] == "past_due"

    def test_update_multiple_fields(self, db_session: Session, test_subscription):
        """Test updating multiple fields at once"""
        new_end = datetime.now(timezone.utc) + timedelta(days=60)
        update_data = {
            "status": "active",
            "current_period_end": new_end,
            "cancel_at_period_end": True,
        }

        result = subscription_crud.update_subscription_orm(
            db_session, test_subscription.stripe_subscription_id, update_data
        )

        assert result is True

        # Verify updates
        updated_sub = subscription_crud.get_subscription_by_stripe_id_orm(
            db_session, test_subscription.stripe_subscription_id
        )
        assert updated_sub["status"] == "active"
        assert updated_sub["cancel_at_period_end"] == True

    def test_update_nonexistent_subscription(self, db_session: Session):
        """Test updating a subscription that doesn't exist"""
        update_data = {"status": "canceled"}

        result = subscription_crud.update_subscription_orm(
            db_session, "sub_nonexistent", update_data
        )

        assert result is False

    def test_update_with_empty_data(self, db_session: Session, test_subscription):
        """Test updating with empty data returns True without error"""
        update_data = {}

        result = subscription_crud.update_subscription_orm(
            db_session, test_subscription.stripe_subscription_id, update_data
        )

        assert result is True


# ============================================================================
# GET CUSTOMER BY STRIPE ID TESTS
# ============================================================================


class TestGetCustomerByStripeIdOrm:
    """Tests for get_customer_by_stripe_id_orm()"""

    def test_get_customer_from_subscription(
        self, db_session: Session, test_subscription, test_user
    ):
        """Test getting customer info from subscription table"""
        # Note: This test uses the fallback method since we don't mock Stripe API
        result = subscription_crud.get_customer_by_stripe_id_orm(
            db_session, test_subscription.stripe_customer_id
        )

        assert result is not None
        assert result["user_id"] == str(test_user.id)
        assert "email" in result
        assert "username" in result

    def test_get_nonexistent_customer(self, db_session: Session):
        """Test getting a customer that doesn't exist"""
        result = subscription_crud.get_customer_by_stripe_id_orm(db_session, "cus_nonexistent")

        assert result is None


# ============================================================================
# GET PLAN BY PRICE ID TESTS
# ============================================================================


class TestGetPlanByPriceIdOrm:
    """Tests for get_plan_by_price_id_orm()"""

    def test_find_by_monthly_price_id(self, db_session: Session):
        """Test finding plan by monthly price ID"""
        import uuid

        from app.models.orm.subscription import SubscriptionPlan

        # Create plan
        plan = SubscriptionPlan(
            id=f"test_plan_monthly_{uuid.uuid4().hex[:8]}",
            name="Test Monthly Plan",
            stripe_product_id="prod_123",
            stripe_price_id_monthly="price_monthly_123",
            stripe_price_id_yearly="price_yearly_123",
            is_active=True,
            sort_order=1,
        )
        db_session.add(plan)
        db_session.commit()

        # Search by monthly price
        result = subscription_crud.get_plan_by_price_id_orm(db_session, "price_monthly_123")

        assert result is not None
        assert result["stripe_price_id_monthly"] == "price_monthly_123"

    def test_find_by_yearly_price_id(self, db_session: Session):
        """Test finding plan by yearly price ID"""
        import uuid

        from app.models.orm.subscription import SubscriptionPlan

        # Create plan
        plan = SubscriptionPlan(
            id=f"test_plan_yearly_{uuid.uuid4().hex[:8]}",
            name="Test Yearly Plan",
            stripe_product_id="prod_456",
            stripe_price_id_monthly="price_monthly_456",
            stripe_price_id_yearly="price_yearly_456",
            is_active=True,
            sort_order=2,
        )
        db_session.add(plan)
        db_session.commit()

        # Search by yearly price
        result = subscription_crud.get_plan_by_price_id_orm(db_session, "price_yearly_456")

        assert result is not None
        assert result["stripe_price_id_yearly"] == "price_yearly_456"

    def test_not_found_returns_none(self, db_session: Session):
        """Test that non-existent price_id returns None"""
        result = subscription_crud.get_plan_by_price_id_orm(db_session, "price_nonexistent")

        assert result is None

    def test_inactive_plan_not_returned(self, db_session: Session):
        """Test that inactive plans are not returned"""
        import uuid

        from app.models.orm.subscription import SubscriptionPlan

        # Create inactive plan
        plan = SubscriptionPlan(
            id=f"inactive_plan_{uuid.uuid4().hex[:8]}",
            name="Inactive Plan",
            stripe_product_id="prod_inactive",
            stripe_price_id_monthly="price_inactive_123",
            is_active=False,
            sort_order=99,
        )
        db_session.add(plan)
        db_session.commit()

        # Try to find it
        result = subscription_crud.get_plan_by_price_id_orm(db_session, "price_inactive_123")

        assert result is None
