"""biometric_module_initial

Revision ID: b1a2c3d4e5f6
Revises: fc4997eeec63
Create Date: 2026-07-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b1a2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'fc4997eeec63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. bm_devices
    op.create_table(
        'bm_devices',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('branch', sa.String(length=100), nullable=True),
        sa.Column('device_name', sa.String(length=100), nullable=False),
        sa.Column('vendor', sa.String(length=50), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('serial_number', sa.String(length=100), nullable=True),
        sa.Column('timezone', sa.String(length=50), server_default='Asia/Kolkata', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='ACTIVE', nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('serial_number')
    )
    op.create_index(op.f('ix_bm_devices_organization_id'), 'bm_devices', ['organization_id'], unique=False)
    op.create_index(op.f('ix_bm_devices_vendor'), 'bm_devices', ['vendor'], unique=False)
    op.create_index(op.f('ix_bm_devices_status'), 'bm_devices', ['status'], unique=False)
    op.create_index(op.f('ix_bm_devices_is_active'), 'bm_devices', ['is_active'], unique=False)

    # 2. bm_sync_history
    op.create_table(
        'bm_sync_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sync_type', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('records_read', sa.Integer(), server_default='0', nullable=False),
        sa.Column('records_saved', sa.Integer(), server_default='0', nullable=False),
        sa.Column('duplicates_found', sa.Integer(), server_default='0', nullable=False),
        sa.Column('errors_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='RUNNING', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('checkpoint_data', sa.JSON(), nullable=True),
        sa.Column('triggered_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('duration_seconds', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['bm_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bm_sync_history_device_id'), 'bm_sync_history', ['device_id'], unique=False)
    op.create_index(op.f('ix_bm_sync_history_sync_type'), 'bm_sync_history', ['sync_type'], unique=False)
    op.create_index(op.f('ix_bm_sync_history_started_at'), 'bm_sync_history', ['started_at'], unique=False)
    op.create_index(op.f('ix_bm_sync_history_status'), 'bm_sync_history', ['status'], unique=False)

    # 3. bm_connection_profiles
    op.create_table(
        'bm_connection_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connection_type', sa.String(length=20), nullable=False),
        sa.Column('config_encrypted', sa.Text(), nullable=False),
        sa.Column('is_primary', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['bm_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 4. bm_employee_mappings
    op.create_table(
        'bm_employee_mappings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('biometric_user_id', sa.String(length=50), nullable=False),
        sa.Column('mapping_method', sa.String(length=20), server_default='MANUAL', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('mapped_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('mapped_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['bm_devices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_id', 'biometric_user_id', name='uq_bm_mapping_device_user'),
        sa.UniqueConstraint('employee_id', 'device_id', name='uq_bm_mapping_employee_device')
    )
    op.create_index(op.f('ix_bm_employee_mappings_biometric_user_id'), 'bm_employee_mappings', ['biometric_user_id'], unique=False)
    op.create_index(op.f('ix_bm_employee_mappings_device_id'), 'bm_employee_mappings', ['device_id'], unique=False)
    op.create_index(op.f('ix_bm_employee_mappings_employee_id'), 'bm_employee_mappings', ['employee_id'], unique=False)

    # 5. bm_raw_logs
    op.create_table(
        'bm_raw_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_mapping_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('device_user_id', sa.String(length=50), nullable=False),
        sa.Column('punch_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('verification_type', sa.String(length=30), nullable=True),
        sa.Column('punch_type', sa.String(length=20), nullable=True),
        sa.Column('raw_payload', sa.JSON(), nullable=False),
        sa.Column('source', sa.String(length=30), server_default='SYNC', nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_duplicate', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('sync_history_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['bm_devices.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['employee_mapping_id'], ['bm_employee_mappings.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sync_history_id'], ['bm_sync_history.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_id', 'device_user_id', 'punch_timestamp', name='uq_bm_raw_log_unique_punch')
    )
    op.create_index('ix_bm_raw_logs_device_timestamp', 'bm_raw_logs', ['device_id', 'punch_timestamp'], unique=False)
    op.create_index(op.f('ix_bm_raw_logs_device_user_id'), 'bm_raw_logs', ['device_user_id'], unique=False)
    op.create_index(op.f('ix_bm_raw_logs_is_duplicate'), 'bm_raw_logs', ['is_duplicate'], unique=False)
    op.create_index(op.f('ix_bm_raw_logs_punch_timestamp'), 'bm_raw_logs', ['punch_timestamp'], unique=False)
    op.create_index(op.f('ix_bm_raw_logs_sync_history_id'), 'bm_raw_logs', ['sync_history_id'], unique=False)

    # 6. bm_normalized_logs
    op.create_table(
        'bm_normalized_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('raw_log_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('employee_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('punch_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('punch_type', sa.String(length=20), nullable=False),
        sa.Column('verification_type', sa.String(length=30), nullable=True),
        sa.Column('normalized_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('processing_status', sa.String(length=20), server_default='PENDING', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('attendance_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['bm_devices.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['raw_log_id'], ['bm_raw_logs.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('raw_log_id')
    )
    op.create_index('ix_bm_norm_logs_emp_time', 'bm_normalized_logs', ['employee_id', 'punch_timestamp'], unique=False)
    op.create_index(op.f('ix_bm_normalized_logs_device_id'), 'bm_normalized_logs', ['device_id'], unique=False)
    op.create_index(op.f('ix_bm_normalized_logs_processing_status'), 'bm_normalized_logs', ['processing_status'], unique=False)
    op.create_index(op.f('ix_bm_normalized_logs_punch_type'), 'bm_normalized_logs', ['punch_type'], unique=False)

    # 7. bm_device_health
    op.create_table(
        'bm_device_health',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('firmware_version', sa.String(length=50), nullable=True),
        sa.Column('storage_used_pct', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('registered_users_count', sa.Integer(), nullable=True),
        sa.Column('connection_status', sa.String(length=20), server_default='UNKNOWN', nullable=False),
        sa.Column('last_successful_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('raw_health_data', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['bm_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_id')
    )

    # 8. bm_sync_configs
    op.create_table(
        'bm_sync_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_auto_sync', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('sync_interval_minutes', sa.Integer(), server_default='30', nullable=False),
        sa.Column('sync_schedule', sa.String(length=100), nullable=True),
        sa.Column('batch_size', sa.Integer(), server_default='500', nullable=False),
        sa.Column('lookback_days', sa.Integer(), server_default='7', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['bm_devices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_id')
    )

    # 9. bm_audit_logs
    op.create_table(
        'bm_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('changes', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bm_audit_logs_actor_id'), 'bm_audit_logs', ['actor_id'], unique=False)
    op.create_index(op.f('ix_bm_audit_logs_created_at'), 'bm_audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_bm_audit_logs_entity_id'), 'bm_audit_logs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_bm_audit_logs_entity_type'), 'bm_audit_logs', ['entity_type'], unique=False)


def downgrade() -> None:
    # Reverse order
    op.drop_table('bm_audit_logs')
    op.drop_table('bm_sync_configs')
    op.drop_table('bm_device_health')
    op.drop_table('bm_normalized_logs')
    op.drop_table('bm_raw_logs')
    op.drop_table('bm_employee_mappings')
    op.drop_table('bm_connection_profiles')
    op.drop_table('bm_sync_history')
    op.drop_table('bm_devices')
