#!/usr/bin/env bash
# Focused programmatic garak runtime, not the full built-in-plugin distribution.
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
garak_env_dir="${1:-${repo_dir}/.venv-garak}"
if [[ -e "${garak_env_dir}" ]]; then
  printf '%s\n' 'Refusing to overwrite an existing environment; supply a new path.' >&2
  exit 1
fi
python3 -m venv "${garak_env_dir}"
"${garak_env_dir}/bin/python" -m pip install --no-deps -r "${repo_dir}/requirements/garak-core.lock"
printf 'Run from the repository root using: %s/bin/python -m calendar_pipeline.garak_scan --help\n' "${garak_env_dir}"
