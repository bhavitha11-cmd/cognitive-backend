import psycopg2

def main():
    conn = psycopg2.connect("postgresql://postgres:Cognitive%402026@localhost:5432/cognitive_erp")
    cur = conn.cursor()
    
    print("--- Roles in DB ---")
    cur.execute("SELECT id, name, is_system_role, is_super_admin, is_active FROM roles")
    roles = cur.fetchall()
    for r in roles:
        print(f"ID: {r[0]}, Name: {r[1]}, System: {r[2]}, SuperAdmin: {r[3]}, Active: {r[4]}")
        
    print("\n--- Non-NONE Permissions ---")
    cur.execute("""
        SELECT r.name, f.feature_name, rp.view_scope, rp.create_scope, rp.update_scope, rp.delete_scope 
        FROM role_permissions rp
        JOIN roles r ON rp.role_id = r.id
        JOIN features f ON rp.feature_id = f.id
        WHERE rp.view_scope != 'NONE' OR rp.create_scope != 'NONE' OR rp.update_scope != 'NONE' OR rp.delete_scope != 'NONE'
        LIMIT 50
    """)
    perms = cur.fetchall()
    if not perms:
        print("No non-NONE permissions found in the database!")
    for p in perms:
        print(f"Role: {p[0]}, Feature: {p[1]}, View: {p[2]}, Create: {p[3]}, Update: {p[4]}, Delete: {p[5]}")
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
