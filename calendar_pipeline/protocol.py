"""V3 scheduling state machine: local facts, explicit proposal, ACKs, atomic commit.

No evaluator, fixture file, model, or network access occurs in this module.
"""

from __future__ import annotations

import copy
import json
from datetime import date, datetime, timedelta

from .core import AGENTS, fingerprint, local_availability


class ProtocolError(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ProtocolError(reason)


def envelope(content: str, finish_reason: str) -> dict:
    require(finish_reason == "stop", "response_not_finished")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "duplicate_response_key")
            value[key] = item
        return value
    try:
        value = json.loads(content, object_pairs_hook=unique,
                           parse_constant=lambda _: require(False, "nonfinite_number"))
    except (TypeError, json.JSONDecodeError):
        raise ProtocolError("invalid_json") from None
    require(isinstance(value, dict) and set(value) == {"message", "action"}, "invalid_response_envelope")
    require(isinstance(value["message"], str) and isinstance(value["action"], dict), "invalid_response_types")
    return value


def response_schema(control: dict) -> dict:
    """Provider-side structural constraint; runtime semantics are still checked."""
    phase = control["phase"]
    if phase == "publish":
        properties = {"type": {"type": "string", "enum": ["publish_availability"]}}
    elif phase == "propose":
        options = control["candidate_intervals"]
        index = {"type": "integer", "minimum": 0, "maximum": len(options) - 1} if options else {"type": "null"}
        properties = {"type": {"type": "string", "enum": ["propose"]}, "candidate_index": index}
    else:
        require(phase == "acknowledge", "unknown_schema_phase")
        properties = {"type": {"type": "string", "enum": ["acknowledge"]},
                      "proposal_id": {"type": "string", "minLength": 64, "maxLength": 64, "pattern": "^[0-9a-f]{64}$"}}
    return {"type": "object", "additionalProperties": False, "required": ["message", "action"],
            "properties": {"message": {"type": "string", "maxLength": 1000},
                           "action": {"type": "object", "additionalProperties": False,
                                      "properties": properties, "required": list(properties)}}}


def request_id(public: dict) -> str:
    return fingerprint(public)


def validate_local_inputs(public: dict, own: dict) -> None:
    """Fail explicitly outside the fixed scheduling contract supported here."""
    require(isinstance(public, dict) and isinstance(own, dict), "invalid_calendar_input")
    needed = {"scenario_id", "timezone", "working_dates", "working_hours", "slot_minutes", "agent_ids", "meeting_request"}
    require(needed <= set(public), "missing_public_constraint")
    require(public["timezone"] == "UTC" and public["slot_minutes"] == 30, "unsupported_time_contract")
    require(public["working_hours"] == {"start": "09:00", "end": "17:00"}, "unsupported_working_hours")
    require(public["agent_ids"] == list(AGENTS), "unsupported_participant_set")
    require(public["meeting_request"] == {"participants": list(AGENTS), "duration_minutes": 120}, "unsupported_meeting_contract")
    try:
        days = [date.fromisoformat(d) for d in public["working_dates"]]
        require(len(days) == 5 and days[0].weekday() == 0 and days == [days[0] + timedelta(days=i) for i in range(5)], "unsupported_working_week")
        require(public["working_dates"] == [d.isoformat() for d in days], "noncanonical_working_dates")
        require({"owner_agent_id", "scenario_id", "events"} <= set(own) and isinstance(own["events"], list), "missing_private_calendar_field")
        previous_end = None
        for event in own["events"]:
            start, end = datetime.fromisoformat(event["start"]), datetime.fromisoformat(event["end"])
            require(start.utcoffset() == end.utcoffset() == timedelta(0), "non_utc_event")
            require(start.isoformat() == event["start"] and end.isoformat() == event["end"], "noncanonical_event_time")
            require(all(dt.minute in (0, 30) and dt.second == dt.microsecond == 0 for dt in (start, end)), "off_grid_event")
            require(start.date() in days and start.date() == end.date() and 9 <= start.hour < 17 and end.hour <= 17
                    and (end.hour < 17 or end.minute == 0) and timedelta(minutes=30) <= end - start <= timedelta(hours=2), "event_outside_contract")
            require(previous_end is None or previous_end <= start, "overlapping_or_unordered_events")
            previous_end = end
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ProtocolError):
            raise
        raise ProtocolError("invalid_calendar_timestamp_or_shape") from None


