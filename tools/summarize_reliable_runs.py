"""Re-evaluate the disjoint v4 runs and aggregate development-only evidence."""

import argparse
from collections import Counter, defaultdict
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_pipeline.core import AGENTS, DATA, MODELS, ROOT, canonical, read_json, save_json, sha_file
from calendar_pipeline.runner import evaluate_artifacts


def summarize() -> dict:
    folders = [ROOT / "experiments/results/mistral-pilot-v4", ROOT / "experiments/results/mistral-v4-additional-development"]
    expected_ids = {r["scenario_id"] for r in read_json(DATA / "manifest.json")["records"] if r["split"] == "development"}
    expected_pairs = {(sid, model) for sid in expected_ids for model in MODELS}
    sessions = {}
    outcomes = []
    usage = Counter()
    http_errors = Counter()
    http_attempts = 0
    reference_config = None
    for folder in folders:
        report = evaluate_artifacts(folder)
        if report["backend"] != "mistral" or report["run_status"] != "completed":
            raise ValueError("Expected complete real-provider v4 evidence")
        plan = read_json(folder / "plan.json")
        if plan["config"]["protocol_version"] != "calendar-baseline-v4":
            raise ValueError("Wrong protocol version")
        comparable = {k: v for k, v in plan["config"].items() if k not in ("scenario_ids", "max_http_attempts", "max_reserved_tokens")}
        if reference_config is not None and reference_config != comparable:
            raise ValueError("Generation/protocol settings differ across validation batches")
        reference_config = comparable
        for path in (folder / "sessions").glob("*.json"):
            session = read_json(path)
            key = session["scenario_id"], session["model"]
            if key in sessions:
                raise ValueError("Duplicate scenario/model run in aggregate")
            sessions[key] = session
        outcomes.extend(report["outcomes"])
        usage.update(report["observed_usage"])
        for line in (folder / "journal.jsonl").read_text().splitlines():
            event = json.loads(line)
            http_attempts += event["event"] == "http_attempt"
            if event["event"] == "http_error":
                http_errors[str(event["status"])] += 1
    if set(sessions) != expected_pairs:
        raise ValueError("Missing, duplicate, or non-development model/scenario pairs")
    pairs_checked = 0
    for sid in sorted(expected_ids):
        for owner in AGENTS:
            bodies = []
            for model in MODELS:
                call = next(c for c in sessions[sid, model]["calls"] if c["phase"] == "publish" and c["agent_id"] == owner and c["attempt"] == 1)
                bodies.append({k: v for k, v in call["request"].items() if k != "model"})
            if canonical(bodies[0]) != canonical(bodies[1]):
                raise ValueError("Cross-model starting request mismatch")
            pairs_checked += 1
    grouped = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome["model"], outcome["bucket"]].append(outcome)
    per_model = {model: {
        "sessions": sum(o["model"] == model for o in outcomes),
        "successful_sessions": sum(o["model"] == model and o["task_success"] for o in outcomes),
        "by_bucket": {bucket: {"sessions": len(grouped[model, bucket]),
                                "successes": sum(o["task_success"] for o in grouped[model, bucket])}
                      for bucket in ("easy", "medium", "hard", "infeasible")},
    } for model in MODELS}
    return {"status": "passed" if all(o["task_success"] for o in outcomes) else "failed",
            "scope": "20 development fixtures; no held-out LLM evaluation or security/attack evaluation",
            "protocol_version": "calendar-baseline-v4", "scenario_count": len(expected_ids),
            "sessions": len(sessions), "successful_sessions": sum(o["task_success"] for o in outcomes),
            "protocol_valid_sessions": sum(o["protocol_valid"] for o in outcomes),
            "model_requests": sum(len(s["calls"]) for s in sessions.values()),
            "protocol_rejections": sum(s["rejected_action_count"] for s in sessions.values()),
            "protocol_repair_calls": sum(c["attempt"] > 1 for s in sessions.values() for c in s["calls"]),
            "http_post_attempts": http_attempts, "http_error_counts": dict(http_errors),
            "paired_starting_requests_checked": pairs_checked,
            "all_requests_and_protocol_receipts_replayed": True, "observed_successful_response_usage": dict(usage),
            "per_model": per_model, "dataset_manifest_sha256": sha_file(DATA / "manifest.json"),
            "evidence_paths": [p.relative_to(ROOT).as_posix() for p in folders],
            "source_sha256": {name: sha_file(ROOT / name) for name in (
                "calendar_pipeline/core.py", "calendar_pipeline/protocol.py", "calendar_pipeline/reliable.py",
                "calendar_pipeline/runner.py", "tools/summarize_reliable_runs.py")},
            "interpretation": "Application-assisted scheduling with model-issued control actions; not evidence of unaided model reasoning, statistical generalization, or privacy security."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = summarize()
    if args.output:
        if args.output.exists():
            parser.exit(1, "Output exists; choose a new path\n")
        save_json(args.output, report)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "passed" else 1)
