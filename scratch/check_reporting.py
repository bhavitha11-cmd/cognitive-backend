import psycopg2

def main():
    conn = psycopg2.connect("postgresql://postgres:Cognitive%402026@localhost:5432/cognitive_erp")
    cur = conn.cursor()
    
    cur.execute("SELECT id, first_name, last_name, reporting_manager_id FROM employees")
    emps = cur.fetchall()
    print("--- Reporting Structure in DB ---")
    for e in emps:
        print(f"ID: {e[0]}, Name: {e[1]} {e[2]}, ReportsTo: {e[3]}")
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
