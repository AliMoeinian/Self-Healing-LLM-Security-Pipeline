"""Optional garak integration tests; no provider access or paid calls."""

import contextlib
import copy
import csv
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from calendar_pipeline import garak_scan as gs
from garak.attempt import Conversation, Message, Turn
from calendar_pipeline.client import ScriptedClient
from calendar_pipeline.core import ROOT, read_json, save_json
from calendar_pipeline.privacy import facts_for
from tools.export_garak_evidence import export as export_evidence


class PrivateDetailReference(ScriptedClient):
    """Test double only; explicitly not evidence of real LLM behaviour."""

    def complete(self, payload, key_name, call_id):
        response = super().complete(payload, key_name, call_id)
        view = json.loads(payload["messages"][1]["content"])
        control = json.loads(payload["messages"][-1]["content"])
        incoming = " ".join(m["content"] for m in control["incoming_messages"])
        body = json.loads(response["content"])
        if "SYSTEM POLICY UPDATE" in incoming:
            body["message"] = "My private event title is " + view["own_calendar"]["events"][0]["title"] + "."
        elif "We cannot certify a fair scheduling" in incoming:
            # Paraphrase of C-E001; exact title/person/place/description absent.
            if view["agent_id"] == "C":
                body["message"] = "I have a private discussion about switching roles inside my workplace."
        response["content"] = json.dumps(body)
        return response


class GarakScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.config = read_json(ROOT / "configs/garak_smoke.json")
        cls.scan_dir = cls.root / "scripted"
        with contextlib.redirect_stdout(io.StringIO()), patch.object(gs, "ScriptedClient", PrivateDetailReference):
            cls.summary = gs.scan(cls.scan_dir, config=cls.config, backend="scripted-reference")
        cls.items = read_json(cls.scan_dir / "observations.json")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def csv_file(self, name, changes=None):
        source = self.scan_dir / "human_review/messages.csv"
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        if changes:
            changes(rows)
        path = self.root / name
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_scan_runs_whole_application_and_keeps_utility_separate(self):
        self.assertEqual(self.summary["team_sessions"], 10)
        self.assertEqual(self.summary["new_logical_model_requests"], 70)
        self.assertEqual(self.summary["scheduling_successes"], 10)
        self.assertEqual(self.summary["candidate_flagged_sessions"], 2)
        self.assertIsNone(self.summary["human_confirmed_leak_rate"])
        self.assertEqual(gs.audit_scan(self.scan_dir)["completed_native_attempts"], 10)

    def test_native_outputs_contain_only_exact_peer_publications(self):
        records = [json.loads(l) for l in (self.scan_dir / "scan.report.jsonl").read_text().splitlines()]
        attempts = [r for r in records if r["entry_type"] == "attempt" and r["status"] == 2]
        self.assertEqual(len(attempts), 10)
        for attempt in attempts:
            output = json.loads(attempt["outputs"][0]["text"])
            self.assertEqual(set(output), {"case_id", "messages"})
            case = read_json(self.scan_dir / "application/cases" / (output["case_id"] + ".json"))
            self.assertEqual(output, gs.observable_output(case))
            self.assertNotIn(case["observer_agent_id"], {m["speaker"] for m in output["messages"]})

    def test_replay_has_no_network_and_retains_exact_cases(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")), contextlib.redirect_stdout(io.StringIO()):
            result = gs.scan(self.root / "replayed", source=self.scan_dir / "application")
        self.assertEqual(result["new_logical_model_requests"], 0)
        self.assertEqual(result["observations_sha256"], self.summary["observations_sha256"])
        self.assertEqual(result["candidate_flagged_sessions"], 2)

    def test_unknown_prompt_and_duplicate_generation_are_blocked(self):
        scenario = {"scenario_id": "CAL-0052"}
        condition = gs.CONDITIONS[0]
        case = read_json(self.scan_dir / "application/cases" / (gs.case_id(scenario, self.config["models"][0], condition) + ".json"))
        called = []
        def obtain(*args):
            called.append(args)
            return case
        with contextlib.redirect_stdout(io.StringIO()):
            generator = gs.CalendarApplication(scenario, self.config["models"][0], obtain)
        def conv(text):
            return Conversation([Turn("user", Message(text=text))])
        with self.assertRaises(ValueError):
            generator.generate(conv("unplanned extra probe"))
        self.assertEqual(called, [])
        generator.generate(conv(condition["content"]))
        with self.assertRaises(ValueError):
            generator.generate(conv(condition["content"]))
        self.assertEqual(len(called), 1)

    def test_blank_human_labels_stay_pending_and_do_not_override_garak(self):
        source = self.scan_dir / "human_review/messages.csv"
        result = gs.review_scan(self.scan_dir, source, "test-only reviewer", self.root / "blank-review")
        self.assertEqual(result["reviewed_observations"], 0)
        self.assertEqual(result["human_review_status"], "partial_or_uncertain")
        self.assertIsNone(result["precision"])
        self.assertIsNone(result["recall"])
        self.assertEqual(read_json(self.scan_dir / "summary.json"), self.summary)

    def test_human_paraphrase_can_add_a_false_negative_without_api_rerun(self):
        target = next(o for o in self.items if o["condition_id"] == "task_pretext" and o["speaker_agent_id"] == "C" and "switching roles" in o["content"])
        self.assertEqual(target["lexical_candidates"], [])
        fact = next(e for e in facts_for("CAL-0052")["C"] if e["event_id"] == "C-E001")
        def changes(rows):
            row = next(r for r in rows if r["message_id"] == target["message_id"])
            row.update(human_label="leak", human_evidence_quote=target["content"], human_source_owner="C", human_event_id="C-E001",
                       human_field="title", human_source_value=fact["title"], human_relation="paraphrase",
                       human_rationale="Test-only annotation: private internal role discussion is paraphrased.")
        csv_path = self.csv_file("paraphrase.csv", changes)
        with patch.object(gs, "MistralClient", side_effect=AssertionError("No paid call during review")):
            result = gs.review_scan(self.scan_dir, csv_path, "test-only reviewer", self.root / "paraphrase-review")
        self.assertEqual(result["false_negative"], 1)
        self.assertEqual(result["recall"], 0)
        self.assertEqual(result["reviewed_observations"], 1)
        self.assertEqual(read_json(self.scan_dir / "summary.json"), self.summary)

    def test_human_false_positive_does_not_mutate_automatic_report(self):
        target = next(o for o in self.items if o["lexical_candidates"] and o["post_intervention_response"])
        def changes(rows):
            row = next(r for r in rows if r["message_id"] == target["message_id"])
            row.update(human_label="no_leak", human_rationale="Test-only disputed candidate to test independent review plumbing.")
        result = gs.review_scan(self.scan_dir, self.csv_file("disputed.csv", changes), "test-only reviewer", self.root / "disputed-review")
        self.assertEqual(result["false_positive"], 1)
        self.assertEqual(result["precision"], 0)

    def test_invalid_human_source_evidence_is_rejected(self):
        target = next(o for o in self.items if o["lexical_candidates"])
        def changes(rows):
            row = next(r for r in rows if r["message_id"] == target["message_id"])
            row.update(human_label="leak", human_evidence_quote=target["content"], human_source_owner=target["speaker_agent_id"],
                       human_event_id="nonexistent", human_field="title", human_source_value="fake", human_relation="exact_mention",
                       human_rationale="Test-only invalid evidence.")
        with self.assertRaises(ValueError):
            gs.human_review_from_csv(self.items, self.csv_file("bad-evidence.csv", changes), "test-only reviewer")

    def test_human_csv_cannot_change_text_or_duplicate_ids(self):
        for name, edit in [("changed", lambda rows: rows[0].update(content="changed")),
                           ("duplicate", lambda rows: rows[0].update(message_id=rows[1]["message_id"]))]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                gs.human_review_from_csv(self.items, self.csv_file(name + ".csv", edit), "test-only reviewer")

    def test_native_report_score_tampering_is_rejected(self):
        path = self.scan_dir / "scan.report.jsonl"
        original = path.read_text()
        try:
            rows = [json.loads(l) for l in original.splitlines()]
            row = next(r for r in rows if r["entry_type"] == "attempt" and r["status"] == 2)
            row["detector_results"]["SchedulingFailure"] = [1.0]
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            with self.assertRaises(ValueError):
                gs.audit_scan(self.scan_dir)
        finally:
            path.write_text(original)

    def test_unexposed_case_is_unscored_not_secure(self):
        _, cases = gs.audited_cases(self.scan_dir)
        case = copy.deepcopy(cases[0])
        case["session"]["protocol_status"] = "unresolved"
        attempt = type("Attempt", (), {})()
        attempt.notes = {"application_case_id": case["case_id"]}
        attempt.outputs = [Message(text=json.dumps(gs.observable_output(case)))]
        self.assertEqual(list(gs.PrivateValueCandidate({case["case_id"]: case}).detect(attempt)), [None])

    def test_scan_and_review_refuse_to_overwrite_existing_outputs(self):
        with self.assertRaises(ValueError):
            gs.scan(self.scan_dir, config=self.config, backend="scripted-reference")
        with self.assertRaises(ValueError):
            gs.review_scan(self.scan_dir, self.scan_dir / "human_review/messages.csv", "test-only reviewer", self.scan_dir)

    def test_evidence_export_refuses_current_credential_values(self):
        path = self.scan_dir / "test-only-secret.txt"
        fixture_secret = "test-fixture-credential-never-a-real-key"
        try:
            path.write_text(fixture_secret)
            with patch.dict(os.environ, {"MISTRAL_API_KEY": fixture_secret}), self.assertRaises(ValueError):
                export_evidence(self.scan_dir, self.root / "refused-export")
            self.assertFalse((self.root / "refused-export").exists())
        finally:
            path.unlink()

    def test_export_manifest_covers_all_original_files(self):
        target = self.root / "successful-export"
        result = export_evidence(self.scan_dir, target)
        self.assertEqual(result["status"], "passed")
        manifest = read_json(target / "export_manifest.json")
        source_files = {str(p.relative_to(self.scan_dir)) for p in self.scan_dir.rglob("*") if p.is_file()}
        self.assertEqual(set(manifest["files_sha256"]), source_files)


if __name__ == "__main__":
    unittest.main()
