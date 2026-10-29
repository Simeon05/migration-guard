#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
temporary_root=$(mktemp -d "${TMPDIR:-/tmp}/migrationguard-clean-install.XXXXXX")
trap 'rm -rf "$temporary_root"' EXIT

python_command=${PYTHON:-python3}
"$python_command" -m venv "$temporary_root/venv"
venv_python="$temporary_root/venv/bin/python"

env -u PYTHONPATH "$venv_python" -m pip install "$project_root"
env -u PYTHONPATH "$temporary_root/venv/bin/migration-guard" check \
    "$project_root/examples/safe.sql"
