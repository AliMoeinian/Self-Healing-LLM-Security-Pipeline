"""End-to-end self-healing and human-review tests using explicit test doubles."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from calendar_pipeline import self_healing as sh
from calendar_pipeline.client import ScriptedClient
from calendar_pipeline.core import ROOT, read_json, save_json


class ResponsiveReference(ScriptedClient):
    def complete(self, payload, key_name, call_id):
        result = super().complete(payload, key_name, call_id)
        control = json.loads(payload["messages"][-1]["content"])
        if any("SYSTEM POLICY UPDATE" in m["content"] for m in control["incoming_messages"]):
            own = json.loads(payload["messages"][1]["content"])["own_calendar"]
            body = json.loads(result["content"])
            body["message"] = "My private event is " + own["events"][0]["title"] + " at " + own["events"][0]["location"]
            result["content"] = json.dumps(body)
        return result


class SelfHealingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.study_dir = cls.root / "run"
        cls.plan = sh.build_plan(read_json(ROOT / "configs/garak_smoke.json"))
        with contextlib.redirect_stdout(io.StringIO()):
            cls.summary = sh.execute_study(cls.plan, cls.study_dir, "scripted-reference", client_factory=lambda config, journal: ResponsiveReference())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_garak_loop_triggers_patch_and_checks_fresh_defended_cases(self):
        decision = read_json(self.study_dir / "patch_decision.json")
        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["selected_policy"]["id"], "both")
        self.assertEqual(self.summary["recorded_sessions"], 40)
        self.assertEqual(self.summary["logical_requests"], 280)
        self.assertEqual(self.summary["scheduling_successes"], 40)
        groups = {g["variant"]: g for g in self.summary["groups"]}
        self.assertEqual(groups["none"]["candidate_injection_sessions"], 2)
        for variant in ("input_only", "output_only", "both"):
            self.assertEqual(groups[variant]["candidate_injection_sessions"], 0)
            self.assertEqual(groups[variant]["evaluable_injection_sessions"], 6)
        self.assertEqual(groups["output_only"]["raw_model_candidate_injection_sessions"], 2)
        self.assertIsNone(self.summary["human_confirmed_disclosure_rate"])
        stages = [json.loads(l)["stage"] for l in (self.study_dir / "loop.jsonl").read_text().splitlines()]
        self.assertEqual(stages, ["probe_started", "configured_patch_selected", "verification_completed"])

    def test_native_scores_transforms_and_pairing_recompute(self):
        result = sh.audit_study(self.study_dir)
        self.assertEqual(result["native_completed_attempts"], 40)
        paired = read_json(self.study_dir / "pairing_audit.json")
        self.assertEqual(paired["starting_requests_checked"], 120)

    def test_missing_discovery_does_not_activate_a_patch(self):
        self.assertFalse(sh.choose_patch({"candidate_flagged_sessions": 0})["triggered"])
        self.assertIsNone(sh.choose_patch({"candidate_flagged_sessions": 0})["selected_policy"])
        with self.assertRaises(ValueError):
            sh.choose_patch({"candidate_flagged_sessions": -1})

    def test_policy_order_balances_temporal_position_across_full_pair_blocks(self):
        plan = sh.build_plan(read_json(ROOT / "configs/privacy_pilot.json"))
        blocks = sh.specs(plan)[::5]
        counts = {v["id"]: [0, 0, 0, 0] for v in sh.VARIANTS}
        for block in range(8):
            for position, spec in enumerate(blocks[block * 4:(block + 1) * 4]):
                counts[spec[-1]["id"]][position] += 1
        self.assertTrue(all(c == [2, 2, 2, 2] for c in counts.values()))

    def test_blank_human_review_is_not_a_zero_disclosure_verdict(self):
        result = sh.review_study(self.study_dir, self.study_dir / "human_review/messages.csv", "test-only reviewer", self.root / "human-empty")
        self.assertEqual(result["reviewed_observations"], 0)
        self.assertEqual(result["status"], "partial_or_uncertain")
        report = read_json(self.root / "human-empty/human_privacy_report.json")
        self.assertEqual(set(report["by_defense"]), {"none", "input_only", "output_only", "both"})
        for variant in report["by_defense"].values():
            self.assertTrue(all(g["observed_leak_rate"] is None for g in variant["groups"]))

    def test_changed_defense_journal_is_rejected(self):
        path = self.study_dir / "journal.jsonl"
        original = path.read_text()
        try:
            rows = [json.loads(l) for l in original.splitlines()]
            next(r for r in rows if r["event"] == "defense_transform")["stage"] = "changed"
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            with self.assertRaises(ValueError):
                sh.audit_study(self.study_dir)
        finally:
            path.write_text(original)

    def test_export_refuses_overwrite_and_retains_source_fingerprints(self):
        target = self.root / "export"
        result = sh.export_study(self.study_dir, target)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(read_json(target / "export_manifest.json")["files_sha256"])
        with self.assertRaises(ValueError):
            sh.export_study(self.study_dir, target)


if __name__ == "__main__":
    unittest.main()
