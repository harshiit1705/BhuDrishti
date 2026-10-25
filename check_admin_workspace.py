import os
import psycopg

conn = psycopg.connect(os.environ["DATABASE_URL"])
try:
    print("=== WORKSPACE USER COUNTS ===")
    rows = conn.execute("""
        SELECT w.name, w.id, COUNT(u.id)
        FROM public.workspaces w
        LEFT JOIN public.users u ON u.workspace_id = w.id
        GROUP BY w.name, w.id
        ORDER BY w.name
    """).fetchall()
    for row in rows:
        print(f"Workspace: {row[0]} | ID: {row[1]} | Users: {row[2]}")

    print("\n=== CHECK TARGET EMAIL ===")
    rows = conn.execute("""
        SELECT email, role, status, workspace_id
        FROM public.users
        WHERE lower(email) = lower(%s)
    """, ("neo.alexander.email@gmail.com",)).fetchall()
    print("Target email exists:", bool(rows))
    for row in rows:
        print(f"Role: {row[1]} | Status: {row[2]} | Workspace ID: {row[3]}")
finally:
    conn.close()
