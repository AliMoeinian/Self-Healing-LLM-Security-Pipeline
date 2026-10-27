"""Recompute inspectable chart rows, before/after examples and provider usage."""

import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_pipeline.core import ROOT, read_json, save_json, sha_file
from calendar_pipeline.self_healing import audit_study, specs, cid, raw_candidate_count
from calendar_pipeline.privacy import observations


def summarize(run, output):
    audit = audit_study(run)
    manifest_path = run / "export_manifest.json"
    if manifest_path.exists():
        for relative, digest in read_json(manifest_path)["files_sha256"].items():
            if sha_file(run / relative) != digest:
                raise ValueError("Published self-healing source differs from export manifest")
    plan, summary = read_json(run / "plan.json"), read_json(run / "summary.json")
    cases = [read_json(run / "cases" / (cid(s, m, c, v) + ".json")) for s, m, c, v in specs(plan)]
    by_id = {c["case_id"]: c for c in cases}
    records = summary["cases"]
    groups = []
    for variant in plan["variants"]:
        for model in plan["experiment"]["base_plan"]["config"]["models"]:
            for condition in plan["experiment"]["conditions"]:
                selected = [r for r in records if r["variant"] == variant["id"] and r["model"] == model and r["condition_id"] == condition["condition_id"]]
                eligible = [r for r in selected if r["evaluable"]]
                groups.append({"variant": variant["id"], "model": model, "condition_id": condition["condition_id"],
                               "kind": condition["kind"], "sessions": len(selected), "evaluable": len(eligible),
                               "candidate_sessions": sum(r["candidate_flagged"] is True for r in eligible),
                               "raw_model_candidate_sessions": sum(r["raw_model_candidate"] for r in selected),
                               "scheduling_successes": sum(r["scheduling_success"] for r in selected)})
    comparisons, examples = [], []
    for row in records:
        if row["variant"] == "none":
            continue
        base_id = row["case_id"].replace(row["variant"] + "__", "none__", 1)
        baseline = next(r for r in records if r["case_id"] == base_id)
        comparisons.append({"baseline_case_id": base_id, "patched_case_id": row["case_id"], "variant": row["variant"],
                            "kind": row["kind"], "evaluable_pair": row["evaluable"] and baseline["evaluable"],
                            "baseline_candidate": baseline["candidate_flagged"], "patched_candidate": row["candidate_flagged"],
                            "both_schedules_correct": baseline["scheduling_success"] and row["scheduling_success"]})
        if baseline["candidate_flagged"] and row["variant"] == "both":
            base_items = observations(by_id[base_id])
            patched_items = observations(by_id[row["case_id"]])
            positive = next(o for o in base_items if o["post_intervention_response"] and o["lexical_candidates"])
            matched = next((o for o in patched_items if o["speaker_agent_id"] == positive["speaker_agent_id"] and o["phase"] == positive["phase"]), None)
            examples.append({"scenario_id": row["scenario_id"], "model": row["model"], "condition_id": row["condition_id"],
                             "speaker": positive["speaker_agent_id"], "phase": positive["phase"],
                             "baseline_case_id": base_id, "patched_case_id": row["case_id"],
                             "baseline_publication": positive["content"],
                             "patched_publication": matched["content"] if matched else None,
                             "baseline_candidates": positive["lexical_candidates"],
                             "interpretation": "Two actual paired-input executions; no claim of identical hidden model state or human confirmation"})
    events = [json.loads(l) for l in (run / "journal.jsonl").read_text().splitlines()]
    successes = [e for e in events if e["event"] == "http_success"]
    usage = {k: sum(e["usage"][k] for e in successes) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    usage_by_variant = {}
    for variant in plan["variants"]:
        own = [e for e in successes if e["case_id"].startswith(variant["id"] + "__")]
        usage_by_variant[variant["id"]] = {k: sum(e["usage"][k] for e in own) for k in usage}
    errors = {}
    for event in events:
        if event["event"] == "http_error":
            status = str(event["status"])
            errors[status] = errors.get(status, 0) + 1
    result = {"audit": audit, "run_status": summary["run_status"], "backend": read_json(run / "metadata.json")["backend"],
              "plan_sha256": plan["plan_sha256"], "recorded_sessions": summary["recorded_sessions"],
              "scheduling_successes": summary["scheduling_successes"], "logical_requests": summary["logical_requests"],
              "http_post_attempts": sum(e["event"] == "http_attempt" for e in events), "http_error_status_counts": errors,
              "provider_usage": usage, "provider_usage_by_variant": usage_by_variant,
              "groups": summary["groups"], "groups_by_model_condition": groups,
              "observations": summary["observations"], "post_delivery_observations": summary["post_delivery_observations"],
              "pairing": read_json(run / "pairing_audit.json"), "comparisons": comparisons,
              "before_after_examples": examples, "human_review_status": "pending; blank worksheets supplied",
              "human_confirmed_disclosure_rate": None,
              "raw_output_warning": "Raw model candidates are researcher-only generations, not published disclosures.",
              "limits": ["Four development fixtures and three fixed injection texts; no live held-out evaluation.",
                         "Exact-value candidates are not complete semantic leak labels; human review remains pending.",
                         "Output filtering deliberately removes all conversational prose; utility claim covers the structured task only.",
                         "Source calendars and seeds match; model outputs may differ despite temperature zero.",
                         "Configured patch activation is a proof-of-concept loop, not autonomous defense invention."]}
    output.mkdir(parents=True, exist_ok=True)
    save_json(output / "evidence_summary.json", result)
    save_json(output / "before_after_examples.json", examples)
    with (output / "chart_rows.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(groups[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(groups)
    with (output / "session_rows.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=ROOT / "experiments/self_healing/run_v1")
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/self_healing")
    args = parser.parse_args()
    result = summarize(args.run, args.output)
    print(json.dumps({k: result[k] for k in ("recorded_sessions", "scheduling_successes", "logical_requests", "http_post_attempts", "groups")}, indent=2))
