"""Export audited synthetic-data traces after scanning for injected credentials."""

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

# Allows `python tools/export_baseline_evidence.py` from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_pipeline.core import AGENTS, canonical, fingerprint, read_json, save_json
from calendar_pipeline.runner import evaluate_artifacts


def export(source: Path, output: Path, connectivity: Path | None = None, allow_incomplete: bool = False) -> dict:
    if output.exists():
        raise ValueError("Evidence output exists; do not overwrite recorded experiments")
    summary = evaluate_artifacts(source)
    if summary["run_status"] != "completed" and not allow_incomplete:
        raise ValueError("Only completed runs can be published as pilot evidence")
    if summary["recorded_sessions"] != summary["expected_sessions"]:
        raise ValueError("Export requires an explicit recorded outcome for every planned session")
    plan = read_json(source / "plan.json")
    files = [p for p in source.rglob("*") if p.is_file()]
    if connectivity:
        files.append(connectivity)
    values = [os.environ[name].encode() for name in plan["config"]["key_by_agent"].values() if os.environ.get(name)]
    for path in files:
        content = path.read_bytes()
        if any(secret in content for secret in values):
            raise ValueError("Credential scan failed; export refused")
    pairs = []
    for scenario in plan["scenarios"]:
        sessions = {model: read_json(source / "sessions" / f"{scenario['scenario_id']}__{model}.json") for model in plan["config"]["models"]}
        for owner in AGENTS:
            bodies = []
            for model, session in sessions.items():
                call = next(c for c in session["calls"] if c["agent_id"] == owner and c["round"] == 1)
                body = {key: value for key, value in call["request"].items() if key != "model"}
                bodies.append(body)
            if len(bodies) != 2 or canonical(bodies[0]) != canonical(bodies[1]):
                raise ValueError("Paired first-round request mismatch")
            pairs.append({"scenario_id": scenario["scenario_id"], "agent_id": owner,
                          "request_without_model_sha256": fingerprint(bodies[0]), "matches": True})
    events = [json.loads(line) for line in (source / "journal.jsonl").read_text().splitlines()]
    http_statuses = Counter(e["status"] for e in events if e["event"] == "http_error")
    usage_by_model = {}
    usage_by_credential = {}
    for scenario in plan["scenarios"]:
        for model in plan["config"]["models"]:
            session = read_json(source / "sessions" / f"{scenario['scenario_id']}__{model}.json")
            for call in session["calls"]:
                usage = call["response"]["usage"]
                if usage is not None:
                    for bucket, key in ((usage_by_model, model), (usage_by_credential, call["credential_variable"])):
                        counts = bucket.setdefault(key, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
                        for field in counts:
                            counts[field] += usage[field]
    audit = {"status": "passed", "scheduling_run_status": summary["run_status"], "successful_sessions": summary["successful_sessions"],
             "paired_first_round_requests_checked": len(pairs),
             "pairs": pairs, "all_later_requests_reconstructed": summary["input_replay_audit"] == "passed",
             "credential_scan": "passed for the credential values currently injected in this process",
             "logical_requests": summary["request_count"],
             "http_attempts": sum(e["event"] == "http_attempt" for e in events),
             "http_error_status_counts": dict(http_statuses),
             "reserved_token_units": sum(e.get("reserved_token_units", 0) for e in events),
             "observed_response_usage_by_model": usage_by_model,
             "observed_response_usage_by_credential_variable": usage_by_credential,
             "pairing_scope": "identical starting requests except model ID; later trajectories intentionally depend on actual model outputs"}
    shutil.copytree(source, output)
    if connectivity:
        shutil.copyfile(connectivity, output / "connectivity.json")
    save_json(output / "pairing_audit.json", audit)
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--connectivity", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true", help="Preserve a protocol-failure pilot explicitly; never reclassifies it as successful")
    args = parser.parse_args()
    try:
        audit = export(args.run, args.output, args.connectivity, args.allow_incomplete)
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"Export failed: {error}\n")
    print(json.dumps({k: v for k, v in audit.items() if k != "pairs"}, indent=2))
