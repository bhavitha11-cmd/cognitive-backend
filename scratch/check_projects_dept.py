import psycopg2

def main():
    conn = psycopg2.connect("postgresql://postgres:Cognitive%402026@localhost:5432/cognitive_erp")
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM projects LIMIT 1")
    colnames = [desc[0] for desc in cur.description]
    print("Columns in projects:", colnames)
    
    cur.execute("SELECT * FROM parent_projects LIMIT 1")
    parent_colnames = [desc[0] for desc in cur.description]
    print("Columns in parent_projects:", parent_colnames)
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
