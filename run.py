"""Local JSON demo or Postgres-backed model load and run persistence."""
import argparse
import json
import os
from pathlib import Path
from core import compare, prepare


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='examples/model.json')
    parser.add_argument('--request', default='examples/request.json')
    parser.add_argument('--db', action='store_true', help='Use DATABASE_URL; insert/load model and save run')
    args = parser.parse_args()
    model = json.loads(Path(args.model).read_text())
    request = json.loads(Path(args.request).read_text())
    prepare(model)
    if args.db:
        import psycopg
        from psycopg.types.json import Jsonb
        with psycopg.connect(os.environ['DATABASE_URL'], prepare_threshold=None) as conn:
            conn.execute('''insert into casuar_do.models (name, version, definition)
                values (%s, %s, %s) on conflict (name, version) do nothing returning id''',
                (model['name'], model['version'], Jsonb(model))).fetchone()
            model_id, stored = conn.execute('''select id, definition from casuar_do.models
                where name = %s and version = %s''', (model['name'], model['version'])).fetchone()
            if stored != model:
                raise ValueError('Model version already exists with different content; increment version')
            result = compare(stored, **request)
            run_id = conn.execute('''insert into casuar_do.runs (model_id, model_snapshot, result)
                values (%s, %s, %s) returning id''', (model_id, Jsonb(stored), Jsonb(result))).fetchone()[0]
            result['run_id'] = str(run_id)
    else:
        result = compare(model, **request)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
