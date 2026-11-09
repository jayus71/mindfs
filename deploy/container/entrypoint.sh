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
  # Run inside the container: inherit its runtime environment, then apply the
  # imported Codex overrides. The SDK treats a nonempty env as a full replacement.
  python3 - <<'PY'
import json, os, sys, tempfile
from pathlib import Path
config = Path.home() / '.config/mindfs'
path = config / 'container-rcc.json'
stage = None
try:
    agents = []
    confirm_project = os.environ.get('RCC_CONFIRM_PROJECT', 'false').strip().lower()
    if confirm_project not in ('true', 'false'):
        sys.exit('RCC_CONFIRM_PROJECT must be true or false.')
    if os.environ.get('RCC_NODE_ID'):
        rcc_args = ['--node', os.environ['RCC_NODE_ID']]
        if confirm_project == 'true':
            rcc_args.append('--confirm-project')
        agents.append({'name': 'rcc', 'command': 'rcc', 'protocol': 'rcc',
                       'args': rcc_args})
    source = config / 'agents.json'
    if source.exists():
        for agent in json.loads(source.read_text()).get('agents', []):
            if agent.get('name') != 'codex' or not agent.get('env'):
                continue
            overrides = agent['env']
            if not isinstance(overrides, dict) or any(not isinstance(v, str) for v in overrides.values()):
                raise ValueError()
            env = dict(os.environ)
            env.update(overrides)
            for key in ('HOME', 'CODEX_HOME', 'PATH', 'XDG_CONFIG_HOME', 'XDG_STATE_HOME'):
                if key in os.environ:
                    env[key] = os.environ[key]
            agents.append(dict(agent, env=env))
    if agents:
        with tempfile.NamedTemporaryFile(mode='w', dir=config, prefix='.container-agents-', delete=False) as handle:
            stage = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            json.dump({'agents': agents}, handle)
            handle.write('\n')
        os.replace(stage, path)
    else:
        path.unlink(missing_ok=True)
except (OSError, ValueError, TypeError, AttributeError):
    sys.exit('Unable to prepare private container agent environment.')
finally:
    if stage is not None:
        stage.unlink(missing_ok=True)
PY
  if [ -f "$HOME/.config/mindfs/container-rcc.json" ]; then
    shift
    set -- mindfs --agent-config "$HOME/.config/mindfs/container-rcc.json" "$@"
  fi
fi
exec "$@"
