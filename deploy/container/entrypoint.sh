#!/bin/sh
set -eu
umask 077
mkdir -p "$HOME/.config/mindfs" "$CODEX_HOME" "$HOME/.local/state"
if [ "${1:-}" = mindfs ]; then
  # The project bind may contain public MindFS data. Refuse a missing mask,
  # rather than starting against that database or modifying its permissions.
  container_project_path="${MINDFS_CONTAINER_PROJECT_PATH:-/workspace}"
  if [ ! "$container_project_path/.mindfs" -ef "$HOME/.workspace-metadata" ]; then
    echo 'Refusing unmasked project metadata; use the provided Compose mounts.' >&2
    exit 1
  fi
  if [ -n "${RCC_NODE_ID:-}" ]; then
    python3 - <<'PY'
import json, os
from pathlib import Path
path = Path.home() / '.config/mindfs/container-rcc.json'
path.write_text(json.dumps({'agents': [{'name': 'rcc', 'command': 'rcc', 'protocol': 'rcc', 'args': ['--node', os.environ['RCC_NODE_ID']]}]}) + '\n')
path.chmod(0o600)
PY
    shift
    set -- mindfs --agent-config "$HOME/.config/mindfs/container-rcc.json" "$@"
  fi
fi
exec "$@"
