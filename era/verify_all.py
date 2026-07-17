from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from era.verification_taxonomy import classify, UNIT, INTEGRATION, SYSTEM, LEGACY


ROOT = Path(__file__).resolve().parent.parent
ERA_DIR = ROOT / "era"
REPORT_DIR = ROOT / "verification_reports"

EXCLUDED_FILES = {
    "verify_all.py",
    "verify_build_gate.py",
    # DCAD-INDEX-001's operational memory benchmark deliberately runs
    # THREE full-scale builds against the real ~700MB combined DCAD
    # files (each taking 60-110s in this environment) -- that's the
    # right cost for an operational check proving real memory behavior,
    # but not something every routine `python -m era.verify_all` run
    # should pay. Run it on its own:
    #   python -m era.acquisition.providers.county.verify_dcad_index_operational
    "verify_dcad_index_operational.py",
    # LIVE-DCAD-VERIFY-001 requires a real DCAD download URL and real
    # network access -- neither exists in this environment or in
    # routine CI. It refuses to run without --download-url (by design,
    # same discipline as never fabricating a placeholder endpoint), so
    # a bare `python -m era.verify_all` sweep would report it as a
    # false FAIL rather than what it actually is: not applicable here.
    # Run it explicitly, on a machine that can reach the real endpoint:
    #   python -m era.acquisition.providers.county.verify_dcad_live_local_only --download-url "<real URL>"
    "verify_dcad_live_local_only.py",
}

# Report group order -- production levels first (most important to see
# at a glance), legacy last (still shown, never hidden).
LEVEL_ORDER = [UNIT, INTEGRATION, SYSTEM, LEGACY, "UNCLASSIFIED"]


@dataclass(frozen=True)
class VerificationResult:
    module: str
    status: str
    exit_code: int
    elapsed_seconds: float
    stdout: str
    stderr: str
    level: str
    engine: str
    verification_status: str
    purpose: str


def discover_verification_modules() -> list[str]:
    modules: list[str] = []

    for path in ERA_DIR.rglob("verify_*.py"):
        if path.name in EXCLUDED_FILES:
            continue

        if "__pycache__" in path.parts:
            continue

        relative = path.relative_to(ROOT).with_suffix("")
        module = ".".join(relative.parts)
        modules.append(module)

    return sorted(set(modules))


