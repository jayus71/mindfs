"""Opt-in released RCC boundary check; HTTPS fixture never starts a model."""
import json
import os
from pathlib import Path
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

import test_entrypoint


@unittest.skipUnless(os.environ.get('RCC_INDEPENDENT_BINARY'), 'requires a released RCC binary')
class ReleasedRCCProjectConfirmationTests(unittest.TestCase):
    def test_generated_configuration_reaches_confirmation_without_reading_model_input(self):
        fixture = test_entrypoint.EntrypointEnvironmentTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root = Path(fixture.tmp.name)
        cert, key = root / 'ca.pem', root / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1',
                        '-keyout', str(key), '-out', str(cert)], check=True, capture_output=True)
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.respond({'Backend': 'personal-systemd-v1'})

            def respond(self, body, status=200):
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append((self.path, body))
                if self.path == '/api/client/resolve':
                    self.respond({'Backend': 'personal-systemd-v1', 'Binding': {
                        'Node': 'fixture-node', 'Project': 'fixture-project', 'Path': body['Path'],
                        'State': 'ready' if body['Confirm'] else 'confirmation_required'}})
                elif self.path == '/api/client/start':
                    # Stop at the launch boundary; no official CLI or stream exists.
                    self.respond({'Error': 'independent_launch_boundary'}, 409)
                else:
                    self.respond({'Error': 'unexpected_fixture_endpoint'}, 404)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f'https://127.0.0.1:{server.server_port}'
        profile = root / 'profile.json'
        profile.write_text(json.dumps({'Origin': origin, 'CAFile': str(cert)}))
        state = root / 'private-client-state'
        state.mkdir(mode=0o700)
        state_file = state / 'state.json'
        stdin = root / 'model-input'
        stdin.write_text('y\nTHIS_IS_MODEL_INPUT_NOT_BINDING_CONFIRMATION\n')
        fixture.env['RCC_NODE_ID'] = 'fixture-node'
        # Also keep imported Codex overrides present while regenerating RCC args.
        fixture.source.write_text(json.dumps({'agents': [{'name': 'codex', 'command': 'codex',
            'env': {'IMPORTED_MARKER': 'retained', 'HOME': '/invalid-host-home'}}]}))
        binary = str(Path(os.environ['RCC_INDEPENDENT_BINARY']).resolve())
        for setting in (None, 'false', 'true', 'true'):
            with self.subTest(setting=setting):
                if setting is None:
                    fixture.env.pop('RCC_CONFIRM_PROJECT', None)
                else:
                    fixture.env['RCC_CONFIRM_PROJECT'] = setting
                fixture.start()
                agents = json.loads(fixture.generated.read_text())['agents']
                rcc = next(a for a in agents if a['name'] == 'rcc')
                codex = next(a for a in agents if a['name'] == 'codex')
                self.assertEqual(codex['env']['HOME'], fixture.env['HOME'])
                self.assertEqual(codex['env']['IMPORTED_MARKER'], 'retained')
                state_file.write_text(json.dumps({'Epoch': 'fixture-epoch', 'Credential': {
                    'Origin': origin, 'DeviceID': 'a' * 64, 'Token': 'b' * 64,
                    'Expires': '2099-01-01T00:00:00Z'}}))
                state_file.chmod(0o600)
                requests.clear()
                claude_args = ['-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose']
                argv = [binary, '--profile', str(profile), '--client-state', str(state), *rcc['args'], '--', *claude_args]
                if setting == 'true':
                    self.assertLess(argv.index('--confirm-project'), argv.index('--'))
                with stdin.open('rb') as model_input:
                    result = subprocess.run(argv, cwd=fixture.env['MINDFS_CONTAINER_PROJECT_PATH'],
                        env=fixture.env, stdin=model_input, capture_output=True, timeout=10)
                    self.assertEqual(model_input.tell(), 0, 'RCC consumed model input as confirmation')
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('确认绑定？', result.stdout.decode())
                resolves = [body for path, body in requests if path == '/api/client/resolve']
                starts = [body for path, body in requests if path == '/api/client/start']
                self.assertEqual([body['Confirm'] for body in resolves], [False, True] if setting == 'true' else [False], result.stderr.decode())
                self.assertTrue(all(body['Path'] == str(Path(fixture.env['MINDFS_CONTAINER_PROJECT_PATH']).resolve()) for body in resolves))
                if setting == 'true':
                    self.assertEqual(len(starts), 1)
                    self.assertEqual(starts[0]['Args'], claude_args)
                    self.assertTrue(starts[0]['Pipe'])
                else:
                    self.assertEqual(starts, [])
                    self.assertIn('首次项目绑定需要 --confirm-project', result.stderr.decode())


if __name__ == '__main__':
    unittest.main()