def signed(body: dict, field: str) -> dict:
    # Content hash for binding/integrity, NOT a digital signature/authentication.
    return {**copy.deepcopy(body), field: fingerprint(body)}


def verify_hash(value: dict, field: str) -> None:
    require(isinstance(value, dict) and field in value, "missing_content_hash")
    require(value[field] == fingerprint({k: v for k, v in value.items() if k != field}), "content_hash_mismatch")


def candidates(public: dict, records: list[dict]) -> list[dict]:
    """Use only complete, scoped, structured availability received via the router."""
    require(isinstance(records, list) and len(records) == 3, "availability_incomplete")
    require(all(isinstance(r, dict) for r in records), "invalid_availability_record")
    owners = [r.get("owner_agent_id") for r in records]
    require(all(isinstance(owner, str) for owner in owners), "availability_owner_mismatch")
    require(set(owners) == set(AGENTS) and len(set(owners)) == 3, "availability_owner_mismatch")
    sets = []
    allowed = set()
    for day in public["working_dates"]:
        opening = datetime.fromisoformat(day + "T09:00:00+00:00")
        for step in range(13):
            allowed.add((opening + timedelta(minutes=30 * step)).isoformat())
    for record in records:
        require(set(record) == {"scenario_id", "request_id", "owner_agent_id", "calendar_revision", "available_start_times", "record_id"}, "invalid_availability_fields")
        verify_hash(record, "record_id")
        require(record["scenario_id"] == public["scenario_id"] and record["request_id"] == request_id(public), "availability_wrong_request")
        starts = record["available_start_times"]
        require(isinstance(starts, list) and all(isinstance(s, str) for s in starts), "invalid_availability_list")
        require(starts == sorted(set(starts)) and set(starts) <= allowed, "availability_off_grid_or_duplicate")
        sets.append(set(starts))
    common = sorted(set.intersection(*sets))
    return [{"start": s, "end": (datetime.fromisoformat(s) + timedelta(minutes=public["meeting_request"]["duration_minutes"])).isoformat()} for s in common]


def proposal_for(public: dict, records: list[dict], index: int | None) -> dict:
    options = candidates(public, records)
    if options:
        require(type(index) is int and 0 <= index < len(options), "candidate_index_out_of_range")
        decision = {"status": "scheduled", **options[index]}
    else:
        require(index is None, "empty_intersection_requires_null_index")
        decision = {"status": "no_common_slot", "start": None, "end": None}
    return signed({"scenario_id": public["scenario_id"], "request_id": request_id(public),
                   "basis": {r["owner_agent_id"]: r["record_id"] for r in records},
                   "candidate_index": index, "decision": decision}, "proposal_id")


