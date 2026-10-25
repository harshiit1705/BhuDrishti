import os
import psycopg

conn = psycopg.connect(os.environ["DATABASE_URL"])
try:
    rows = conn.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND is_nullable = 'NO'
          AND column_default IS NULL
        ORDER BY ordinal_position
    """).fetchall()

    print("Required columns without defaults:")
    for row in rows:
        print("-", row[0])
finally:
    conn.close()
