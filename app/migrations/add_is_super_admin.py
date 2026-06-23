"""
Migration: Add is_super_admin column to roles table.
Run this script once to add the is_super_admin boolean column.

Usage:
    python -m app.migrations.add_is_super_admin
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
                    WHERE table_name = 'roles' AND column_name = 'is_super_admin'
                ) THEN
                    ALTER TABLE roles ADD COLUMN is_super_admin BOOLEAN NOT NULL DEFAULT FALSE;
                END IF;
            END $$;
        """))
        db.commit()
        print("[OK] Migration complete: is_super_admin column added to roles table.")
    except Exception as e:
        db.rollback()
        print(f"[FAIL] Migration failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
