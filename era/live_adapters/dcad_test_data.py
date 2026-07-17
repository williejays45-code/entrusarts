from __future__ import annotations

import os
from pathlib import Path

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

def resolve_dcad_test_paths() -> tuple[str, str, bool]:
    """Return appraisal path, info path, and whether they are full production files.

    Full data can be supplied portably with ERA_DCAD_APPR_PATH and
    ERA_DCAD_INFO_PATH. Routine verification falls back to bundled, real-row
    fixtures so it never depends on a Claude/Linux-only /mnt path.
    """
    appr = os.environ.get("ERA_DCAD_APPR_PATH")
    info = os.environ.get("ERA_DCAD_INFO_PATH")
    if appr and info and Path(appr).is_file() and Path(info).is_file():
        return appr, info, True
    return (
        str(_FIXTURE_DIR / "ACCOUNT_APPRL_YEAR_FIXTURE.CSV"),
        str(_FIXTURE_DIR / "ACCOUNT_INFO_FIXTURE.CSV"),
        False,
    )
