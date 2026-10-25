import os
import psycopg

conn = psycopg.connect(os.environ["DATABASE_URL"])
try:
    rows = conn.execute(
        "SELECT id, name FROM public.workspaces ORDER BY name"
    ).fetchall()
    print("Existing workspaces:")
    for row in rows:
        print(f"ID: {row[0]} | Name: {row[1]}")
finally:
    conn.close()
