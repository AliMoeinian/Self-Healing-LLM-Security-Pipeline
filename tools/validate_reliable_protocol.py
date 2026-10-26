"""Offline exhaustive fixture/commit verification; never calls an LLM or API."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_pipeline.core import AGENTS, DATA, ROOT, read_json, save_json, sha_file
from calendar_pipeline.protocol import Coordination, LocalCalendar


def validate(data: Path = DATA) -> dict:
    from tools.validate_calendar_dataset import validate_dataset
    validate_dataset(data)
    rows = []
    option_commits = 0
    no_slot_commits = 0
    def state_for(sid):
        folder = data / "scenarios" / sid
        public = read_json(folder / "public.json")
        participants = {a: LocalCalendar(public, read_json(folder / "private" / f"{a}.json")) for a in AGENTS}
        state = Coordination(public, participants)
        for a in AGENTS:
            state.publish(a, participants[a].advertisement())
        return state
    for entry in read_json(data / "manifest.json")["records"]:
        sid = entry["scenario_id"]
        oracle = read_json(data / "scenarios" / sid / "evaluator.json")
        options = state_for(sid).options()
        if options != oracle["valid_meeting_intervals"]:
            raise ValueError("Shared-availability computation differs from independent oracle: " + sid)
        for index in range(len(options)) if options else [None]:
            state = state_for(sid)
            proposal = state.propose(index)
            for a in AGENTS:
                state.acknowledge(a, proposal["proposal_id"])
            receipt = state.commit()
            if any(p.commits.get(proposal["proposal_id"]) != receipt for p in state.participants.values()):
                raise ValueError("Owner receipts disagree: " + sid)
            decision = receipt["decision"]
            if options:
                if {k: decision[k] for k in ("start", "end")} not in oracle["valid_meeting_intervals"]:
                    raise ValueError("Invalid committed interval: " + sid)
                if any(list(p.bookings.values()) != [{k: decision[k] for k in ("start", "end")}] for p in state.participants.values()):
                    raise ValueError("Bookings disagree with receipt: " + sid)
                option_commits += 1
            else:
                if oracle["feasible"] is not False or decision["status"] != "no_common_slot" or any(p.bookings for p in state.participants.values()):
                    raise ValueError("Incorrect no-slot commit: " + sid)
                no_slot_commits += 1
            if state.commit() != receipt or any(len(p.bookings) != int(bool(options)) for p in state.participants.values()):
                raise ValueError("Idempotent commit changed state: " + sid)
        rows.append({"scenario_id": sid, "bucket": entry["bucket"], "split": entry["split"],
                     "valid_start_count": len(options), "all_options_committed_correctly": True,
                     "identical_owner_receipts": True})
    return {"status": "passed", "scope": "offline deterministic protocol verification, not model evaluation",
            "fixture_count": len(rows), "candidate_intervals_independently_checked": 65 * len(rows),
            "feasible_option_commits_checked": option_commits, "infeasible_case_commits_checked": no_slot_commits,
            "atomic_owner_receipts_checked": 3 * (option_commits + no_slot_commits),
            "dataset_manifest_sha256": sha_file(data / "manifest.json"),
            "source_sha256": {name: sha_file(ROOT / name) for name in (
                "calendar_pipeline/core.py", "calendar_pipeline/protocol.py", "tools/validate_reliable_protocol.py")},
            "cases": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional new report path; never overwrites a prior report")
    args = parser.parse_args()
    report = validate()
    if args.output:
        if args.output.exists():
            parser.exit(1, "Report output exists; use a fresh path\n")
        save_json(args.output, report)
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
