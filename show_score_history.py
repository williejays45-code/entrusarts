import sqlite3
conn = sqlite3.connect("eri_persistence.db")
print("LATEST SNAPSHOT")
for row in conn.execute("""
SELECT id, engine, score_name, value, confidence, validator_status, weight_table
FROM score_entries
WHERE engine='ERA' AND score_name='THS'
""").fetchall():
    print(row)
print()
print("HISTORY")
for row in conn.execute("""
SELECT score_entry_id, engine, score_name, value, confidence, validator_status, weight_table
FROM score_history
WHERE engine='ERA' AND score_name='THS'
ORDER BY id
""").fetchall():
    print(row)
conn.close()
