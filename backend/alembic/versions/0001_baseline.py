"""Baseline: esquema completo generado desde los modelos ORM

Unica migracion inicial. Una BD vacia llega al esquema actual con
`alembic upgrade head`, sin dump ni scripts SQL previos.

Revision ID: 0001
Revises:
Create Date: 2026-10-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.create_table('csrf_tokens',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('token', sa.String(length=255), nullable=False),
    sa.Column('session_id', sa.String(length=255), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used', sa.Boolean(), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_csrf_tokens'))
    )
    op.create_index('idx_csrf_tokens_active', 'csrf_tokens', ['used', 'expires_at'], unique=False)
    op.create_index('idx_csrf_tokens_session', 'csrf_tokens', ['session_id'], unique=False, postgresql_where=sa.text('session_id IS NOT NULL'))
    op.create_index(op.f('ix_csrf_tokens_expires_at'), 'csrf_tokens', ['expires_at'], unique=False)
    op.create_index(op.f('ix_csrf_tokens_token'), 'csrf_tokens', ['token'], unique=True)
    op.create_table('security_rate_limits',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('identifier', sa.String(length=255), nullable=False),
    sa.Column('ip_address', sa.String(length=255), nullable=False),
    sa.Column('endpoint', sa.String(length=255), nullable=False),
    sa.Column('request_count', sa.Integer(), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('window_start', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_attempt', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('blocked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_security_rate_limits'))
    )
    op.create_index('idx_security_rate_limits_blocked', 'security_rate_limits', ['blocked_until'], unique=False, postgresql_where=sa.text('blocked_until IS NOT NULL'))
    op.create_index(op.f('ix_security_rate_limits_endpoint'), 'security_rate_limits', ['endpoint'], unique=False)
    op.create_index(op.f('ix_security_rate_limits_identifier'), 'security_rate_limits', ['identifier'], unique=False)
    op.create_index(op.f('ix_security_rate_limits_ip_address'), 'security_rate_limits', ['ip_address'], unique=False)
    op.create_index(op.f('ix_security_rate_limits_updated_at'), 'security_rate_limits', ['updated_at'], unique=False)
    op.create_index(op.f('ix_security_rate_limits_window_start'), 'security_rate_limits', ['window_start'], unique=False)
    op.create_index('unique_identifier_endpoint_window', 'security_rate_limits', ['identifier', 'endpoint', 'window_start'], unique=True)
    op.create_index('unique_ip_endpoint', 'security_rate_limits', ['ip_address', 'endpoint'], unique=True)
    op.create_table('subscription_plans',
    sa.Column('id', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('price_monthly', sa.DECIMAL(precision=10, scale=2), nullable=True),
    sa.Column('price_yearly', sa.DECIMAL(precision=10, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('max_projects', sa.Integer(), nullable=True),
    sa.Column('max_tables', sa.Integer(), nullable=True),
    sa.Column('max_columns_per_table', sa.Integer(), nullable=True),
    sa.Column('stripe_product_id', sa.String(length=255), nullable=True),
    sa.Column('stripe_price_id_monthly', sa.String(length=255), nullable=True),
    sa.Column('stripe_price_id_yearly', sa.String(length=255), nullable=True),
    sa.Column('stripe_secret_key', sa.String(length=500), nullable=True),
    sa.Column('stripe_publishable_key', sa.String(length=500), nullable=True),
    sa.Column('stripe_webhook_secret', sa.String(length=500), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_subscription_plans'))
    )
    op.create_index('idx_subscription_plans_active', 'subscription_plans', ['is_active', 'sort_order'], unique=False)
    op.create_index(op.f('ix_subscription_plans_is_active'), 'subscription_plans', ['is_active'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('username', sa.String(length=100), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('avatar_url', sa.String(length=500), nullable=True),
    sa.Column('totp_secret', sa.String(length=64), nullable=True),
    sa.Column('totp_enabled', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('is_verified', sa.Boolean(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('failed_login_attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_login_ip', sa.String(length=64), nullable=True),
    sa.Column('password_changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index('idx_users_active', 'users', ['is_deleted', 'is_verified'], unique=False)
    op.create_index('idx_users_locked', 'users', ['locked_until'], unique=False, postgresql_where=sa.text('locked_until IS NOT NULL'))
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_is_deleted'), 'users', ['is_deleted'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('api_request_logs',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('method', sa.String(length=10), nullable=False),
    sa.Column('endpoint', sa.String(length=255), nullable=False),
    sa.Column('status_code', sa.Integer(), nullable=False),
    sa.Column('response_time_ms', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_api_request_logs_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_request_logs'))
    )
    op.create_index('idx_api_request_logs_endpoint_status', 'api_request_logs', ['endpoint', 'status_code'], unique=False)
    op.create_index(op.f('ix_api_request_logs_created_at'), 'api_request_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_api_request_logs_endpoint'), 'api_request_logs', ['endpoint'], unique=False)
    op.create_index(op.f('ix_api_request_logs_user_id'), 'api_request_logs', ['user_id'], unique=False)
    op.create_table('email_otps',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('otp_code', sa.Text(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_email_otps_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_email_otps'))
    )
    op.create_index(op.f('ix_email_otps_expires_at'), 'email_otps', ['expires_at'], unique=False)
    op.create_table('project_metrics_history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('date', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=False),
    sa.Column('total_projects', sa.Integer(), nullable=False),
    sa.Column('active_projects', sa.Integer(), nullable=False),
    sa.Column('paused_projects', sa.Integer(), nullable=False),
    sa.Column('completed_projects', sa.Integer(), nullable=False),
    sa.Column('total_budget', sa.DECIMAL(precision=10, scale=2), nullable=False),
    sa.Column('avg_progress', sa.DECIMAL(precision=5, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_project_metrics_history_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_project_metrics_history'))
    )
    op.create_index('idx_metrics_date_range', 'project_metrics_history', ['user_id', 'date'], unique=False)
    op.create_index(op.f('ix_project_metrics_history_date'), 'project_metrics_history', ['date'], unique=False)
    op.create_index(op.f('ix_project_metrics_history_user_id'), 'project_metrics_history', ['user_id'], unique=False)
    op.create_index('uq_metrics_user_date', 'project_metrics_history', ['user_id', 'date'], unique=True)
    op.create_table('projects',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('origin_db', sa.String(length=255), nullable=True),
    sa.Column('destination_db', sa.String(length=255), nullable=True),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=True),
    sa.Column('progress', sa.Integer(), nullable=True),
    sa.Column('budget', sa.DECIMAL(precision=10, scale=2), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_projects_owner_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_projects'))
    )
    op.create_index(op.f('ix_projects_last_accessed_at'), 'projects', ['last_accessed_at'], unique=False)
    op.create_index(op.f('ix_projects_name'), 'projects', ['name'], unique=False)
    op.create_index(op.f('ix_projects_owner_id'), 'projects', ['owner_id'], unique=False)
    op.create_table('security_logs',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('event_type', sa.String(length=100), nullable=False),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('username', sa.String(length=100), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('endpoint', sa.String(length=255), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_security_logs_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_security_logs'))
    )
    op.create_index('idx_security_logs_details', 'security_logs', ['details'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_security_logs_created_at'), 'security_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_security_logs_endpoint'), 'security_logs', ['endpoint'], unique=False)
    op.create_index(op.f('ix_security_logs_event_type'), 'security_logs', ['event_type'], unique=False)
    op.create_index(op.f('ix_security_logs_severity'), 'security_logs', ['severity'], unique=False)
    op.create_index(op.f('ix_security_logs_user_id'), 'security_logs', ['user_id'], unique=False)
    op.create_index(op.f('ix_security_logs_username'), 'security_logs', ['username'], unique=False)
    op.create_table('user_api_keys',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('key_prefix', sa.String(length=8), nullable=False),
    sa.Column('key_hash', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_api_keys_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_api_keys')),
    sa.UniqueConstraint('key_hash', name=op.f('uq_user_api_keys_key_hash'))
    )
    op.create_index('idx_api_keys_expires', 'user_api_keys', ['expires_at'], unique=False, postgresql_where=sa.text('expires_at IS NOT NULL'))
    op.create_index('idx_api_keys_user_active', 'user_api_keys', ['user_id', 'is_active'], unique=False)
    op.create_index(op.f('ix_user_api_keys_user_id'), 'user_api_keys', ['user_id'], unique=False)
    op.create_table('user_preferences',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('language', sa.String(length=10), server_default='es', nullable=False),
    sa.Column('timezone', sa.String(length=64), server_default='UTC', nullable=False),
    sa.Column('default_db_type', sa.String(length=50), nullable=True),
    sa.Column('default_export_format', sa.String(length=20), server_default='xlsx', nullable=False),
    sa.Column('email_notifications', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('in_app_notifications', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_preferences_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_user_preferences'))
    )
    op.create_table('user_sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('session_token', sa.String(length=64), nullable=False),
    sa.Column('refresh_token', sa.String(length=64), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('device_fingerprint', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_activity', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_revoked', sa.Boolean(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_reason', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_sessions'))
    )
    op.create_index('idx_sessions_active', 'user_sessions', ['user_id', 'is_revoked', 'expires_at'], unique=False)
    op.create_index('idx_sessions_expired', 'user_sessions', ['expires_at', 'is_revoked'], unique=False)
    op.create_index('idx_sessions_refresh_token', 'user_sessions', ['refresh_token'], unique=False, postgresql_where=sa.text('refresh_token IS NOT NULL'))
    op.create_index(op.f('ix_user_sessions_expires_at'), 'user_sessions', ['expires_at'], unique=False)
    op.create_index(op.f('ix_user_sessions_is_revoked'), 'user_sessions', ['is_revoked'], unique=False)
    op.create_index(op.f('ix_user_sessions_session_token'), 'user_sessions', ['session_token'], unique=True)
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)
    op.create_table('comments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('entity_type', sa.String(length=50), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('parent_id', sa.UUID(), nullable=True),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('content_encrypted', sa.Text(), nullable=True),
    sa.Column('content_nonce', sa.Text(), nullable=True),
    sa.Column('is_encrypted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_edited', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('is_resolved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('resolved_by', sa.UUID(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('mentions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.CheckConstraint('\n            (content IS NOT NULL AND LENGTH(TRIM(content)) > 0 AND (is_encrypted IS NULL OR is_encrypted = FALSE))\n            OR\n            (content_encrypted IS NOT NULL AND content_nonce IS NOT NULL AND is_encrypted = TRUE)\n            ', name=op.f('ck_comments_check_comment_not_empty')),
    sa.ForeignKeyConstraint(['parent_id'], ['comments.id'], name=op.f('fk_comments_parent_id_comments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_comments_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], name=op.f('fk_comments_resolved_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_comments_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_comments'))
    )
    op.create_index('idx_comments_encrypted', 'comments', ['is_encrypted'], unique=False, postgresql_where=sa.text('is_encrypted = true'))
    op.create_index('idx_comments_entity', 'comments', ['entity_id', 'entity_type', 'created_at'], unique=False)
    op.create_index('idx_comments_parent', 'comments', ['parent_id'], unique=False, postgresql_where=sa.text('parent_id IS NOT NULL'))
    op.create_index('idx_comments_project_encrypted', 'comments', ['project_id', 'is_encrypted'], unique=False)
    op.create_index('idx_comments_unresolved', 'comments', ['project_id', 'is_resolved'], unique=False, postgresql_where=sa.text('is_resolved = false'))
    op.create_index(op.f('ix_comments_created_at'), 'comments', ['created_at'], unique=False)
    op.create_index(op.f('ix_comments_entity_id'), 'comments', ['entity_id'], unique=False)
    op.create_index(op.f('ix_comments_is_encrypted'), 'comments', ['is_encrypted'], unique=False)
    op.create_index(op.f('ix_comments_is_resolved'), 'comments', ['is_resolved'], unique=False)
    op.create_index(op.f('ix_comments_project_id'), 'comments', ['project_id'], unique=False)
    op.create_index(op.f('ix_comments_user_id'), 'comments', ['user_id'], unique=False)
    op.create_table('entity_locks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('entity_type', sa.String(length=50), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('acquired_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_heartbeat', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_entity_locks_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_entity_locks_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_entity_locks'))
    )
    op.create_index('idx_locks_expires', 'entity_locks', ['expires_at'], unique=False)
    op.create_index('idx_locks_project_user', 'entity_locks', ['project_id', 'user_id'], unique=False)
    op.create_index(op.f('ix_entity_locks_entity_id'), 'entity_locks', ['entity_id'], unique=False)
    op.create_index(op.f('ix_entity_locks_expires_at'), 'entity_locks', ['expires_at'], unique=False)
    op.create_index(op.f('ix_entity_locks_project_id'), 'entity_locks', ['project_id'], unique=False)
    op.create_index(op.f('ix_entity_locks_user_id'), 'entity_locks', ['user_id'], unique=False)
    op.create_index('uq_entity_locks_entity', 'entity_locks', ['entity_id', 'entity_type'], unique=True)
    op.create_table('entity_versions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('hash', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=False),
    sa.Column('entity_type', sa.String(length=50), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('change_type', sa.String(length=20), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('snapshot_encrypted', sa.Text(), nullable=True),
    sa.Column('snapshot_nonce', sa.Text(), nullable=True),
    sa.Column('diff', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('diff_encrypted', sa.Text(), nullable=True),
    sa.Column('diff_nonce', sa.Text(), nullable=True),
    sa.Column('is_encrypted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('parent_version_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['parent_version_id'], ['entity_versions.id'], name=op.f('fk_entity_versions_parent_version_id_entity_versions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_entity_versions_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_entity_versions_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_entity_versions'))
    )
    op.create_index('idx_versions_encrypted', 'entity_versions', ['is_encrypted'], unique=False, postgresql_where=sa.text('is_encrypted = true'))
    op.create_index('idx_versions_entity', 'entity_versions', ['entity_id', 'created_at'], unique=False)
    op.create_index('idx_versions_project_encrypted', 'entity_versions', ['project_id', 'is_encrypted'], unique=False)
    op.create_index('idx_versions_project_type', 'entity_versions', ['project_id', 'entity_type'], unique=False)
    op.create_index(op.f('ix_entity_versions_created_at'), 'entity_versions', ['created_at'], unique=False)
    op.create_index(op.f('ix_entity_versions_entity_id'), 'entity_versions', ['entity_id'], unique=False)
    op.create_index(op.f('ix_entity_versions_hash'), 'entity_versions', ['hash'], unique=True)
    op.create_index(op.f('ix_entity_versions_is_encrypted'), 'entity_versions', ['is_encrypted'], unique=False)
    op.create_index(op.f('ix_entity_versions_project_id'), 'entity_versions', ['project_id'], unique=False)
    op.create_index(op.f('ix_entity_versions_user_id'), 'entity_versions', ['user_id'], unique=False)
    op.create_index('uq_entity_versions_entity_version', 'entity_versions', ['entity_id', 'version_number'], unique=True)
    op.create_table('migration_executions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('script_hash', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('rows_migrated', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('backup_id', sa.String(length=255), nullable=True),
    sa.Column('execution_log', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('pending', 'running', 'success', 'failed', 'rolled_back', 'dry_run_complete')", name=op.f('ck_migration_executions_chk_migration_execution_status')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_migration_executions_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_migration_executions_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_migration_executions'))
    )
    op.create_index('idx_migration_executions_project_status', 'migration_executions', ['project_id', 'status'], unique=False)
    op.create_index('idx_migration_executions_started', 'migration_executions', ['started_at'], unique=False)
    op.create_index(op.f('ix_migration_executions_project_id'), 'migration_executions', ['project_id'], unique=False)
    op.create_index(op.f('ix_migration_executions_script_hash'), 'migration_executions', ['script_hash'], unique=False)
    op.create_index(op.f('ix_migration_executions_started_at'), 'migration_executions', ['started_at'], unique=False)
    op.create_index(op.f('ix_migration_executions_status'), 'migration_executions', ['status'], unique=False)
    op.create_table('migration_scripts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('script_content', sa.Text(), nullable=False),
    sa.Column('script_hash', sa.String(length=64), nullable=False),
    sa.Column('batch_size', sa.Integer(), nullable=False),
    sa.Column('include_constraints', sa.Boolean(), nullable=False),
    sa.Column('include_validation', sa.Boolean(), nullable=False),
    sa.Column('dialect', sa.String(length=50), nullable=False),
    sa.Column('dependency_order', postgresql.ARRAY(sa.Text()), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_migration_scripts_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_migration_scripts_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_migration_scripts'))
    )
    op.create_index(op.f('ix_migration_scripts_created_at'), 'migration_scripts', ['created_at'], unique=False)
    op.create_index(op.f('ix_migration_scripts_project_id'), 'migration_scripts', ['project_id'], unique=False)
    op.create_index(op.f('ix_migration_scripts_script_hash'), 'migration_scripts', ['script_hash'], unique=False)
    op.create_table('notifications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('recipient_id', sa.UUID(), nullable=False),
    sa.Column('notification_kind', sa.String(length=50), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=True),
    sa.Column('invitation_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('link_url', sa.String(length=500), nullable=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('actions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_notifications_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], name=op.f('fk_notifications_recipient_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications'))
    )
    op.create_index('idx_notifications_kind', 'notifications', ['notification_kind'], unique=False)
    op.create_index('idx_notifications_project', 'notifications', ['project_id'], unique=False, postgresql_where=sa.text('project_id IS NOT NULL'))
    op.create_index('idx_notifications_read', 'notifications', ['recipient_id', 'read_at'], unique=False, postgresql_where=sa.text('read_at IS NULL'))
    op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)
    op.create_index(op.f('ix_notifications_recipient_id'), 'notifications', ['recipient_id'], unique=False)
    op.create_table('project_activity',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('activity_type', sa.String(length=50), nullable=False),
    sa.Column('entity_id', sa.UUID(), nullable=True),
    sa.Column('entity_type', sa.String(length=50), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_project_activity_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_project_activity_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_project_activity'))
    )
    op.create_index('idx_activity_entity', 'project_activity', ['entity_id', 'entity_type'], unique=False, postgresql_where=sa.text('entity_id IS NOT NULL'))
    op.create_index('idx_activity_project_created', 'project_activity', ['project_id', 'created_at'], unique=False)
    op.create_index('idx_activity_type', 'project_activity', ['activity_type'], unique=False)
    op.create_index('idx_activity_user', 'project_activity', ['user_id'], unique=False, postgresql_where=sa.text('user_id IS NOT NULL'))
    op.create_index(op.f('ix_project_activity_activity_type'), 'project_activity', ['activity_type'], unique=False)
    op.create_index(op.f('ix_project_activity_created_at'), 'project_activity', ['created_at'], unique=False)
    op.create_index(op.f('ix_project_activity_project_id'), 'project_activity', ['project_id'], unique=False)
    op.create_table('project_encryption',
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('master_key_hash', sa.Text(), nullable=False),
    sa.Column('salt_verification', sa.Text(), nullable=False),
    sa.Column('salt_key_derivation', sa.Text(), nullable=False),
    sa.Column('encryption_enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_project_encryption_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('project_id', name=op.f('pk_project_encryption'))
    )
    op.create_index(op.f('ix_project_encryption_encryption_enabled'), 'project_encryption', ['encryption_enabled'], unique=False)
    op.create_table('project_members',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.Enum('owner', 'editor', 'viewer', name='member_role'), nullable=False),
    sa.Column('added_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['added_by'], ['users.id'], name=op.f('fk_project_members_added_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_project_members_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_project_members_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_project_members'))
    )
    op.create_index('idx_project_members_role', 'project_members', ['project_id', 'role'], unique=False)
    op.create_index(op.f('ix_project_members_project_id'), 'project_members', ['project_id'], unique=False)
    op.create_index(op.f('ix_project_members_user_id'), 'project_members', ['user_id'], unique=False)
    op.create_index('uq_project_members_project_user', 'project_members', ['project_id', 'user_id'], unique=True)
    op.create_table('subscriptions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('plan_id', sa.String(length=50), nullable=False),
    sa.Column('stripe_customer_id', sa.String(length=255), nullable=True),
    sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True),
    sa.Column('price_id', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False),
    sa.Column('cancel_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('trial_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('unit_amount', sa.Integer(), nullable=True),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('default_payment_method', sa.String(length=255), nullable=True),
    sa.Column('latest_invoice_id', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['plan_id'], ['subscription_plans.id'], name=op.f('fk_subscriptions_plan_id_subscription_plans')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_subscriptions_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_subscriptions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_subscriptions'))
    )
    op.create_index('idx_subscriptions_status', 'subscriptions', ['status'], unique=False, postgresql_where=sa.text("status IN ('active', 'trialing')"))
    op.create_index('idx_subscriptions_trial', 'subscriptions', ['trial_end'], unique=False, postgresql_where=sa.text('trial_end IS NOT NULL'))
    op.create_index('idx_subscriptions_user_project', 'subscriptions', ['user_id', 'project_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_plan_id'), 'subscriptions', ['plan_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_project_id'), 'subscriptions', ['project_id'], unique=False)
    op.create_index(op.f('ix_subscriptions_stripe_subscription_id'), 'subscriptions', ['stripe_subscription_id'], unique=True)
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=False)
    op.create_table('tables',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('name_encrypted', sa.Text(), nullable=True),
    sa.Column('name_nonce', sa.Text(), nullable=True),
    sa.Column('is_encrypted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('\n            (name IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))\n            OR\n            (name_encrypted IS NOT NULL AND name_nonce IS NOT NULL AND is_encrypted = TRUE)\n            ', name=op.f('ck_tables_check_table_name_or_encrypted')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_tables_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tables'))
    )
    op.create_index('idx_tables_encrypted', 'tables', ['is_encrypted'], unique=False, postgresql_where=sa.text('is_encrypted = true'))
    op.create_index('idx_tables_project_encrypted', 'tables', ['project_id', 'is_encrypted'], unique=False)
    op.create_index('idx_tables_project_type', 'tables', ['project_id', 'type'], unique=False)
    op.create_index(op.f('ix_tables_is_encrypted'), 'tables', ['is_encrypted'], unique=False)
    op.create_index(op.f('ix_tables_project_id'), 'tables', ['project_id'], unique=False)
    op.create_index('uq_tables_project_name_type', 'tables', ['project_id', 'name', 'type'], unique=True, postgresql_where=sa.text('is_encrypted = false'))
    op.create_table('columns',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('table_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('name_encrypted', sa.Text(), nullable=True),
    sa.Column('name_nonce', sa.Text(), nullable=True),
    sa.Column('data_type', sa.String(length=100), nullable=True),
    sa.Column('data_type_encrypted', sa.Text(), nullable=True),
    sa.Column('data_type_nonce', sa.Text(), nullable=True),
    sa.Column('is_encrypted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('table_type', sa.String(length=50), nullable=False),
    sa.Column('is_nullable', sa.Boolean(), nullable=False),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.Column('is_autogenerated', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('\n            (data_type IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))\n            OR\n            (data_type_encrypted IS NOT NULL AND data_type_nonce IS NOT NULL AND is_encrypted = TRUE)\n            ', name=op.f('ck_columns_check_column_datatype_or_encrypted')),
    sa.CheckConstraint('\n            (name IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))\n            OR\n            (name_encrypted IS NOT NULL AND name_nonce IS NOT NULL AND is_encrypted = TRUE)\n            ', name=op.f('ck_columns_check_column_name_or_encrypted')),
    sa.ForeignKeyConstraint(['table_id'], ['tables.id'], name=op.f('fk_columns_table_id_tables'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_columns'))
    )
    op.create_index('idx_columns_encrypted', 'columns', ['is_encrypted'], unique=False, postgresql_where=sa.text('is_encrypted = true'))
    op.create_index('idx_columns_primary', 'columns', ['table_id', 'is_primary'], unique=False, postgresql_where=sa.text('is_primary = true'))
    op.create_index('idx_columns_table_encrypted', 'columns', ['table_id', 'is_encrypted'], unique=False)
    op.create_index(op.f('ix_columns_is_encrypted'), 'columns', ['is_encrypted'], unique=False)
    op.create_index(op.f('ix_columns_table_id'), 'columns', ['table_id'], unique=False)
    op.create_index('uq_columns_table_name', 'columns', ['table_id', 'name'], unique=True, postgresql_where=sa.text('is_encrypted = false'))
    op.create_table('comment_reactions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('comment_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('emoji', sa.String(length=10), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], name=op.f('fk_comment_reactions_comment_id_comments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_comment_reactions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_comment_reactions'))
    )
    op.create_index(op.f('ix_comment_reactions_comment_id'), 'comment_reactions', ['comment_id'], unique=False)
    op.create_index(op.f('ix_comment_reactions_user_id'), 'comment_reactions', ['user_id'], unique=False)
    op.create_index('uq_comment_reactions_comment_user_emoji', 'comment_reactions', ['comment_id', 'user_id', 'emoji'], unique=True)
    op.create_table('comment_reads',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('comment_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['comment_id'], ['comments.id'], name=op.f('fk_comment_reads_comment_id_comments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_comment_reads_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_comment_reads'))
    )
    op.create_index('idx_comment_reads_user_read', 'comment_reads', ['user_id', 'read_at'], unique=False)
    op.create_index(op.f('ix_comment_reads_comment_id'), 'comment_reads', ['comment_id'], unique=False)
    op.create_index(op.f('ix_comment_reads_read_at'), 'comment_reads', ['read_at'], unique=False)
    op.create_index(op.f('ix_comment_reads_user_id'), 'comment_reads', ['user_id'], unique=False)
    op.create_index('uq_comment_reads_comment_user', 'comment_reads', ['comment_id', 'user_id'], unique=True)
    op.create_table('mappings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('origin_source_type', sa.String(length=20), nullable=False),
    sa.Column('origin_table', sa.String(length=255), nullable=True),
    sa.Column('origin_table_encrypted', sa.Text(), nullable=True),
    sa.Column('origin_table_nonce', sa.Text(), nullable=True),
    sa.Column('origin_column', sa.String(length=255), nullable=True),
    sa.Column('origin_column_encrypted', sa.Text(), nullable=True),
    sa.Column('origin_column_nonce', sa.Text(), nullable=True),
    sa.Column('origin_table_hash', sa.String(length=64), nullable=True),
    sa.Column('origin_column_hash', sa.String(length=64), nullable=True),
    sa.Column('origin_session_id', sa.UUID(), nullable=True),
    sa.Column('origin_table_id', sa.UUID(), nullable=True),
    sa.Column('destination_source_type', sa.String(length=20), nullable=False),
    sa.Column('destination_table', sa.String(length=255), nullable=True),
    sa.Column('destination_table_encrypted', sa.Text(), nullable=True),
    sa.Column('destination_table_nonce', sa.Text(), nullable=True),
    sa.Column('destination_column', sa.String(length=255), nullable=True),
    sa.Column('destination_column_encrypted', sa.Text(), nullable=True),
    sa.Column('destination_column_nonce', sa.Text(), nullable=True),
    sa.Column('destination_table_hash', sa.String(length=64), nullable=True),
    sa.Column('destination_column_hash', sa.String(length=64), nullable=True),
    sa.Column('destination_session_id', sa.UUID(), nullable=True),
    sa.Column('destination_table_id', sa.UUID(), nullable=True),
    sa.Column('transformation_logic', sa.Text(), nullable=True),
    sa.Column('transformation_logic_encrypted', sa.Text(), nullable=True),
    sa.Column('transformation_logic_nonce', sa.Text(), nullable=True),
    sa.Column('is_encrypted', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("\n            (destination_column IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))\n            OR\n            (destination_column_encrypted IS NOT NULL AND destination_column_nonce IS NOT NULL AND is_encrypted = TRUE)\n            OR\n            (destination_source_type = 'connector')\n            ", name=op.f('ck_mappings_check_mapping_dest_column_or_encrypted')),
    sa.CheckConstraint("\n            (destination_table IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))\n            OR\n            (destination_table_encrypted IS NOT NULL AND destination_table_nonce IS NOT NULL AND is_encrypted = TRUE)\n            OR\n            (destination_source_type = 'connector')\n            ", name=op.f('ck_mappings_check_mapping_dest_table_or_encrypted')),
    sa.CheckConstraint("\n            (origin_column IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))\n            OR\n            (origin_column_encrypted IS NOT NULL AND origin_column_nonce IS NOT NULL AND is_encrypted = TRUE)\n            OR\n            (origin_source_type = 'connector')\n            ", name=op.f('ck_mappings_check_mapping_origin_column_or_encrypted')),
    sa.CheckConstraint("\n            (origin_table IS NOT NULL AND (is_encrypted IS NULL OR is_encrypted = FALSE))\n            OR\n            (origin_table_encrypted IS NOT NULL AND origin_table_nonce IS NOT NULL AND is_encrypted = TRUE)\n            OR\n            (origin_source_type = 'connector')\n            ", name=op.f('ck_mappings_check_mapping_origin_table_or_encrypted')),
    sa.CheckConstraint("\n            destination_source_type != 'connector' OR (\n                destination_session_id IS NOT NULL AND\n                destination_table_hash IS NOT NULL\n            )\n            ", name=op.f('ck_mappings_chk_destination_connector_requirements')),
    sa.CheckConstraint("\n            destination_source_type != 'import' OR (\n                destination_table_id IS NOT NULL OR\n                destination_table IS NOT NULL OR\n                destination_table_encrypted IS NOT NULL\n            )\n            ", name=op.f('ck_mappings_chk_destination_import_requirements')),
    sa.CheckConstraint("\n            origin_source_type != 'connector' OR (\n                origin_session_id IS NOT NULL AND\n                origin_table_hash IS NOT NULL\n            )\n            ", name=op.f('ck_mappings_chk_origin_connector_requirements')),
    sa.CheckConstraint("\n            origin_source_type != 'import' OR (\n                origin_table_id IS NOT NULL OR\n                origin_table IS NOT NULL OR\n                origin_table_encrypted IS NOT NULL\n            )\n            ", name=op.f('ck_mappings_chk_origin_import_requirements')),
    sa.CheckConstraint("destination_source_type IN ('import', 'connector')", name=op.f('ck_mappings_chk_destination_source_type_values')),
    sa.CheckConstraint("origin_source_type IN ('import', 'connector')", name=op.f('ck_mappings_chk_origin_source_type_values')),
    sa.ForeignKeyConstraint(['destination_table_id'], ['tables.id'], name=op.f('fk_mappings_destination_table_id_tables'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['origin_table_id'], ['tables.id'], name=op.f('fk_mappings_origin_table_id_tables'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_mappings_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_mappings'))
    )
    op.create_index('idx_mappings_destination_hashes', 'mappings', ['destination_table_hash', 'destination_column_hash'], unique=False, postgresql_where=sa.text("destination_source_type = 'connector'"))
    op.create_index('idx_mappings_destination_session_id', 'mappings', ['destination_session_id'], unique=False, postgresql_where=sa.text('destination_session_id IS NOT NULL'))
    op.create_index('idx_mappings_destination_table_id', 'mappings', ['destination_table_id'], unique=False, postgresql_where=sa.text('destination_table_id IS NOT NULL'))
    op.create_index('idx_mappings_encrypted', 'mappings', ['is_encrypted'], unique=False, postgresql_where=sa.text('is_encrypted = true'))
    op.create_index('idx_mappings_origin_hashes', 'mappings', ['origin_table_hash', 'origin_column_hash'], unique=False, postgresql_where=sa.text("origin_source_type = 'connector'"))
    op.create_index('idx_mappings_origin_session_id', 'mappings', ['origin_session_id'], unique=False, postgresql_where=sa.text('origin_session_id IS NOT NULL'))
    op.create_index('idx_mappings_origin_table_id', 'mappings', ['origin_table_id'], unique=False, postgresql_where=sa.text('origin_table_id IS NOT NULL'))
    op.create_index('idx_mappings_project_encrypted', 'mappings', ['project_id', 'is_encrypted'], unique=False)
    op.create_index('idx_mappings_project_modes', 'mappings', ['project_id', 'origin_source_type', 'destination_source_type'], unique=False)
    op.create_index(op.f('ix_mappings_destination_source_type'), 'mappings', ['destination_source_type'], unique=False)
    op.create_index(op.f('ix_mappings_is_encrypted'), 'mappings', ['is_encrypted'], unique=False)
    op.create_index(op.f('ix_mappings_origin_source_type'), 'mappings', ['origin_source_type'], unique=False)
    op.create_index(op.f('ix_mappings_project_id'), 'mappings', ['project_id'], unique=False)
    op.create_table('migration_audit_log',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('migration_number', sa.String(length=20), nullable=False),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('table_id', sa.UUID(), nullable=True),
    sa.Column('column_id', sa.UUID(), nullable=True),
    sa.Column('project_id', sa.UUID(), nullable=True),
    sa.Column('old_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('new_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('validation_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('backup_reference', sa.String(length=255), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ip_address', sa.String(length=50), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_migration_audit_log_project_id_projects'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['table_id'], ['tables.id'], name=op.f('fk_migration_audit_log_table_id_tables'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_migration_audit_log_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_migration_audit_log'))
    )
    op.create_index('idx_audit_migration_action', 'migration_audit_log', ['migration_number', 'action'], unique=False)
    op.create_index('idx_audit_table_id', 'migration_audit_log', ['table_id'], unique=False, postgresql_where=sa.text('table_id IS NOT NULL'))
    op.create_index('idx_audit_user_id', 'migration_audit_log', ['user_id'], unique=False, postgresql_where=sa.text('user_id IS NOT NULL'))
    op.create_index(op.f('ix_migration_audit_log_migration_number'), 'migration_audit_log', ['migration_number'], unique=False)
    op.create_index(op.f('ix_migration_audit_log_timestamp'), 'migration_audit_log', ['timestamp'], unique=False)
    op.create_table('primary_key_constraints',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('table_id', sa.UUID(), nullable=False),
    sa.Column('column_ids', postgresql.ARRAY(sa.UUID()), nullable=False),
    sa.Column('constraint_name', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('array_length(column_ids, 1) >= 1', name=op.f('ck_primary_key_constraints_pk_at_least_one_column')),
    sa.ForeignKeyConstraint(['table_id'], ['tables.id'], name=op.f('fk_primary_key_constraints_table_id_tables'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_primary_key_constraints'))
    )
    op.create_index('idx_pk_constraints_column_ids', 'primary_key_constraints', ['column_ids'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_primary_key_constraints_table_id'), 'primary_key_constraints', ['table_id'], unique=True)
    op.create_table('version_tags',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('version_id', sa.UUID(), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('color', sa.String(length=7), nullable=True),
    sa.Column('created_by', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_version_tags_created_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_version_tags_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['version_id'], ['entity_versions.id'], name=op.f('fk_version_tags_version_id_entity_versions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_version_tags'))
    )
    op.create_index(op.f('ix_version_tags_project_id'), 'version_tags', ['project_id'], unique=False)
    op.create_index(op.f('ix_version_tags_version_id'), 'version_tags', ['version_id'], unique=False)
    op.create_index('uq_version_tags_project_name', 'version_tags', ['project_id', 'name'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_version_tags_project_name', table_name='version_tags')
    op.drop_index(op.f('ix_version_tags_version_id'), table_name='version_tags')
    op.drop_index(op.f('ix_version_tags_project_id'), table_name='version_tags')
    op.drop_table('version_tags')
    op.drop_index(op.f('ix_primary_key_constraints_table_id'), table_name='primary_key_constraints')
    op.drop_index('idx_pk_constraints_column_ids', table_name='primary_key_constraints', postgresql_using='gin')
    op.drop_table('primary_key_constraints')
    op.drop_index(op.f('ix_migration_audit_log_timestamp'), table_name='migration_audit_log')
    op.drop_index(op.f('ix_migration_audit_log_migration_number'), table_name='migration_audit_log')
    op.drop_index('idx_audit_user_id', table_name='migration_audit_log', postgresql_where=sa.text('user_id IS NOT NULL'))
    op.drop_index('idx_audit_table_id', table_name='migration_audit_log', postgresql_where=sa.text('table_id IS NOT NULL'))
    op.drop_index('idx_audit_migration_action', table_name='migration_audit_log')
    op.drop_table('migration_audit_log')
    op.drop_index(op.f('ix_mappings_project_id'), table_name='mappings')
    op.drop_index(op.f('ix_mappings_origin_source_type'), table_name='mappings')
    op.drop_index(op.f('ix_mappings_is_encrypted'), table_name='mappings')
    op.drop_index(op.f('ix_mappings_destination_source_type'), table_name='mappings')
    op.drop_index('idx_mappings_project_modes', table_name='mappings')
    op.drop_index('idx_mappings_project_encrypted', table_name='mappings')
    op.drop_index('idx_mappings_origin_table_id', table_name='mappings', postgresql_where=sa.text('origin_table_id IS NOT NULL'))
    op.drop_index('idx_mappings_origin_session_id', table_name='mappings', postgresql_where=sa.text('origin_session_id IS NOT NULL'))
    op.drop_index('idx_mappings_origin_hashes', table_name='mappings', postgresql_where=sa.text("origin_source_type = 'connector'"))
    op.drop_index('idx_mappings_encrypted', table_name='mappings', postgresql_where=sa.text('is_encrypted = true'))
    op.drop_index('idx_mappings_destination_table_id', table_name='mappings', postgresql_where=sa.text('destination_table_id IS NOT NULL'))
    op.drop_index('idx_mappings_destination_session_id', table_name='mappings', postgresql_where=sa.text('destination_session_id IS NOT NULL'))
    op.drop_index('idx_mappings_destination_hashes', table_name='mappings', postgresql_where=sa.text("destination_source_type = 'connector'"))
    op.drop_table('mappings')
    op.drop_index('uq_comment_reads_comment_user', table_name='comment_reads')
    op.drop_index(op.f('ix_comment_reads_user_id'), table_name='comment_reads')
    op.drop_index(op.f('ix_comment_reads_read_at'), table_name='comment_reads')
    op.drop_index(op.f('ix_comment_reads_comment_id'), table_name='comment_reads')
    op.drop_index('idx_comment_reads_user_read', table_name='comment_reads')
    op.drop_table('comment_reads')
    op.drop_index('uq_comment_reactions_comment_user_emoji', table_name='comment_reactions')
    op.drop_index(op.f('ix_comment_reactions_user_id'), table_name='comment_reactions')
    op.drop_index(op.f('ix_comment_reactions_comment_id'), table_name='comment_reactions')
    op.drop_table('comment_reactions')
    op.drop_index('uq_columns_table_name', table_name='columns', postgresql_where=sa.text('is_encrypted = false'))
    op.drop_index(op.f('ix_columns_table_id'), table_name='columns')
    op.drop_index(op.f('ix_columns_is_encrypted'), table_name='columns')
    op.drop_index('idx_columns_table_encrypted', table_name='columns')
    op.drop_index('idx_columns_primary', table_name='columns', postgresql_where=sa.text('is_primary = true'))
    op.drop_index('idx_columns_encrypted', table_name='columns', postgresql_where=sa.text('is_encrypted = true'))
    op.drop_table('columns')
    op.drop_index('uq_tables_project_name_type', table_name='tables', postgresql_where=sa.text('is_encrypted = false'))
    op.drop_index(op.f('ix_tables_project_id'), table_name='tables')
    op.drop_index(op.f('ix_tables_is_encrypted'), table_name='tables')
    op.drop_index('idx_tables_project_type', table_name='tables')
    op.drop_index('idx_tables_project_encrypted', table_name='tables')
    op.drop_index('idx_tables_encrypted', table_name='tables', postgresql_where=sa.text('is_encrypted = true'))
    op.drop_table('tables')
    op.drop_index(op.f('ix_subscriptions_user_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_stripe_subscription_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_project_id'), table_name='subscriptions')
    op.drop_index(op.f('ix_subscriptions_plan_id'), table_name='subscriptions')
    op.drop_index('idx_subscriptions_user_project', table_name='subscriptions')
    op.drop_index('idx_subscriptions_trial', table_name='subscriptions', postgresql_where=sa.text('trial_end IS NOT NULL'))
    op.drop_index('idx_subscriptions_status', table_name='subscriptions', postgresql_where=sa.text("status IN ('active', 'trialing')"))
    op.drop_table('subscriptions')
    op.drop_index('uq_project_members_project_user', table_name='project_members')
    op.drop_index(op.f('ix_project_members_user_id'), table_name='project_members')
    op.drop_index(op.f('ix_project_members_project_id'), table_name='project_members')
    op.drop_index('idx_project_members_role', table_name='project_members')
    op.drop_table('project_members')
    op.drop_index(op.f('ix_project_encryption_encryption_enabled'), table_name='project_encryption')
    op.drop_table('project_encryption')
    op.drop_index(op.f('ix_project_activity_project_id'), table_name='project_activity')
    op.drop_index(op.f('ix_project_activity_created_at'), table_name='project_activity')
    op.drop_index(op.f('ix_project_activity_activity_type'), table_name='project_activity')
    op.drop_index('idx_activity_user', table_name='project_activity', postgresql_where=sa.text('user_id IS NOT NULL'))
    op.drop_index('idx_activity_type', table_name='project_activity')
    op.drop_index('idx_activity_project_created', table_name='project_activity')
    op.drop_index('idx_activity_entity', table_name='project_activity', postgresql_where=sa.text('entity_id IS NOT NULL'))
    op.drop_table('project_activity')
    op.drop_index(op.f('ix_notifications_recipient_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_created_at'), table_name='notifications')
    op.drop_index('idx_notifications_read', table_name='notifications', postgresql_where=sa.text('read_at IS NULL'))
    op.drop_index('idx_notifications_project', table_name='notifications', postgresql_where=sa.text('project_id IS NOT NULL'))
    op.drop_index('idx_notifications_kind', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_migration_scripts_script_hash'), table_name='migration_scripts')
    op.drop_index(op.f('ix_migration_scripts_project_id'), table_name='migration_scripts')
    op.drop_index(op.f('ix_migration_scripts_created_at'), table_name='migration_scripts')
    op.drop_table('migration_scripts')
    op.drop_index(op.f('ix_migration_executions_status'), table_name='migration_executions')
    op.drop_index(op.f('ix_migration_executions_started_at'), table_name='migration_executions')
    op.drop_index(op.f('ix_migration_executions_script_hash'), table_name='migration_executions')
    op.drop_index(op.f('ix_migration_executions_project_id'), table_name='migration_executions')
    op.drop_index('idx_migration_executions_started', table_name='migration_executions')
    op.drop_index('idx_migration_executions_project_status', table_name='migration_executions')
    op.drop_table('migration_executions')
    op.drop_index('uq_entity_versions_entity_version', table_name='entity_versions')
    op.drop_index(op.f('ix_entity_versions_user_id'), table_name='entity_versions')
    op.drop_index(op.f('ix_entity_versions_project_id'), table_name='entity_versions')
    op.drop_index(op.f('ix_entity_versions_is_encrypted'), table_name='entity_versions')
    op.drop_index(op.f('ix_entity_versions_hash'), table_name='entity_versions')
    op.drop_index(op.f('ix_entity_versions_entity_id'), table_name='entity_versions')
    op.drop_index(op.f('ix_entity_versions_created_at'), table_name='entity_versions')
    op.drop_index('idx_versions_project_type', table_name='entity_versions')
    op.drop_index('idx_versions_project_encrypted', table_name='entity_versions')
    op.drop_index('idx_versions_entity', table_name='entity_versions')
    op.drop_index('idx_versions_encrypted', table_name='entity_versions', postgresql_where=sa.text('is_encrypted = true'))
    op.drop_table('entity_versions')
    op.drop_index('uq_entity_locks_entity', table_name='entity_locks')
    op.drop_index(op.f('ix_entity_locks_user_id'), table_name='entity_locks')
    op.drop_index(op.f('ix_entity_locks_project_id'), table_name='entity_locks')
    op.drop_index(op.f('ix_entity_locks_expires_at'), table_name='entity_locks')
    op.drop_index(op.f('ix_entity_locks_entity_id'), table_name='entity_locks')
    op.drop_index('idx_locks_project_user', table_name='entity_locks')
    op.drop_index('idx_locks_expires', table_name='entity_locks')
    op.drop_table('entity_locks')
    op.drop_index(op.f('ix_comments_user_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_project_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_is_resolved'), table_name='comments')
    op.drop_index(op.f('ix_comments_is_encrypted'), table_name='comments')
    op.drop_index(op.f('ix_comments_entity_id'), table_name='comments')
    op.drop_index(op.f('ix_comments_created_at'), table_name='comments')
    op.drop_index('idx_comments_unresolved', table_name='comments', postgresql_where=sa.text('is_resolved = false'))
    op.drop_index('idx_comments_project_encrypted', table_name='comments')
    op.drop_index('idx_comments_parent', table_name='comments', postgresql_where=sa.text('parent_id IS NOT NULL'))
    op.drop_index('idx_comments_entity', table_name='comments')
    op.drop_index('idx_comments_encrypted', table_name='comments', postgresql_where=sa.text('is_encrypted = true'))
    op.drop_table('comments')
    op.drop_index(op.f('ix_user_sessions_user_id'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_session_token'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_is_revoked'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_expires_at'), table_name='user_sessions')
    op.drop_index('idx_sessions_refresh_token', table_name='user_sessions', postgresql_where=sa.text('refresh_token IS NOT NULL'))
    op.drop_index('idx_sessions_expired', table_name='user_sessions')
    op.drop_index('idx_sessions_active', table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_table('user_preferences')
    op.drop_index(op.f('ix_user_api_keys_user_id'), table_name='user_api_keys')
    op.drop_index('idx_api_keys_user_active', table_name='user_api_keys')
    op.drop_index('idx_api_keys_expires', table_name='user_api_keys', postgresql_where=sa.text('expires_at IS NOT NULL'))
    op.drop_table('user_api_keys')
    op.drop_index(op.f('ix_security_logs_username'), table_name='security_logs')
    op.drop_index(op.f('ix_security_logs_user_id'), table_name='security_logs')
    op.drop_index(op.f('ix_security_logs_severity'), table_name='security_logs')
    op.drop_index(op.f('ix_security_logs_event_type'), table_name='security_logs')
    op.drop_index(op.f('ix_security_logs_endpoint'), table_name='security_logs')
    op.drop_index(op.f('ix_security_logs_created_at'), table_name='security_logs')
    op.drop_index('idx_security_logs_details', table_name='security_logs', postgresql_using='gin')
    op.drop_table('security_logs')
    op.drop_index(op.f('ix_projects_owner_id'), table_name='projects')
    op.drop_index(op.f('ix_projects_name'), table_name='projects')
    op.drop_index(op.f('ix_projects_last_accessed_at'), table_name='projects')
    op.drop_table('projects')
    op.drop_index('uq_metrics_user_date', table_name='project_metrics_history')
    op.drop_index(op.f('ix_project_metrics_history_user_id'), table_name='project_metrics_history')
    op.drop_index(op.f('ix_project_metrics_history_date'), table_name='project_metrics_history')
    op.drop_index('idx_metrics_date_range', table_name='project_metrics_history')
    op.drop_table('project_metrics_history')
    op.drop_index(op.f('ix_email_otps_expires_at'), table_name='email_otps')
    op.drop_table('email_otps')
    op.drop_index(op.f('ix_api_request_logs_user_id'), table_name='api_request_logs')
    op.drop_index(op.f('ix_api_request_logs_endpoint'), table_name='api_request_logs')
    op.drop_index(op.f('ix_api_request_logs_created_at'), table_name='api_request_logs')
    op.drop_index('idx_api_request_logs_endpoint_status', table_name='api_request_logs')
    op.drop_table('api_request_logs')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_is_deleted'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index('idx_users_locked', table_name='users', postgresql_where=sa.text('locked_until IS NOT NULL'))
    op.drop_index('idx_users_active', table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_subscription_plans_is_active'), table_name='subscription_plans')
    op.drop_index('idx_subscription_plans_active', table_name='subscription_plans')
    op.drop_table('subscription_plans')
    op.drop_index('unique_ip_endpoint', table_name='security_rate_limits')
    op.drop_index('unique_identifier_endpoint_window', table_name='security_rate_limits')
    op.drop_index(op.f('ix_security_rate_limits_window_start'), table_name='security_rate_limits')
    op.drop_index(op.f('ix_security_rate_limits_updated_at'), table_name='security_rate_limits')
    op.drop_index(op.f('ix_security_rate_limits_ip_address'), table_name='security_rate_limits')
    op.drop_index(op.f('ix_security_rate_limits_identifier'), table_name='security_rate_limits')
    op.drop_index(op.f('ix_security_rate_limits_endpoint'), table_name='security_rate_limits')
    op.drop_index('idx_security_rate_limits_blocked', table_name='security_rate_limits', postgresql_where=sa.text('blocked_until IS NOT NULL'))
    op.drop_table('security_rate_limits')
    op.drop_index(op.f('ix_csrf_tokens_token'), table_name='csrf_tokens')
    op.drop_index(op.f('ix_csrf_tokens_expires_at'), table_name='csrf_tokens')
    op.drop_index('idx_csrf_tokens_session', table_name='csrf_tokens', postgresql_where=sa.text('session_id IS NOT NULL'))
    op.drop_index('idx_csrf_tokens_active', table_name='csrf_tokens')
    op.drop_table('csrf_tokens')
    op.execute('DROP TYPE IF EXISTS member_role')
