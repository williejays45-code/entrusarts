from era.decision_trace import DecisionTraceRepository, create_decision_trace
repo = DecisionTraceRepository("eri_persistence.db")
trace = create_decision_trace(
    engine="ERA",
    metric="THS",
    score_value=94.44,
    confidence="PARTIAL",
    decision_context="Hold score review after score history patch",
    decision_impact="ACQUISITION",
    reason="THS is strong but remains PARTIAL because placeholder constants are not validated.",
)
repo.save(trace)
rows = repo.load_all()
print("TRACE COUNT:", len(rows))
for row in rows:
    print(row)
