from persistence.repository import ScoreEntryRepository, SimpleScoreEntry
repo = ScoreEntryRepository("eri_persistence.db")
entry = SimpleScoreEntry(
    engine="TRIAD",
    metric="THS",
    score=93.92,
    confidence="PARTIAL",
    assumption_type="PLACEHOLDER",
    notes="First persisted hold score",
)
repo.save(entry)
loaded = repo.load("TRIAD", "THS")
print("ENGINE:", loaded.engine)
print("METRIC:", loaded.metric)
print("SCORE:", loaded.score)
print("CONFIDENCE:", loaded.confidence)
print("ASSUMPTION:", loaded.assumption_type)
print("NOTES:", loaded.notes)
