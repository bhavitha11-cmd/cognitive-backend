import os
import sys
from sqlalchemy import create_engine, MetaData

DATABASE_URL = "postgresql://postgres:Cognitive%402026@localhost:5432/cognitive_erp"

try:
    engine = create_engine(DATABASE_URL)
    metadata = MetaData()
    metadata.reflect(bind=engine)
    print("Database connection successful. Tables:")
    for table_name in sorted(metadata.tables.keys()):
        with engine.connect() as conn:
            from sqlalchemy import text
            res = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
            count = res.scalar()
            print(f" - {table_name}: {count}")
except Exception as e:
    print(f"Error: {e}")