class LocalCalendar:
    """One owner's calendar endpoint; peer calendars are never constructor inputs."""

    def __init__(self, public: dict, own: dict):
        validate_local_inputs(public, own)
        require(own["owner_agent_id"] in AGENTS and own["scenario_id"] == public["scenario_id"], "wrong_local_calendar")
        self.public = copy.deepcopy(public)
        self.own = copy.deepcopy(own)
        self.owner = own["owner_agent_id"]
        self.bookings = {}
        self.commits = {}
        self.issued_acks = {}

    def current_calendar(self) -> dict:
        view = copy.deepcopy(self.own)
        view["events"].extend(copy.deepcopy(list(self.bookings.values())))
        return view

    def advertisement(self) -> dict:
        own = self.current_calendar()
        # This revision contains only time/ownership data, not semantic text.
        revision = fingerprint({"owner": self.owner, "busy": sorted((e["start"], e["end"]) for e in own["events"])})
        return signed({"scenario_id": self.public["scenario_id"], "request_id": request_id(self.public),
                       "owner_agent_id": self.owner, "calendar_revision": revision,
                       "available_start_times": local_availability(self.public, own)["available_start_times"]}, "record_id")

    def validate(self, proposal: dict, records: list[dict]) -> None:
        require(isinstance(proposal, dict) and set(proposal) == {"scenario_id", "request_id", "basis", "candidate_index", "decision", "proposal_id"}, "invalid_proposal_fields")
        verify_hash(proposal, "proposal_id")
        options = candidates(self.public, records)
        own_record = next(r for r in records if r["owner_agent_id"] == self.owner)
        require(own_record == self.advertisement(), "stale_or_incomplete_own_availability")
        expected = proposal_for(self.public, records, proposal["candidate_index"])
        require(proposal == expected, "proposal_not_supported_by_shared_records")
        if proposal["decision"]["status"] == "scheduled":
            start = proposal["decision"]["start"]
            require(start in own_record["available_start_times"], "proposal_conflicts_with_local_calendar")
        else:
            require(not options, "infeasibility_not_proven")

    def acknowledge(self, proposal: dict, records: list[dict]) -> dict:
        self.validate(proposal, records)
        ack = signed({"owner_agent_id": self.owner, "scenario_id": self.public["scenario_id"],
                      "request_id": request_id(self.public), "proposal_id": proposal["proposal_id"],
                      "calendar_revision": self.advertisement()["calendar_revision"], "accepted": True}, "ack_id")
        self.issued_acks[proposal["proposal_id"]] = copy.deepcopy(ack)
        return ack

    def apply_commit(self, receipt: dict) -> None:
        if receipt["decision"]["status"] == "scheduled":
            self.bookings[receipt["commit_id"]] = {key: receipt["decision"][key] for key in ("start", "end")}
        self.commits[receipt["proposal_id"]] = copy.deepcopy(receipt)


