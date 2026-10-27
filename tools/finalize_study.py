"""One entry point for the final paid study, audited export and final artifacts.

--dry-run is entirely local: it never checks the endpoint or spends credit.
"""

import argparse
import importlib.metadata
from pathlib import Path
import os
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from calendar_pipeline.core import ROOT,read_json,canonical
from calendar_pipeline.self_healing import verify_plan,specs,execute_study,export_study


def readiness(plan_path):
    plan=read_json(plan_path);verify_plan(plan)
    config=plan["experiment"]["base_plan"]["config"]
    modules={name:importlib.metadata.version(name) for name in ("garak","matplotlib","python-pptx","reportlab")}
    presence={name:bool(os.environ.get(name)) for name in set(config["key_by_agent"].values())}
    if not all(presence.values()):raise ValueError("Missing required credential variable; no values are displayed")
    return {"local_readiness":"passed","connectivity":"not tested by dry-run",
            "planned_fresh_sessions":len(specs(plan)),"nominal_logical_requests":len(specs(plan))*7,
            "max_http_attempts":plan["max_total_http_attempts"],"max_reserved_units":plan["max_total_reserved_units"],
            "credential_presence":presence,"packages":modules,"human_review_status":"pending"}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan",type=Path,default=ROOT/"experiments/self_healing_plan_v1.json")
    p.add_argument("--run",type=Path,default=ROOT/"runs/self-healing-final-v1")
    p.add_argument("--evidence-output",type=Path,default=ROOT/"experiments/self_healing/run_v1")
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args()
    state=readiness(args.plan)
    print(canonical(state).decode(),flush=True)
    if args.dry_run:return
    if args.run.exists() or args.evidence_output.exists():
        raise ValueError("Run/evidence destination exists; use fresh paths to preserve prior evidence")
    result=execute_study(read_json(args.plan),args.run,"mistral")
    if result["run_status"]!="completed":
        raise RuntimeError("Live study incomplete; preserve its evidence, do not build a complete-result report")
    export_study(args.run,args.evidence_output)
    subprocess.run([sys.executable,str(ROOT/"tools/build_research_artifacts.py"),"--run",str(args.evidence_output)],check=True,cwd=ROOT)


if __name__=="__main__":main()
