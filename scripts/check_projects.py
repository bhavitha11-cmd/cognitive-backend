import sys
from sqlalchemy import create_engine, text

sys.path.append(r"c:\Users\91891\OneDrive\Desktop\cognitive\cognitive-backend")

db_url = "postgresql://postgres:Cognitive%402026@localhost:5432/cognitive_erp"
engine = create_engine(db_url)

with engine.connect() as conn:
    print("Projects in DB:")
    projects = conn.execute(text("SELECT id, project_code, name FROM projects")).fetchall()
    for p in projects:
        print(f"  {p[0]} | {p[1]} | {p[2]}")
