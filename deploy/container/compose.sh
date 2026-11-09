#!/usr/bin/env bash
set -euo pipefail
container_deploy_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export MINDFS_UID="${MINDFS_UID:-$(id -u)}" MINDFS_GID="${MINDFS_GID:-$(id -g)}"
python3 - "$container_deploy_dir" <<'PY'
import os, pathlib, sys
repo = pathlib.Path(sys.argv[1]).parent.parent.resolve()
def required(name):
    value = os.environ.get(name, '')
    path = pathlib.Path(value)
    if not value or not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        sys.exit(name + ' must be an absolute path without symlinks')
    return path
private = required('MINDFS_CONTAINER_HOME')
project = required('MINDFS_PROJECT_DIR')
host_home = pathlib.Path.home().resolve()
if private == host_home or private == repo or repo in private.parents or private in repo.parents or private in project.parents or project in private.parents or private == project:
    sys.exit('Choose a private container HOME outside the checkout and project source')
if project in (host_home, pathlib.Path('/')) or not project.is_dir():
    sys.exit('Choose one project directory, not the host HOME or filesystem root')
if (project / '.mindfs').is_symlink():
    sys.exit('The host project .mindfs mount point must not be a symlink')
private.mkdir(parents=True, exist_ok=True, mode=0o700)
if private.stat().st_uid != os.getuid() or private.stat().st_mode & 0o077:
    sys.exit('Private container HOME must belong to this user with mode 0700')
metadata = private / '.workspace-metadata'
if metadata.is_symlink():
    sys.exit('Metadata mask must not be a symlink')
metadata.mkdir(mode=0o700, exist_ok=True)
if metadata.stat().st_uid != os.getuid() or metadata.stat().st_mode & 0o077:
    sys.exit('Private metadata must belong to this user with mode 0700')
if os.environ.get('RCC_RELEASE_DIR'):
    release = required('RCC_RELEASE_DIR')
    if not release.is_dir():
        sys.exit('RCC_RELEASE_DIR must be a complete release directory')
PY
container_compose_args=(-f "$container_deploy_dir/compose.yaml")
if [[ -n "${RCC_RELEASE_DIR:-}" ]]; then
  [[ -x "$RCC_RELEASE_DIR/bin/rcc" && -x "$RCC_RELEASE_DIR/bin/reach-helper" ]] || { echo 'RCC_RELEASE_DIR must contain real executable bin/rcc and bin/reach-helper.' >&2; exit 1; }
  container_compose_args+=(-f "$container_deploy_dir/compose.rcc.yaml")
fi
exec docker compose "${container_compose_args[@]}" "$@"