def run_module(module: str) -> VerificationResult:
    started = time.perf_counter()

    completed = subprocess.run(
        [sys.executable, "-m", module],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    elapsed = time.perf_counter() - started
    status = "PASS" if completed.returncode == 0 else "FAIL"
    meta = classify(module)

    return VerificationResult(
        module=module,
        status=status,
        exit_code=completed.returncode,
        elapsed_seconds=round(elapsed, 3),
        stdout=completed.stdout,
        stderr=completed.stderr,
        level=meta["level"],
        engine=meta["engine"],
        verification_status=meta["status"],
        purpose=meta["purpose"],
    )


def write_reports(results: list[VerificationResult], total_elapsed: float) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).isoformat()
    passed = sum(result.status == "PASS" for result in results)
    failed = len(results) - passed

    grouped: dict[str, list[VerificationResult]] = {}
    for result in results:
        grouped.setdefault(result.level, []).append(result)

    level_summary = {
        level: {
            "total": len(items),
            "passed": sum(r.status == "PASS" for r in items),
            "failed": sum(r.status == "FAIL" for r in items),
        }
        for level, items in grouped.items()
    }

    payload = {
        "generated_at": generated_at,
        "total_modules": len(results),
        "passed": passed,
        "failed": failed,
        "elapsed_seconds": round(total_elapsed, 3),
        "level_summary": level_summary,
        "results": [asdict(result) for result in results],
    }

    json_path = REPORT_DIR / "latest_verification_report.json"
    json_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    markdown_lines = [
        "# ERA Verification Report",
        "",
        f"- Generated: `{generated_at}`",
        f"- Total modules: **{len(results)}**",
        f"- Passed: **{passed}**",
        f"- Failed: **{failed}**",
        f"- Elapsed: **{total_elapsed:.3f} seconds**",
        "",
        "## Summary by Level",
        "",
        "| Level | Total | Passed | Failed |",
        "|---|---:|---:|---:|",
    ]
    for level in LEVEL_ORDER:
        if level not in level_summary:
            continue
        s = level_summary[level]
        markdown_lines.append(f"| {level} | {s['total']} | {s['passed']} | {s['failed']} |")

    for level in LEVEL_ORDER:
        if level not in grouped:
            continue
        markdown_lines.extend(["", f"## {level}", ""])
        if level == LEGACY:
            markdown_lines.append(
                "_A passing result at this level validates only the legacy code path "
                "itself, not any current production path. See each module's own "
                "docstring for what it does and does not cover._"
            )
            markdown_lines.append("")
        markdown_lines.extend([
            "| Status | Module | Engine | Purpose | Exit | Seconds |",
            "|---|---|---|---|---:|---:|",
        ])
        for result in grouped[level]:
            markdown_lines.append(
                f"| {result.status} | `{result.module}` | {result.engine} | "
                f"{result.purpose} | {result.exit_code} | {result.elapsed_seconds:.3f} |"
            )

    failures = [result for result in results if result.status == "FAIL"]

    if failures:
        markdown_lines.extend(["", "## Failure Details", ""])

        for result in failures:
            markdown_lines.extend(
                [
                    f"### `{result.module}` ({result.level})",
                    "",
                    "```text",
                    result.stdout.strip() or "(no stdout)",
                    "",
                    result.stderr.strip() or "(no stderr)",
                    "```",
                    "",
                ]
            )

    markdown_path = REPORT_DIR / "latest_verification_report.md"
    markdown_path.write_text(
        "\n".join(markdown_lines),
        encoding="utf-8",
    )


def main() -> int:
    modules = discover_verification_modules()

    print("ERA MASTER VERIFICATION GATE")
    print("=" * 78)
    print("PROJECT ROOT:", ROOT)
    print("VERIFY MODULES FOUND:", len(modules))
    print()

    if not modules:
        print("OVERALL: FAIL")
        print("REASON: No verification modules were discovered.")
        return 1

    results: list[VerificationResult] = []
    suite_started = time.perf_counter()

    for index, module in enumerate(modules, start=1):
        print(f"[{index:02d}/{len(modules):02d}] {module}")

        result = run_module(module)
        results.append(result)

        print(
            f"         {result.status} | "
            f"exit={result.exit_code} | "
            f"{result.elapsed_seconds:.3f}s"
        )

        if result.status == "FAIL":
            print("         FAILURE OUTPUT")
            print("         " + "-" * 60)

            if result.stdout.strip():
                print(result.stdout.rstrip())

            if result.stderr.strip():
                print(result.stderr.rstrip())

            print("         " + "-" * 60)

    total_elapsed = time.perf_counter() - suite_started
    write_reports(results, total_elapsed)

    passed = sum(result.status == "PASS" for result in results)
    failed = len(results) - passed

    print()
    print("=" * 78)
    print("ERA VERIFICATION SUMMARY")
    print("=" * 78)
    print("PASSED:", f"{passed}/{len(results)}")
    print("FAILED:", failed)
    print("ELAPSED:", f"{total_elapsed:.3f} seconds")
    print()
    print("BY LEVEL:")
    grouped: dict[str, list[VerificationResult]] = {}
    for result in results:
        grouped.setdefault(result.level, []).append(result)
    for level in LEVEL_ORDER:
        if level not in grouped:
            continue
        items = grouped[level]
        level_passed = sum(r.status == "PASS" for r in items)
        note = "  (legacy -- does not validate current production paths)" if level == LEGACY else ""
        print(f"  {level:14s} {level_passed}/{len(items)}{note}")
    print()
    print(
        "REPORT:",
        REPORT_DIR / "latest_verification_report.md",
    )
    print(
        "JSON:",
        REPORT_DIR / "latest_verification_report.json",
    )
    print("OVERALL:", "PASS" if failed == 0 else "FAIL")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
