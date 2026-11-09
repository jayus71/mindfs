#!/usr/bin/env python3
"""Run isolated fake-config container checks; never discover host credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='already-built image')
    parser.add_argument('--port', type=int, default=17332, help='unused host loopback port')
    parser.add_argument('--rcc-release-dir', help='optional complete release; read-only --help check only')
    args = parser.parse_args()
    deploy = Path(__file__).resolve().parent
    root = Path(tempfile.mkdtemp(prefix='mindfs-container-smoke-'))
    group = 'mindfs-smoke-' + uuid.uuid4().hex[:10]
    private, project = root / 'home', root / 'project'
    source, codex = root / 'source-mindfs', root / 'source-codex'
    checks = []
    env = os.environ.copy()
    # Ignore operator deployment settings; every runtime path belongs to this run.
    for key in ('RCC_RELEASE_DIR', 'RCC_NODE_ID', 'COMPOSE_FILE', 'COMPOSE_PROFILES'):
        env.pop(key, None)
    env.update(MINDFS_CONTAINER_HOME=str(private), MINDFS_PROJECT_DIR=str(project),
               MINDFS_CONTAINER_PORT=str(args.port), MINDFS_CONTAINER_IMAGE=args.image,
               MINDFS_UID=str(os.getuid()), MINDFS_GID=str(os.getgid()))

    def run(command, expected=0):
        result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != expected:
            raise RuntimeError('command failed: ' + command[0] + ' (exit ' + str(result.returncode) + ')\n' + result.stderr)
        return result.stdout

    def compose(*command):
        return run(['bash', str(deploy / 'compose.sh'), '-p', group, *command])

    def request(path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request('http://127.0.0.1:' + str(args.port) + path, data=data,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read()

    def healthy():
        for _ in range(90):
            try:
                if request('/health'):
                    return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(1)
        raise RuntimeError('container health did not become available')

    def source_hash():
        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for directory in (source, codex) for p in directory.rglob('*') if p.is_file()}

    try:
        source.mkdir(mode=0o700)
        codex.mkdir(mode=0o700)
        (project / '.mindfs').mkdir(parents=True)
        sentinel = project / '.mindfs/public-sentinel'
        sentinel.write_text('public-instance-untouched\n')
        (source / 'api-providers.json').write_text(json.dumps([{
            'id': 'fixture', 'name': 'Fixture', 'baseUrl': 'https://container-fixture.invalid/v1',
            'apiKey': 'FAKE-CONTAINER-SECRET', 'protocols': ['openai-compatible'],
            'modelFamilies': ['gpt'], 'models': ['gpt-fixture']}]))
        (codex / 'config.toml').write_text('model = "gpt-fixture"\n')
        original = source_hash()
        run(['python3', str(deploy / 'import-settings.py'), '--mindfs-config-dir', str(source),
             '--codex-home', str(codex), '--destination', str(private), '--include-mindfs-providers'])
        # Prevent startup/config-switch probes from executing real model-capable agents.
        (private / '.config/mindfs/agents.json').write_text(json.dumps({'agents': [
            {'name': 'codex', 'command': '/nonexistent-container-fixture', 'protocol': 'codex-sdk'}]}))
        (private / '.config/mindfs/agents.json').chmod(0o600)
        env.pop('MINDFS_CONTAINER_PORT')
        default_ports = json.loads(compose('config', '--format', 'json'))['services']['mindfs']['ports']
        assert default_ports[0]['host_ip'] == '127.0.0.1' and str(default_ports[0]['published']) == '7332'
        env['MINDFS_CONTAINER_PORT'] = str(args.port)
        rendered = json.loads(compose('config', '--format', 'json'))['services']['mindfs']
        assert rendered['ports'][0]['host_ip'] == '127.0.0.1'
        assert str(rendered['ports'][0]['published']) == str(args.port)
        checks.append('compose loopback and isolated fixture paths')
        version = run(['docker', 'run', '--rm', '--network', 'none', args.image, 'codex', '--version']).strip()
        assert version.startswith('codex-cli '), version
        uid = run(['docker', 'run', '--rm', '--network', 'none', args.image, 'id', '-u']).strip()
        assert uid == str(os.getuid()), uid
        checks.append('non-root UID and installed ' + version)
        rejected = subprocess.run(['docker', 'run', '--rm', '--network', 'none', args.image, 'mindfs', '--version'],
                                  env=env, capture_output=True, text=True)
        assert rejected.returncode != 0 and 'unmasked project metadata' in rejected.stderr
        checks.append('unmasked startup refusal')
        compose('up', '-d', '--no-build')
        healthy()
        html = request('/').decode()
        assert 'MindFS RCC Container' in html and 'frontend assets missing' not in html
        asset = re.search(r'(?:src|href)="(?:\./|/)(assets/[^"\s]+\.js)"', html)
        assert asset and len(request('/' + asset.group(1))) > 100
        # The health endpoint precedes the CLI's managed-project registration.
        for _ in range(15):
            dirs = json.loads(request('/api/dirs'))
            if str(project) in json.dumps(dirs):
                break
            time.sleep(1)
        assert str(project) in json.dumps(dirs), dirs
        request('/api/sessions?root=' + dirs[0]['id'])
        providers = request('/api/agent-api-providers')
        assert b'Fixture' in providers and b'FAKE-CONTAINER-SECRET' not in providers and b'apiKey' not in providers
        checks.append('health, titled web UI, bundled asset, dirs/sessions and redacted provider list')
        request('/api/agent-api-providers/switch', {'agent': 'codex', 'provider_id': 'fixture'})
        config = (private / '.codex/config.toml').read_text()
        assert 'container-fixture.invalid' in config and 'FAKE-CONTAINER-SECRET' in config
        assert source_hash() == original
        assert sentinel.read_text() == 'public-instance-untouched\n'
        assert list((project / '.mindfs').iterdir()) == [sentinel]
        metadata = private / '.workspace-metadata'
        assert any(metadata.iterdir())
        (metadata / 'restart-sentinel').write_text('persistent')
        checks.append('provider switch writes private HOME; source hashes and public metadata unchanged')
        compose('restart')
        healthy()
        assert (metadata / 'restart-sentinel').read_text() == 'persistent'
        assert (private / '.codex/config.toml').read_text() == config
        checks.append('HOME and metadata persist across restart')
        if args.rcc_release_dir:
            release = Path(args.rcc_release_dir).resolve(strict=True)
            help_text = run(['docker', 'run', '--rm', '--network', 'none', '--mount',
                             'type=bind,src=' + str(release) + ',dst=/opt/rcc,readonly', args.image, 'rcc', '--help'])
            assert '--node' in help_text
            env.update(RCC_RELEASE_DIR=str(release), RCC_NODE_ID='fixture-external-node')
            compose('run', '--rm', '--no-deps', 'mindfs', 'mindfs', '--version')
            generated = json.loads((private / '.config/mindfs/container-rcc.json').read_text())
            assert generated['agents'][0]['args'] == ['--node', 'fixture-external-node']
            rcc_mount = [v for v in json.loads(compose('config', '--format', 'json'))['services']['mindfs']['volumes']
                         if v['target'] == '/opt/rcc'][0]
            assert rcc_mount['read_only'] is True
            checks.append('read-only RCC binary and external --node config; no login/session request')
        for check in checks:
            print('PASS ' + check)
    finally:
        try:
            run(['docker', 'compose', '-f', str(deploy / 'compose.yaml'), '-p', group, 'down', '--remove-orphans'])
        finally:
            shutil.rmtree(root)


if __name__ == '__main__':
    main()
