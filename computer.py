"""OpenBot transport through docker exec: no exposed port, host mounts or network."""
from __future__ import annotations

import base64
import json
import re
import secrets
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
ORIGIN = 'http://127.0.0.1:8765'
IMAGE = 'kareos-research-lab:pilot-v1'
LABEL = 'kareos.computer-research=pilot-v1'
CLIENT = """import json,sys,urllib.request,urllib.error
r=json.load(sys.stdin)
data=json.dumps(r['body']).encode() if r['body'] is not None else None
request=urllib.request.Request('http://127.0.0.1:4100'+r['path'],data=data,method=r['method'],headers={'Authorization':'Bearer '+r['token'],'x-openbot-bot-id':'research','Content-Type':'application/json'})
try:
 with urllib.request.urlopen(request,timeout=35) as response: print(response.read().decode())
except urllib.error.HTTPError as error:
 print(json.dumps({'transport_error':error.code,'message':error.read().decode()[:1000]}))
"""


def docker(*arguments, input=None, timeout=60):
    result = subprocess.run(['docker', *arguments], input=input, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    if result.returncode:
        # Do not echo argv: start arguments contain the ephemeral computer token.
        raise RuntimeError(f'Docker failed: {result.stderr[:1200]}')
    return result.stdout.strip()


def safe_path(path):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}\.txt', path):
        raise ValueError('Only a simple workspace .txt filename is allowed')
    return path


class ComputerActionError(RuntimeError):
    def __init__(self, status, message):
        self.status = int(status)
        super().__init__(f'Computer HTTP {self.status}: {message[:1000]}')


class Computer:
    def __init__(self, documents, report_dir: Path):
        self.documents = documents
        self.directory = report_dir
        self.name = 'kareos-research-' + secrets.token_hex(6)
        self.token = secrets.token_urlsafe(32)
        self.trace = []
        self.created = False
        self.startup_seconds = None

    def __enter__(self):
        started = time.monotonic()
        self.directory.mkdir(parents=True, exist_ok=True)
        fixture = self.directory / 'documents.json'
        fixture.write_text(json.dumps(self.documents), encoding='utf-8')
        try:
            docker('create', '--name', self.name, '--label', LABEL,
                   '--network', 'none', '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges', '--memory', '2g', '--cpus', '2',
                   '--pids-limit', '256', '--shm-size', '256m',
                   '-e', 'COMPUTER_TOKEN=' + self.token, IMAGE)
            self.created = True
            docker('cp', str(fixture), self.name + ':/lab-data/documents.json')
            docker('start', self.name)
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    if self.request('GET', '/health').get('status') == 'ok':
                        self.startup_seconds = round(time.monotonic() - started, 3)
                        return self
                except (RuntimeError, ValueError):
                    pass
                time.sleep(.5)
            raise RuntimeError('Computer did not become healthy: ' + docker('logs', self.name)[-1600:])
        except BaseException:
            self.close()
            raise

    def request(self, method, path, body=None):
        payload = json.dumps({'method': method, 'path': path, 'body': body, 'token': self.token})
        response = json.loads(docker('exec', '-i', self.name, 'python3', '-c', CLIENT, input=payload, timeout=45))
        if 'transport_error' in response:
            raise ComputerActionError(response['transport_error'], response['message'])
        return response

    def allowed_url(self, url):
        parsed = urlsplit(url)
        paths = {'/'} | {'/documents/' + doc['id'] for doc in self.documents}
        if parsed.scheme != 'http' or parsed.netloc != '127.0.0.1:8765' or parsed.path not in paths or parsed.query or parsed.fragment:
            raise ValueError('Only this case’s container-local synthetic portal is allowed')
        return url

    def action(self, operation, **args):
        if operation == 'navigate':
            result = self.request('POST', '/navigate', {'url': self.allowed_url(args['url'])})
        elif operation in ('snapshot', 'read', 'click'):
            current = self.request('GET', '/read')
            self.allowed_url(current['url'])
            if operation == 'snapshot':
                result = self.request('POST', '/snapshot', {})
            elif operation == 'read':
                result = self.request('GET', '/read')
            else:
                result = self.request('POST', '/click', {'ref': args['ref'], 'snapshotId': args['snapshot_id']})
                # Never read a redirected page outside the portal.
                self.allowed_url(self.request('POST', '/snapshot', {})['url'])
                result = self.request('GET', '/read')
        elif operation == 'calculate':
            # Validate on host before passing a quoted numeric expression to fixed shell command.
            from calculator import calculate
            calculate(args['expression'])
            expression = args['expression']
            if not re.fullmatch(r'[0-9eE+*/(). \-]+', expression):
                raise ValueError('Unexpected arithmetic characters')
            result = self.request('POST', '/exec', {'command': "python3 /lab/calculator.py '" + expression + "'", 'timeoutMs': 5000})
            if result['exitCode'] != 0:
                raise RuntimeError('Container calculation failed')
            result = json.loads(result['stdout'])
        elif operation in ('read_file', 'write_file'):
            path = safe_path(args['path'])
            payload = {'path': path}
            if operation == 'write_file':
                if len(args['contents']) > 4000:
                    raise ValueError('Workspace note exceeds limit')
                payload['contents'] = args['contents']
            result = self.request('POST', '/files/' + ('read' if operation == 'read_file' else 'write'), payload)
        else:
            raise ValueError('Unsupported computer operation')
        if 'url' in result:
            self.allowed_url(result['url'])
        self.trace.append({'operation': operation, 'arguments': args, 'result': result})
        return result

    def screenshot(self):
        result = self.request('GET', '/screenshot')
        target = self.directory / 'browser.png'
        target.write_bytes(base64.b64decode(result['base64']))
        return target

    def inspect(self):
        state = json.loads(docker('inspect', self.name))[0]
        # Deliberately omit Config.Env, which includes the computer token.
        return {'name': self.name, 'image_id': state['Image'], 'network': state['HostConfig']['NetworkMode'],
                'mounts': state['Mounts'], 'ports': state['HostConfig']['PortBindings'],
                'user': state['Config']['User'], 'cap_drop': state['HostConfig']['CapDrop'],
                'security_options': state['HostConfig']['SecurityOpt'], 'startup_seconds': self.startup_seconds}

    def close(self):
        if self.created:
            state = json.loads(docker('inspect', self.name))[0]
            if state['Config']['Labels'].get('kareos.computer-research') != 'pilot-v1':
                raise RuntimeError('Refusing cleanup of a container without research ownership label')
            docker('rm', '-f', self.name)
            self.created = False
        if self.directory.exists():
            (self.directory / 'computer-trace.json').write_text(json.dumps(self.trace, indent=2), encoding='utf-8')

    def __exit__(self, *_):
        self.close()
