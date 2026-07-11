"""create_missing_migration_tables

Revision ID: 80e2f6c70828
Revises: 3892bafdb259
Create Date: 2026-04-22 13:46:34.247921

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '80e2f6c70828'
down_revision: Union[str, None] = '3892bafdb259'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'migration_executions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('script_hash', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('rows_migrated', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('backup_id', sa.String(length=255), nullable=True),
        sa.Column('execution_log', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'success', 'failed', 'rolled_back', 'dry_run_complete')",
            name=op.f('ck_migration_executions_chk_migration_execution_status'),
        ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_migration_executions_created_by_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_migration_executions_project_id_projects'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_migration_executions')),
    )
    op.create_index('idx_migration_executions_project_status', 'migration_executions', ['project_id', 'status'], unique=False)
    op.create_index('idx_migration_executions_started', 'migration_executions', ['started_at'], unique=False)
    op.create_index(op.f('ix_migration_executions_project_id'), 'migration_executions', ['project_id'], unique=False)
    op.create_index(op.f('ix_migration_executions_script_hash'), 'migration_executions', ['script_hash'], unique=False)
    op.create_index(op.f('ix_migration_executions_started_at'), 'migration_executions', ['started_at'], unique=False)
    op.create_index(op.f('ix_migration_executions_status'), 'migration_executions', ['status'], unique=False)

    op.create_table(
        'migration_scripts',
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
        sa.PrimaryKeyConstraint('id', name=op.f('pk_migration_scripts')),
    )
    op.create_index(op.f('ix_migration_scripts_created_at'), 'migration_scripts', ['created_at'], unique=False)
    op.create_index(op.f('ix_migration_scripts_project_id'), 'migration_scripts', ['project_id'], unique=False)
    op.create_index(op.f('ix_migration_scripts_script_hash'), 'migration_scripts', ['script_hash'], unique=False)

    op.create_table(
        'migration_audit_log',
        sa.Column('id', sa.UUID(), nullable=False),
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
        sa.PrimaryKeyConstraint('id', name=op.f('pk_migration_audit_log')),
    )
    op.create_index('idx_audit_migration_action', 'migration_audit_log', ['migration_number', 'action'], unique=False)
    op.create_index('idx_audit_table_id', 'migration_audit_log', ['table_id'], unique=False, postgresql_where=sa.text('table_id IS NOT NULL'))
    op.create_index('idx_audit_user_id', 'migration_audit_log', ['user_id'], unique=False, postgresql_where=sa.text('user_id IS NOT NULL'))
    op.create_index(op.f('ix_migration_audit_log_migration_number'), 'migration_audit_log', ['migration_number'], unique=False)
    op.create_index(op.f('ix_migration_audit_log_timestamp'), 'migration_audit_log', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_migration_audit_log_timestamp'), table_name='migration_audit_log')
    op.drop_index(op.f('ix_migration_audit_log_migration_number'), table_name='migration_audit_log')
    op.drop_index('idx_audit_user_id', table_name='migration_audit_log')
    op.drop_index('idx_audit_table_id', table_name='migration_audit_log')
    op.drop_index('idx_audit_migration_action', table_name='migration_audit_log')
    op.drop_table('migration_audit_log')

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
