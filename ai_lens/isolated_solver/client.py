"""Parent controller. Call solve off the GUI thread, or use SolverService.submit."""
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from .protocol import (MAX_INPUT, MAX_OUTPUT, STATUSES, SolverError, dumps, loads,
                       request, response)

@dataclass(frozen=True)
class Limits:
    wall_seconds: float=3.0
    memory_mb: int=256
    cpu_seconds: int=2
    require_memory: bool=True
    output_bytes: int=MAX_OUTPUT
    def __post_init__(self):
        if type(self.wall_seconds) not in (int,float) or not math.isfinite(self.wall_seconds) or not 0.05<=self.wall_seconds<=60:
            raise ValueError('wall_seconds must be finite and in [0.05,60]')
        for key,low,high in [('memory_mb',64,4096),('cpu_seconds',1,60),('output_bytes',1024,MAX_OUTPUT)]:
            value=getattr(self,key)
            if type(value) is not int or not low<=value<=high:
                raise ValueError(f'{key} must be an integer in [{low},{high}]')
        if type(self.require_memory) is not bool:
            raise ValueError('require_memory must be boolean')

def _environment():
    # Avoid forwarding model/API credentials. This is not a filesystem/network sandbox.
    keep=('SYSTEMROOT','WINDIR','TEMP','TMP','LANG','LC_ALL','LD_LIBRARY_PATH','PATH')
    env={key:os.environ[key] for key in keep if key in os.environ}
    env['PYTHONIOENCODING']='utf-8'
    return env

def _run_command(command, payload, req, policy, cancel_event):
    """Private trusted-command runner; never accepts commands in the public JSON API."""
    start=time.monotonic()
    process=None
    reader=None
    feeder=None
    overflow=threading.Event()
    chunks=[]
    try:
        if cancel_event is not None and cancel_event.is_set():
            return response(req,'CANCELLED',error='cancelled before process launch')
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                 cwd=None,env=_environment(),shell=False,close_fds=(sys.platform!='win32'))
        def feed():
            try:
                if process.stdin is not None:
                    process.stdin.write(payload)
                    process.stdin.flush()
                    process.stdin.close()
            except (OSError,ValueError):
                pass
        feeder=threading.Thread(target=feed,name='solver-stdin-feeder',daemon=True)
        feeder.start()
        def drain():
            used=0
            try:
                while True:
                    part=process.stdout.read(min(8192,policy.output_bytes+1-used))
                    if not part:
                        return
                    used+=len(part)
                    chunks.append(part)
                    if used>policy.output_bytes:
                        overflow.set()
                        return
            except (OSError,ValueError):
                overflow.set()
        reader=threading.Thread(target=drain,name='solver-bounded-output',daemon=True)
        reader.start()
        status=None
        while True:
            if cancel_event is not None and cancel_event.is_set():
                status='CANCELLED'
                break
            if overflow.is_set():
                status='OUTPUT_LIMIT_EXCEEDED'
                break
            if time.monotonic()-start>=policy.wall_seconds:
                status='TIMEOUT'
                break
            if process.poll() is not None:
                break
            time.sleep(0.005)
        if status is not None and process.poll() is None:
            process.kill()
        process.wait()
        reader.join(timeout=1)
        if feeder is not None:
            feeder.join(timeout=1)
        if reader.is_alive():
            return response(req,'WORKER_CRASH',error='worker output stream failed to close')
        meta={'worker_pid':process.pid,'returncode':process.returncode,
              'elapsed_seconds':round(time.monotonic()-start,6),'reaped':True}
        if overflow.is_set():
            status='OUTPUT_LIMIT_EXCEEDED'
        if status is not None:
            return response(req,status,error=status,meta=meta)
        if process.returncode!=0:
            # A signal alone does not identify memory exhaustion reliably.
            return response(req,'WORKER_CRASH',error='worker exited abnormally',meta=meta)
        try:
            answer=loads(b''.join(chunks),policy.output_bytes)
            expected={'schema_version','request_id','algorithm','status','result','quality','verification','error','meta'}
            if type(answer) is not dict or set(answer)!=expected or type(answer['schema_version']) is not int or answer['schema_version']!=1:
                raise SolverError('PROTOCOL_ERROR','unexpected response shape')
            if answer['request_id']!=req['request_id'] or answer['algorithm']!=req['algorithm'] or answer['status'] not in STATUSES:
                raise SolverError('PROTOCOL_ERROR','worker correlation/status mismatch')
            if type(answer['meta']) is not dict:
                raise SolverError('PROTOCOL_ERROR','worker meta must be an object')
            if answer['status']=='OK':
                if answer['quality']!='EXACT' or answer['verification'] not in {'CERTIFICATE_CHECKED','INVARIANTS_CHECKED'} or type(answer['result']) is not dict:
                    raise SolverError('PROTOCOL_ERROR','unexpected successful-result contract')
            elif answer['result'] is not None or answer['quality'] is not None or answer['verification']!='NOT_CHECKED':
                raise SolverError('PROTOCOL_ERROR','error response must not expose an answer')
            answer['meta'].update(meta)
            return answer
        except (SolverError,TypeError,KeyError,ValueError):
            return response(req,'PROTOCOL_ERROR',error='invalid or mismatched worker reply',meta=meta)
    except OSError:
        return response(req,'WORKER_CRASH',error='worker could not be started or controlled')
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout is not None:
                try:
                    process.stdout.close()
                except Exception:
                    pass
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except Exception:
                    pass
        if feeder is not None:
            feeder.join(timeout=1)
        if reader is not None:
            reader.join(timeout=1)

