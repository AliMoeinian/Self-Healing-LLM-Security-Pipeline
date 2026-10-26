"""Command-line entry points; all commands except Mistral calls work offline."""

import argparse
import json
from pathlib import Path

from .client import check_connections
from .core import ROOT, build_plan, read_json, save_json, validate_config, verify_plan
from .runner import evaluate_artifacts, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--config", type=Path, default=ROOT / "configs/baseline.json")
    prepare.add_argument("--output", type=Path, required=True)
    connect = commands.add_parser("check-connection")
    connect.add_argument("--config", type=Path, default=ROOT / "configs/baseline.json")
    connect.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("run")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    execute.add_argument("--backend", choices=("scripted-reference", "mistral"), required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            plan = build_plan(read_json(args.config))
            if args.output.exists() and read_json(args.output) != plan:
                raise ValueError("Existing plan differs; choose another output path")
            save_json(args.output, plan)
            print(json.dumps({"plan_sha256": plan["plan_sha256"], "scenarios": len(plan["scenarios"]), "models": plan["config"]["models"], "expected_logical_calls": 9 * len(plan["scenarios"]) * len(plan["config"]["models"])}))
            return 0
        if args.command == "check-connection":
            config = read_json(args.config)
            validate_config(config)
            if args.output.exists():
                raise ValueError("Connectivity output exists; preserve it and use a fresh path")
            report = {"checks": check_connections(config), "secret_values_recorded": False}
            report["success"] = all(r["success"] for r in report["checks"])
            save_json(args.output, report)
            print(json.dumps(report, indent=2))
            return 0 if report["success"] else 2
        if args.command == "evaluate":
            report = evaluate_artifacts(args.run)
        else:
            plan = read_json(args.plan)
            verify_plan(plan)
            if args.backend == "mistral":
                checks = check_connections(plan["config"])
                if not all(c["success"] for c in checks):
                    print(json.dumps({"status": "blocked", "preflight": checks}, indent=2))
                    return 2
            report = run(plan, args.output, args.backend)
        print(json.dumps(report, indent=2))
        if report["run_status"] != "completed":
            return 2
        return 0 if report["successful_sessions"] == report["expected_sessions"] else 3
    except (ValueError, KeyError, TypeError, OSError) as error:
        # Configuration/data errors cannot contain credential values. Transport
        # failures are sanitized at the client boundary before they are logged.
        parser.exit(2, f"Pipeline check failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
