# routers/admin.py
"""
Admin API endpoints — requires get_current_admin dependency.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.crud import request_log_crud, security_log_crud
from app.utils.error_codes import ErrorCode, make_error
from app.database.session import get_db_session
from app.models.orm import (
    Project,
    ProjectActivity,
    Subscription,
    SubscriptionPlan,
    User,
    UserSession,
)
from app.routers.dependencies import get_current_admin
from app.utils.redis_client import get_redis_client

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ============================================================================
# Health
# ============================================================================


@router.get("/health/detailed")
def get_detailed_health(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_admin),
) -> Dict[str, Any]:
    """Returns detailed system health stats. Requires admin."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "error"

    try:
        redis = get_redis_client()
        redis.ping()
        redis_status = "healthy"
    except Exception:
        redis_status = "error"

    mem = psutil.virtual_memory()
    process = psutil.Process()

    return {
        "db_status": db_status,
        "redis_status": redis_status,
        "memory_percent": mem.percent,
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "process_memory_mb": round(process.memory_info().rss / 1024 / 1024, 1),
        "environment": os.getenv("ENV", "production"),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================================================
# Users
# ============================================================================


@router.get("/users/stats")
def get_user_stats(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_admin),
) -> Dict[str, Any]:
    """Returns aggregate user statistics."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    total_users = db.query(func.count(User.id)).filter(User.is_deleted == False).scalar() or 0

    verified_users = (
        db.query(func.count(User.id))
        .filter(User.is_deleted == False, User.is_verified == True)
        .scalar()
        or 0
    )

    new_last_7_days = (
        db.query(func.count(User.id))
        .filter(User.is_deleted == False, User.created_at >= seven_days_ago)
        .scalar()
        or 0
    )

    currently_locked = (
        db.query(func.count(User.id))
        .filter(User.locked_until.isnot(None), User.locked_until > now)
        .scalar()
        or 0
    )

    active_last_30_days = (
        db.query(func.count(func.distinct(UserSession.user_id)))
        .filter(UserSession.last_activity >= thirty_days_ago)
        .scalar()
        or 0
    )

    return {
        "success": True,
        "data": {
            "total_users": total_users,
            "verified_users": verified_users,
            "new_last_7_days": new_last_7_days,
            "currently_locked": currently_locked,
            "active_last_30_days": active_last_30_days,
        },
    }


@router.get("/users")
def list_users(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_admin),
    search: Optional[str] = Query(None),
    verified: Optional[bool] = Query(None),
    locked: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Returns paginated user list with optional filters."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    query = db.query(User).filter(User.is_deleted == False)

    if search:
        pattern = f"%{search}%"
        query = query.filter((User.username.ilike(pattern)) | (User.email.ilike(pattern)))

    if verified is not None:
        query = query.filter(User.is_verified == verified)

    if locked is not None:
        if locked:
            query = query.filter(User.locked_until.isnot(None), User.locked_until > now)
        else:
            query = query.filter((User.locked_until.is_(None)) | (User.locked_until <= now))

    total = query.count()
    users = (
        query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    )

    def serialize_user(u: User) -> Dict[str, Any]:
        return {
            "id": str(u.id),
            "username": u.username,
            "email": u.email,
            "is_verified": u.is_verified,
            "is_deleted": u.is_deleted,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "failed_login_attempts": u.failed_login_attempts,
            "locked_until": u.locked_until.isoformat() if u.locked_until else None,
        }

    return {
        "success": True,
        "data": {
            "users": [serialize_user(u) for u in users],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.patch("/users/{user_id}/unlock")
def unlock_user(
    user_id: str,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_admin),
) -> Dict[str, Any]:
    """Unlocks a user account by clearing locked_until and failed_login_attempts."""
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail=make_error(ErrorCode.USER_NOT_FOUND))

    user.locked_until = None  # type: ignore[assignment]
    user.failed_login_attempts = 0  # type: ignore[assignment]
    db.commit()

    return {"success": True, "message": f"User {user.username} unlocked successfully"}


# ============================================================================
# Security
# ============================================================================


@router.get("/security/stats")
def get_security_stats(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_admin),
    days: int = Query(7, ge=1, le=90),
) -> Dict[str, Any]:
    """Returns aggregated security log statistics."""
    stats = security_log_crud.get_logs_stats_orm(db, days=days)
    return {"success": True, "data": stats}


@router.get("/security/events")
def get_security_events(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_admin),
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Returns security events with optional filters."""
    events = security_log_crud.get_logs_orm(
        db,
        event_type=event_type,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    return {"success": True, "data": {"events": events, "limit": limit, "offset": offset}}


# ============================================================================
# Business Metrics
# ============================================================================


@router.get("/metrics/business")
def get_business_metrics(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_admin),
    days: int = Query(30, ge=1, le=365),
) -> Dict[str, Any]:
    """Returns business metrics for the given period."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    since = now - timedelta(days=days)

    total_projects = (
        db.query(func.count(Project.id)).filter(Project.is_deleted == False).scalar() or 0
    )

    status_rows = (
        db.query(Project.status, func.count(Project.id))
        .filter(Project.is_deleted == False)
        .group_by(Project.status)
        .all()
    )
    projects_by_status: Dict[str, Any] = {row[0]: row[1] for row in status_rows}

    total_users = db.query(func.count(User.id)).filter(User.is_deleted == False).scalar() or 0

    user_day_rows = (
        db.query(
            func.date_trunc("day", User.created_at).label("day"),
            func.count(User.id).label("count"),
        )
        .filter(User.is_deleted == False, User.created_at >= since)
        .group_by(func.date_trunc("day", User.created_at))
        .order_by(func.date_trunc("day", User.created_at))
        .all()
    )
    new_users_by_day: List[Dict[str, Any]] = [
        {"date": row.day.strftime("%Y-%m-%d"), "count": row.count} for row in user_day_rows
    ]

    project_day_rows = (
        db.query(
            func.date_trunc("day", Project.created_at).label("day"),
            func.count(Project.id).label("count"),
        )
        .filter(Project.is_deleted == False, Project.created_at >= since)
        .group_by(func.date_trunc("day", Project.created_at))
        .order_by(func.date_trunc("day", Project.created_at))
        .all()
    )
    projects_by_day: List[Dict[str, Any]] = [
        {"date": row.day.strftime("%Y-%m-%d"), "count": row.count} for row in project_day_rows
    ]

    sub_rows = (
        db.query(SubscriptionPlan.name, func.count(Subscription.id).label("count"))
        .join(Subscription, Subscription.plan_id == SubscriptionPlan.id)
        .filter(Subscription.status == "active")
        .group_by(SubscriptionPlan.name)
        .all()
    )
    subscription_breakdown: Dict[str, Any] = {row[0]: row[1] for row in sub_rows}

    total_active_subscriptions = (
        db.query(func.count(Subscription.id)).filter(Subscription.status == "active").scalar() or 0
    )

    return {
        "success": True,
        "data": {
            "total_projects": total_projects,
            "projects_by_status": projects_by_status,
            "total_users": total_users,
            "new_users_by_day": new_users_by_day,
            "projects_by_day": projects_by_day,
            "subscription_breakdown": subscription_breakdown,
            "total_active_subscriptions": total_active_subscriptions,
        },
    }


@router.get("/metrics/platform-activity")
def get_platform_activity(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_admin),
    days: int = Query(7, ge=1, le=90),
) -> Dict[str, Any]:
    """Returns platform activity metrics for the given period."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    since = now - timedelta(days=days)

    day_rows = (
        db.query(
            func.date_trunc("day", ProjectActivity.created_at).label("day"),
            func.count(ProjectActivity.id).label("count"),
        )
        .filter(ProjectActivity.created_at >= since)
        .group_by(func.date_trunc("day", ProjectActivity.created_at))
        .order_by(func.date_trunc("day", ProjectActivity.created_at))
        .all()
    )
    activity_by_day: List[Dict[str, Any]] = [
        {"date": row.day.strftime("%Y-%m-%d"), "count": row.count} for row in day_rows
    ]

    type_rows = (
        db.query(ProjectActivity.activity_type, func.count(ProjectActivity.id).label("count"))
        .filter(ProjectActivity.created_at >= since)
        .group_by(ProjectActivity.activity_type)
        .order_by(func.count(ProjectActivity.id).desc())
        .limit(10)
        .all()
    )
    activity_by_type: List[Dict[str, Any]] = [
        {"type": row[0], "count": row[1]} for row in type_rows
    ]

    user_rows = (
        db.query(
            ProjectActivity.user_id,
            User.username,
            func.count(ProjectActivity.id).label("count"),
        )
        .join(User, User.id == ProjectActivity.user_id)
        .filter(ProjectActivity.created_at >= since, ProjectActivity.user_id.isnot(None))
        .group_by(ProjectActivity.user_id, User.username)
        .order_by(func.count(ProjectActivity.id).desc())
        .limit(10)
        .all()
    )
    most_active_users: List[Dict[str, Any]] = [
        {"user_id": str(row[0]), "username": row[1], "count": row[2]} for row in user_rows
    ]

    return {
        "success": True,
        "data": {
            "activity_by_day": activity_by_day,
            "activity_by_type": activity_by_type,
            "most_active_users": most_active_users,
        },
    }


# ============================================================================
# API Performance Metrics (Fase 2)
# ============================================================================


@router.get("/metrics/api-performance")
def get_api_performance(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_admin),
    hours: int = Query(24, ge=1, le=168),
) -> Dict[str, Any]:
    """Returns endpoint performance stats for the given hours window."""
    stats = request_log_crud.get_endpoint_stats_orm(db, hours=hours)
    return {"success": True, "data": {"stats": stats, "hours": hours}}


@router.get("/metrics/errors")
def get_api_errors(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_admin),
    hours: int = Query(24, ge=1, le=168),
) -> Dict[str, Any]:
    """Returns 4xx/5xx error counts grouped by endpoint and status code."""
    errors = request_log_crud.get_error_stats_orm(db, hours=hours)
    return {"success": True, "data": {"errors": errors, "hours": hours}}
