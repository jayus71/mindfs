import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ENTRYPOINT = Path(__file__).with_name('entrypoint.sh')


class EntrypointEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mindfs-entrypoint-test-')
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home, project, self.bin = root / 'home', root / 'project', root / 'bin'
        self.config = self.home / '.config/mindfs'
        self.config.mkdir(parents=True)
        self.bin.mkdir()
        project.mkdir()
        (self.home / '.workspace-metadata').mkdir()
        (project / '.mindfs').symlink_to(self.home / '.workspace-metadata', target_is_directory=True)
        self.source = self.config / 'agents.json'
        self.generated = self.config / 'container-rcc.json'
        # A fake parent captures startup args without running a service or model.
        command = self.bin / 'mindfs'
        command.write_text('#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
        command.chmod(0o755)
        self.env = {
            'HOME': str(self.home), 'CODEX_HOME': str(self.home / '.codex'),
            'XDG_CONFIG_HOME': str(self.home / '.config'),
            'XDG_STATE_HOME': str(self.home / '.local/state'),
            'PATH': str(self.bin) + ':/usr/local/bin:/usr/bin:/bin',
            'MINDFS_CONTAINER_PROJECT_PATH': str(project),
            'CONTAINER_RUNTIME_MARKER': 'runtime',
            'HTTP_PROXY': 'http://127.0.0.1:9',
        }

    def start(self):
        result = subprocess.run(['/bin/sh', str(ENTRYPOINT), 'mindfs', '--version'], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_nonempty_import_uses_container_environment_without_mutating_source(self):
        definition = {'agents': [{'name': 'codex', 'command': 'codex', 'protocol': 'codex-sdk',
                                  'env': {'IMPORTED_MARKER': 'imported', 'HOME': '/host/home',
                                          'CODEX_HOME': '/host/codex', 'PATH': '/host/bin',
                                          'XDG_CONFIG_HOME': '/host/config', 'XDG_STATE_HOME': '/host/state'}}]}
        self.source.write_text(json.dumps(definition))
        original = self.source.read_bytes()
        # A host-only variable must not enter the separately supplied runtime env.
        from unittest.mock import patch
        with patch.dict(os.environ, {'HOST_ONLY_SECRET': 'must-not-copy'}):
            argv = self.start()
        self.assertEqual(argv, ['--agent-config', str(self.generated), '--version'])
        agent = json.loads(self.generated.read_text())['agents'][0]
        self.assertEqual(agent['command'], 'codex')
        self.assertEqual(agent['env']['IMPORTED_MARKER'], 'imported')
        self.assertEqual(agent['env']['CONTAINER_RUNTIME_MARKER'], 'runtime')
        for key in ('HOME', 'CODEX_HOME', 'PATH', 'XDG_CONFIG_HOME', 'XDG_STATE_HOME', 'HTTP_PROXY'):
            self.assertEqual(agent['env'][key], self.env[key])
        self.assertNotIn('HOST_ONLY_SECRET', agent['env'])
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(self.generated.stat().st_mode & 0o777, 0o600)

    def test_restart_rebuilds_environment_and_keeps_rcc_definition(self):
        self.source.write_text(json.dumps({'agents': [{'name': 'codex', 'command': 'codex',
                                                      'env': {'IMPORTED_MARKER': 'imported'}}]}))
        self.env['RCC_NODE_ID'] = 'fixture-node'
        self.start()
        self.env.pop('HTTP_PROXY')
        self.env['CONTAINER_RUNTIME_MARKER'] = 'updated'
        self.start()
        agents = json.loads(self.generated.read_text())['agents']
        self.assertEqual(agents[0]['args'], ['--node', 'fixture-node'])
        self.assertEqual(agents[1]['env']['CONTAINER_RUNTIME_MARKER'], 'updated')
        self.assertNotIn('HTTP_PROXY', agents[1]['env'])
        self.assertEqual(agents[1]['env']['IMPORTED_MARKER'], 'imported')

    def test_empty_env_keeps_normal_inheritance_and_removes_stale_overlay(self):
        self.source.write_text(json.dumps({'agents': [{'name': 'codex', 'command': 'codex', 'env': {}}]}))
        self.generated.write_text('{"stale":true}')
        self.assertEqual(self.start(), ['--version'])
        self.assertFalse(self.generated.exists())

    def test_project_confirmation_is_opt_in_and_rebuilt_on_restart(self):
        self.env['RCC_NODE_ID'] = 'fixture-node'
        for enabled, expected in [(None, False), ('false', False), ('true', True), ('true', True), ('false', False)]:
            with self.subTest(value=enabled, expected=expected):
                if enabled is None:
                    self.env.pop('RCC_CONFIRM_PROJECT', None)
                else:
                    self.env['RCC_CONFIRM_PROJECT'] = enabled
                self.start()
                agent = json.loads(self.generated.read_text())['agents'][0]
                expected_args = ['--node', 'fixture-node'] + (['--confirm-project'] if expected else [])
                self.assertEqual(agent['args'], expected_args)
                self.assertNotIn('--', agent['args'], 'SDK must add the Claude argument separator')
                self.assertEqual(agent['protocol'], 'rcc')
                self.assertEqual(agent['command'], 'rcc')
                self.assertNotIn('env', agent)

    def test_project_confirmation_without_node_does_not_create_rcc_agent(self):
        self.env['RCC_CONFIRM_PROJECT'] = 'true'
        self.assertEqual(self.start(), ['--version'])
        self.assertFalse(self.generated.exists())

    def test_invalid_project_confirmation_fails_clearly(self):
        self.env['RCC_CONFIRM_PROJECT'] = 'yes'
        result = subprocess.run(['/bin/sh', str(ENTRYPOINT), 'mindfs'], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('RCC_CONFIRM_PROJECT must be true or false', result.stderr)

    def test_invalid_env_fails_without_echoing_values(self):
        secret = 'FAKE-INVALID-SECRET'
        self.source.write_text(json.dumps({'agents': [{'name': 'codex', 'env': {secret: ['invalid']}}]}))
        result = subprocess.run(['/bin/sh', str(ENTRYPOINT), 'mindfs'], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(secret, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
