import os
import sqlite3
print("Current directory:")
print(os.getcwd())
print()
print("Database exists:", os.path.exists("eri_persistence.db"))
print()
conn = sqlite3.connect("eri_persistence.db")
tables = conn.execute("""
SELECT name
FROM sqlite_master
WHERE type='table'
ORDER BY name
""").fetchall()
print("Tables found:", len(tables))
print()
for t in tables:
    print(t[0])
conn.close()
