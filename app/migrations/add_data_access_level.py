"""
Migration: Add data_access_level column to roles table.
Run this script once to add the RBAC data access level column.

Usage:
    python -m app.migrations.add_data_access_level
"""

from sqlalchemy import text
from app.database.session import SessionLocal


def migrate():
    db = SessionLocal()
    try:
        # Add column if not exists
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'roles' AND column_name = 'data_access_level'
                ) THEN
                    ALTER TABLE roles ADD COLUMN data_access_level VARCHAR(20) NOT NULL DEFAULT 'SELF';
                END IF;
            END $$;
        """))

        # Seed super-admin roles to FULL access
        db.execute(text("""
            UPDATE roles
            SET data_access_level = 'FULL'
            WHERE role_code IN ('ADMIN', 'CEO', 'CHIEF_EXECUTIVE_OFFICER', 'ADMINISTRATOR')
               OR is_super_admin = TRUE;
        """))

        db.commit()
        print("[OK] Migration complete: data_access_level column added and admin roles seeded.")
    except Exception as e:
        db.rollback()
        print(f"[FAIL] Migration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
