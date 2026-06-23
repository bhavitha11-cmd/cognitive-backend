"""
Migration: add_project_computed_fields
Adds `actual_hours` and `progress` as persisted computed columns on the projects table.
Safe, additive-only — no existing data is modified until the backfill step.
"""
from sqlalchemy import text


def upgrade(engine) -> None:
    """Add new columns. Idempotent — uses ADD COLUMN IF NOT EXISTS."""
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE projects
                ADD COLUMN IF NOT EXISTS actual_hours NUMERIC(10, 2) NOT NULL DEFAULT 0,
                ADD COLUMN IF NOT EXISTS progress     NUMERIC(5, 2)  NOT NULL DEFAULT 0;
        """))
        conn.commit()
    print("[Migration] add_project_computed_fields: upgrade complete.")


def downgrade(engine) -> None:
    """Remove the two columns (data loss — use with care)."""
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE projects
                DROP COLUMN IF EXISTS actual_hours,
                DROP COLUMN IF EXISTS progress;
        """))
        conn.commit()
    print("[Migration] add_project_computed_fields: downgrade complete.")


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    from app.database.connection import engine as _engine
    upgrade(_engine)
