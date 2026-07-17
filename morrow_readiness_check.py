import os
from pathlib import Path
ROOT = Path.cwd()
candidate_roots = [
    ROOT / "morrow_core",
    ROOT / "morrow",
    ROOT / "MORROW",
    ROOT.parent / "morrow_core",
    ROOT.parent / "morrow",
]
existing_roots = [p for p in candidate_roots if p.exists() and p.is_dir()]
print("MORROW READINESS CHECK 001")
print("=" * 70)
print("PROJECT ROOT:", ROOT)
print()
if not existing_roots:
    print("STATUS: BLOCKED")
    print("REASON: No MORROW module folder found near this project.")
    raise SystemExit(0)
for morrow_root in existing_roots:
    print("MORROW ROOT:", morrow_root)
    print("-" * 70)
    py_files = sorted([
        p for p in morrow_root.rglob("*.py")
        if "__pycache__" not in str(p)
    ])
    module_files = [
        p for p in py_files
        if not p.name.startswith("test_") and p.name != "__init__.py"
    ]
    test_files = [
        p for p in py_files
        if p.name.startswith("test_")
    ]
    print("MODULE COUNT:", len(module_files))
    print("TEST FILE COUNT:", len(test_files))
    print()
    test_names = {p.stem.replace("test_", "") for p in test_files}
    eligible = []
    blocked = []
    for module in module_files:
        text = module.read_text(encoding="utf-8", errors="ignore")
        module_name = module.stem
        has_test = module_name in test_names
        has_version = (
            "__version__" in text
            or "VERSION" in text
            or "INTERFACE_VERSION" in text
        )
        status = "ELIGIBLE" if has_test and has_version else "BLOCKED"
        row = {
            "module": str(module.relative_to(morrow_root)),
            "has_test": has_test,
            "has_version": has_version,
            "status": status,
        }
        if status == "ELIGIBLE":
            eligible.append(row)
        else:
            blocked.append(row)
        print(
            f"{status} | {module.relative_to(morrow_root)} | "
            f"pytest={has_test} | version={has_version}"
        )
    print()
    print("ELIGIBLE MODULES:", len(eligible))
    print("BLOCKED MODULES:", len(blocked))
    print()
    if eligible:
        print("FIRST LIVE ADAPTER SCOPE:")
        for row in eligible:
            print(" -", row["module"])
    else:
        print("FIRST LIVE ADAPTER SCOPE: NONE")
        print("REASON: No MORROW module has both formal pytest coverage and version tag.")
    print("=" * 70)
