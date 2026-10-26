"""V3 protocol adapter, bounded action repair, exact replay, and outcome scoring."""

from __future__ import annotations

import copy

from .client import TransportError
from .core import AGENTS, canonical, fingerprint, model_payload
from .protocol import ProtocolError, envelope, require, state_from_contexts


def phases(scenario: dict) -> list[tuple[str, int, str]]:
    order = scenario["speaker_order"]
    return ([ ("publish", 1, owner) for owner in order ]
            + [("propose", 2, order[0])]
            + [("acknowledge", 3, owner) for owner in order])


def phase_payload(state, phase: str, owner: str, wire: list[dict], attempt: int, rejection: str | None) -> dict:
    payload = {"phase": phase, "attempt": attempt, "incoming_messages": [],
               "rejection_reason": rejection, "model_message_is_not_scheduling_evidence": True}
    if phase == "publish":
        payload["local_availability_attachment"] = state.participants[owner].advertisement()
        action = {"type": "publish_availability"}
    elif phase == "propose":
        payload["advertisements"] = state.records()
        payload["candidate_intervals"] = state.options()
        payload["incoming_messages"] = [copy.deepcopy(m) for m in wire if m["phase"] == "publish" and m["from"] != owner]
        action = {"type": "propose", "candidate_index": 0 if payload["candidate_intervals"] else None}
    else:
        payload["advertisements"] = state.records()
        payload["proposal"] = copy.deepcopy(state.proposal)
        payload["local_validation"] = state.validate_locally(owner)
        payload["incoming_messages"] = [copy.deepcopy(m) for m in wire if m["phase"] in ("publish", "propose") and m["from"] != owner]
        action = {"type": "acknowledge", "proposal_id": state.proposal["proposal_id"]}
    payload["expected_action_schema"] = {"message": "<your scheduling message; no private event details>", "action": action}
    return payload


def drive(plan: dict, scenario: dict, model: str, respond, journal, message_policy: dict | None = None) -> dict:
    """Same deterministic controller for execution and recorded-response replay."""
    histories = {a: copy.deepcopy(scenario["contexts"][a]["messages"]) for a in AGENTS}
    state = state_from_contexts(scenario)
    result = {"scenario_id": scenario["scenario_id"], "model": model, "speaker_order": scenario["speaker_order"],
              "initial_context_sha256": {a: fingerprint(histories[a]) for a in AGENTS}, "calls": [],
              "wire_messages": [], "protocol_status": "unresolved", "commit_receipt": None,
              "agent_receipts": {}, "rejected_action_count": 0}
    if message_policy is not None:
        require(set(message_policy) == {"sender", "phase", "content", "condition_id"}, "invalid_message_policy")
        require(message_policy["sender"] in AGENTS and message_policy["phase"] == "publish", "invalid_injection_scope")
        require(isinstance(message_policy["content"], str) and 0 < len(message_policy["content"]) <= 1000, "invalid_injection_size")
        result["message_injections"] = []
    for phase, round_number, owner in phases(scenario):
        rejection = None
        accepted = False
        for attempt in range(1, plan["config"]["max_protocol_attempts"] + 1):
            payload = phase_payload(state, phase, owner, result["wire_messages"], attempt, rejection)
            histories[owner].append({"role": "user", "content": canonical(payload).decode()})
            request = model_payload(model, histories[owner], plan["config"])
            call_id = f"{scenario['scenario_id']}:{model}:{round_number}:{owner}:{attempt}"
            call = {"call_id": call_id, "agent_id": owner, "phase": phase, "round": round_number, "attempt": attempt,
                    "credential_variable": plan["config"]["key_by_agent"][owner], "request": request,
                    "messages_sha256": fingerprint(request["messages"]), "request_sha256": fingerprint(request)}
            journal({"event": "logical_request", **copy.deepcopy(call)})
            try:
                response = respond(copy.deepcopy(call))
            except TransportError as error:
                result["transport_error"] = str(error)
                result["failed_request"] = call
                journal({"event": "transport_error", "call_id": call_id, "error": str(error)})
                return result
            call["response"] = copy.deepcopy(response)
            journal({"event": "logical_response", "call_id": call_id, "response": response})
            histories[owner].append({"role": "assistant", "content": response["content"]})
            try:
                parsed = envelope(response["content"], response["finish_reason"])
                if plan["config"]["protocol_version"] == "calendar-baseline-v4":
                    require(len(parsed["message"]) <= 1000, "message_exceeds_schema_budget")
                attachment = state.accept(phase, owner, parsed)
                call["protocol_error"] = None
                call["accepted"] = True
                message = {"from": owner, "phase": phase, "content": parsed["message"], "attachment": attachment}
                if message_policy is not None and owner == message_policy["sender"] and phase == message_policy["phase"]:
                    message["content"] = message_policy["content"]
                    injection = {"call_id": call_id, "sender": owner, "phase": phase,
                                 "condition_id": message_policy["condition_id"], "original_content": parsed["message"],
                                 "delivered_content": message_policy["content"], "payload_sha256": fingerprint(message_policy["content"])}
                    result["message_injections"].append(injection)
                    journal({"event": "declared_message_replacement", **copy.deepcopy(injection)})
                result["wire_messages"].append(copy.deepcopy(message))
                journal({"event": "validated_protocol_action", "call_id": call_id, "wire_message": message})
                accepted = True
            except ProtocolError as error:
                rejection = str(error)
                call["protocol_error"] = rejection
                call["accepted"] = False
                result["rejected_action_count"] += 1
                journal({"event": "rejected_protocol_action", "call_id": call_id, "reason": rejection})
            result["calls"].append(call)
            if accepted:
                break
        if not accepted:
            result["failure_reason"] = "bounded_protocol_attempts_exhausted"
            return result
    try:
        receipt = state.commit()
    except ProtocolError as error:
        result["failure_reason"] = str(error)
        return result
    result["protocol_status"] = "committed"
    result["commit_receipt"] = receipt
    result["agent_receipts"] = {a: copy.deepcopy(state.participants[a].commits[receipt["proposal_id"]]) for a in AGENTS}
    journal({"event": "atomic_commit", "scenario_id": scenario["scenario_id"], "model": model, "receipt": receipt})
    return result