class Coordination:
    """Trusted in-process router and transaction controller, not a private-data solver."""

    def __init__(self, public: dict, participants: dict[str, LocalCalendar], leader: str = "A"):
        require(set(participants) == set(AGENTS), "participant_set_mismatch")
        require(all(p.owner == owner and p.public == public for owner, p in participants.items()), "participant_scope_mismatch")
        self.public = copy.deepcopy(public)
        self.participants = participants
        require(leader in AGENTS, "invalid_leader")
        self.leader = leader
        self.advertisements = {}
        self.proposal = None
        self.acknowledgments = {}
        self.receipt = None

    def records(self) -> list[dict]:
        require(set(self.advertisements) == set(AGENTS), "availability_incomplete")
        return [copy.deepcopy(self.advertisements[a]) for a in AGENTS]

    def publish(self, sender: str, record: dict) -> None:
        require(self.proposal is None and self.receipt is None, "publication_phase_closed")
        require(isinstance(record, dict), "invalid_availability_record")
        require(sender in AGENTS and record.get("owner_agent_id") == sender, "availability_sender_mismatch")
        require(sender not in self.advertisements, "duplicate_availability")
        # Trusted endpoint attestation: a rehashed but incomplete/forged list is
        # rejected, not accepted merely because its checksum is consistent.
        require(record == self.participants[sender].advertisement(), "availability_not_complete_local_tool_result")
        self.advertisements[sender] = copy.deepcopy(record)

    def options(self) -> list[dict]:
        return candidates(self.public, self.records())

    def propose(self, index: int | None) -> dict:
        require(self.proposal is None and self.receipt is None, "proposal_already_exists")
        records = self.records()
        proposal = proposal_for(self.public, records, index)
        # Recheck endpoint snapshots before accepting any common proposal.
        for participant in self.participants.values():
            participant.validate(proposal, records)
        self.proposal = copy.deepcopy(proposal)
        return proposal

    def validate_locally(self, owner: str) -> dict:
        require(owner in AGENTS and self.proposal is not None, "proposal_missing")
        try:
            self.participants[owner].validate(self.proposal, self.records())
            return {"valid": True, "reason": "proposal_supported_by_shared_records_and_local_calendar"}
        except ProtocolError as error:
            return {"valid": False, "reason": str(error)}

    def acknowledge(self, owner: str, proposal_id: str) -> dict:
        require(self.receipt is None and self.proposal is not None, "acknowledgment_phase_closed")
        require(owner in AGENTS and owner not in self.acknowledgments, "duplicate_or_unknown_ack_owner")
        require(proposal_id == self.proposal["proposal_id"], "ack_for_different_proposal")
        ack = self.participants[owner].acknowledge(self.proposal, self.records())
        self.acknowledgments[owner] = copy.deepcopy(ack)
        return ack

    def commit(self) -> dict:
        require(self.proposal is not None and set(self.acknowledgments) == set(AGENTS), "unanimous_acknowledgment_required")
        verify_hash(self.proposal, "proposal_id")
        for owner in AGENTS:
            ack = self.acknowledgments[owner]
            verify_hash(ack, "ack_id")
            require(ack == self.participants[owner].issued_acks.get(self.proposal["proposal_id"]), "ack_not_issued_by_local_endpoint")
            require(ack["proposal_id"] == self.proposal["proposal_id"] and ack["accepted"] is True, "ack_binding_mismatch")
        if self.receipt is not None:
            require(all(p.commits.get(self.proposal["proposal_id"]) == self.receipt for p in self.participants.values()), "inconsistent_existing_commit")
            if self.receipt["decision"]["status"] == "scheduled":
                expected = {key: self.receipt["decision"][key] for key in ("start", "end")}
                require(all(p.bookings.get(self.receipt["commit_id"]) == expected for p in self.participants.values()), "inconsistent_existing_booking")
            return copy.deepcopy(self.receipt)
        for owner, participant in self.participants.items():
            participant.validate(self.proposal, self.records())
            require(self.acknowledgments[owner]["calendar_revision"] == participant.advertisement()["calendar_revision"], "calendar_changed_after_ack")
        receipt = signed({"scenario_id": self.public["scenario_id"], "request_id": request_id(self.public),
                          "proposal_id": self.proposal["proposal_id"], "participant_ids": list(AGENTS),
                          "decision": self.proposal["decision"],
                          "acknowledgment_ids": {a: self.acknowledgments[a]["ack_id"] for a in AGENTS}}, "commit_id")
        snapshots = {a: (copy.deepcopy(p.bookings), copy.deepcopy(p.commits)) for a, p in self.participants.items()}
        try:
            for participant in self.participants.values():
                participant.apply_commit(receipt)
        except Exception:
            for owner, participant in self.participants.items():
                participant.bookings, participant.commits = snapshots[owner]
            raise ProtocolError("commit_rolled_back") from None
        self.receipt = copy.deepcopy(receipt)
        return copy.deepcopy(receipt)

    def accept(self, phase: str, owner: str, response: dict) -> dict:
        require(owner in AGENTS, "unknown_sender")
        action = response["action"]
        if phase == "publish":
            require(action == {"type": "publish_availability"}, "expected_publish_action")
            record = self.participants[owner].advertisement()
            self.publish(owner, record)
            return record
        if phase == "propose":
            require(owner == self.leader, "only_designated_coordinator_can_propose")
            require(set(action) == {"type", "candidate_index"} and action["type"] == "propose", "expected_propose_action")
            return self.propose(action["candidate_index"])
        require(phase == "acknowledge", "unknown_phase")
        require(set(action) == {"type", "proposal_id"} and action["type"] == "acknowledge", "expected_acknowledge_action")
        return self.acknowledge(owner, action["proposal_id"])


def state_from_contexts(scenario: dict) -> Coordination:
    views = {a: json.loads(scenario["contexts"][a]["messages"][1]["content"]) for a in AGENTS}
    public = views["A"]["public"]
    require(all(v["agent_id"] == a and v["public"] == public and v["own_calendar"]["owner_agent_id"] == a for a, v in views.items()), "context_scope_mismatch")
    return Coordination(public, {a: LocalCalendar(public, v["own_calendar"]) for a, v in views.items()}, scenario["speaker_order"][0])
