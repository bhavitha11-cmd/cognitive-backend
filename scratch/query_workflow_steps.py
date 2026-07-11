import psycopg2

def main():
    conn = psycopg2.connect("postgresql://postgres:Cognitive%402026@localhost:5432/cognitive_erp")
    cur = conn.cursor()
    
    workflow_id = "c61f337c-92a4-40ea-87b8-ad3f775bf839"
    cur.execute(
        "SELECT id, workflow_id, requester_role_id, approver_role_id, level, resolution_scope "
        "FROM approval_workflow_steps WHERE workflow_id = %s",
        (workflow_id,)
    )
    steps = cur.fetchall()
    
    print(f"--- Steps for Workflow {workflow_id} ---")
    for s in steps:
        role_id = s[2]
        # Get role name
        cur.execute("SELECT name FROM roles WHERE id = %s", (role_id,))
        role_name = cur.fetchone()
        role_name = role_name[0] if role_name else str(role_id)
        
        app_role_id = s[3]
        cur.execute("SELECT name FROM roles WHERE id = %s", (app_role_id,))
        app_role_name = cur.fetchone()
        app_role_name = app_role_name[0] if app_role_name else str(app_role_id)
        
        print(f"Step ID: {s[0]}, Requester Role: {role_name}, Approver Role: {app_role_name}, Level: {s[4]}, Scope: {s[5]}")
        
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
