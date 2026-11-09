#!/usr/bin/env python3
"""One-time, explicit allowlist import into an unused private container HOME.

Run on the host before starting the container. No source is discovered implicitly.
Provider records can contain credentials; copying them requires explicit opt-in.
Codex config.toml is always copied verbatim and may contain credentials and host paths.
Agent env values may contain secrets and require --include-agent-env.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile


class ImportFailure(Exception):
    pass


def checked_path(value):
    path = Path(os.path.abspath(value))
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ImportFailure("symbolic links are not accepted")
    return path


def read_optional(directory, name):
    path = checked_path(directory / name)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ImportFailure("source must be a regular file")
        return handle.read()


def preferences(payload, provider_ids):
    try:
        source = json.loads(payload)
        agents = source.get('agents', {})
        if not isinstance(agents, dict):
            raise ValueError()
        filtered = {}
        for name, settings in agents.items():
            if not isinstance(settings, dict):
                raise ValueError()
            selected = {}
            for field in ('model', 'effort', 'fast_service'):
                if field in settings:
                    if not isinstance(settings[field], str):
                        raise ValueError()
                    selected[field] = settings[field]
            if 'last_config_selection' in settings:
                selection = settings['last_config_selection']
                if selection is not None:
                    if not isinstance(selection, dict):
                        raise ValueError()
                    if selection.get('type') == 'api_provider' and selection.get('id') in provider_ids:
                        selected['last_config_selection'] = {
                            key: value for key, value in selection.items()
                            if key in ('type', 'id', 'name') and isinstance(value, str)
                        }
            if selected:
                filtered[name] = selected
        result = {'agents': filtered}
        if isinstance(source.get('last_agent'), str):
            result['last_agent'] = source['last_agent']
        pinned = source.get('agent_pinned_models', {})
        if not isinstance(pinned, dict) or any(not isinstance(v, list) or any(not isinstance(m, str) for m in v) for v in pinned.values()):
            raise ValueError()
        if pinned:
            result['agent_pinned_models'] = pinned
        return encode_json(result)
    except (ValueError, AttributeError, TypeError):
        raise ImportFailure('invalid preferences structure') from None


def encode_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def agent_env(payload):
    """Only Codex is installed by this container; commands are container constants."""
    try:
        source = json.loads(payload)
        agents = source.get('agents', [])
        if not isinstance(agents, list):
            raise ValueError()
        output = []
        for agent in agents:
            if not isinstance(agent, dict):
                raise ValueError()
            if agent.get('name') != 'codex' or not agent.get('env'):
                continue
            env = agent['env']
            if not isinstance(env, dict) or any(not isinstance(v, str) for v in env.values()):
                raise ValueError()
            output.append({'name': 'codex', 'command': 'codex', 'protocol': 'codex-sdk', 'env': env})
        if len(output) > 1:
            raise ValueError()
        return encode_json({'agents': output})
    except (ValueError, AttributeError, TypeError):
        raise ImportFailure('invalid agent environment structure') from None


def run(args):
    source = checked_path(args.mindfs_config_dir)
    codex = checked_path(args.codex_home)
    destination = checked_path(args.destination)
    for directory in (source, codex):
        if not directory.is_dir():
            raise ImportFailure('source directories must exist')
        if destination == directory or destination in directory.parents or directory in destination.parents:
            raise ImportFailure('source and destination must be separate trees')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ImportFailure('destination must be absent or empty')
    files = {}
    provider_ids = set()
    if args.include_mindfs_providers:
        payload = read_optional(source, 'api-providers.json')
        if payload is not None:
            try:
                providers = json.loads(payload)
                if not isinstance(providers, list) or any(not isinstance(p, dict) for p in providers):
                    raise ValueError()
                provider_ids = {p['id'] for p in providers if isinstance(p.get('id'), str)}
            except ValueError:
                raise ImportFailure('invalid provider list') from None
            files['.config/mindfs/api-providers.json'] = payload
    payload = read_optional(source, 'preferences.json')
    if payload is not None:
        files['.config/mindfs/preferences.json'] = preferences(payload, provider_ids)
    if args.include_agent_env:
        payload = read_optional(source, 'agents.json')
        if payload is not None:
            files['.config/mindfs/agents.json'] = agent_env(payload)
    payload = read_optional(codex, 'config.toml')
    if payload is not None:
        files['.codex/config.toml'] = payload
    if args.include_codex_auth:
        payload = read_optional(codex, 'auth.json')
        if payload is not None:
            files['.codex/auth.json'] = payload
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.mindfs-import-', dir=destination.parent))
    try:
        for name, content in files.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as handle:
                os.fchmod(handle.fileno(), 0o600)
                handle.write(content)
        for root, dirs, _ in os.walk(stage):
            os.chmod(root, 0o700)
        # POSIX rename refuses to replace a destination that became nonempty.
        os.rename(stage, destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print('Import complete. Private HOME files: ' + str(len(files)))
    if '.codex/config.toml' in files:
        print('Codex config may contain credentials; preserved verbatim. Review host-specific paths before container use.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mindfs-config-dir', required=True)
    parser.add_argument('--codex-home', required=True)
    parser.add_argument('--destination', required=True, help='unused private HOME directory')
    parser.add_argument('--include-mindfs-providers', action='store_true', help='explicitly copy provider records, including their credentials')
    parser.add_argument('--include-agent-env', action='store_true', help='explicitly copy supported Codex env values; these may contain secrets')
    parser.add_argument('--include-codex-auth', action='store_true', help='explicitly copy Codex auth.json')
    args = parser.parse_args()
    try:
        run(args)
    except (ImportFailure, OSError):
        # Never echo source content or exception text that may contain secrets.
        print('Import failed: invalid input, unsafe path, occupied destination, or filesystem error.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
