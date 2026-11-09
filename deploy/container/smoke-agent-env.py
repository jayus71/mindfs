#!/usr/bin/env python3
"""Exercise imported env through the real MindFS SDK and a fake app-server."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--go', default='go', help='Go compiler for the existing offline fixture')
    args = parser.parse_args()
    deploy = Path(__file__).resolve().parent
    fixture_source = deploy.parent.parent / 'tools/container-independent'
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(fixture_source))
    from ws_fixture import WebSocket

    root = Path(tempfile.mkdtemp(prefix='mindfs-container-env-dev-'))
    private, source, codex, project, fixtures = [root / name for name in ('home', 'source', 'codex', 'project', 'fixtures')]
    group = 'mindfs-env-dev-' + uuid.uuid4().hex[:10]
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = {key: value for key, value in os.environ.items() if not key.startswith(('MINDFS_', 'COMPOSE_', 'RCC_'))}
    env.update(MINDFS_CONTAINER_HOME=str(private), MINDFS_PROJECT_DIR=str(project),
               MINDFS_CONTAINER_PORT=str(port), MINDFS_CONTAINER_IMAGE=args.image,
               MINDFS_UID=str(os.getuid()), MINDFS_GID=str(os.getgid()))
    override = root / 'override.yaml'
    empty_env = root / 'empty.env'
    command = ['bash', str(deploy / 'compose.sh'), '-f', str(override), '-p', group, '--env-file', str(empty_env)]

    def run(argv, **kwargs):
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=120, **kwargs)
        if result.returncode:
            raise RuntimeError('command failed: ' + argv[0] + '\n' + result.stderr)
        return result.stdout

    def api(path):
        with urllib.request.urlopen('http://127.0.0.1:' + str(port) + path, timeout=5) as response:
            return json.loads(response.read())

    def ready():
        for _ in range(120):
            try:
                if api('/api/dirs'):
                    return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(.25)
        raise RuntimeError('fixture service did not start')

    def turn(content, session=None):
        websocket = WebSocket(port)
        request_id = uuid.uuid4().hex
        payload = {'root_id': project.name, 'content': content, 'type': 'chat',
                   'agent': 'codex', 'model': 'fixture-model'}
        if session:
            payload['session_key'] = session
        websocket.send({'id': request_id, 'type': 'session.message', 'payload': payload})
        events = []
        try:
            for _ in range(150):
                event = websocket.recv()
                events.append(event)
                if event.get('id') == request_id and event.get('type') == 'session.accepted':
                    session = event['payload']['session_key']
                if event.get('id') == request_id and event.get('type') == 'session.done':
                    break
            else:
                raise RuntimeError('SDK turn did not finish')
        finally:
            websocket.close()
        assert not any(event.get('error') or event.get('payload', {}).get('event', {}).get('type') == 'error' for event in events)
        text = ''.join(event.get('payload', {}).get('event', {}).get('data', {}).get('content', '')
                       for event in events if event.get('type') == 'session.stream')
        assert 'fixture-response' in text, text
        return session, text

    try:
        for directory in (source, codex, fixtures):
            directory.mkdir(mode=0o700)
        (project / '.mindfs').mkdir(parents=True)
        empty_env.touch()
        (source / 'agents.json').write_text(json.dumps({'agents': [{
            'name': 'codex', 'command': '/host/unused', 'env': {
                'IMPORTED_MARKER': 'present', 'HOME': '/host/wrong-home',
                'CODEX_HOME': '/host/wrong-codex', 'PATH': '/host/wrong-bin'}}]}))
        (codex / 'config.toml').write_text('model="fixture-model"\n')
        original = hashlib.sha256((source / 'agents.json').read_bytes()).hexdigest()
        run(['python3', str(deploy / 'import-settings.py'), '--mindfs-config-dir', str(source),
             '--codex-home', str(codex), '--destination', str(private), '--include-agent-env'])
        run(['env', 'CGO_ENABLED=0', args.go, 'build', '-o', str(fixtures / 'fake-codex'), str(fixture_source / 'fake_codex.go')])
        (fixtures / 'record-env.py').write_text(
            'import json,os\n'
            'keys=("HOME","CODEX_HOME","PATH","XDG_CONFIG_HOME","XDG_STATE_HOME","IMPORTED_MARKER","CONTAINER_RUNTIME_MARKER")\n'
            'with open("/home/mindfs/.local/state/env-observation.jsonl","a") as f:\n'
            ' f.write(json.dumps({k:os.environ.get(k) for k in keys})+"\\n")\n')
        wrapper = fixtures / 'probe-codex'
        wrapper.write_text('#!/bin/sh\n/usr/bin/python3 /fixtures/record-env.py\nexec /fixtures/fake-codex "$@"\n')
        wrapper.chmod(0o755)
        agent_path = private / '.config/mindfs/agents.json'
        imported = json.loads(agent_path.read_text())
        imported['agents'][0]['command'] = '/fixtures/probe-codex'
        agent_path.write_text(json.dumps(imported))
        imported_bytes = agent_path.read_bytes()
        (private / '.independent-fixture-owned').touch()
        override.write_text('services:\n  mindfs:\n    environment:\n'
                            '      CONTAINER_RUNTIME_MARKER: runtime-present\n'
                            '      INDEPENDENT_CODEX_LOG: /home/mindfs/.local/state/sdk.jsonl\n'
                            '      HTTP_PROXY: http://127.0.0.1:9\n'
                            '      HTTPS_PROXY: http://127.0.0.1:9\n'
                            '    volumes:\n      - ' + str(fixtures) + ':/fixtures:ro\n')
        run(command + ['up', '-d', '--no-build'])
        ready()
        # Disable optional model-based session naming for this offline fixture.
        request = urllib.request.Request('http://127.0.0.1:' + str(port) + '/api/preferences/session-naming',
                                         data=b'{"disabled":true}', method='PUT', headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
        session, first = turn('imported env first turn')
        same, second = turn('imported env second turn', session)
        assert same == session and second.endswith('2'), second
        observations = [json.loads(line) for line in (private / '.local/state/env-observation.jsonl').read_text().splitlines()]
        assert observations
        for observed in observations:
            assert observed['HOME'] == '/home/mindfs'
            assert observed['CODEX_HOME'] == '/home/mindfs/.codex'
            assert observed['XDG_CONFIG_HOME'] == '/home/mindfs/.config'
            assert observed['XDG_STATE_HOME'] == '/home/mindfs/.local/state'
            assert '/usr/local/bin' in observed['PATH'] and '/host/wrong-bin' not in observed['PATH']
            assert observed['IMPORTED_MARKER'] == 'present' and observed['CONTAINER_RUNTIME_MARKER'] == 'runtime-present'
        run(command + ['restart'])
        ready()
        same, resumed = turn('imported env after restart', session)
        assert same == session
        assert agent_path.read_bytes() == imported_bytes
        assert hashlib.sha256((source / 'agents.json').read_bytes()).hexdigest() == original
        print(json.dumps({'passed': True, 'sdk_starts': len(observations), 'first': first, 'second': second,
                          'resumed': resumed, 'source_and_import_unchanged': True, 'environment': observations[0]}, indent=2))
    finally:
        try:
            run(['docker', 'compose', '-f', str(deploy / 'compose.yaml'), '-p', group, 'down', '--remove-orphans'])
        finally:
            shutil.rmtree(root)


if __name__ == '__main__':
    main()
