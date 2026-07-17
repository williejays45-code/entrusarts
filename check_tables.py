import sqlite3
conn = sqlite3.connect("eri_persistence.db")
rows = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()
for row in rows:
    print(row[0])
conn.close()
