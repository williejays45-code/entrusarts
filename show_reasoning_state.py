import sqlite3
conn = sqlite3.connect("eri_persistence.db")
print()
print("WEIGHT REGISTRY")
for row in conn.execute("""
SELECT weight_id, evidence_type, weight_value, status, source
FROM weight_registry
WHERE engine='ERA' AND metric='THS'
ORDER BY id
""").fetchall():
    print(row)
print()
print("LATEST SCORE")
for row in conn.execute("""
SELECT id, engine, score_name, value, confidence, validator_status, weight_table
FROM score_entries
WHERE engine='ERA' AND score_name='THS'
""").fetchall():
    print(row)
print()
print("LATEST HISTORY")
for row in conn.execute("""
SELECT score_entry_id, engine, score_name, value, confidence, validator_status, weight_table
FROM score_history
WHERE engine='ERA' AND score_name='THS'
ORDER BY id DESC
LIMIT 3
""").fetchall():
    print(row)
print()
print("LATEST DECISION TRACE")
for row in conn.execute("""
SELECT trace_id, score_entry_id, engine, metric, score_value, confidence, decision_impact, recovery_action, reason
FROM decision_trace
WHERE engine='ERA' AND metric='THS'
ORDER BY id DESC
LIMIT 3
""").fetchall():
    print(row)
conn.close()
