"""Versioned, bounded JSON data only; no Python expression evaluation."""
import json
import math
import re

VERSION = 1
MAX_INPUT = 65536
MAX_OUTPUT = 1048576
STATUSES = {'OK', 'INVALID_INPUT', 'LIMIT_EXCEEDED', 'UNSUPPORTED_ALGORITHM',
            'NEGATIVE_CYCLE', 'CYCLE_DETECTED', 'TIMEOUT', 'CANCELLED', 'WORKER_CRASH',
            'OUTPUT_LIMIT_EXCEEDED', 'PROTOCOL_ERROR', 'LIMITS_UNAVAILABLE',
            'INTERNAL_ERROR', 'BUSY', 'CLOSED'}

class SolverError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)

def integer(value, name, low=None, high=None):
    if type(value) is not int:
        raise SolverError('INVALID_INPUT', f'{name} must be an integer (not bool/float)')
    if low is not None and value < low:
        raise SolverError('INVALID_INPUT', f'{name} must be >= {low}')
    if high is not None and value > high:
        raise SolverError('LIMIT_EXCEEDED', f'{name} exceeds policy limit {high}')
    return value

def validate_shape(value):
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > 30000 or depth > 10:
            raise SolverError('LIMIT_EXCEEDED', 'JSON node/depth policy exceeded')
        if type(item) is dict:
            if len(item) > 32 or any(type(k) is not str for k in item):
                raise SolverError('INVALID_INPUT', 'object keys must be bounded strings')
            stack.extend((v, depth+1) for v in item.values())
        elif type(item) is list:
            stack.extend((v, depth+1) for v in item)
        elif item is not None and type(item) not in (str, int, bool, float):
            raise SolverError('INVALID_INPUT', 'only JSON primitive/list/object values accepted')
        if type(item) is str and len(item) > MAX_INPUT:
            raise SolverError('LIMIT_EXCEEDED', 'string too long')
        if type(item) is float and not math.isfinite(item):
            raise SolverError('INVALID_INPUT', 'floating values must be finite')
        if type(item) is int and item.bit_length() > 256:
            raise SolverError('LIMIT_EXCEEDED', 'integer encoding exceeds 256 bits')

def loads(raw, limit=MAX_INPUT):
    if len(raw) > limit:
        raise SolverError('LIMIT_EXCEEDED', 'serialized payload too large')
    # Bound structural nesting before JSONDecoder recursion; ignore brackets in strings.
    quoted = escaped = False
    depth = 0
    for c in raw:
        if quoted:
            if escaped:
                escaped = False
            elif c == 92:
                escaped = True
            elif c == 34:
                quoted = False
        elif c == 34:
            quoted = True
        elif c in (91, 123):
            depth += 1
            if depth > 10:
                raise SolverError('LIMIT_EXCEEDED', 'encoded nesting exceeds ten levels')
        elif c in (93, 125):
            depth -= 1
    def unique(pairs):
        result = {}
        for k,v in pairs:
            if k in result:
                raise SolverError('INVALID_INPUT', f'duplicate object key: {k}')
            result[k] = v
        return result
    def constant(token):
        raise SolverError('INVALID_INPUT', f'non-finite token {token}')
    try:
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SolverError('INVALID_INPUT', 'invalid UTF-8 JSON') from exc
    validate_shape(value)
    return value

def dumps(value, limit=MAX_INPUT):
    validate_shape(value)
    try:
        raw = json.dumps(value, ensure_ascii=True, allow_nan=False,
                         separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise SolverError('INVALID_INPUT', 'value is not finite bounded JSON') from exc
    if len(raw) > limit:
        raise SolverError('LIMIT_EXCEEDED', 'serialized payload too large')
    return raw

def request(value):
    validate_shape(value)
    if type(value) is not dict or set(value) != {'schema_version', 'request_id', 'algorithm', 'params'}:
        raise SolverError('INVALID_INPUT', 'exact request keys: schema_version, request_id, algorithm, params')
    if type(value['schema_version']) is not int or value['schema_version'] != VERSION:
        raise SolverError('INVALID_INPUT', 'unsupported schema version')
    rid = value['request_id']
    if type(rid) is not str or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', rid):
        raise SolverError('INVALID_INPUT', 'request_id must contain 1-64 portable identifier characters')
    algo = value['algorithm']
    if type(algo) is not str or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', algo):
        raise SolverError('INVALID_INPUT', 'algorithm must be an explicit uppercase identifier')
    if type(value['params']) is not dict:
        raise SolverError('INVALID_INPUT', 'params must be an object')
    return value

def response(req, status, result=None, error=None, quality=None, verification='NOT_CHECKED', meta=None):
    req = req if type(req) is dict else {}
    rid = req.get('request_id')
    algo = req.get('algorithm')
    return {'schema_version': VERSION,
            'request_id': rid if type(rid) is str and len(rid) <= 64 else None,
            'algorithm': algo if type(algo) is str and len(algo) <= 64 else None,
            'status': status, 'result': result if status == 'OK' else None,
            'quality': quality if status == 'OK' else None,
            'verification': verification if status == 'OK' else 'NOT_CHECKED',
            'error': str(error)[:256] if error is not None else None,
            'meta': meta or {}}
