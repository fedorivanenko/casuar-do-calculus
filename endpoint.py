"""Authenticated, bounded HTTP adapter for the tiny causal engine."""
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from uuid import UUID
from core import compare, prepare

MAX_BODY = 65536


def request_key(secret):
    return hmac.new(secret.encode(), b'casuar-causal-run-v1', hashlib.sha256).hexdigest()


def calculate(model, request):
    if not isinstance(model, dict) or not isinstance(model.get('variables'), dict):
        raise ValueError('model.variables must be an object')
    if not 1 <= len(model['variables']) <= 32 or len(model.get('parameters', {})) > 32:
        raise ValueError('At most 32 variables and 32 parameters')
    steps, draws = request['steps'], request['draws']
    if type(steps) is not int or not 1 <= steps <= 120:
        raise ValueError('steps must be 1..120')
    if type(draws) is not int or not 1 <= draws <= 5000:
        raise ValueError('draws must be 1..5000')
    if steps * draws * len(model['variables']) > 500000:
        raise ValueError('Run exceeds 500000 variable updates per scenario; reduce steps/draws')
    if type(request['seed']) is not int or not 0 <= request['seed'] <= 2147483647:
        raise ValueError('seed must be an integer in 0..2147483647')
    if not isinstance(request['initial'], dict) or not isinstance(request['interventions'], dict):
        raise ValueError('initial and interventions must be objects')
    prepare(model)
    return {**compare(model, **request), 'model_snapshot': model, 'persisted': False,
            'interpretation': 'Simulation under supplied assumptions; not causal identification or clinical advice.'}


def run(payload):
    if not isinstance(payload, dict):
        raise ValueError('Request must be an object')
    allowed = {'model', 'model_id', 'steps', 'draws', 'seed', 'initial', 'interventions', 'persist'}
    if set(payload) - allowed:
        raise ValueError('Unknown request fields')
    if 'model_id' in payload and 'model' in payload:
        raise ValueError('Supply model or model_id, not both')
    if type(payload.get('persist', False)) is not bool:
        raise ValueError('persist must be boolean')
    request = {key: payload.get(key, default) for key, default in
               {'steps': 12, 'draws': 500, 'seed': 42, 'initial': {}, 'interventions': {}}.items()}
    model_id = payload.get('model_id')
    if model_id is not None:
        model_id = str(UUID(model_id))
    model = payload.get('model')
    if model is None and model_id is None:
        model = json.loads((Path(__file__).parent / 'examples/model.json').read_text())
    if not model_id and not payload.get('persist', False):
        return calculate(model, request)
    if not os.environ.get('DATABASE_URL'):
        raise RuntimeError('Database-backed runs are not configured')
    import psycopg
    from psycopg.types.json import Jsonb
    with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None, connect_timeout=5) as conn:
        conn.execute("set local statement_timeout = '5s'")
        if model_id:
            row = conn.execute('select definition from casuar_do.models where id = %s', (model_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown model_id')
            model = row[0]
        result = calculate(model, request)
        if model_id is None:
            name, version = model.get('name'), model.get('version')
            if not isinstance(name, str) or not name or type(version) is not int or version < 1:
                raise ValueError('Persistence requires a model name and positive integer version')
            conn.execute('''insert into casuar_do.models (name, version, definition) values (%s, %s, %s)
                         on conflict (name, version) do nothing''', (name, version, Jsonb(model)))
            model_id, stored = conn.execute('select id, definition from casuar_do.models where name=%s and version=%s',
                                           (name, version)).fetchone()
            if stored != model:
                raise ValueError('Model version has different content; increment version')
        result['persisted'] = True
        run_id = conn.execute('''insert into casuar_do.runs (model_id, model_snapshot, result)
                            values (%s, %s, %s) returning id''',
                            (model_id, Jsonb(model), Jsonb(result))).fetchone()[0]
        return {**result, 'run_id': str(run_id), 'model_id': str(model_id)}


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, value):
        body = json.dumps(value, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        secret = os.environ.get('CASUAR_MCP_TOKEN')
        if not secret:
            self.reply(503, {'error': 'Causal endpoint is not configured'})
            return
        supplied = self.headers.get('Authorization', '')
        if not hmac.compare_digest(supplied.encode(), ('Bearer ' + request_key(secret)).encode()):
            self.reply(401, {'error': 'Unauthorized'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_BODY:
                self.reply(413, {'error': 'JSON body must be 1..65536 bytes'})
                return
            payload = json.loads(self.rfile.read(size))
            result = run(payload)
            # Check serializability before emitting HTTP headers.
            json.dumps(result, allow_nan=False)
        except (ValueError, TypeError, KeyError, SyntaxError, ArithmeticError, AttributeError):
            self.reply(400, {'error': 'Invalid model or request; check names, equations, finite values and workload limits'})
            return
        except Exception:
            self.reply(503, {'error': 'Run unavailable; check database configuration and service health'})
            return
        self.reply(200, result)

    def do_GET(self):
        self.reply(405, {'error': 'Use authenticated POST'})

    def log_message(self, *_):
        pass  # Do not log patient inputs or authorization headers.