def solve(value, limits=None, cancel_event=None):
    policy=limits if limits is not None else Limits()
    if not isinstance(policy,Limits):
        raise TypeError('limits must be a Limits instance')
    req=value
    try:
        req=request(value)
        # Serialize a snapshot; subsequent caller mutations cannot change the worker input.
        payload=dumps(req,MAX_INPUT)
        req=request(loads(payload))
    except SolverError as exc:
        return response(value,exc.status,error=str(exc))
    if cancel_event is not None and cancel_event.is_set():
        return response(req,'CANCELLED',error='cancelled before process launch')
    if policy.require_memory and not sys.platform.startswith('linux'):
        return response(req,'LIMITS_UNAVAILABLE',error='strict memory backend is implemented only for Linux')
    worker=Path(__file__).with_name('worker.py').resolve()
    command=[sys.executable,'-I','-B',str(worker),'--memory-mb',str(policy.memory_mb),
             '--cpu-seconds',str(policy.cpu_seconds),'--require-memory',str(int(policy.require_memory))]
    return _run_command(command,payload,req,policy,cancel_event)

@dataclass
class Job:
    future: Future
    cancel_event: threading.Event
    def cancel(self):
        # Cooperative at the parent; the parent kills/reaps any active worker.
        self.cancel_event.set()

class SolverService:
    """Bounded admission; completion runs outside Qt GUI thread. No Qt dependency."""
    def __init__(self,max_workers=2,max_pending=4,limits=None):
        if type(max_workers) is not int or type(max_pending) is not int or not 1<=max_workers<=4 or not max_workers<=max_pending<=16:
            raise ValueError('require 1<=workers<=4 and workers<=pending<=16')
        self.limits=limits if limits is not None else Limits()
        if not isinstance(self.limits,Limits):
            raise TypeError('limits must be a Limits instance')
        self._pool=ThreadPoolExecutor(max_workers=max_workers,thread_name_prefix='solver-p1')
        self._lock=threading.Lock()
        self._closed=False
        self._events=set()
        self._max_pending=max_pending
    def submit(self,value):
        event=threading.Event()
        try:
            snapshot=request(loads(dumps(request(value))))
        except SolverError as exc:
            f=Future();f.set_result(response(value,exc.status,error=str(exc)))
            return Job(f,event)
        with self._lock:
            if self._closed or len(self._events)>=self._max_pending:
                status='CLOSED' if self._closed else 'BUSY'
                f=Future();f.set_result(response(snapshot,status,error=status))
                return Job(f,event)
            self._events.add(event)
            future=self._pool.submit(solve,snapshot,self.limits,event)
        def completed(_):
            with self._lock:
                self._events.discard(event)
        future.add_done_callback(completed)
        return Job(future,event)
    def close(self,wait=True):
        with self._lock:
            self._closed=True
            for event in self._events:
                event.set()
        self._pool.shutdown(wait=wait,cancel_futures=False)
    def __enter__(self):
        return self
    def __exit__(self,*_):
        self.close()
