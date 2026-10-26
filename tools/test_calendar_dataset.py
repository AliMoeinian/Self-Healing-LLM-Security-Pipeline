"""Meaningful acceptance and fault-injection tests for the synthetic fixture."""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import generate_calendar_dataset as generator
import validate_calendar_dataset as validator

DATA = Path(__file__).resolve().parents[1] / "data" / "calendar" / "v1"


class DatasetTests(unittest.TestCase):
    def test_entire_dataset_against_independent_oracle(self):
        report, rows = validator.validate_dataset(DATA)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(len(rows), 60)
        self.assertEqual(report["candidate_intervals_checked"], 3900)
        self.assertEqual(validator.read(DATA / "validation_report.json"), report)
        self.assertEqual((DATA / "summary.csv").read_text(), validator.summary_csv(rows))

    def test_regeneration_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "regenerated"
            with contextlib.redirect_stdout(io.StringIO()):
                generator.generate(root)
            originals = {p.relative_to(DATA).as_posix() for p in (DATA / "scenarios").rglob("*.json")}
            recreated = {p.relative_to(root).as_posix() for p in (root / "scenarios").rglob("*.json")}
            self.assertEqual(originals, recreated)
            for relative in sorted(originals | {"manifest.json"}):
                self.assertEqual((root / relative).read_bytes(), (DATA / relative).read_bytes(), relative)
            report, _ = validator.validate_dataset(root)
            self.assertEqual(report["scenario_count"], 60)

    def test_generator_refuses_nonempty_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sentinel = root / "user-file.txt"
            sentinel.write_text("preserve me")
            with self.assertRaises(ValueError):
                generator.generate(root)
            self.assertEqual(sentinel.read_text(), "preserve me")

    def test_half_open_interval_boundaries(self):
        def at(hour, minute=0):
            return datetime(2026, 11, 2, hour, minute, tzinfo=timezone.utc)
        events = [(at(10), at(11))]
        self.assertTrue(validator.free(events, at(9), at(10)))
        self.assertTrue(validator.free(events, at(11), at(13)))
        self.assertFalse(validator.free(events, at(10, 30), at(12, 30)))
        self.assertFalse(validator.free(events, at(9), at(12)))

    def test_duplicate_occupancy_is_rejected_despite_new_scenario_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "dataset"
            shutil.copytree(DATA, root)
            records = validator.read(root / "manifest.json")["records"]
            selected = [r for r in records if r["bucket"] == "hard" and r["split"] == "development"]
            source, target = selected[:2]
            source_dir = root / "scenarios" / source["scenario_id"]
            target_dir = root / "scenarios" / target["scenario_id"]
            target_oracle = validator.read(target_dir / "evaluator.json")
            for path in source_dir.rglob("*.json"):
                value = validator.read(path)
                value["scenario_id"] = target["scenario_id"]
                if path.name == "evaluator.json":
                    for key in ("generation_seed", "suggested_attacker_agent_id", "speaker_order"):
                        value[key] = target_oracle[key]
                (target_dir / path.relative_to(source_dir)).write_text(json.dumps(value))
            with self.assertRaisesRegex(validator.ValidationError, "Duplicate calendar occupancy"):
                validator.validate_dataset(root, verify_hashes=False)

    def test_candidate_windows_do_not_cross_workday(self):
        days = [date(2026, 11, d) for d in range(2, 7)]
        candidates = validator.candidate_intervals(days)
        self.assertEqual(len(candidates), 65)
        self.assertTrue(all(s.date() == e.date() and s.hour >= 9 and e.hour <= 17 for s, e in candidates))
        self.assertEqual(candidates[0][0].isoformat(), "2026-11-02T09:00:00+00:00")
        self.assertEqual(candidates[-1][1].isoformat(), "2026-11-06T17:00:00+00:00")


class CorruptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        manifest = validator.read(DATA / "manifest.json")
        sid = next(r["scenario_id"] for r in manifest["records"] if r["bucket"] == "hard")
        self.folder = Path(self.temp.name) / sid
        shutil.copytree(DATA / "scenarios" / sid, self.folder)
        validator.validate_scenario(self.folder)

    def mutate(self, relative, change):
        path = self.folder / relative
        value = validator.read(path)
        change(value)
        path.write_text(json.dumps(value))

    def rejected(self, pattern):
        # These checks deliberately bypass manifest hashes: semantic checks must
        # catch corruption even if somebody recomputes the hashes after editing.
        with self.assertRaisesRegex(validator.ValidationError, pattern):
            validator.validate_scenario(self.folder)

    def test_private_data_cannot_be_added_to_public_record(self):
        self.mutate("public.json", lambda v: v.update(events=[{"title": "private detail"}]))
        self.rejected("public: unexpected")

    def test_extra_payload_in_public_policy_is_rejected(self):
        self.mutate("public.json", lambda v: v["privacy_policy"]["allowed"].append("private detail"))
        self.rejected("Public policy changed")

    def test_wrong_private_owner_is_rejected(self):
        self.mutate("private/A.json", lambda v: v.update(owner_agent_id="B"))
        self.rejected("Wrong private owner")

    def test_cross_owner_entity_overlap_is_rejected(self):
        other = validator.read(self.folder / "private/A.json")["events"][0]["location"]
        def change(v):
            event = v["events"][0]
            event["description"] = event["description"].replace(event["location"], other)
            event["location"] = other
        self.mutate("private/B.json", change)
        self.rejected("Entities shared between owners")

    def test_overlapping_events_are_rejected(self):
        def change(v):
            v["events"][1]["start"] = v["events"][0]["start"]
            v["events"][1]["end"] = v["events"][0]["end"]
        self.mutate("private/A.json", change)
        self.rejected("Events overlap")

    def test_off_grid_times_are_rejected(self):
        def change(v):
            start = v["events"][0]["start"]
            v["events"][0]["start"] = start[:14] + "15" + start[16:]
        self.mutate("private/A.json", change)
        self.rejected("half-hour grid")

    def test_zero_duration_event_is_rejected(self):
        self.mutate("private/A.json", lambda v: v["events"][0].update(end=v["events"][0]["start"]))
        self.rejected("nonpositive duration")

    def test_out_of_hours_event_is_rejected(self):
        def change(v):
            start = v["events"][0]["start"]
            v["events"][0]["start"] = start[:11] + "08:00" + start[16:]
        self.mutate("private/A.json", change)
        self.rejected("outside working hours")

    def test_fabricated_oracle_is_rejected(self):
        self.mutate("evaluator.json", lambda v: v.update(valid_meeting_intervals=[]))
        self.rejected("Oracle intervals disagree")

    def test_incorrect_bucket_is_rejected(self):
        self.mutate("evaluator.json", lambda v: v.update(bucket="easy"))
        self.rejected("difficulty bucket")

    def test_incorrect_feasibility_is_rejected(self):
        self.mutate("evaluator.json", lambda v: v.update(feasible=False))
        self.rejected("Wrong feasibility")

    def test_changed_protected_facts_are_rejected(self):
        self.mutate("evaluator.json", lambda v: v["protected_facts_by_owner"]["A"][0].update(title="wrong fact"))
        self.rejected("facts do not match")

    def test_incorrect_structural_metrics_are_rejected(self):
        self.mutate("evaluator.json", lambda v: v["structural_metrics"].update(valid_start_count=999))
        self.rejected("Structural metrics disagree")

    def test_duplicate_json_keys_are_rejected(self):
        path = self.folder / "public.json"
        path.write_text('{"scenario_id": "one", "scenario_id": "two"}')
        self.rejected("duplicate JSON key")

    def test_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / "dataset"
            shutil.copytree(DATA, copy)
            path = copy / "scenarios" / self.folder.name / "public.json"
            path.write_text(path.read_text() + " ")
            with self.assertRaisesRegex(validator.ValidationError, "hash mismatch"):
                validator.validate_dataset(copy)


if __name__ == "__main__":
    unittest.main()
