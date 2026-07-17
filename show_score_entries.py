import sqlite3
conn = sqlite3.connect("eri_persistence.db")
rows = conn.execute("""
SELECT *
FROM score_entries
ORDER BY id;
""").fetchall()
print("=" * 80)
print("ROW COUNT:", len(rows))
print("=" * 80)
for row in rows:
    print(row)
conn.close()
