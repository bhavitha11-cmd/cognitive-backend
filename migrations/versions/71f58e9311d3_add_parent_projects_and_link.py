"""add_parent_projects_and_link

Revision ID: 71f58e9311d3
Revises: 307fa2ef02ca
Create Date: 2026-07-08 21:24:52.248675

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '71f58e9311d3'
down_revision: Union[str, Sequence[str], None] = '307fa2ef02ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create parent_projects table
    op.create_table(
        'parent_projects',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('client_id', sa.UUID(), nullable=False),
        sa.Column('project_manager_id', sa.UUID(), nullable=True),
        sa.Column('department_id', sa.UUID(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='Yet To Start'),
        sa.Column('progress', sa.Numeric(precision=5, scale=2), nullable=False, server_default='0'),
        sa.Column('planned_start_date', sa.Date(), nullable=True),
        sa.Column('planned_end_date', sa.Date(), nullable=True),
        sa.Column('actual_start_date', sa.Date(), nullable=True),
        sa.Column('actual_end_date', sa.Date(), nullable=True),
        sa.Column('estimated_hours', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0'),
        sa.Column('actual_hours', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_manager_id'], ['employees.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['employees.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_parent_projects_client_id', 'parent_projects', ['client_id'], unique=False)
    op.create_index('ix_parent_projects_project_manager_id', 'parent_projects', ['project_manager_id'], unique=False)
    op.create_index('ix_parent_projects_department_id', 'parent_projects', ['department_id'], unique=False)
    op.create_index('ix_parent_projects_is_active', 'parent_projects', ['is_active'], unique=False)

    # 2. Add parent_project_id to projects
    op.add_column('projects', sa.Column('parent_project_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_projects_parent_project_id',
        'projects', 'parent_projects',
        ['parent_project_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_index('ix_projects_parent_project_id', 'projects', ['parent_project_id'], unique=False)

    # 3. Backfill data
    connection = op.get_bind()
    projects = connection.execute(
        sa.text("SELECT id, name, client_id, project_manager_id, department_id, created_by, is_active, created_at, updated_at FROM projects")
    ).fetchall()

    import uuid
    # Group by name
    groups = {}
    for p in projects:
        name = p[1]
        if name not in groups:
            groups[name] = []
        groups[name].append(p)

    for name, p_list in groups.items():
        first = p_list[0]
        p_id = str(uuid.uuid4())
        connection.execute(
            sa.text(
                "INSERT INTO parent_projects (id, name, client_id, project_manager_id, department_id, created_by, is_active, created_at, updated_at) "
                "VALUES (:id, :name, :client_id, :project_manager_id, :department_id, :created_by, :is_active, :created_at, :updated_at)"
            ),
            {
                "id": p_id,
                "name": name,
                "client_id": first[2],
                "project_manager_id": first[3],
                "department_id": first[4],
                "created_by": first[5],
                "is_active": first[6],
                "created_at": first[7],
                "updated_at": first[8]
            }
        )
        for p in p_list:
            connection.execute(
                sa.text("UPDATE projects SET parent_project_id = :parent_project_id WHERE id = :id"),
                {"parent_project_id": p_id, "id": p[0]}
            )


def downgrade() -> None:
    # Remove parent_project_id from projects
    op.drop_constraint('fk_projects_parent_project_id', 'projects', type_='foreignkey')
    op.drop_index('ix_projects_parent_project_id', table_name='projects')
    op.drop_column('projects', 'parent_project_id')

    # Drop parent_projects table
    op.drop_index('ix_parent_projects_is_active', table_name='parent_projects')
    op.drop_index('ix_parent_projects_department_id', table_name='parent_projects')
    op.drop_index('ix_parent_projects_project_manager_id', table_name='parent_projects')
    op.drop_index('ix_parent_projects_client_id', table_name='parent_projects')
    op.drop_table('parent_projects')

