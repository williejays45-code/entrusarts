# ERA Verification Standard v1.0

**Status:** frozen. Every future verify script is classified against this standard in `era/verification_taxonomy.py` before it's considered complete.

## Why this exists

This standard exists because of a real incident, not a hypothetical one: `verify_dcad_to_upr.py` (now `verify_legacy_dcad_to_upr.py`) tested a hardcoded stub with placeholder values like `"AWAITING OFFICIAL ENTRY"`, built before any real DCAD file was ever uploaded to this project. It kept passing, correctly, the whole time — and a passing legacy test was briefly mistaken for evidence that the real `DCADBulkDataAdapter`/`DCAD-JOIN-001` pipeline had been verified. It hadn't been touched by that test at all.

The bug wasn't in the test. The test did exactly what it was written to do. The bug was that a flat list of 53 green checkmarks gives no signal about what each one actually proves. This standard fixes that structurally, not by trusting people to remember.

## The four levels

| Level | Definition | Example |
|---|---|---|
| **UNIT** | One engine's own logic, in isolation. No cross-engine flow. | `verify_ecm001.py`, `verify_dec001.py` |
| **INTEGRATION** | Two or more engines/subsystems working together, through the real pipeline or a real cross-engine call path. | `verify_dcad_join001.py`, `verify_ecm_to_epm.py` |
| **SYSTEM** | Full pipeline execution, or a cross-cutting concern that spans the whole architecture (transactions, concurrency, schema versioning, the master gate itself). | `verify_spine002.py`, `verify_txn001.py` |
| **LEGACY** | Retained for regression coverage of superseded code. A passing result validates only that legacy path — never any current production path. | `verify_legacy_dcad_capture.py` |

## The contract for every new verify script

1. **Classify it in `era/verification_taxonomy.py` before considering the work done.** Not in the file's own header — in the central registry. This is a deliberate choice: metadata scattered across 50+ files is metadata nobody maintains; one file is one thing to check.
2. **Pick the level honestly, not optimistically.** If a script exercises one engine's own methods directly, it's UNIT — even if that engine is important. If it doesn't run through `build_app()`/`run_property()` or a real multi-engine call chain, it isn't INTEGRATION.
3. **Write the `purpose` field as what the test actually proves, not what it's named after.** `verify_dcad_to_upr.py`'s name implied it verified DCAD-to-UPR flow. Its actual purpose was "the original stub's hardcoded fixture flows into UPR." Those are different sentences. Write the second kind.
4. **When code is superseded, don't delete its verify script — reclassify it to LEGACY** and add a header (see the template below) pointing to what replaced it. Deleting it loses regression coverage of the old path; leaving it unclassified is what caused the original incident.
5. **Every verify script still follows C1's real-gate rule**: compute pass/fail, `sys.exit(1)` on failure. Classification doesn't relax that — a LEGACY test that silently returns 0 on failure is exactly as dangerous as a production one.

## LEGACY reclassification header template

```python
"""
LEGACY VERIFICATION

Purpose:
    <what this test actually verifies, plainly>

This does NOT validate:
    - <the new/real thing someone might mistake this for>
    - <specifics>

See instead:
    <the real verify script(s) for the current production path>

Retained (not deleted) for regression coverage of <the old thing>.
"""
```

## `verify_all.py`'s obligations

- Reports grouped by level, not as one flat list — production levels first, LEGACY last but never hidden.
- Prints an explicit warning inline in the LEGACY group, both in the console summary and the markdown report: *"does not validate current production paths."*
- Any verify script not yet in `era/verification_taxonomy.py` is reported as `UNCLASSIFIED`, not silently omitted — new work is visible immediately, not invisible until someone remembers to classify it.
- A green master gate means: production UNIT tests pass, production INTEGRATION tests pass, SYSTEM tests pass, and LEGACY tests pass (on their own, narrower terms) — four separate claims, not one.

## What this standard does not do

It doesn't replace reading the actual test. A LEGACY classification tells you not to over-trust a pass; it doesn't tell you what the underlying code should be replaced with, or when. That's still a judgment call for whoever's doing the work — the standard's job is only to make sure nobody has to guess what a green checkmark means.
