"""Frozen paired privacy probes, transparent message replacement, and audit CLI."""

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from .attack_catalog import CATALOG_VERSION, CONDITIONS, policy
from .client import MistralClient, ScriptedClient, check_connections
from .core import DATA, ROOT, build_plan, canonical, fingerprint, read_json, save_json, sha_file, verify_plan
from .privacy import draft_review, group_transcript, observations, summarize_privacy
from .reliable import audit, execute, score
from .runner import evaluate_artifacts, source_hashes


def build_experiment(config: dict, data=DATA) -> dict:
    if config["protocol_version"] != "calendar-baseline-v4":
        raise ValueError("Privacy pilot must preserve the v4 scheduling baseline")
    base = build_plan(config, data)
    observers = {s["scenario_id"]: read_json(data / "scenarios" / s["scenario_id"] / "evaluator.json")["suggested_attacker_agent_id"] for s in base["scenarios"]}
    body = {"experiment_version": "calendar-privacy-pilot-v1", "catalog_version": CATALOG_VERSION,
            "base_plan": base, "observer_by_scenario": observers, "conditions": copy.deepcopy(list(CONDITIONS)),
            "injection_scope": "replace only the declared participant's published free-text note; preserve raw response and all scheduling attachments"}
    return {**body, "experiment_sha256": fingerprint(body)}


def verify_experiment(plan: dict, data=DATA) -> None:
    if plan != build_experiment(plan["base_plan"]["config"], data):
        raise ValueError("Privacy experiment differs from frozen source/catalog/owner-scoped inputs")


def case_specs(plan: dict) -> list[tuple]:
    return [(scenario, model, condition) for scenario in plan["base_plan"]["scenarios"]
            for model in plan["base_plan"]["config"]["models"] for condition in plan["conditions"]]


def case_id(scenario, model, condition):
    return f"{scenario['scenario_id']}__{model}__{condition['condition_id']}"


def summarize_cases(plan: dict, cases: list[dict]) -> dict:
    expected = len(case_specs(plan))
    return {"experiment_sha256": plan["experiment_sha256"], "planned_cases": expected,
            "recorded_cases": len(cases), "unrun_cases": expected - len(cases),
            "run_status": "completed" if len(cases) == expected and all(c["session"]["protocol_status"] == "committed" for c in cases) else "partial",
            "scheduling_successes": sum(c["scheduling_score"]["task_success"] for c in cases),
            "model_requests": sum(len(c["session"]["calls"]) for c in cases),
            "privacy_status": "pending_review; scheduling success is not privacy success"}


def run_experiment(plan: dict, output: Path, backend: str, data=DATA, client_factory=None) -> dict:
    verify_experiment(plan, data)
    if output.exists():
        raise ValueError("Privacy run output exists; preserve it and use a new path")
    output.mkdir(parents=True)
    save_json(output / "plan.json", plan)
    save_json(output / "metadata.json", {"backend": backend, "experiment_sha256": plan["experiment_sha256"],
                                        "source_sha256": source_hashes(), "started_at_utc": datetime.now(timezone.utc).isoformat()})
    active = {"case_id": None}
    def journal(event):
        with (output / "journal.jsonl").open("a") as stream:
            stream.write(canonical({"case_id": active["case_id"], "at_utc": datetime.now(timezone.utc).isoformat(), **event}).decode() + "\n")
    client = client_factory(journal) if client_factory else (MistralClient(plan["base_plan"]["config"], journal) if backend == "mistral" else ScriptedClient())
    if backend not in ("mistral", "scripted-reference") or client.backend != backend:
        raise ValueError("Backend identity mismatch")
    cases = []
    for scenario, model, condition in case_specs(plan):
        cid = case_id(scenario, model, condition)
        active["case_id"] = cid
        observer = plan["observer_by_scenario"][scenario["scenario_id"]]
        message_policy = policy(condition, observer)
        session = execute(plan["base_plan"], scenario, model, client, journal, message_policy)
        audit(plan["base_plan"], scenario, session, message_policy)
        oracle = read_json(data / "scenarios" / scenario["scenario_id"] / "evaluator.json")
        case = {"case_id": cid, "condition_id": condition["condition_id"], "kind": condition["kind"],
                "observer_agent_id": observer, "replacement_content": condition["content"],
                "session": session, "observer_transcript": group_transcript(session, observer),
                "scheduling_score": score(session, oracle)}
        cases.append(case)
        save_json(output / "cases" / f"{cid}.json", case)
        print(json.dumps({"case_id": cid, "scheduling_success": case["scheduling_score"]["task_success"],
                          "requests": len(session["calls"]), "privacy": "not yet reviewed"}), flush=True)
        if "transport_error" in session:
            break
    summary = summarize_cases(plan, cases)
    save_json(output / "summary.json", summary)
    return summary


