from pathlib import Path
root = Path.cwd()
search_terms = [
    "eri001",
    "eri-001",
    "evidence_reliability",
    "founder_lock",
    "founder certificate",
    "certificate",
    "audit",
    "violation",
    "regression",
]
print("GR-001 ERI-001 CERTIFICATE SEARCH")
print("=" * 70)
print("ROOT:", root)
print()
matches = []
for path in root.rglob("*"):
    if path.is_file():
        name = path.name.lower()
        full = str(path).lower()
        if any(term in name or term in full for term in search_terms):
            matches.append(path)
for match in matches:
    print(match)
print()
print("MATCH COUNT:", len(matches))
print()
eri001_files = [
    root / "era" / "evidence_reliability.py",
    root / "verify_eri001.py",
    root / "era" / "verify_eri001.py",
]
print("DIRECT ERI-001 FILE CHECK")
print("=" * 70)
for file in eri001_files:
    print(file, "EXISTS" if file.exists() else "MISSING")
