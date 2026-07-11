import psycopg2

def main():
    conn = psycopg2.connect("postgresql://postgres:Cognitive%402026@localhost:5432/cognitive_erp")
    cur = conn.cursor()
    
    cur.execute("SELECT id, project_code, part_name, planned_start_date, planned_end_date, parent_project_id FROM projects")
    projects = cur.fetchall()
    print("--- Projects (Parts) in DB ---")
    for p in projects:
        print(f"ID: {p[0]}, Code: {p[1]}, Name: {p[2]}, Start: {p[3]}, End: {p[4]}, ParentID: {p[5]}")
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
