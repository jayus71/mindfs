import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('import-settings.py')


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mindfs = self.root / 'host-mindfs'
        self.codex = self.root / 'host-codex'
        self.dest = self.root / 'private-home'
        self.mindfs.mkdir()
        self.codex.mkdir()
        self.secret = 'FAKE-SECRET-do-not-print'
        (self.mindfs / 'api-providers.json').write_text(json.dumps([{'id': 'p', 'api_key': self.secret}]))
        (self.mindfs / 'preferences.json').write_text(json.dumps({
            'agents': {'codex': {'model': 'test', 'effort': 'high', 'fast_service': 'fast',
                                 'last_config_selection': {'type': 'api_provider', 'id': 'p', 'backup': self.secret}}},
            'registry': self.secret, 'last_agent': 'codex', 'agent_pinned_models': {'codex': ['test']}}))
        (self.mindfs / 'agents.json').write_text(json.dumps({'relayBaseUrl': self.secret, 'agents': [
            {'name': 'codex', 'command': '/host/secret-command', 'installCommands': ['bad'], 'env': {'TEST_TOKEN': self.secret}},
            {'name': 'unknown', 'env': {'TOKEN': self.secret}}]}))
        (self.codex / 'config.toml').write_text('model="test"\nproject="/host/absolute"\n')
        (self.codex / 'auth.json').write_text(json.dumps({'token': self.secret}))
        for directory in (self.mindfs, self.codex):
            (directory / 'sessions').mkdir()
            (directory / 'sessions' / 'secret').write_text(self.secret)
            (directory / 'registry.json').write_text(self.secret)
            (directory / 'state.db').write_text(self.secret)
            (directory / 'backup.json').write_text(self.secret)

    def execute(self, *extra):
        result = subprocess.run([sys.executable, str(SCRIPT), '--mindfs-config-dir', str(self.mindfs),
                                 '--codex-home', str(self.codex), '--destination', str(self.dest), *extra],
                                capture_output=True, text=True)
        self.assertNotIn(self.secret, result.stdout + result.stderr)
        return result

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mode)
                for directory in (self.mindfs, self.codex) for p in directory.rglob('*') if p.is_file()}

    def test_opt_in_allowlist_permissions_and_source_unchanged(self):
        before = self.snapshot()
        self.assertEqual(self.execute('--include-mindfs-providers', '--include-codex-auth').returncode, 0)
        expected = {'.config/mindfs/api-providers.json', '.config/mindfs/preferences.json', '.codex/config.toml', '.codex/auth.json'}
        self.assertEqual({str(p.relative_to(self.dest)) for p in self.dest.rglob('*') if p.is_file()}, expected)
        for path in [self.dest, *self.dest.rglob('*')]:
            self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600)
        prefs = json.loads((self.dest / '.config/mindfs/preferences.json').read_text())
        self.assertEqual(prefs, {'agents': {'codex': {'model': 'test', 'effort': 'high', 'fast_service': 'fast', 'last_config_selection': {'type': 'api_provider', 'id': 'p'}}}, 'last_agent': 'codex', 'agent_pinned_models': {'codex': ['test']}})
        self.assertEqual((self.dest / '.codex/config.toml').read_bytes(), (self.codex / 'config.toml').read_bytes())
        self.assertEqual(before, self.snapshot())

    def test_default_excludes_opt_in_files(self):
        self.assertEqual(self.execute().returncode, 0)
        self.assertFalse((self.dest / '.codex/auth.json').exists())
        self.assertFalse((self.dest / '.config/mindfs/api-providers.json').exists())
        self.assertFalse((self.dest / '.config/mindfs/agents.json').exists())
        prefs = json.loads((self.dest / '.config/mindfs/preferences.json').read_text())
        self.assertNotIn('last_config_selection', prefs['agents']['codex'])

    def test_explicit_agent_env_uses_container_definition(self):
        self.assertEqual(self.execute('--include-agent-env').returncode, 0)
        output = json.loads((self.dest / '.config/mindfs/agents.json').read_text())
        self.assertEqual(output, {'agents': [{'name': 'codex', 'command': 'codex', 'protocol': 'codex-sdk', 'env': {'TEST_TOKEN': self.secret}}]})
        self.assertEqual((self.dest / '.config/mindfs/agents.json').stat().st_mode & 0o777, 0o600)

    def test_missing_provider_and_backup_selection_removed(self):
        prefs_file = self.mindfs / 'preferences.json'
        prefs = json.loads(prefs_file.read_text())
        prefs['agents']['other'] = {'last_config_selection': {'type': 'api_provider', 'id': 'missing'}}
        prefs['agents']['codex']['last_config_selection'] = {'type': 'backup', 'id': 'host-path'}
        prefs_file.write_text(json.dumps(prefs))
        self.assertEqual(self.execute('--include-mindfs-providers').returncode, 0)
        result = json.loads((self.dest / '.config/mindfs/preferences.json').read_text())
        self.assertNotIn('last_config_selection', result['agents']['codex'])
        self.assertNotIn('other', result['agents'])

    def test_reject_nonempty_destination_and_repeat(self):
        self.assertEqual(self.execute().returncode, 0)
        before = (self.dest / '.codex/config.toml').read_bytes()
        self.assertEqual(self.execute().returncode, 1)
        self.assertEqual(before, (self.dest / '.codex/config.toml').read_bytes())

    def test_empty_destination(self):
        self.dest.mkdir()
        self.assertEqual(self.execute().returncode, 0)

    def test_reject_symlink_file(self):
        (self.codex / 'config.toml').unlink()
        (self.codex / 'config.toml').symlink_to(self.codex / 'auth.json')
        self.assertEqual(self.execute().returncode, 1)
        self.assertFalse(self.dest.exists())

    def test_reject_symlink_destination_ancestor(self):
        link = self.root / 'link'
        link.symlink_to(self.root, target_is_directory=True)
        self.dest = link / 'private-home'
        self.assertEqual(self.execute().returncode, 1)

    def test_reject_source_destination_overlap(self):
        self.dest = self.codex / 'private'
        self.assertEqual(self.execute().returncode, 1)

    def test_invalid_json_does_not_echo_content_or_write(self):
        (self.mindfs / 'preferences.json').write_text(self.secret)
        self.assertEqual(self.execute().returncode, 1)
        self.assertFalse(self.dest.exists())

    def test_symlink_source_directory(self):
        link = self.root / 'source-link'
        link.symlink_to(self.codex, target_is_directory=True)
        self.codex = link
        self.assertEqual(self.execute().returncode, 1)


if __name__ == '__main__':
    unittest.main()
