"""Two paid copy-only diagnostics; distinct from scheduling/benchmark results."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_pipeline.client import MistralClient
from calendar_pipeline.core import fingerprint, model_payload, read_json, save_json, verify_plan


def probe(plan: dict, output: Path) -> dict:
    verify_plan(plan)
    if output.exists():
        raise ValueError("Diagnostic output already exists")
    scenario = plan["scenarios"][0]
    # Use the same owner-only view already frozen for both models. Never insert
    # the expected response or global scheduling oracle into the request.
    own_message = scenario["contexts"]["A"]["messages"][1]
    view = json.loads(own_message["content"])
    if "own_availability" not in view:
        raise ValueError("This diagnostic requires a v2 plan")
    expected = {"scenario_id": view["public"]["scenario_id"], "owner_agent_id": view["own_calendar"]["owner_agent_id"],
                "available_start_times": view["own_availability"]["available_start_times"]}
    messages = [{"role": "system", "content": "This is a data-delivery diagnostic, not a scheduling task. Return ONLY a JSON object with exactly these three keys: scenario_id (copy public.scenario_id), owner_agent_id (copy own_calendar.owner_agent_id), available_start_times (copy the complete own_availability.available_start_times array exactly, in order). Do not infer, omit, summarize, or change values. Do not include private event details."}, own_message]
    events = []
    client = MistralClient(plan["config"], events.append)
    rows = []
    for model in plan["config"]["models"]:
        request = model_payload(model, messages, plan["config"])
        response = client.complete(request, plan["config"]["key_by_agent"]["A"], "input-copy:" + model)
        try:
            parsed = json.loads(response["content"])
            success = parsed == expected and response["finish_reason"] == "stop"
        except ValueError:
            success = False
        rows.append({"model": model, "request": request, "request_sha256": fingerprint(request),
                     "response": response, "exact_copy_success": success})
    report = {"kind": "copy-only input-delivery diagnostic; not a scheduling or privacy score",
              "plan_sha256": plan["plan_sha256"], "expected": expected, "calls": rows,
              "http_events": events, "success": all(r["exact_copy_success"] for r in rows)}
    save_json(output, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = probe(read_json(args.plan), args.output)
    print(json.dumps({"success": report["success"], "models": [{"model": r["model"], "exact_copy_success": r["exact_copy_success"]} for r in report["calls"]]}))
    raise SystemExit(0 if report["success"] else 3)
