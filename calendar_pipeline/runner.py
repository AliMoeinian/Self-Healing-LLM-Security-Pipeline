"""Persist every logical call and evaluate only after model contexts are built."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from .client import MistralClient, ScriptedClient, TransportError
from .core import AGENTS, DATA, ROOT, canonical, fingerprint, model_payload, parse_reply, phase_message, read_json, save_json, score_session, sha_file, verify_plan


def source_hashes() -> dict:
    return {p.relative_to(ROOT).as_posix(): sha_file(p) for p in sorted((ROOT / "calendar_pipeline").glob("*.py"))}


def execute_session(plan: dict, scenario: dict, model: str, client, journal) -> dict:
    if plan["config"]["protocol_version"] in ("calendar-baseline-v3", "calendar-baseline-v4"):
        from .reliable import execute
        return execute(plan, scenario, model, client, journal)
    histories = {a: copy.deepcopy(scenario["contexts"][a]["messages"]) for a in AGENTS}
    result = {"scenario_id": scenario["scenario_id"], "model": model,
              "speaker_order": scenario["speaker_order"], "initial_context_sha256": {a: fingerprint(histories[a]) for a in AGENTS},
              "calls": []}
    previous = []
    for phase, round_number in (("discussion", 1), ("discussion", 2), ("final", 3)):
        outgoing = []
        for owner in scenario["speaker_order"]:
            # Snapshot ONLY prior-round messages. Current-round outgoing is not
            # visible here, eliminating order-dependent exposure within a round.
            incoming = [copy.deepcopy(m) for m in previous if m["from"] != owner]
            histories[owner].append(phase_message(phase, round_number, incoming, plan["config"]["protocol_version"]))
            request = model_payload(model, histories[owner], plan["config"])
            call_id = f"{scenario['scenario_id']}:{model}:{round_number}:{owner}"
            call = {"call_id": call_id, "agent_id": owner, "phase": phase, "round": round_number,
                    "credential_variable": plan["config"]["key_by_agent"][owner],
                    "request": request, "messages_sha256": fingerprint(request["messages"]),
                    "request_sha256": fingerprint(request)}
            journal({"event": "logical_request", **copy.deepcopy(call)})
            try:
                response = client.complete(request, call["credential_variable"], call_id)
            except TransportError as error:
                result["transport_error"] = str(error)
                journal({"event": "transport_error", "call_id": call_id, "error": str(error)})
                return result
            call["response"] = response
            result["calls"].append(call)
            journal({"event": "logical_response", "call_id": call_id, "response": response})
            try:
                parsed = parse_reply(response["content"], phase, response["finish_reason"])
                broadcast = parsed["message"]
                call["protocol_error"] = None
            except (ValueError, TypeError, KeyError):
                call["protocol_error"] = "invalid_model_reply"
                # Preserve actual output; no silent repair or semantic filtering.
                broadcast = response["content"]
            histories[owner].append({"role": "assistant", "content": response["content"]})
            outgoing.append({"from": owner, "content": broadcast})
        previous = outgoing
    return result


def audit_session(plan: dict, scenario: dict, session: dict) -> None:
    """Reconstruct EVERY recorded request from the frozen plan and prior outputs."""
    if plan["config"]["protocol_version"] in ("calendar-baseline-v3", "calendar-baseline-v4"):
        from .reliable import audit
        return audit(plan, scenario, session)
    if session["scenario_id"] != scenario["scenario_id"] or session["speaker_order"] != scenario["speaker_order"] or session["model"] not in plan["config"]["models"]:
        raise ValueError("Session identity or role order mismatch")
    expected_hashes = {a: scenario["contexts"][a]["sha256"] for a in AGENTS}
    if session["initial_context_sha256"] != expected_hashes:
        raise ValueError("Initial input mismatch")
    histories = {a: copy.deepcopy(scenario["contexts"][a]["messages"]) for a in AGENTS}
    previous, index = [], 0
    for phase, round_number in (("discussion", 1), ("discussion", 2), ("final", 3)):
        outgoing = []
        for owner in scenario["speaker_order"]:
            if index >= len(session["calls"]):
                return  # Scorer marks incomplete sessions; never marks them successful.
            call = session["calls"][index]
            index += 1
            incoming = [copy.deepcopy(m) for m in previous if m["from"] != owner]
            histories[owner].append(phase_message(phase, round_number, incoming, plan["config"]["protocol_version"]))
            expected = model_payload(session["model"], histories[owner], plan["config"])
            expected_id = f"{scenario['scenario_id']}:{session['model']}:{round_number}:{owner}"
            if (call["call_id"] != expected_id or call["agent_id"] != owner or call["round"] != round_number
                    or call["phase"] != phase or call["credential_variable"] != plan["config"]["key_by_agent"][owner]
                    or canonical(call["request"]) != canonical(expected)
                    or call["messages_sha256"] != fingerprint(expected["messages"])
                    or call["request_sha256"] != fingerprint(expected)):
                raise ValueError("Recorded request differs from deterministic replay")
            response = call["response"]
            try:
                parsed = parse_reply(response["content"], phase, response["finish_reason"])
                broadcast = parsed["message"]
                error = None
            except (ValueError, TypeError, KeyError):
                broadcast = response["content"]
                error = "invalid_model_reply"
            if call["protocol_error"] != error:
                raise ValueError("Incorrect protocol-error annotation")
            histories[owner].append({"role": "assistant", "content": response["content"]})
            outgoing.append({"from": owner, "content": broadcast})
        previous = outgoing
    if index != len(session["calls"]):
        raise ValueError("Unexpected extra calls")


def evaluate_run(plan: dict, sessions: list[dict], backend: str, data: Path = DATA) -> dict:
    verify_plan(plan, data)
    expected = [(s["scenario_id"], m) for s in plan["scenarios"] for m in plan["config"]["models"]]
    if [(s["scenario_id"], s["model"]) for s in sessions] != expected[:len(sessions)]:
        raise ValueError("Session ordering, identity, duplication, or model pairing mismatch")
    if len(sessions) > len(expected):
        raise ValueError("Too many sessions")
    by_id = {s["scenario_id"]: s for s in plan["scenarios"]}
    outcomes = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if backend not in ("mistral", "scripted-reference"):
        raise ValueError("Unknown recorded backend")
    usage_complete = backend == "mistral" and not any("transport_error" in s for s in sessions)
    for session in sessions:
        sid = session["scenario_id"]
        audit_session(plan, by_id[sid], session)
        oracle = read_json(data / "scenarios" / sid / "evaluator.json")
        if plan["config"]["protocol_version"] in ("calendar-baseline-v3", "calendar-baseline-v4"):
            from .reliable import score as score_v3
            score = score_v3(session, oracle)
        else:
            score = score_session(session, oracle)
        outcomes.append({"scenario_id": sid, "model": session["model"], "bucket": oracle["bucket"], **score})
        for call in session["calls"]:
            response = call["response"]
            if backend == "mistral" and response["reported_model"] != session["model"]:
                raise ValueError("Provider reported a different model identity")
            if response["usage"] is None:
                usage_complete = False
            else:
                for key in usage:
                    value = response["usage"][key]
                    if type(value) is not int or value < 0:
                        raise ValueError("Invalid recorded token usage")
                    usage[key] += value
                if response["usage"]["total_tokens"] != response["usage"]["prompt_tokens"] + response["usage"]["completion_tokens"]:
                    raise ValueError("Inconsistent recorded usage")
    complete = len(sessions) == len(expected) and all(o["complete"] for o in outcomes)
    return {"backend": backend, "run_status": "completed" if complete else "partial",
            "expected_sessions": len(expected), "recorded_sessions": len(sessions),
            "complete_sessions": sum(o["complete"] for o in outcomes),
            "unrun_sessions": len(expected) - len(sessions),
            "successful_sessions": sum(o["task_success"] for o in outcomes),
            "protocol_valid_sessions": sum(o["protocol_valid"] for o in outcomes),
            "request_count": sum(len(s["calls"]) for s in sessions),
            "input_replay_audit": "passed", "observed_usage": usage if usage_complete else None,
            "usage_complete": usage_complete, "outcomes": outcomes,
            "privacy_evaluation": "not performed; no attack or validated semantic leak detector yet"}


def run(plan: dict, output: Path, backend: str, data: Path = DATA, client_factory=None) -> dict:
    verify_plan(plan, data)
    if output.exists():
        raise ValueError("Run output must not exist; choose a fresh directory")
    output.mkdir(parents=True)
    save_json(output / "plan.json", plan)
    def journal(record):
        with (output / "journal.jsonl").open("a") as stream:
            stream.write(canonical({"at_utc": datetime.now(timezone.utc).isoformat(), **record}).decode() + "\n")
    client = client_factory(journal) if client_factory else (ScriptedClient() if backend == "scripted-reference" else MistralClient(plan["config"], journal))
    if client.backend != backend:
        raise ValueError("Client backend does not match declared run backend")
    sessions = []
    metadata = {"plan_sha256": plan["plan_sha256"], "source_sha256": source_hashes(),
                "backend": backend, "started_at_utc": datetime.now(timezone.utc).isoformat()}
    save_json(output / "metadata.json", metadata)
    for scenario in plan["scenarios"]:
        for model in plan["config"]["models"]:
            session = execute_session(plan, scenario, model, client, journal)
            audit_session(plan, scenario, session)
            sessions.append(session)
            save_json(output / "sessions" / f"{scenario['scenario_id']}__{model}.json", session)
            if "transport_error" in session:
                summary = evaluate_run(plan, sessions, backend, data)
                summary["transport_error"] = session["transport_error"]
                save_json(output / "summary.json", summary)
                return summary
    summary = evaluate_run(plan, sessions, backend, data)
    save_json(output / "summary.json", summary)
    return summary


def evaluate_artifacts(output: Path, data: Path = DATA) -> dict:
    """Audit saved requests, responses, journal correspondence, and score again."""
    plan = read_json(output / "plan.json")
    metadata = read_json(output / "metadata.json")
    if metadata["plan_sha256"] != plan["plan_sha256"]:
        raise ValueError("Run metadata differs from plan")
    sessions = []
    for scenario in plan["scenarios"]:
        for model in plan["config"]["models"]:
            path = output / "sessions" / f"{scenario['scenario_id']}__{model}.json"
            if path.exists():
                sessions.append(read_json(path))
    if len(list((output / "sessions").glob("*.json"))) != len(sessions):
        raise ValueError("Unexpected session files")
    events = [json.loads(line) for line in (output / "journal.jsonl").read_text().splitlines()]
    requests, responses = {}, {}
    for event in events:
        if event["event"] in ("logical_request", "logical_response"):
            destination = requests if event["event"] == "logical_request" else responses
            if event["call_id"] in destination:
                raise ValueError("Duplicate logical journal entry")
            destination[event["call_id"]] = event
    expected_response_ids = set()
    for session in sessions:
        for call in session["calls"]:
            call_id = call["call_id"]
            expected_response_ids.add(call_id)
            request = requests[call_id]
            recorded_request = {k: v for k, v in request.items() if k not in ("at_utc", "event")}
            expected_request = {k: v for k, v in call.items() if k not in ("response", "protocol_error", "accepted")}
            if (recorded_request != expected_request
                    or responses[call_id]["response"] != call["response"]):
                raise ValueError("Session and journal disagree")
    if set(responses) != expected_response_ids:
        raise ValueError("Unaccounted journal response")
    unmatched = set(requests) - set(responses)
    failures = [s for s in sessions if "transport_error" in s]
    if len(unmatched) != len(failures) or len(failures) > 1:
        raise ValueError("Unaccounted incomplete requests")
    if plan["config"]["protocol_version"] in ("calendar-baseline-v3", "calendar-baseline-v4"):
        expected_failures = {s["failed_request"]["call_id"] for s in failures}
        if unmatched != expected_failures:
            raise ValueError("V3/V4 unmatched request identity differs from failed request")
        expected_validated, expected_rejected, expected_commits = {}, {}, {}
        for session in sessions:
            accepted = [c for c in session["calls"] if c["accepted"]]
            if len(accepted) != len(session["wire_messages"]):
                raise ValueError("Wrong accepted-action count")
            expected_validated.update({c["call_id"]: wire for c, wire in zip(accepted, session["wire_messages"])})
            expected_rejected.update({c["call_id"]: c["protocol_error"] for c in session["calls"] if not c["accepted"]})
            if session["commit_receipt"] is not None:
                expected_commits[session["scenario_id"], session["model"]] = session["commit_receipt"]
        def unique_events(event_type, key_fn, value_fn):
            found = {}
            for event in events:
                if event["event"] == event_type:
                    key = key_fn(event)
                    if key in found:
                        raise ValueError("Duplicate protocol journal event")
                    found[key] = value_fn(event)
            return found
        if unique_events("validated_protocol_action", lambda e: e["call_id"], lambda e: e["wire_message"]) != expected_validated:
            raise ValueError("Validated-action journal differs from replayed session")
        if unique_events("rejected_protocol_action", lambda e: e["call_id"], lambda e: e["reason"]) != expected_rejected:
            raise ValueError("Rejected-action journal differs from replayed session")
        if unique_events("atomic_commit", lambda e: (e["scenario_id"], e["model"]), lambda e: e["receipt"]) != expected_commits:
            raise ValueError("Commit journal differs from replayed session")
    if metadata["backend"] == "mistral":
        successes = {}
        for event in events:
            if event["event"] == "http_attempt":
                logical = requests.get(event["call_id"])
                if (logical is None or event["credential_variable"] != logical["credential_variable"]
                        or event["request_sha256"] != logical["request_sha256"]):
                    raise ValueError("HTTP attempt differs from logical request")
            if event["event"] == "http_success":
                if event["call_id"] in successes:
                    raise ValueError("Duplicate HTTP success")
                successes[event["call_id"]] = event
        if set(successes) != set(responses):
            raise ValueError("HTTP and logical response sets differ")
        for call_id, event in successes.items():
            response = responses[call_id]["response"]
            if event["usage"] != response["usage"] or event["reported_model"] != response["reported_model"]:
                raise ValueError("HTTP usage/model metadata differs from logical response")
    report = evaluate_run(plan, sessions, metadata["backend"], data)
    if failures:
        report["transport_error"] = failures[0]["transport_error"]
    if read_json(output / "summary.json") != report:
        raise ValueError("Saved scores differ from independent re-evaluation")
    return report
