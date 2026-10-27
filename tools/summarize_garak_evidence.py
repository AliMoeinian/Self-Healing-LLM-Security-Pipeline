"""Offline aggregation of the published garak replay and live smoke evidence."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_pipeline.core import ROOT, canonical, read_json, save_json, sha_file
from calendar_pipeline.garak_scan import audit_scan


def summarize():
    folder = ROOT / "experiments/garak"
    bundles = {}
    for name, source in (("replay_v1", ROOT / "experiments/privacy/paired_runs"), ("live_v1", None)):
        path = folder / name
        manifest = read_json(path / "export_manifest.json")
        for relative, digest in manifest["files_sha256"].items():
            if sha_file(path / relative) != digest:
                raise ValueError("Published garak evidence file differs from export manifest")
        audit = audit_scan(path, source)
        summary = read_json(path / "summary.json")
        bundles[name] = {k: v for k, v in summary.items() if k not in ("cases", "pairing_audit")}
        bundles[name]["audit"] = audit
        bundles[name]["pairing_audit"] = summary["pairing_audit"]
    live = folder / "live_v1/application"
    events = [json.loads(l) for l in (live / "journal.jsonl").read_text().splitlines()]
    successes = [e for e in events if e["event"] == "http_success"]
    usage = {k: sum(e["usage"][k] for e in successes) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    live_cases = [read_json(p) for p in sorted((live / "cases").glob("*.json"))]
    source = ROOT / "experiments/privacy/paired_runs/cases"
    same_start = 0
    for case in live_cases:
        if case["condition_id"] != "benign_control":
            continue
        previous = read_json(source / (case["case_id"] + ".json"))
        for owner in ("A", "B", "C"):
            def first(c):
                return next(call["request"] for call in c["session"]["calls"] if call["phase"] == "publish" and call["agent_id"] == owner and call["attempt"] == 1)
            if canonical(first(case)) != canonical(first(previous)):
                raise ValueError("Live smoke and earlier pilot started with different owner data/settings")
            same_start += 1
    return {"garak_version": "0.17.1", "bundles": bundles, "live_provider_usage": usage,
            "live_http_post_attempts": sum(e["event"] == "http_attempt" for e in events),
            "live_http_errors": sum(e["event"] == "http_error" for e in events),
            "live_rejected_actions": sum(e["event"] == "rejected_protocol_action" for e in events),
            "live_vs_earlier_pilot_identical_starting_requests": same_start,
            "human_review_status": "pending; no human labels supplied",
            "human_confirmed_disclosure_rate": None,
            "limits": ["Replay reuses the original 40 cases; it adds zero independent model observations.",
                       "The 10 live cases are a selected one-scenario integration smoke, not a broad vulnerability estimate.",
                       "Exact candidates need semantic review; a zero is not evidence of confidentiality.",
                       "The initial garak reports are retained separately from future human-scored reports."]}


if __name__ == "__main__":
    result = summarize()
    save_json(ROOT / "experiments/garak/evidence_summary.json", result)
    print(json.dumps(result, indent=2))
