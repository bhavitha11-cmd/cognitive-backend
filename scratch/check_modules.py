import psycopg2

def main():
    conn = psycopg2.connect("postgresql://postgres:Cognitive%402026@localhost:5432/cognitive_erp")
    cur = conn.cursor()
    
    print("--- Modules in DB ---")
    cur.execute("SELECT id, module_key, module_name, is_active FROM modules")
    modules = cur.fetchall()
    for m in modules:
        print(f"ID: {m[0]}, Key: {m[1]}, Name: {m[2]}, Active: {m[3]}")
        
    print("\n--- Features in DB ---")
    cur.execute("""
        SELECT f.id, f.feature_key, f.feature_name, m.module_name, f.permission_enabled, f.is_active 
        FROM features f
        JOIN modules m ON f.module_id = m.id
        ORDER BY m.module_name, f.display_order
    """)
    features = cur.fetchall()
    for f in features:
        print(f"ID: {f[0]}, Key: {f[1]}, Name: {f[2]}, Module: {f[3]}, PermEnabled: {f[4]}, Active: {f[5]}")
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
