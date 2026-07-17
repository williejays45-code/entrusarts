import sqlite3
conn = sqlite3.connect("eri_persistence.db")
conn.execute("""
CREATE TABLE IF NOT EXISTS decision_trace (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    score_entry_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    metric TEXT NOT NULL,
    score_value REAL NOT NULL,
    confidence TEXT NOT NULL,
    decision_context TEXT NOT NULL,
    decision_impact TEXT NOT NULL,
    reason TEXT NOT NULL,
    recovery_action TEXT NOT NULL,
    created_at TEXT NOT NULL
)
""")
conn.commit()
tables = conn.execute("""
SELECT name
FROM sqlite_master
WHERE type='table'
ORDER BY name
""").fetchall()
print("TABLES:")
for table in tables:
    print(table[0])
conn.close()
