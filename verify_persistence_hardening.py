import sqlite3
from persistence.repository import ScoreEntryRepository, SimpleScoreEntry
repo = ScoreEntryRepository("eri_persistence.db")
repo.save(SimpleScoreEntry(
    engine="ERA",
    metric="THS",
    score=95.55,
    confidence="PARTIAL",
    assumption_type="PLACEHOLDER",
    notes="Persistence hardening patch verification",
))
loaded = repo.load("ERA", "THS")
print("LATEST")
print(loaded)
conn = sqlite3.connect("eri_persistence.db")
print()
print("INDEXES")
indexes = conn.execute("""
SELECT name, tbl_name
FROM sqlite_master
WHERE type='index'
ORDER BY name
""").fetchall()
for row in indexes:
    print(row)
print()
print("LATEST SNAPSHOT")
for row in conn.execute("""
SELECT id, engine, score_name, value, confidence, validator_status, weight_table
FROM score_entries
WHERE engine='ERA' AND score_name='THS'
""").fetchall():
    print(row)
print()
print("HISTORY COUNT")
count = conn.execute("""
SELECT COUNT(*)
FROM score_history
WHERE engine='ERA' AND score_name='THS'
""").fetchone()[0]
print(count)
conn.close()