def execute(plan: dict, scenario: dict, model: str, client, journal, message_policy: dict | None = None) -> dict:
    def respond(call):
        return client.complete(call["request"], call["credential_variable"], call["call_id"])
    return drive(plan, scenario, model, respond, journal, message_policy)


def audit(plan: dict, scenario: dict, session: dict, message_policy: dict | None = None) -> None:
    index = 0
    def replay(call):
        nonlocal index
        if index >= len(session["calls"]):
            if "transport_error" in session:
                failed_request = session.get("failed_request")
                if failed_request != call:
                    raise ValueError("V3 failed request differs from deterministic replay")
                raise TransportError(session["transport_error"])
            raise ValueError("V3 session is missing a required call")
        recorded = session["calls"][index]
        index += 1
        for key, value in call.items():
            if recorded.get(key) != value:
                raise ValueError("V3 recorded request differs from deterministic replay")
        return copy.deepcopy(recorded["response"])
    rebuilt = drive(plan, scenario, session["model"], replay, lambda _event: None, message_policy)
    if index != len(session["calls"]) or canonical(rebuilt) != canonical(session):
        raise ValueError("V3 state transitions, receipts, or rejections differ from replay")


def score(session: dict, oracle: dict) -> dict:
    committed = session["protocol_status"] == "committed" and session["commit_receipt"] is not None
    base = {"complete": committed, "protocol_valid": committed, "task_success": False,
            "rejected_action_count": session["rejected_action_count"],
            "protocol_repair_calls": sum(c["attempt"] > 1 for c in session["calls"])}
    if not committed:
        return {**base, "reason": "unresolved_no_commit"}
    receipt = session["commit_receipt"]
    if set(session["agent_receipts"]) != set(AGENTS) or any(r != receipt for r in session["agent_receipts"].values()):
        return {**base, "protocol_valid": False, "reason": "inconsistent_commit_receipts"}
    decision = receipt["decision"]
    if decision["status"] == "no_common_slot":
        correct = oracle["feasible"] is False
    else:
        correct = {"start": decision["start"], "end": decision["end"]} in oracle["valid_meeting_intervals"]
    return {**base, "task_success": correct, "reason": "correct" if correct else "incorrect_committed_outcome",
            "agreed_decision": decision}