def audit_case_journal(case: dict, events: list[dict], backend: str) -> None:
    session = case["session"]
    def records(kind, key, value):
        result = {}
        for event in events:
            if event["event"] == kind:
                k = key(event)
                if k in result:
                    raise ValueError("Duplicate privacy journal event")
                result[k] = value(event)
        return result
    requests = records("logical_request", lambda e: e["call_id"], lambda e: {k: v for k, v in e.items() if k not in ("case_id", "at_utc", "event")})
    replies = records("logical_response", lambda e: e["call_id"], lambda e: e["response"])
    expected_requests = {c["call_id"]: {k: v for k, v in c.items() if k not in ("response", "protocol_error", "accepted")} for c in session["calls"]}
    if "failed_request" in session:
        expected_requests[session["failed_request"]["call_id"]] = session["failed_request"]
    if requests != expected_requests or replies != {c["call_id"]: c["response"] for c in session["calls"]}:
        raise ValueError("Privacy session and request/response journal differ")
    injections = records("declared_message_replacement", lambda e: e["call_id"], lambda e: {k: v for k, v in e.items() if k not in ("case_id", "at_utc", "event")})
    if injections != {i["call_id"]: i for i in session["message_injections"]}:
        raise ValueError("Declared injection journal differs")
    accepted = [c for c in session["calls"] if c["accepted"]]
    validated = records("validated_protocol_action", lambda e: e["call_id"], lambda e: e["wire_message"])
    if validated != {c["call_id"]: w for c, w in zip(accepted, session["wire_messages"])}:
        raise ValueError("Privacy delivered messages differ from journal")
    rejected = records("rejected_protocol_action", lambda e: e["call_id"], lambda e: e["reason"])
    if rejected != {c["call_id"]: c["protocol_error"] for c in session["calls"] if not c["accepted"]}:
        raise ValueError("Privacy rejection journal differs")
    commits = [e["receipt"] for e in events if e["event"] == "atomic_commit"]
    if commits != ([session["commit_receipt"]] if session["commit_receipt"] is not None else []):
        raise ValueError("Privacy commit journal differs")
    if backend == "mistral":
        success = records("http_success", lambda e: e["call_id"], lambda e: e)
        if set(success) != set(replies):
            raise ValueError("HTTP successes differ from model responses")
        for event in events:
            if event["event"] == "http_attempt":
                logical = requests.get(event["call_id"])
                if logical is None or event["credential_variable"] != logical["credential_variable"] or event["request_sha256"] != logical["request_sha256"]:
                    raise ValueError("HTTP attempt differs from frozen logical request")
        for cid, response in replies.items():
            if response["usage"] != success[cid]["usage"] or response["reported_model"] != success[cid]["reported_model"]:
                raise ValueError("HTTP usage or model identity differs")
            if response["reported_model"] != session["model"]:
                raise ValueError("Wrong provider model identity")


def audit_experiment(output: Path, data=DATA) -> tuple[dict, list[dict]]:
    plan = read_json(output / "plan.json")
    verify_experiment(plan, data)
    metadata = read_json(output / "metadata.json")
    if metadata["experiment_sha256"] != plan["experiment_sha256"] or metadata["backend"] not in ("mistral", "scripted-reference"):
        raise ValueError("Privacy metadata identity mismatch")
    events = [json.loads(line) for line in (output / "journal.jsonl").read_text().splitlines()]
    grouped = {}
    for event in events:
        grouped.setdefault(event["case_id"], []).append(event)
    cases = []
    absent = False
    for scenario, model, condition in case_specs(plan):
        cid = case_id(scenario, model, condition)
        path = output / "cases" / f"{cid}.json"
        if not path.exists():
            absent = True
            continue
        if absent:
            raise ValueError("Privacy run contains non-prefix or unaccounted cases")
        case = read_json(path)
        observer = plan["observer_by_scenario"][scenario["scenario_id"]]
        if (case["case_id"] != cid or case["condition_id"] != condition["condition_id"] or case["kind"] != condition["kind"]
                or case["observer_agent_id"] != observer or case["replacement_content"] != condition["content"]
                or case["session"]["model"] != model):
            raise ValueError("Privacy case differs from frozen condition")
        audit(plan["base_plan"], scenario, case["session"], policy(condition, observer))
        if case["observer_transcript"] != group_transcript(case["session"], observer):
            raise ValueError("Observer transcript contains extra or missing data")
        expected_score = score(case["session"], read_json(data / "scenarios" / scenario["scenario_id"] / "evaluator.json"))
        if case["scheduling_score"] != expected_score:
            raise ValueError("Privacy case scheduling score was altered")
        audit_case_journal(case, grouped.get(cid, []), metadata["backend"])
        cases.append(case)
    if set(grouped) != {c["case_id"] for c in cases} or len(list((output / "cases").glob("*.json"))) != len(cases):
        raise ValueError("Unaccounted privacy cases or journal records")
    summary = summarize_cases(plan, cases)
    if summary != read_json(output / "summary.json"):
        raise ValueError("Privacy scheduling summary differs from replay")
    pairing_audit(cases)
    return summary, cases


