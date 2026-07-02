from pathlib import Path
import sys
from sqlalchemy import create_engine, text

sys.path.append(str(Path(__file__).resolve().parent.parent))

db_url = "postgresql://postgres:Cognitive%402026@localhost:5432/cognitive_erp"
engine = create_engine(db_url)

with engine.connect() as conn:
    for table in ["departments", "teams", "projects", "tasks"]:
        res = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
        print(f"Row count for '{table}': {res.scalar()}")
        
    print("\nDepartments in DB:")
    depts = conn.execute(text("SELECT id, name, code FROM departments")).fetchall()
    for d in depts:
        print(f"  {d[0]} | {d[1]} | {d[2]}")
        
    print("\nTeams in DB:")
    tms = conn.execute(text("SELECT id, team_name, department_id FROM teams")).fetchall()
    for t in tms:
        print(f"  {t[0]} | {t[1]} | {t[2]}")
