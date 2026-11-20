"""Private, restartable CSV preparation in small HTTP requests; no task worker needed.

Only disposable export copies are written. A checkpoint is committed after each
batch; retries truncate uncommitted bytes before continuing. OS file locks are
released even if a worker is killed. Tokens are owner/session-bound and expire.
"""
import csv
import io
import json
import os
import shutil
import tempfile
import time
import uuid
from contextlib import contextmanager
from itertools import islice
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder

from . import activity_data as data

TTL = 24 * 60 * 60
BATCH_SIZE = 100
SALT = 'dashboard.activity-export.v1'


def root():
    path = Path(getattr(settings, 'ACTIVITY_EXPORT_ROOT', Path(tempfile.gettempdir()) / 'modulearn-activity-exports'))
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def save_state(path, state):
    temporary = path / 'state.new'
    with temporary.open('w', encoding='utf-8') as output:
        json.dump(state, output, cls=DjangoJSONEncoder)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path / 'state.json')


@contextmanager
def locked(path):
    # Advisory locks, shared across Gunicorn workers and released by the OS on exit.
    with (path / 'lock').open('a+b') as handle:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                if exc.errno in (13, 36):
                    raise BlockingIOError('Export is busy') from exc
                raise
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def new(instance, owner, filters, context):
    contexts = data.CONTEXTS if context == 'all' else (context,)
    if any(value not in (*data.CONTEXTS, 'summary') for value in contexts):
        raise ValueError('Unknown activity stream.')
    directory = root()
    # Bounded cleanup, confined to generated UUID directories; never under MEDIA_ROOT.
    for candidate in islice(directory.iterdir(), 100):
        try:
            if (candidate.is_dir() and not candidate.is_symlink() and candidate.resolve().parent == directory.resolve()
                    and len(candidate.name) == 32 and all(c in '0123456789abcdef' for c in candidate.name)):
                if candidate.stat().st_mtime < time.time() - TTL:
                    with locked(candidate):
                        for file in candidate.iterdir():
                            if file.name != 'lock':
                                file.unlink()
                    shutil.rmtree(candidate)
        except OSError:
            pass
    identifier = uuid.uuid4().hex
    path = directory / identifier
    path.mkdir(mode=0o700)
    state = {'filters': filters, 'contexts': contexts, 'stream': 0, 'before': None,
             'ceilings': {key: data.snapshot(instance, key, filters) for key in contexts},
             'count': 0, 'bytes': 0, 'done': False}
    save_state(path, state)
    token = signing.dumps({'id': identifier, 'owner': owner.pk, 'instance': instance.pk}, salt=SALT)
    return token


def locate(token, instance, owner):
    ticket = signing.loads(token, salt=SALT, max_age=TTL)
    if ticket.get('owner') != owner.pk or ticket.get('instance') != instance.pk:
        raise signing.BadSignature('Export belongs to another user or session.')
    identifier = ticket.get('id', '')
    if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
        raise signing.BadSignature('Invalid export identifier.')
    path = root() / identifier
    if not (path / 'state.json').is_file():
        raise signing.BadSignature('Export has expired or the server restarted.')
    return path


def csv_bytes(records, header=False):
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    if header:
        writer.writerow(data.CSV_FIELDS)
    for record in records:
        values = []
        for field in data.CSV_FIELDS:
            value = record.get(field, '')
            if field == 'payload':
                value = json.dumps(value, ensure_ascii=False, cls=DjangoJSONEncoder)
            elif hasattr(value, 'isoformat'):
                value = value.isoformat()
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return out.getvalue().encode('utf-8')


def advance(path, instance):
    with locked(path):
        state = json.loads((path / 'state.json').read_text(encoding='utf-8'))
        if state['done']:
            return state
        context = state['contexts'][state['stream']]
        records = data.rows(instance, context, state['filters'], state['ceilings'][context],
                            before=state['before'], limit=BATCH_SIZE, payload=True)
        chunk = csv_bytes(records, header=state['bytes'] == 0)
        with (path / 'activity.csv').open('a+b') as output:
            output.truncate(state['bytes'])
            output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        state['bytes'] += len(chunk)
        state['count'] += len(records)
        if len(records) < BATCH_SIZE:
            state['stream'] += 1
            state['before'] = None
            state['done'] = state['stream'] == len(state['contexts'])
        else:
            state['before'] = records[-1]['id']
        save_state(path, state)
        return state
