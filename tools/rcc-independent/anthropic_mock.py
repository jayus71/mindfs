#!/usr/bin/python3
"""Controlled Anthropic JSON/SSE fixture for official CLI integration tests."""
import http.server
import json
import pathlib
import sys
import threading

steps = json.loads(pathlib.Path(sys.argv[1]).read_text())
request_log = pathlib.Path(sys.argv[2])
lock = threading.Lock()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with lock:
            with request_log.open('a') as log:
                log.write(json.dumps(body) + '\n')
        seen = set()
        for message in body.get('messages', []):
            content = message.get('content', [])
            if isinstance(content, list):
                seen.update(part.get('tool_use_id') for part in content if part.get('type') == 'tool_result')
        selected = len([ident for ident in seen if ident and ident.startswith('toolu_independent_')])
        block = {'type': 'text', 'text': 'Independent fixture completed.'}
        stop = 'end_turn'
        if body.get('stream') and selected < len(steps):
            step = steps[selected]
            block = {'type': 'tool_use', 'id': 'toolu_independent_' + str(selected), 'name': step['name'], 'input': step['input']}
            stop = 'tool_use'
        usage = {'input_tokens': 12, 'output_tokens': 8, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0}
        message = {'id': 'msg_independent', 'type': 'message', 'role': 'assistant', 'model': body.get('model', 'claude-sonnet-4-6'), 'content': [block], 'stop_reason': stop, 'stop_sequence': None, 'usage': usage}
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream' if body.get('stream') else 'application/json')
        self.end_headers()
        if not body.get('stream'):
            self.wfile.write(json.dumps(message).encode())
            return
        start_message = dict(message, content=[], stop_reason=None, usage=dict(usage, output_tokens=0))
        start_block = dict(block, input={}) if block['type'] == 'tool_use' else dict(block, text='')
        delta = {'type': 'input_json_delta', 'partial_json': json.dumps(block['input'])} if block['type'] == 'tool_use' else {'type': 'text_delta', 'text': block['text']}
        for event in [
            {'type': 'message_start', 'message': start_message},
            {'type': 'content_block_start', 'index': 0, 'content_block': start_block},
            {'type': 'content_block_delta', 'index': 0, 'delta': delta},
            {'type': 'content_block_stop', 'index': 0},
            {'type': 'message_delta', 'delta': {'stop_reason': stop, 'stop_sequence': None}, 'usage': usage},
            {'type': 'message_stop'},
        ]:
            self.wfile.write(('event: ' + event['type'] + '\ndata: ' + json.dumps(event) + '\n\n').encode())
        self.wfile.flush()


server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
print('http://127.0.0.1:' + str(server.server_port), flush=True)
server.serve_forever()
