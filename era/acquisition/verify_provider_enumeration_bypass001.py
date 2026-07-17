"""PER-001 production authority-bypass scan.

The scan deliberately excludes verification/test modules and comments are not
treated as execution. Each rule targets a concrete prohibited authority path.
"""

from pathlib import Path
import ast


ERA = Path(__file__).resolve().parents[1]


def production_files():
    for path in sorted(ERA.rglob("*.py")):
        if path.name.startswith(("verify_", "test_")) or "__pycache__" in path.parts:
            continue
        yield path


def executable_source(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return ast.dump(tree, include_attributes=False)


def run_checks():
    sources = {path: executable_source(path) for path in production_files()}
    text = {path: path.read_text(encoding="utf-8") for path in sources}
    combined_ast = "\n".join(sources.values())
    lpa = text[ERA / "providers" / "live_provider_adapter.py"]
    orchestration = text[ERA / "orchestration" / "era_orchestrator.py"]
    pipeline = text[ERA / "pipeline.py"]
    enumeration = text[ERA / "acquisition" / "provider_enumeration_authority.py"]

    checks = {
        "no_approved_provider_allowlist": "APPROVED_PROVIDERS" not in combined_ast,
        "manifest_list_operational_not_called": "list_operational" not in enumeration + lpa + orchestration + pipeline,
        "manifest_list_by_state_not_called": "list_by_state" not in enumeration + lpa + orchestration + pipeline,
        "manifest_health_not_selection_input": "provider_manifest" not in enumeration + lpa + orchestration + pipeline,
        "container_map_not_iterated_for_membership": "county_connectors.keys" not in combined_ast,
        "jre_operational_filter_not_canonical": "operational_only=True" not in pipeline,
        "lpa_no_local_lifecycle_filter": "ConnectorStatus" not in lpa,
        "lpa_no_local_health_filter": "evaluate_provider_health" not in lpa,
        "orchestration_no_local_lifecycle_filter": "ConnectorStatus" not in orchestration,
        "orchestration_no_local_health_filter": "evaluate_provider_health" not in orchestration,
        "enumeration_has_no_persistence_dependency": "persistence" not in enumeration.lower(),
        "enumeration_has_no_registry_store": "self.connectors" not in enumeration and "self.providers" not in enumeration,
        "no_forbidden_new_architecture": all(term not in combined_ast for term in (
            "EligibilityDatabase", "ProviderSelectionDatabase", "DiscoveryRegistry",
            "ProviderRankingEngine", "EngineRegistry",
        )),
    }
    return checks


if __name__ == "__main__":
    checks = run_checks()
    for name, passed in checks.items():
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    passed = sum(checks.values())
    print(f"PER-001 BYPASS CHECKS PASSED: {passed}/{len(checks)}")
    raise SystemExit(0 if passed == len(checks) else 1)
