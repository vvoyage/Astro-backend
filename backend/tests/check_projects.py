import psycopg2
conn = psycopg2.connect("postgresql://astro:astro_pass@localhost:5432/astro_db")
cur = conn.cursor()
cur.execute(
    "SELECT id, status, created_at FROM projects "
    "WHERE user_id='33a951dc-3268-498c-ba66-cde648b9fe24' "
    "ORDER BY created_at DESC LIMIT 10"
)
for row in cur.fetchall():
    print(row[0], row[1], str(row[2])[:19])
conn.close()
