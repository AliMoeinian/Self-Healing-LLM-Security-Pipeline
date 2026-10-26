"""Re-audit execution, observation coverage, and AI-assisted privacy annotations."""

import argparse
from collections import Counter
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_pipeline.core import ROOT, read_json, save_json, sha_file
from calendar_pipeline.privacy import summarize_privacy
from calendar_pipeline.privacy_experiment import audit_experiment, historical_cases, make_observations, pairing_audit


def summarize() -> dict:
    folder = ROOT / "experiments/privacy"
    run = folder / "paired_runs"
    scheduling, cases = audit_experiment(run)
    items = make_observations(cases)
    review = read_json(folder / "paired_review/review.json")
    privacy = summarize_privacy(cases, items, review)
    if privacy != read_json(folder / "paired_privacy_report.json"):
        raise ValueError("Stored paired privacy report is stale or altered")
    historical = historical_cases(full_group=True)
    historical_items = make_observations(historical)
    historical_report = summarize_privacy(historical, historical_items, read_json(folder / "historical_group_review/review.json"))
    if historical_report != read_json(folder / "historical_group_privacy_report.json"):
        raise ValueError("Stored historical privacy report differs")
    injection = [g for g in privacy["groups"] if g["kind"] == "prompt_injection"]
    direct = [g for g in privacy["groups"] if g["kind"] == "direct_privacy_request"]
    control = [g for g in privacy["groups"] if g["kind"] == "benign"]
    events = [json.loads(line) for line in (run / "journal.jsonl").read_text().splitlines()]
    usage = Counter()
    for case in cases:
        for call in case["session"]["calls"]:
            usage.update(call["response"]["usage"])
    return {"status": "audited; semantic labels are AI-assisted and awaiting human confirmation",
            "scheduling": scheduling, "pairing": pairing_audit(cases),
            "historical_cases": len(historical), "historical_published_messages_reviewed": len(historical_items),
            "historical_detail_leaking_cases": sum(g["confirmed_leaking_sessions"] for g in historical_report["groups"]),
            "paired_published_messages_reviewed": len(items),
            "post_intervention_messages_reviewed": sum(o["post_intervention_response"] is True for o in items),
            "prompt_injection": {"evaluable_sessions": sum(g["evaluable_sessions"] for g in injection),
                                 "private_detail_disclosure_sessions": sum(g["confirmed_leaking_sessions"] for g in injection),
                                 "consistently_attributed_event_disclosure_sessions": sum(g["consistently_attributed_event_disclosure_sessions"] for g in injection),
                                 "misattributed_private_detail_sessions": sum(g["misattributed_private_detail_disclosure_sessions"] for g in injection)},
            "direct_request": {"evaluable_sessions": sum(g["evaluable_sessions"] for g in direct), "leaking_sessions": sum(g["confirmed_leaking_sessions"] for g in direct)},
            "matched_benign_control": {"evaluable_sessions": sum(g["evaluable_sessions"] for g in control), "leaking_sessions": sum(g["confirmed_leaking_sessions"] for g in control)},
            "new_disclosures_relative_to_matched_control": sum(p["new_disclosure_relative_to_control"] is True for p in privacy["paired_comparisons"]),
            "groups": privacy["groups"], "observed_successful_response_usage": dict(usage),
            "http_attempts": sum(e["event"] == "http_attempt" for e in events),
            "http_error_status_counts": dict(Counter(str(e["status"]) for e in events if e["event"] == "http_error")),
            "human_review": {"status": "pending", "original_subset_message_count": 176, "paired_message_count": 180,
                             "original_subset_csv": "experiments/privacy/human_review_176/messages.csv", "paired_csv": "experiments/privacy/human_review_paired180/messages.csv"},
            "source_sha256": {name: sha_file(ROOT / name) for name in (
                "calendar_pipeline/privacy.py", "calendar_pipeline/privacy_experiment.py", "calendar_pipeline/attack_catalog.py", "tools/summarize_privacy_evidence.py")},
            "limits": ["No independent human audit yet.", "Only four development scenarios and three fixed nonadaptive injection payloads.",
                       "A direct request is reported separately from prompt injection.", "One positive contains incorrect owner/conflict attribution despite disclosing real private values.",
                       "Paired differences are observations, not a controlled estimate of general causal effects.", "No Garak integration or mitigation evaluation in this stage."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = summarize()
    if args.output:
        if args.output.exists():
            parser.exit(1, "Output exists; preserve evidence and use a new path\n")
        save_json(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k not in ("groups", "source_sha256")}, indent=2))
