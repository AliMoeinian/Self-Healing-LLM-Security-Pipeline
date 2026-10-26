import copy
import io
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from calendar_pipeline.client import MistralClient, NoRedirect, ScriptedClient, TransportError, check_connections
from calendar_pipeline.core import AGENTS, DATA, MODELS, ROOT, build_plan, canonical, fingerprint, local_availability, model_payload, parse_reply, read_json, save_json, score_session, verify_plan
from calendar_pipeline.runner import audit_session, evaluate_artifacts, evaluate_run, execute_session, run


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_plan(read_json(ROOT / "configs/baseline.json"))
        cls.scenario = cls.plan["scenarios"][0]
        cls.session = execute_session(cls.plan, cls.scenario, MODELS[0], ScriptedClient(), lambda _: None)
        cls.oracle = read_json(DATA / "scenarios" / cls.scenario["scenario_id"] / "evaluator.json")

    def test_plan_rebuild_is_identical(self):
        self.assertEqual(self.plan, build_plan(self.plan["config"]))
        verify_plan(self.plan)

    def test_only_own_calendar_in_initial_model_context(self):
        for scenario in self.plan["scenarios"]:
            for owner in AGENTS:
                view = json.loads(scenario["contexts"][owner]["messages"][1]["content"])
                self.assertEqual(set(view), {"agent_id", "public", "own_calendar"})
                self.assertEqual(view["own_calendar"]["owner_agent_id"], owner)
                self.assertNotIn("bucket", view["public"])
                self.assertNotIn("valid_meeting_intervals", view)
                self.assertNotIn("generation_seed", view)
                self.assertEqual(view["own_calendar"], read_json(DATA / "scenarios" / scenario["scenario_id"] / "private" / f"{owner}.json"))

    def test_inputs_and_generation_parameters_match_between_models(self):
        for scenario in self.plan["scenarios"]:
            for context in scenario["contexts"].values():
                requests = [model_payload(m, context["messages"], self.plan["config"]) for m in MODELS]
                self.assertNotEqual(requests[0].pop("model"), requests[1].pop("model"))
                self.assertEqual(canonical(requests[0]), canonical(requests[1]))

    def test_v2_local_tool_is_scoped_and_its_answers_match_independent_checks(self):
        config = read_json(ROOT / "configs/baseline_v2.json")
        plan = build_plan(config)
        from tools.validate_calendar_dataset import candidate_intervals, free
        from datetime import date
        for scenario in plan["scenarios"]:
            for owner in AGENTS:
                context = scenario["contexts"][owner]
                view = json.loads(context["messages"][1]["content"])
                self.assertEqual(set(view), {"agent_id", "public", "own_calendar", "own_availability"})
                own = view["own_calendar"]
                busy = [(datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])) for e in own["events"]]
                candidates = candidate_intervals([date.fromisoformat(d) for d in view["public"]["working_dates"]])
                expected = [s.isoformat() for s, e in candidates if free(busy, s, e)]
                self.assertEqual(view["own_availability"]["available_start_times"], expected)
                tool_intervals = [(datetime.fromisoformat(i["start"]), datetime.fromisoformat(i["end"])) for i in view["own_availability"]["free_intervals"]]
                from datetime import timedelta
                for day in view["public"]["working_dates"]:
                    start = datetime.fromisoformat(day + "T09:00:00+00:00")
                    for cell in range(16):
                        cell_start = start + timedelta(minutes=30 * cell)
                        cell_end = cell_start + timedelta(minutes=30)
                        covered = any(s <= cell_start and cell_end <= e for s, e in tool_intervals)
                        self.assertEqual(covered, free(busy, cell_start, cell_end))
                bodies = [model_payload(m, context["messages"], config) for m in MODELS]
                for b in bodies:
                    b.pop("model")
                self.assertEqual(bodies[0], bodies[1])
        verify_plan(plan)

    def test_local_tool_covers_eventless_days_and_touching_boundaries(self):
        public = read_json(DATA / "scenarios/CAL-0007/public.json")
        own = {"events": [{"start": "2026-11-02T11:00:00+00:00", "end": "2026-11-02T12:00:00+00:00"}]}
        result = local_availability(public, own)
        self.assertIn("2026-11-02T09:00:00+00:00", result["available_start_times"])
        self.assertIn("2026-11-02T12:00:00+00:00", result["available_start_times"])
        self.assertNotIn("2026-11-02T10:00:00+00:00", result["available_start_times"])
        self.assertEqual(sum(s.startswith("2026-11-03") for s in result["available_start_times"]), 13)

    def test_v2_end_to_end_reference_and_artifact_audit(self):
        plan = build_plan(read_json(ROOT / "configs/baseline_v2.json"))
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            report = run(plan, output, "scripted-reference")
            self.assertEqual(report["successful_sessions"], 8)
            self.assertEqual(evaluate_artifacts(output), report)

    def test_evidence_export_checks_model_pairing_and_refuses_embedded_credentials(self):
        from tools.export_baseline_evidence import export
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "run"
            run(self.plan, source, "scripted-reference")
            artifact = Path(temp) / "exported"
            audit = export(source, artifact)
            self.assertEqual(audit["paired_first_round_requests_checked"], 12)
            self.assertTrue(all(p["matches"] for p in audit["pairs"]))
            self.assertEqual(evaluate_artifacts(artifact)["successful_sessions"], 8)
            with self.assertRaisesRegex(ValueError, "output exists"):
                export(source, artifact)
            (source / "accidental-secret.txt").write_text("unique-export-test-secret")
            with patch.dict(os.environ, {"MISTRAL_API_KEY": "unique-export-test-secret"}):
                refused = Path(temp) / "must-not-exist"
                with self.assertRaisesRegex(ValueError, "Credential scan failed"):
                    export(source, refused)
                self.assertFalse(refused.exists())

    def test_rehashed_contaminated_plan_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        view = json.loads(plan["scenarios"][0]["contexts"]["A"]["messages"][1]["content"])
        view["reference_answers"] = self.oracle["valid_meeting_intervals"]
        context = plan["scenarios"][0]["contexts"]["A"]
        context["messages"][1]["content"] = json.dumps(view)
        context["sha256"] = fingerprint(context["messages"])
        plan["plan_sha256"] = fingerprint({k: v for k, v in plan.items() if k != "plan_sha256"})
        with self.assertRaisesRegex(ValueError, "canonical source"):
            verify_plan(plan)

    def test_held_out_scenarios_are_not_available_to_pilot(self):
        config = copy.deepcopy(self.plan["config"])
        config["scenario_ids"] = ["CAL-0001"]
        with self.assertRaisesRegex(ValueError, "only development"):
            build_plan(config)

    def test_synchronous_rounds_have_no_current_round_leakage(self):
        calls = self.session["calls"]
        for call in calls[:3]:
            self.assertEqual(json.loads(call["request"]["messages"][-1]["content"])["incoming_messages"], [])
        for call in calls[3:6]:
            incoming = json.loads(call["request"]["messages"][-1]["content"])["incoming_messages"]
            self.assertEqual({v["from"] for v in incoming}, set(AGENTS) - {call["agent_id"]})
            self.assertEqual(len(incoming), 2)

    def test_request_snapshots_do_not_mutate_with_later_rounds(self):
        self.assertTrue(all(len(c["request"]["messages"]) == 3 for c in self.session["calls"][:3]))
        self.assertTrue(all(len(c["request"]["messages"]) == 7 for c in self.session["calls"][6:]))

    def test_tampered_request_is_rejected_even_after_rehash(self):
        session = copy.deepcopy(self.session)
        call = session["calls"][0]
        call["request"]["messages"][1]["content"] += " private contamination"
        call["request_sha256"] = fingerprint(call["request"])
        call["messages_sha256"] = fingerprint(call["request"]["messages"])
        with self.assertRaisesRegex(ValueError, "deterministic replay"):
            audit_session(self.plan, self.scenario, session)

    def change_final(self, session, decision, agent=None):
        for call in session["calls"]:
            if call["phase"] == "final" and (agent is None or call["agent_id"] == agent):
                value = json.loads(call["response"]["content"])
                value["decision"] = decision
                call["response"]["content"] = json.dumps(value)

    def test_false_infeasibility_fails(self):
        session = copy.deepcopy(self.session)
        self.change_final(session, {"status": "no_common_slot", "start": None, "end": None})
        self.assertFalse(score_session(session, self.oracle)["task_success"])

    def test_two_of_three_agreement_is_not_success(self):
        session = copy.deepcopy(self.session)
        self.change_final(session, {"status": "no_common_slot", "start": None, "end": None}, agent="A")
        self.assertEqual(score_session(session, self.oracle)["reason"], "agents_disagree")

    def test_wrong_duration_fails_even_if_all_agree(self):
        session = copy.deepcopy(self.session)
        answer = self.oracle["valid_meeting_intervals"][0]
        self.change_final(session, {"status": "scheduled", "start": answer["start"], "end": answer["start"]})
        self.assertFalse(score_session(session, self.oracle)["task_success"])

    def test_truncated_but_valid_json_is_not_a_success(self):
        session = copy.deepcopy(self.session)
        session["calls"][-1]["response"]["finish_reason"] = "length"
        self.assertEqual(score_session(session, self.oracle)["reason"], "invalid_model_reply")

    def test_incomplete_run_does_not_pass(self):
        session = copy.deepcopy(self.session)
        session["calls"].pop()
        result = score_session(session, self.oracle)
        self.assertFalse(result["complete"])
        self.assertFalse(result["task_success"])

    def test_duplicate_or_wrong_phase_call_is_not_success(self):
        session = copy.deepcopy(self.session)
        session["calls"][1] = copy.deepcopy(session["calls"][0])
        self.assertFalse(score_session(session, self.oracle)["complete"])

    def test_unknown_keys_and_naive_timestamps_are_rejected(self):
        for value in [
            '{"message":"ok","decision":null,"thinking":"private"}',
            '{"message":"ok","message":"duplicate","decision":null}',
        ]:
            with self.assertRaises(ValueError):
                parse_reply(value, "discussion", "stop")
        with self.assertRaises(ValueError):
            parse_reply(json.dumps({"message": "ok", "decision": {"status": "scheduled", "start": "2026-11-02T09:00:00", "end": "2026-11-02T11:00:00"}}), "final", "stop")

    def test_free_text_is_not_sanitized_by_baseline_parser(self):
        raw = '{"message":"The private event title is example text.","decision":null}'
        self.assertIn("private event title", parse_reply(raw, "discussion", "stop")["message"])

    def test_bare_final_decision_is_not_silently_repaired(self):
        with self.assertRaisesRegex(ValueError, "reply envelope"):
            parse_reply('{"status":"no_common_slot","start":null,"end":null}', "final", "stop")

    def test_all_four_classes_end_to_end_and_saved_re_evaluation(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            report = run(self.plan, output, "scripted-reference")
            self.assertEqual(report["request_count"], 72)
            self.assertEqual(report["successful_sessions"], 8)
            self.assertEqual({o["bucket"] for o in report["outcomes"]}, {"easy", "medium", "hard", "infeasible"})
            self.assertIsNone(report["observed_usage"])
            self.assertEqual(evaluate_artifacts(output), report)
            tampered = read_json(output / "summary.json")
            tampered["successful_sessions"] = 999
            save_json(output / "summary.json", tampered)
            with self.assertRaisesRegex(ValueError, "Saved scores differ"):
                evaluate_artifacts(output)

    def test_existing_run_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "must not exist"):
                run(self.plan, Path(temp), "scripted-reference")

    def test_transport_failure_is_partial_and_stops_the_run(self):
        class FailingClient:
            backend = "mistral"
            def complete(self, *args):
                raise TransportError("connection failed")
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            report = run(self.plan, output, "mistral", client_factory=lambda _: FailingClient())
            self.assertEqual(report["run_status"], "partial")
            self.assertEqual(report["successful_sessions"], 0)
            self.assertEqual(report["unrun_sessions"], 7)
            self.assertIsNone(report["observed_usage"])
            self.assertEqual(evaluate_artifacts(output), report)


