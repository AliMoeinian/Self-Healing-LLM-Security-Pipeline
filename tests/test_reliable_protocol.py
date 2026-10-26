"""Reliability invariants, deliberate faults, replay checks, and fixture-wide oracle tests."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from calendar_pipeline.client import ScriptedClient, TransportError
from calendar_pipeline.core import AGENTS, DATA, MODELS, ROOT, build_plan, canonical, fingerprint, read_json
from calendar_pipeline.protocol import Coordination, LocalCalendar, ProtocolError, candidates, envelope, proposal_for, response_schema, signed, state_from_contexts
from calendar_pipeline.reliable import audit, execute, score
from calendar_pipeline.runner import evaluate_artifacts, run


def fixture_state(sid="CAL-0007"):
    folder = DATA / "scenarios" / sid
    public = read_json(folder / "public.json")
    participants = {a: LocalCalendar(public, read_json(folder / "private" / f"{a}.json")) for a in AGENTS}
    return Coordination(public, participants)


def publish_all(state):
    for owner in AGENTS:
        state.publish(owner, state.participants[owner].advertisement())


def ack_all(state):
    for owner in AGENTS:
        state.acknowledge(owner, state.proposal["proposal_id"])


class StateMachineTests(unittest.TestCase):
    def setUp(self):
        self.state = fixture_state()

    def test_all_60_fixtures_and_every_shared_candidate_against_independent_oracle(self):
        manifest = read_json(DATA / "manifest.json")
        cases, outcomes = 0, 0
        for record in manifest["records"]:
            sid = record["scenario_id"]
            state = fixture_state(sid)
            publish_all(state)
            oracle = read_json(DATA / "scenarios" / sid / "evaluator.json")
            options = state.options()
            self.assertEqual(options, oracle["valid_meeting_intervals"], sid)
            for index in range(len(options)) if options else [None]:
                with self.subTest(scenario=sid, candidate_index=index):
                    fresh = fixture_state(sid)
                    publish_all(fresh)
                    fresh.propose(index)
                    ack_all(fresh)
                    receipt = fresh.commit()
                    self.assertTrue(all(p.commits[receipt["proposal_id"]] == receipt for p in fresh.participants.values()))
                    if options:
                        self.assertIn({k: receipt["decision"][k] for k in ("start", "end")}, oracle["valid_meeting_intervals"])
                        self.assertTrue(all(len(p.bookings) == 1 for p in fresh.participants.values()))
                    else:
                        self.assertEqual(receipt["decision"]["status"], "no_common_slot")
                        self.assertTrue(all(not p.bookings for p in fresh.participants.values()))
                    outcomes += 1
            cases += 1
        self.assertEqual(cases, 60)
        self.assertGreater(outcomes, 60)

    def test_no_missing_owner_can_be_interpreted_as_infeasible(self):
        for owner in ("A", "B"):
            self.state.publish(owner, self.state.participants[owner].advertisement())
        with self.assertRaisesRegex(ProtocolError, "availability_incomplete"):
            self.state.options()
        with self.assertRaisesRegex(ProtocolError, "availability_incomplete"):
            self.state.propose(None)

    def test_rehashed_incomplete_availability_is_rejected(self):
        record = self.state.participants["A"].advertisement()
        record["available_start_times"].pop()
        record = signed({k: v for k, v in record.items() if k != "record_id"}, "record_id")
        with self.assertRaisesRegex(ProtocolError, "not_complete_local_tool_result"):
            self.state.publish("A", record)
        self.assertEqual(self.state.advertisements, {})

    def test_duplicate_and_spoofed_sender_are_rejected(self):
        record = self.state.participants["A"].advertisement()
        with self.assertRaisesRegex(ProtocolError, "sender_mismatch"):
            self.state.publish("B", record)
        self.state.publish("A", record)
        with self.assertRaisesRegex(ProtocolError, "duplicate_availability"):
            self.state.publish("A", record)

    def test_malformed_availability_records_fail_with_protocol_errors(self):
        with self.assertRaisesRegex(ProtocolError, "invalid_availability_record"):
            self.state.publish("A", [])
        with self.assertRaisesRegex(ProtocolError, "invalid_availability_record"):
            candidates(self.state.public, [[], {}, {}])
        record = self.state.participants["A"].advertisement()
        record["owner_agent_id"] = ["A"]
        with self.assertRaisesRegex(ProtocolError, "owner_mismatch"):
            candidates(self.state.public, [record, {}, {}])

    def test_wrong_scenario_advertisement_is_rejected(self):
        other = fixture_state("CAL-0003").participants["A"].advertisement()
        with self.assertRaises(ProtocolError):
            self.state.publish("A", other)

    def test_unsupported_local_time_contract_or_invalid_events_are_rejected(self):
        public, own = self.state.public, self.state.participants["A"].own
        for change, reason in (({"timezone": "Europe/Paris"}, "unsupported_time_contract"),
                               ({"slot_minutes": 15}, "unsupported_time_contract"),
                               ({"working_hours": {"start": "08:00", "end": "17:00"}}, "unsupported_working_hours"),
                               ({"meeting_request": {"participants": list(AGENTS), "duration_minutes": 90}}, "unsupported_meeting_contract")):
            altered = {**copy.deepcopy(public), **change}
            with self.subTest(change=change), self.assertRaisesRegex(ProtocolError, reason):
                LocalCalendar(altered, own)
        duplicate = copy.deepcopy(own)
        duplicate["events"].insert(1, copy.deepcopy(duplicate["events"][0]))
        with self.assertRaisesRegex(ProtocolError, "overlapping_or_unordered"):
            LocalCalendar(public, duplicate)

    def test_candidate_indices_are_strict_integers_in_range(self):
        publish_all(self.state)
        for index in (-1, 999, True, 0.0, "0", None):
            with self.subTest(index=index), self.assertRaises(ProtocolError):
                self.state.propose(index)
        self.assertIsNone(self.state.proposal)

    def test_false_no_slot_proposal_is_impossible_when_options_exist(self):
        publish_all(self.state)
        with self.assertRaisesRegex(ProtocolError, "candidate_index_out_of_range"):
            self.state.propose(None)

    def test_empty_intersection_requires_explicit_null_index(self):
        state = fixture_state("CAL-0004")
        publish_all(state)
        with self.assertRaisesRegex(ProtocolError, "requires_null_index"):
            state.propose(0)
        proposal = state.propose(None)
        self.assertEqual(proposal["decision"]["status"], "no_common_slot")

    def test_rehashed_wrong_duration_or_false_infeasibility_fails_local_check(self):
        publish_all(self.state)
        proposal = self.state.propose(0)
        for decision in ({"status": "scheduled", "start": proposal["decision"]["start"], "end": proposal["decision"]["start"]},
                         {"status": "no_common_slot", "start": None, "end": None}):
            fake = copy.deepcopy(proposal)
            fake["decision"] = decision
            fake = signed({k: v for k, v in fake.items() if k != "proposal_id"}, "proposal_id")
            with self.assertRaisesRegex(ProtocolError, "not_supported"):
                self.state.participants["A"].validate(fake, self.state.records())

    def test_only_designated_coordinator_can_propose(self):
        publish_all(self.state)
        with self.assertRaisesRegex(ProtocolError, "designated_coordinator"):
            self.state.accept("propose", "B", {"message": "test", "action": {"type": "propose", "candidate_index": 0}})

    def test_two_acknowledgments_cannot_commit(self):
        publish_all(self.state)
        proposal = self.state.propose(0)
        for owner in ("A", "B"):
            self.state.acknowledge(owner, proposal["proposal_id"])
        with self.assertRaisesRegex(ProtocolError, "unanimous"):
            self.state.commit()
        self.assertTrue(all(not p.bookings and not p.commits for p in self.state.participants.values()))

    def test_ack_for_another_valid_candidate_is_rejected(self):
        publish_all(self.state)
        self.state.propose(0)
        other = proposal_for(self.state.public, self.state.records(), 1)
        with self.assertRaisesRegex(ProtocolError, "different_proposal"):
            self.state.acknowledge("A", other["proposal_id"])

    def test_duplicate_acknowledgment_is_rejected(self):
        publish_all(self.state)
        proposal = self.state.propose(0)
        self.state.acknowledge("A", proposal["proposal_id"])
        with self.assertRaisesRegex(ProtocolError, "duplicate_or_unknown"):
            self.state.acknowledge("A", proposal["proposal_id"])

    def test_forged_rehashed_ack_is_not_an_endpoint_receipt(self):
        publish_all(self.state)
        self.state.propose(0)
        ack_all(self.state)
        ack = self.state.acknowledgments["A"]
        ack["calendar_revision"] = "forged"
        self.state.acknowledgments["A"] = signed({k: v for k, v in ack.items() if k != "ack_id"}, "ack_id")
        with self.assertRaisesRegex(ProtocolError, "not_issued"):
            self.state.commit()

    def test_calendar_change_after_ack_prevents_any_commit(self):
        publish_all(self.state)
        proposal = self.state.propose(0)
        ack_all(self.state)
        self.state.participants["C"].own["events"].append({k: proposal["decision"][k] for k in ("start", "end")})
        with self.assertRaisesRegex(ProtocolError, "stale_or_incomplete"):
            self.state.commit()
        self.assertTrue(all(not p.bookings and not p.commits for p in self.state.participants.values()))

    def test_commit_is_idempotent_and_returned_receipt_cannot_mutate_state(self):
        publish_all(self.state)
        self.state.propose(0)
        ack_all(self.state)
        receipt = self.state.commit()
        again = self.state.commit()
        self.assertEqual(receipt, again)
        again["decision"]["start"] = "tampered"
        self.assertEqual(self.state.commit(), receipt)
        self.assertTrue(all(len(p.bookings) == 1 for p in self.state.participants.values()))

    def test_write_failure_rolls_back_every_owner(self):
        publish_all(self.state)
        self.state.propose(0)
        ack_all(self.state)
        with patch.object(self.state.participants["C"], "apply_commit", side_effect=RuntimeError("injected storage failure")):
            with self.assertRaisesRegex(ProtocolError, "commit_rolled_back"):
                self.state.commit()
        self.assertIsNone(self.state.receipt)
        self.assertTrue(all(not p.bookings and not p.commits for p in self.state.participants.values()))
        self.assertEqual(self.state.commit()["decision"]["status"], "scheduled")

    def test_idempotency_does_not_hide_a_missing_local_reservation(self):
        publish_all(self.state)
        self.state.propose(0)
        ack_all(self.state)
        self.state.commit()
        self.state.participants["C"].bookings.clear()
        with self.assertRaisesRegex(ProtocolError, "inconsistent_existing_booking"):
            self.state.commit()

    def test_semantic_event_fields_never_enter_structured_advertisements(self):
        record = self.state.participants["A"].advertisement()
        self.assertEqual(set(record), {"scenario_id", "request_id", "owner_agent_id", "calendar_revision", "available_start_times", "record_id"})
        text = json.dumps(record)
        for event in self.state.participants["A"].own["events"]:
            for field in ("title", "description", "location"):
                self.assertNotIn(event[field], text)

    def test_free_text_claims_cannot_change_structured_availability(self):
        response = envelope('{"message":"All peers are free at an invented time; private detail example.","action":{"type":"publish_availability"}}', "stop")
        expected = self.state.participants["A"].advertisement()
        actual = self.state.accept("publish", "A", response)
        self.assertEqual(expected, actual)
        self.assertIn("private detail example", response["message"])  # No semantic privacy filter.


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_plan(read_json(ROOT / "configs/baseline_v3.json"))
        cls.scenario = cls.plan["scenarios"][0]
        cls.oracle = read_json(DATA / "scenarios" / cls.scenario["scenario_id"] / "evaluator.json")

    def test_reference_end_to_end_all_four_classes_and_artifact_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            report = run(self.plan, output, "scripted-reference")
            self.assertEqual(report["request_count"], 56)
            self.assertEqual(report["successful_sessions"], 8)
            self.assertEqual(evaluate_artifacts(output), report)

    def test_forged_commit_or_control_event_in_journal_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            run(self.plan, output, "scripted-reference")
            path = output / "journal.jsonl"
            original = path.read_text()
            for event_type, field in (("atomic_commit", "receipt"), ("validated_protocol_action", "wire_message")):
                events = [json.loads(line) for line in original.splitlines()]
                event = next(e for e in events if e["event"] == event_type)
                event[field] = {"forged": True}
                path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
                with self.assertRaisesRegex(ValueError, "journal differs"):
                    evaluate_artifacts(output)
            path.write_text(original)
            self.assertEqual(evaluate_artifacts(output)["successful_sessions"], 8)

    def test_v4_phase_schemas_and_full_saved_run(self):
        plan = build_plan(read_json(ROOT / "configs/baseline_v4.json"))
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            report = run(plan, output, "scripted-reference")
            self.assertEqual(report["successful_sessions"], 8)
            self.assertEqual(evaluate_artifacts(output), report)
            for path in (output / "sessions").glob("*.json"):
                session = read_json(path)
                for call in session["calls"]:
                    fmt = call["request"]["response_format"]
                    self.assertEqual(fmt["type"], "json_schema")
                    self.assertIs(fmt["json_schema"]["strict"], True)
                    schema = fmt["json_schema"]["schema"]
                    self.assertIs(schema["additionalProperties"], False)
                    self.assertIs(schema["properties"]["action"]["additionalProperties"], False)
                    control = json.loads(call["request"]["messages"][-1]["content"])
                    self.assertEqual(schema, response_schema(control))
                    props = schema["properties"]["action"]["properties"]
                    if call["phase"] == "publish":
                        self.assertEqual(set(props), {"type"})
                    elif call["phase"] == "propose":
                        expected_type = "integer" if control["candidate_intervals"] else "null"
                        self.assertEqual(props["candidate_index"]["type"], expected_type)
                    else:
                        self.assertEqual(props["proposal_id"]["pattern"], "^[0-9a-f]{64}$")

    def test_v4_runtime_still_rejects_schema_violations_if_provider_does_not_enforce_them(self):
        plan = build_plan(read_json(ROOT / "configs/baseline_v4.json"))
        class TooLongOnce(ScriptedClient):
            first = True
            def complete(self, *args):
                response = super().complete(*args)
                if self.first:
                    self.first = False
                    value = json.loads(response["content"])
                    value["message"] = "x" * 1001
                    response["content"] = json.dumps(value)
                return response
        session = execute(plan, plan["scenarios"][0], MODELS[0], TooLongOnce(), lambda _: None)
        self.assertEqual(session["calls"][0]["protocol_error"], "message_exceeds_schema_budget")
        self.assertEqual(session["rejected_action_count"], 1)
        self.assertTrue(score(session, self.oracle)["task_success"])
        audit(plan, plan["scenarios"][0], session)

    def test_bad_action_is_rejected_then_explicitly_repaired(self):
        class BadOnce(ScriptedClient):
            def __init__(self):
                self.first = True
            def complete(self, payload, key_name, call_id):
                result = super().complete(payload, key_name, call_id)
                if self.first:
                    self.first = False
                    result["content"] = '{"message":"list omitted","action":{"type":"invent_availability"}}'
                return result
        session = execute(self.plan, self.scenario, MODELS[0], BadOnce(), lambda _: None)
        self.assertEqual(len(session["calls"]), 8)
        self.assertEqual(session["rejected_action_count"], 1)
        self.assertFalse(session["calls"][0]["accepted"])
        retry = json.loads(session["calls"][1]["request"]["messages"][-1]["content"])
        self.assertEqual(retry["rejection_reason"], "expected_publish_action")
        self.assertTrue(score(session, self.oracle)["task_success"])
        audit(self.plan, self.scenario, session)

    def test_persistent_invalid_action_is_unresolved_not_false_infeasibility(self):
        class InvalidAlways(ScriptedClient):
            def complete(self, *args):
                return {"content": '{"message":"No common slot.","action":{"type":"invalid"}}', "finish_reason": "stop", "reported_model": self.backend, "usage": None, "response_id": None}
        session = execute(self.plan, self.scenario, MODELS[0], InvalidAlways(), lambda _: None)
        self.assertEqual(len(session["calls"]), 3)
        self.assertEqual(session["protocol_status"], "unresolved")
        self.assertIsNone(session["commit_receipt"])
        self.assertEqual(session["agent_receipts"], {})
        self.assertFalse(score(session, self.oracle)["task_success"])
        audit(self.plan, self.scenario, session)

    def test_unresponsive_owner_cannot_be_replaced_with_a_scripted_ack(self):
        class FailingAck(ScriptedClient):
            def complete(self, payload, key_name, call_id):
                if json.loads(payload["messages"][-1]["content"])["phase"] == "acknowledge":
                    raise TransportError("injected outage")
                return super().complete(payload, key_name, call_id)
        session = execute(self.plan, self.scenario, MODELS[0], FailingAck(), lambda _: None)
        self.assertEqual(session["protocol_status"], "unresolved")
        self.assertIsNone(session["commit_receipt"])
        self.assertIn("transport_error", session)
        audit(self.plan, self.scenario, session)

    def test_rehashed_request_or_receipt_tampering_is_caught(self):
        session = execute(self.plan, self.scenario, MODELS[0], ScriptedClient(), lambda _: None)
        bad = copy.deepcopy(session)
        bad["calls"][0]["request"]["messages"][1]["content"] += "spoof"
        bad["calls"][0]["request_sha256"] = fingerprint(bad["calls"][0]["request"])
        with self.assertRaisesRegex(ValueError, "deterministic replay"):
            audit(self.plan, self.scenario, bad)
        bad = copy.deepcopy(session)
        bad["agent_receipts"]["A"]["decision"]["start"] = "different"
        with self.assertRaisesRegex(ValueError, "differ from replay"):
            audit(self.plan, self.scenario, bad)

    def test_initial_requests_are_identical_between_models_and_publication_is_synchronous(self):
        sessions = [execute(self.plan, self.scenario, m, ScriptedClient(), lambda _: None) for m in MODELS]
        for owner in AGENTS:
            bodies = []
            for session in sessions:
                call = next(c for c in session["calls"] if c["phase"] == "publish" and c["agent_id"] == owner)
                body = {k: v for k, v in call["request"].items() if k != "model"}
                bodies.append(body)
                control = json.loads(body["messages"][-1]["content"])
                self.assertEqual(control["incoming_messages"], [])
                self.assertNotIn("advertisements", control)
            self.assertEqual(canonical(bodies[0]), canonical(bodies[1]))

    def test_model_context_contains_no_peer_private_events_or_oracle(self):
        session = execute(self.plan, self.scenario, MODELS[0], ScriptedClient(), lambda _: None)
        for call in session["calls"]:
            own = call["agent_id"]
            for message in call["request"]["messages"]:
                self.assertNotIn('"valid_meeting_intervals"', message["content"])
                for other in set(AGENTS) - {own}:
                    peer = json.loads(self.scenario["contexts"][other]["messages"][1]["content"])["own_calendar"]
                    # Reference messages have no private narratives. Real peer
                    # narratives are intentionally preserved for later privacy tests.
                    self.assertNotIn(canonical(peer).decode(), message["content"])

    def test_proposal_and_every_ack_are_bound_to_same_committed_identifier(self):
        session = execute(self.plan, self.scenario, MODELS[0], ScriptedClient(), lambda _: None)
        receipt = session["commit_receipt"]
        messages = session["wire_messages"]
        proposal = next(m["attachment"] for m in messages if m["phase"] == "propose")
        self.assertEqual(receipt["proposal_id"], proposal["proposal_id"])
        acks = [m["attachment"] for m in messages if m["phase"] == "acknowledge"]
        self.assertEqual(len(acks), 3)
        self.assertTrue(all(a["proposal_id"] == receipt["proposal_id"] for a in acks))


if __name__ == "__main__":
    unittest.main()