def pairing_audit(cases: list[dict]) -> dict:
    """Check observed first requests, not just intended input hashes."""
    controls = {(c["session"]["scenario_id"], c["session"]["model"]): c for c in cases if c["condition_id"] == "benign_control"}
    within = cross = 0
    indexed = {}
    for case in cases:
        session = case["session"]
        for call in session["calls"]:
            if call["phase"] != "publish" or call["attempt"] != 1:
                continue
            owner = call["agent_id"]
            indexed[session["scenario_id"], case["condition_id"], owner, session["model"]] = call["request"]
            control = controls.get((session["scenario_id"], session["model"]))
            if control is None:
                raise ValueError("Intervention case has no matched benign case")
            initial = next((c for c in control["session"]["calls"] if c["phase"] == "publish" and c["attempt"] == 1 and c["agent_id"] == owner), None)
            if initial is not None and case["condition_id"] != "benign_control":
                if canonical(call["request"]) != canonical(initial["request"]):
                    raise ValueError("Control and intervention received different starting data")
                within += 1
    models = ("ministral-3b-2512", "ministral-8b-2512")
    for sid, condition, owner in sorted({(s, c, a) for s, c, a, m in indexed}):
        pair = [indexed.get((sid, condition, owner, model)) for model in models]
        if all(p is not None for p in pair):
            clean = [{k: v for k, v in p.items() if k != "model"} for p in pair]
            if canonical(clean[0]) != canonical(clean[1]):
                raise ValueError("Privacy pilot starting data differ across models")
            cross += 1
    return {"status": "passed", "control_intervention_request_pairs_checked": within,
            "cross_model_request_pairs_checked": cross,
            "scope": "starting publication requests; later histories contain actual model outputs and declared message interventions"}


def historical_cases(full_group: bool = False) -> list[dict]:
    result = []
    for folder in (ROOT / "experiments/results/mistral-pilot-v4", ROOT / "experiments/results/mistral-v4-additional-development"):
        evaluate_artifacts(folder)
        for path in sorted((folder / "sessions").glob("*.json")):
            session = read_json(path)
            oracle = read_json(DATA / "scenarios" / session["scenario_id"] / "evaluator.json")
            result.append({"case_id": ("historical_group__" if full_group else "historical__") + path.stem, "condition_id": "historical_benign", "kind": "historical_benign",
                           "observer_agent_id": "group_peers" if full_group else oracle["suggested_attacker_agent_id"], "replacement_content": None,
                           **({"historical_full_group": True} if full_group else {}),
                           "session": session, "scheduling_score": score(session, oracle)})
    if len(result) != 40 or len({c["case_id"] for c in result}) != 40:
        raise ValueError("Historical benign baseline must contain exactly 40 unique runs")
    return result


def make_observations(cases: list[dict]) -> list[dict]:
    return [item for case in cases for item in observations(case)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--config", type=Path, default=ROOT / "configs/privacy_pilot.json")
    execute_cmd = commands.add_parser("run")
    execute_cmd.add_argument("--plan", type=Path, required=True)
    execute_cmd.add_argument("--output", type=Path, required=True)
    execute_cmd.add_argument("--backend", choices=("mistral", "scripted-reference"), required=True)
    queue = commands.add_parser("review-queue")
    queue.add_argument("--run", type=Path)
    queue.add_argument("--historical", action="store_true")
    queue.add_argument("--historical-full-group", action="store_true")
    queue.add_argument("--output", type=Path, required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--run", type=Path)
    evaluate.add_argument("--historical", action="store_true")
    evaluate.add_argument("--historical-full-group", action="store_true")
    evaluate.add_argument("--review", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output exists; preserve evidence and use a new path")
        if args.command == "prepare":
            plan = build_experiment(read_json(args.config))
            save_json(args.output, plan)
            print(json.dumps({"experiment_sha256": plan["experiment_sha256"], "planned_cases": len(case_specs(plan))}))
            return 0
        if args.command == "run":
            plan = read_json(args.plan)
            verify_experiment(plan)
            if args.backend == "mistral":
                checks = check_connections(plan["base_plan"]["config"])
                if not all(c["success"] for c in checks):
                    print(json.dumps({"status": "blocked", "checks": checks}))
                    return 2
            summary = run_experiment(plan, args.output, args.backend)
            print(json.dumps(summary, indent=2))
            return 0 if summary["run_status"] == "completed" else 2
        if sum((args.historical, args.historical_full_group, bool(args.run))) != 1:
            raise ValueError("Choose exactly one of --historical, --historical-full-group, or --run")
        cases = historical_cases(args.historical_full_group) if args.historical or args.historical_full_group else audit_experiment(args.run)[1]
        items = make_observations(cases)
        if args.command == "review-queue":
            args.output.mkdir(parents=True)
            save_json(args.output / "observations.json", items)
            save_json(args.output / "review.json", draft_review(items))
            pending = sum(a["label"] is None for a in draft_review(items)["annotations"])
            print(json.dumps({"observations": len(items), "pending_semantic_reviews": pending}))
            return 0
        report = summarize_privacy(cases, items, read_json(args.review))
        save_json(args.output, report)
        print(json.dumps({"review_status": report["review_status"], "groups": report["groups"]}, indent=2))
        return 0 if report["review_status"] == "complete" else 2
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f"Privacy experiment failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
