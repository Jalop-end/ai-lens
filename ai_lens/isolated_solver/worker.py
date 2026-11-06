"""One request per fresh process; only bundled trusted kernels are imported."""
import argparse
import os
from pathlib import Path
import sys

_curr = Path(__file__).resolve()
for p in (_curr.parents[1], _curr.parents[2] if len(_curr.parents) > 2 else _curr.parents[1], _curr.parent):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

from ai_lens.isolated_solver.protocol import (
    MAX_INPUT,
    MAX_OUTPUT,
    SolverError,
    dumps,
    loads,
    request,
    response,
)

def limits(memory_mb, cpu_seconds, required):
    """Linux RLIMIT_AS limits address space, not measured resident memory."""
    capabilities={'address_space_limit':False,'cpu_limit':False,'network_sandbox':False}
    if sys.platform.startswith('linux'):
        import resource
        def lower(kind, requested):
            _,hard=resource.getrlimit(kind)
            if hard!=resource.RLIM_INFINITY:
                requested=min(requested,hard)
            resource.setrlimit(kind,(requested,requested))
            return requested
        try:
            capabilities['address_space_bytes']=lower(resource.RLIMIT_AS,memory_mb*1024*1024)
            capabilities['address_space_limit']=True
            capabilities['cpu_seconds']=lower(resource.RLIMIT_CPU,cpu_seconds)
            capabilities['cpu_limit']=True
        except (OSError,ValueError):
            if required:
                raise SolverError('LIMITS_UNAVAILABLE','requested Linux resource limit could not be installed')
    elif required:
        raise SolverError('LIMITS_UNAVAILABLE','strict resource limits supported here only on Linux')
    return capabilities

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--memory-mb',type=int,required=True)
    parser.add_argument('--cpu-seconds',type=int,required=True)
    parser.add_argument('--require-memory',type=int,choices=[0,1],required=True)
    args=parser.parse_args()
    req=None
    meta={'worker_pid':os.getpid()}
    try:
        meta.update(limits(args.memory_mb,args.cpu_seconds,bool(args.require_memory)))
        req=request(loads(sys.stdin.buffer.read(MAX_INPUT+1)))
        from ai_lens.isolated_solver.kernels import execute
        result,verification=execute(req)
        answer=response(req,'OK',result=result,quality='EXACT',verification=verification,meta=meta)
    except SolverError as exc:
        answer=response(req,exc.status,error=str(exc),meta=meta)
    except MemoryError:
        answer=response(req,'LIMIT_EXCEEDED',error='worker memory budget exhausted',meta=meta)
    except Exception:
        answer=response(req,'INTERNAL_ERROR',error='unexpected trusted-worker error',meta=meta)
    try:
        encoded=dumps(answer,MAX_OUTPUT)
    except (SolverError,MemoryError):
        encoded=dumps(response(req,'OUTPUT_LIMIT_EXCEEDED',error='result cannot fit output policy',meta=meta),MAX_OUTPUT)
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()

if __name__=='__main__':
    main()