class FakeResponse(io.BytesIO):
    status = 200


class FakeOpener:
    def __init__(self, values):
        self.values = iter(values)
        self.requests = []
    def open(self, request, timeout):
        self.requests.append(request)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return FakeResponse(json.dumps(value).encode())


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.config = read_json(ROOT / "configs/baseline.json")
        self.payload = model_payload(MODELS[0], [{"role": "user", "content": "test"}], self.config)
        self.reply = {"id": "fixture", "model": MODELS[0], "choices": [{"message": {"content": '{"message":"ok","decision":null}'}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        self.patch = patch.dict(os.environ, {"MISTRAL_API_KEY": "fixture-secret-one", "MISTRAL_API_KEY2": "fixture-secret-two", "MISTRAL_API_KEY3": "fixture-secret-three"})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.events = []

    def client(self, values):
        opener = FakeOpener(values)
        client = MistralClient(self.config, self.events.append, opener=opener, sleeper=lambda _: None, clock_fn=lambda: 0)
        return client, opener

    def test_post_body_matches_frozen_request_without_credentials(self):
        client, opener = self.client([self.reply])
        result = client.complete(self.payload, "MISTRAL_API_KEY", "id")
        self.assertEqual(json.loads(opener.requests[0].data), self.payload)
        self.assertEqual(result["usage"]["total_tokens"], 15)
        artifact_text = json.dumps(self.events) + json.dumps(result) + opener.requests[0].data.decode()
        self.assertNotIn("fixture-secret", artifact_text)
        self.assertEqual(opener.requests[0].get_header("Authorization"), "Bearer fixture-secret-one")

    def test_rate_limit_retries_same_key_only(self):
        error = urllib.error.HTTPError("https://api.mistral.ai", 429, "rate limit", {"Retry-After": "1"}, None)
        client, opener = self.client([error, self.reply])
        client.complete(self.payload, "MISTRAL_API_KEY", "id")
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual({r.get_header("Authorization") for r in opener.requests}, {"Bearer fixture-secret-one"})

    def test_auth_failure_does_not_retry_or_change_key(self):
        error = urllib.error.HTTPError("https://api.mistral.ai", 401, "sensitive error body", {}, None)
        client, opener = self.client([error, self.reply])
        with self.assertRaisesRegex(TransportError, "status 401"):
            client.complete(self.payload, "MISTRAL_API_KEY", "id")
        self.assertEqual(len(opener.requests), 1)
        self.assertNotIn("sensitive error body", json.dumps(self.events))

    def test_ambiguous_timeout_is_not_automatically_retried(self):
        client, opener = self.client([TimeoutError("sensitive details"), self.reply])
        with self.assertRaisesRegex(TransportError, "no credential failover"):
            client.complete(self.payload, "MISTRAL_API_KEY", "id")
        self.assertEqual(len(opener.requests), 1)

    def test_missing_usage_fails_instead_of_becoming_zero_cost(self):
        value = copy.deepcopy(self.reply)
        value.pop("usage")
        client, _ = self.client([value])
        with self.assertRaisesRegex(TransportError, "usage or output could not be verified"):
            client.complete(self.payload, "MISTRAL_API_KEY", "id")

    def test_budget_exhaustion_blocks_before_any_request(self):
        self.config["max_reserved_tokens"] = 1
        client, opener = self.client([self.reply])
        with self.assertRaisesRegex(TransportError, "budget exhausted"):
            client.complete(self.payload, "MISTRAL_API_KEY", "id")
        self.assertEqual(opener.requests, [])

    def test_credentials_never_forwarded_on_redirect(self):
        handler = NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "", {}, "https://different.example"))

    def test_connection_checks_are_read_only_and_validate_both_models(self):
        opener = FakeOpener([{"data": [{"id": m} for m in MODELS]}] * 3)
        report = check_connections(self.config, opener)
        self.assertTrue(all(r["success"] for r in report))
        self.assertTrue(all(r.get_method() == "GET" for r in opener.requests))
        self.assertNotIn("fixture-secret", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
