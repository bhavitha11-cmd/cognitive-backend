from pathlib import Path
import sys
from sqlalchemy import create_engine, text

sys.path.append(str(Path(__file__).resolve().parent.parent))

db_url = "postgresql://postgres:Cognitive%402026@localhost:5432/cognitive_erp"
engine = create_engine(db_url)

with engine.connect() as conn:
    print("Projects in DB:")
    projects = conn.execute(text("SELECT id, project_code, name FROM projects")).fetchall()
    for p in projects:
        print(f"  {p[0]} | {p[1]} | {p[2]}")
