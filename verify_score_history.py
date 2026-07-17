from persistence.repository import ScoreEntryRepository, SimpleScoreEntry
repo = ScoreEntryRepository("eri_persistence.db")
repo.save(SimpleScoreEntry(
    engine="ERA",
    metric="THS",
    score=91.11,
    confidence="PARTIAL",
    assumption_type="PLACEHOLDER",
    notes="History test first write",
))
repo.save(SimpleScoreEntry(
    engine="ERA",
    metric="THS",
    score=94.44,
    confidence="PARTIAL",
    assumption_type="PLACEHOLDER",
    notes="History test second write",
))
loaded = repo.load("ERA", "THS")
print("LATEST_ENGINE:", loaded.engine)
print("LATEST_METRIC:", loaded.metric)
print("LATEST_SCORE:", loaded.score)
print("LATEST_NOTES:", loaded.notes)
