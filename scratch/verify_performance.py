import os
import sys
import uuid
import datetime
from datetime import date
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import sessionmaker

# Setup system path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.database.connection import engine
from app.database.session import SessionLocal

# Setup a query counter listener
query_count = 0
queries = []

@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    global query_count
    query_count += 1
    queries.append(statement)

def reset_counter():
    global query_count, queries
    query_count = 0
    queries = []

def run_explain_analyze(statement, label="Query"):
    print(f"\n=== EXPLAIN ANALYZE for: {label} ===")
    with engine.connect() as conn:
        from sqlalchemy import text
        try:
            res = conn.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {statement}"))
            for row in res.all():
                print(row[0])
        except Exception as e:
            print(f"Error running explain: {e}")

def check_active_connections():
    print("\n=== ACTIVE PostgreSQL CONNECTIONS & STATES ===")
    with engine.connect() as conn:
        from sqlalchemy import text
        res = conn.execute(text("""
            SELECT pid, state, query, age(clock_timestamp(), query_start) as age 
            FROM pg_stat_activity 
            WHERE datname = 'cognitive_erp' AND pid <> pg_backend_pid();
        """))
        rows = res.all()
        if not rows:
            print("No other active connections.")
        for row in rows:
            print(f"PID: {row.pid} | State: {row.state} | Age: {row.age} | Query: {row.query[:100]}")

def profile_dashboard_stats():
    print("\n=== PROFILING DASHBOARD STATS ===")
    from app.services.analytics_service import AnalyticsService
    db = SessionLocal()
    try:
        reset_counter()
        service = AnalyticsService(db)
        # Fetching dashboard stats (simulating superadmin to run baseline)
        stats = service.get_dashboard_stats()
        print(f"Total queries executed for dashboard stats: {query_count}")
        # Print first few queries
        for idx, q in enumerate(queries[:5]):
            print(f" Query {idx+1}: {q.replace(chr(10), ' ')[:120]}...")
        if len(queries) > 5:
            print(f" ... and {len(queries)-5} more queries.")
    finally:
        db.close()

def profile_client_list():
    print("\n=== PROFILING CLIENT LIST (N+1 check) ===")
    from app.services.client_service import ClientService
    db = SessionLocal()
    try:
        reset_counter()
        service = ClientService(db)
        clients, total = service.get_all(skip=0, limit=100)
        print(f"Total queries executed for listing clients: {query_count}")
        print(f"Number of clients fetched: {len(clients)}")
        for idx, q in enumerate(queries):
            print(f" Query {idx+1}: {q.replace(chr(10), ' ')[:120]}...")
    finally:
        db.close()

def profile_leave_requests():
    print("\n=== PROFILING LEAVE REQUESTS (N+1 check) ===")
    from app.services.leave_service import LeaveService
    db = SessionLocal()
    try:
        reset_counter()
        service = LeaveService(db)
        # Let's see if we have leave requests in the DB
        requests, total = service.get_all_requests(skip=0, limit=50)
        print(f"Total queries executed for leave requests list: {query_count}")
        print(f"Number of leave requests fetched: {len(requests)}")
        # Print unique query templates to see repetition
        unique_queries = list(set(queries))
        print(f"Unique query templates executed: {len(unique_queries)}")
        for idx, q in enumerate(queries[:10]):
            print(f" Query {idx+1}: {q.replace(chr(10), ' ')[:120]}...")
        if len(queries) > 10:
            print(f" ... and {len(queries)-10} more queries.")
    finally:
        db.close()

if __name__ == "__main__":
    print("PostgreSQL Database URL:", settings.DATABASE_URL)
    check_active_connections()
    profile_dashboard_stats()
    profile_client_list()
    profile_leave_requests()
    
    # Run EXPLAIN on the case-insensitive ILIKE check
    run_explain_analyze(
        "SELECT id, name, client_code FROM clients WHERE name ILIKE 'Acme Corp' LIMIT 1",
        "Client Name Uniqueness Check (ILIKE)"
    )
