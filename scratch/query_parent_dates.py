import psycopg2

def main():
    conn = psycopg2.connect("postgresql://postgres:Cognitive%402026@localhost:5432/cognitive_erp")
    cur = conn.cursor()
    
    cur.execute("SELECT id, name, planned_start_date, planned_end_date FROM parent_projects")
    projects = cur.fetchall()
    print("--- Parent Projects in DB ---")
    for p in projects:
        print(f"ID: {p[0]}, Name: {p[1]}, Start: {p[2]}, End: {p[3]}")
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
