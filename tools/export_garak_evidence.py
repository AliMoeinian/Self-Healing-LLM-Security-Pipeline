"""Audit a garak scan and export it after scanning currently injected secrets."""

import argparse
import os
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_pipeline.garak_scan import audit_scan
from calendar_pipeline.core import read_json, save_json, sha_file


def export(scan, output, source=None):
    if output.exists():
        raise ValueError("Evidence destination exists; never overwrite recorded scans")
    audit = audit_scan(scan, source)
    plan = read_json(scan / "scan_plan.json")["experiment_plan"]
    names = plan["base_plan"]["config"]["key_by_agent"].values()
    secrets = [os.environ[n].encode() for n in names if os.environ.get(n)]
    files = [p for p in scan.rglob("*") if p.is_file()]
    for path in files:
        if path.is_symlink() or any(secret in path.read_bytes() for secret in secrets):
            raise ValueError("Credential or symlink scan failed; export refused")
    shutil.copytree(scan, output)
    save_json(output / "export_manifest.json", {"audit": audit,
              "credential_scan": "passed for the credential values currently injected in this process",
              "files_sha256": {str(p.relative_to(output)): sha_file(p) for p in sorted(output.rglob("*")) if p.is_file()}})
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    print(export(args.scan, args.output, args.source))
