import os
import psycopg

conn = psycopg.connect(os.environ["DATABASE_URL"])
try:
    print("=== WORKSPACE-RELATED TABLES ===")
    rows = conn.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name ILIKE '%workspace%'
        ORDER BY table_name
    """).fetchall()

    for row in rows:
        print("-", row[0])

    print("\n=== USERS TABLE COLUMNS ===")
    rows = conn.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'users'
        ORDER BY ordinal_position
    """).fetchall()

    for row in rows:
        print(row)

    for (table_name,) in conn.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name ILIKE '%workspace%'
        ORDER BY table_name
    """).fetchall():
        print(f"\n=== {table_name} COLUMNS ===")
        columns = conn.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, (table_name,)).fetchall()
        for column in columns:
            print(column)
finally:
    conn.close()
