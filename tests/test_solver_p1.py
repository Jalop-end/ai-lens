"""Run: python tests/test_solver_p1.py --out results/new-run
Constructed deterministic tests, not production data or a performance benchmark.
"""
import argparse
import csv
from concurrent.futures import Future
import itertools
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ai_lens.isolated_solver import Limits, SolverService, solve, LatestOnly
from ai_lens.isolated_solver.client import _run_command
from ai_lens.isolated_solver.kernels import execute, verify_distances
from ai_lens.isolated_solver.protocol import SolverError, dumps, loads, request, response

COUNTS={}
CAPABILITIES={}

def solve_for_host(value, limits=None, cancel_event=None):
    if limits is None:
        limits = Limits(require_memory=sys.platform.startswith('linux'))
    return solve(value, limits=limits, cancel_event=cancel_event)

def req(algorithm='DIJKSTRA',params=None,rid='test-1'):
    return {'schema_version':1,'request_id':rid,'algorithm':algorithm,
            'params':params if params is not None else {'n':3,'edges':[[0,1,2],[1,2,3]],'source':0}}

def error_status(value):
    try:
        execute(request(value))
    except SolverError as exc:
        return exc.status
    return 'OK'

def path_reference(n,edges,source):
    adj=[[] for _ in range(n)]
    for u,v,w in edges:
        adj[u].append((v,w))
    dist=[None]*n
    def visit(u,total,seen):
        if dist[u] is None or total<dist[u]:
            dist[u]=total
        for v,w in adj[u]:
            if v not in seen:
                visit(v,total+w,seen|{v})
    visit(source,0,{source})
    return dist

def has_reachable_negative_cycle(n,edges,source):
    reachable={source}
    for _ in range(n):
        reachable|={v for u,v,w in edges if u in reachable}
    adj=[[] for _ in range(n)]
    for u,v,w in edges:
        adj[u].append((v,w))
    def cycle(start,u,total,seen):
        for v,w in adj[u]:
            if v==start and total+w<0:
                return True
            if v not in seen and cycle(start,v,total+w,seen|{v}):
                return True
        return False
    return any(cycle(start,start,0,{start}) for start in reachable)

class ProtocolTests(unittest.TestCase):
    def test_duplicate_keys(self):
        with self.assertRaises(SolverError):
            loads(b'{"a":1,"a":2}')
    def test_nonfinite(self):
        for raw in [b'[NaN]',b'[Infinity]',b'[-Infinity]']:
            with self.assertRaises(SolverError):loads(raw)
    def test_exponent_overflow_rejected(self):
        with self.assertRaises(SolverError):loads(b'[1e999]')
    def test_nesting(self):
        with self.assertRaises(SolverError) as e:loads(b'['*20+b'0'+b']'*20)
        self.assertEqual(e.exception.status,'LIMIT_EXCEEDED')
    def test_brackets_in_string(self):
        self.assertEqual(loads(b'{"x":"[[[[[[[[[[[[[[[[[[[[[[["}')['x'],'['*23)
    def test_payload_limit(self):
        with self.assertRaises(SolverError):loads(b' '*65537)
    def test_schema_version_bool(self):
        r=req();r['schema_version']=True
        self.assertEqual(solve_for_host(r)['status'],'INVALID_INPUT')
    def test_wrong_version(self):
        r=req();r['schema_version']=2
        self.assertEqual(solve_for_host(r)['status'],'INVALID_INPUT')
    def test_unknown_top_key(self):
        r=req();r['ignore_limits']=True
        self.assertEqual(solve_for_host(r)['status'],'INVALID_INPUT')
    def test_bad_identifier(self):
        self.assertEqual(solve_for_host(req(rid='bad\nname'))['status'],'INVALID_INPUT')
    def test_unknown_op(self):
        self.assertEqual(solve_for_host(req('RUN_PYTHON'))['status'],'UNSUPPORTED_ALGORITHM')
    def test_bool_weight(self):
        self.assertEqual(error_status(req(params={'n':2,'edges':[[0,1,True]],'source':0})),'INVALID_INPUT')
    def test_float_weight(self):
        self.assertEqual(error_status(req(params={'n':2,'edges':[[0,1,1.5]],'source':0})),'INVALID_INPUT')
    def test_bad_endpoint(self):
        self.assertNotEqual(error_status(req(params={'n':2,'edges':[[0,2,1]],'source':0})),'OK')
    def test_node_limit(self):
        self.assertEqual(error_status(req(params={'n':2001,'edges':[],'source':0})),'LIMIT_EXCEEDED')
    def test_invalid_source(self):
        self.assertNotEqual(error_status(req(params={'n':2,'edges':[],'source':2})),'OK')
    def test_unknown_param(self):
        self.assertEqual(error_status(req(params={'n':2,'edges':[],'source':0,'timeout':1000})),'INVALID_INPUT')
    def test_invalid_limits(self):
        for kw in [{'wall_seconds':True},{'wall_seconds':float('nan')},{'memory_mb':32},{'cpu_seconds':0},{'require_memory':1}]:
            with self.assertRaises(ValueError):Limits(**kw)
    def test_pure_json_no_expression(self):
        with self.assertRaises(SolverError):loads(b'__import__("os")')

class GraphCases(unittest.TestCase):
    def test_bfs_disconnected(self):
        result,_=execute(req('BFS',{'n':4,'edges':[[0,1],[1,2]],'source':0}))
        self.assertEqual(result['distances'],[0,1,2,None])
    def test_dijkstra_negative_rejected(self):
        self.assertEqual(error_status(req(params={'n':2,'edges':[[0,1,-1]],'source':0})),'INVALID_INPUT')
    def test_bellman_negative_valid(self):
        result,_=execute(req('BELLMAN_FORD',{'n':3,'edges':[[0,1,4],[0,2,8],[1,2,-2]],'source':0}))
        self.assertEqual(result['distances'],[0,4,2])
    def test_reachable_negative_cycle(self):
        self.assertEqual(error_status(req('BELLMAN_FORD',{'n':2,'edges':[[0,1,0],[1,1,-1]],'source':0})),'NEGATIVE_CYCLE')
    def test_unreachable_negative_cycle_ignored(self):
        result,_=execute(req('BELLMAN_FORD',{'n':3,'edges':[[1,2,-2],[2,1,1]],'source':0}))
        self.assertEqual(result['distances'],[0,None,None])
    def test_undirected_negative_cycle(self):
        self.assertEqual(error_status(req('BELLMAN_FORD',{'n':2,'edges':[[0,1,-1]],'source':0,'directed':False})),'NEGATIVE_CYCLE')
    def test_weighted_parallel(self):
        result,_=execute(req(params={'n':2,'edges':[[0,1,9],[0,1,2]],'source':0}))
        self.assertEqual(result['distances'],[0,2])
    def test_zero_cycle_certificate(self):
        result,_=execute(req(params={'n':3,'edges':[[0,1,0],[1,0,0],[1,2,0]],'source':0}))
        self.assertEqual(result['distances'],[0,0,0])
    def test_integer_sum(self):
        result,_=execute(req(params={'n':3,'edges':[[0,1,10**12],[1,2,10**12]],'source':0}))
        self.assertEqual(result['distances'][2],2*10**12)
    def test_undirected_bfs(self):
        result,_=execute(req('BFS',{'n':3,'edges':[[0,1],[1,2]],'directed':False,'source':2}))
        self.assertEqual(result['distances'],[2,1,0])
    def test_dfs_not_shortest_path(self):
        result,_=execute(req('DFS',{'n':4,'edges':[[0,1],[1,2],[0,2]],'source':0}))
        self.assertEqual(result['discovery_order'],[0,1,2])
        self.assertEqual(result['finish_order'],[2,1,0])
        self.assertNotIn('distances',result)
    def test_topological_order(self):
        result,_=execute(req('TOPOLOGICAL_SORT',{'n':4,'edges':[[0,2],[1,2],[2,3]]}))
        self.assertEqual(result['order'],[0,1,2,3])
    def test_topological_cycle(self):
        self.assertEqual(error_status(req('TOPOLOGICAL_SORT',{'n':2,'edges':[[0,1],[1,0]]})),'CYCLE_DETECTED')
    def test_topological_self_loop(self):
        self.assertEqual(error_status(req('TOPOLOGICAL_SORT',{'n':1,'edges':[[0,0]]})),'CYCLE_DETECTED')
    def test_topological_undirected(self):
        self.assertEqual(error_status(req('TOPOLOGICAL_SORT',{'n':2,'edges':[],'directed':False})),'INVALID_INPUT')
    def test_bellman_budget(self):
        self.assertEqual(error_status(req('BELLMAN_FORD',{'n':2000,'edges':[[0,1,1]]*1001,'source':0})),'LIMIT_EXCEEDED')
    def test_false_certificate_rejected(self):
        self.assertFalse(verify_distances(3,[(0,1,1),(1,2,1)],0,[0,1,5],[None,0,1]))
    def test_cyclic_parents_rejected(self):
        self.assertFalse(verify_distances(3,[(0,1,0),(1,2,0),(2,1,0)],0,[0,0,0],[None,2,1]))

class ProcessTests(unittest.TestCase):
    def test_boolean_response_version_rejected(self):
        answer=response(req(),'OK',result={},quality='EXACT',verification='CERTIFICATE_CHECKED')
        answer['schema_version']=True
        self.assertEqual(self.fixture(f'print({json.dumps(answer)!r})')['status'],'PROTOCOL_ERROR')
    def test_real_worker_and_limits(self):
        answer=solve_for_host(req())
        self.assertEqual(answer['status'],'OK',answer)
        self.assertEqual(answer['result']['distances'],[0,2,5])
        self.assertNotEqual(answer['meta']['worker_pid'],os.getpid())
        self.assertTrue(answer['meta']['reaped'])
        self.assertEqual(answer['meta']['address_space_limit'],sys.platform.startswith('linux'))
        self.assertEqual(answer['meta']['cpu_limit'],sys.platform.startswith('linux'))
        CAPABILITIES.update(answer['meta'])
    def test_error_has_no_result(self):
        answer=solve_for_host(req('BELLMAN_FORD',{'n':2,'edges':[[0,1,-1],[1,0,0]],'source':0}))
        self.assertEqual(answer['status'],'NEGATIVE_CYCLE')
        self.assertIsNone(answer['result'])
        self.assertIsNone(answer['quality'])
    def test_no_stale_result(self):
        good=solve_for_host(req(rid='success'))
        bad=solve_for_host(req('DIJKSTRA',{'n':2,'edges':[[0,1,-1]],'source':0},rid='failure'))
        self.assertEqual(good['status'],'OK')
        self.assertEqual(bad['status'],'INVALID_INPUT')
        self.assertEqual(bad['request_id'],'failure')
        self.assertIsNone(bad['result'])
    def test_cancel_before_launch(self):
        event=threading.Event();event.set()
        self.assertEqual(solve_for_host(req(),cancel_event=event)['status'],'CANCELLED')
    def fixture(self,code,policy=None,cancel=None):
        with tempfile.TemporaryDirectory() as folder:
            f=Path(folder)/'fixture.py';f.write_text(code)
            return _run_command([sys.executable,'-I','-B',str(f)],b'{}',req(),policy or Limits(),cancel)
    def test_wall_timeout(self):
        answer=self.fixture('import time\ntime.sleep(30)',Limits(wall_seconds=0.15))
        self.assertEqual(answer['status'],'TIMEOUT')
        self.assertTrue(answer['meta']['reaped'])
        self.assertNotEqual(answer['meta']['returncode'],0)
    def test_active_cancel(self):
        event=threading.Event()
        timer=threading.Timer(0.1,event.set);timer.start()
        try:
            answer=self.fixture('import time\ntime.sleep(30)',cancel=event)
            self.assertEqual(answer['status'],'CANCELLED')
            self.assertTrue(answer['meta']['reaped'])
        finally:timer.cancel()
    def test_output_flood(self):
        code='import os\nwhile True: os.write(1,b"x"*8192)'
        answer=self.fixture(code,Limits(output_bytes=1024,wall_seconds=1))
        self.assertEqual(answer['status'],'OUTPUT_LIMIT_EXCEEDED')
        self.assertTrue(answer['meta']['reaped'])
    def test_worker_crash(self):
        answer=self.fixture('import os\nos._exit(7)')
        self.assertEqual(answer['status'],'WORKER_CRASH')
        self.assertEqual(answer['meta']['returncode'],7)
    def test_malformed_worker_json(self):
        self.assertEqual(self.fixture('print("not-json")')['status'],'PROTOCOL_ERROR')
    def test_correlation_mismatch(self):
        answer=response(req(rid='wrong'),'OK',result={},quality='EXACT',verification='CERTIFICATE_CHECKED')
        self.assertEqual(self.fixture(f'print({json.dumps(answer)!r})')['status'],'PROTOCOL_ERROR')
    @unittest.skipUnless(sys.platform.startswith('linux'), 'requires Linux RLIMIT_CPU')
    def test_cpu_kill(self):
        code='import resource\nresource.setrlimit(resource.RLIMIT_CPU,(1,1))\nwhile True: pass'
        answer=self.fixture(code,Limits(wall_seconds=4))
        self.assertEqual(answer['status'],'WORKER_CRASH')
        self.assertLess(answer['meta']['returncode'],0)
    @unittest.skipUnless(sys.platform.startswith('linux'), 'requires Linux RLIMIT_AS')
    def test_address_space_exhaustion(self):
        template=response(req(),'LIMIT_EXCEEDED',error='allocation refused',meta={'memory_refused':True})
        code=('import resource\nresource.setrlimit(resource.RLIMIT_AS,(64*1024*1024,64*1024*1024))\n'
              'try:\n    x=bytearray(200*1024*1024)\nexcept MemoryError:\n'
              f'    print({json.dumps(template)!r})\nelse:\n    raise RuntimeError("limit not enforced")')
        answer=self.fixture(code)
        self.assertEqual(answer['status'],'LIMIT_EXCEEDED')
        self.assertTrue(answer['meta']['memory_refused'])
    def test_no_environment_secret(self):
        old=os.environ.get('SOLVER_TEST_SECRET')
        os.environ['SOLVER_TEST_SECRET']='must-not-be-forwarded'
        answer=response(req(),'OK',result={'leaked':False},quality='EXACT',verification='CERTIFICATE_CHECKED')
        code='import json,os\na='+repr(answer)+'\na["result"]["leaked"]="SOLVER_TEST_SECRET" in os.environ\nprint(json.dumps(a))'
        try:self.assertFalse(self.fixture(code)['result']['leaked'])
        finally:
            if old is None:os.environ.pop('SOLVER_TEST_SECRET',None)
            else:os.environ['SOLVER_TEST_SECRET']=old
    def test_nonlinux_fail_closed(self):
        with patch('ai_lens.isolated_solver.client.sys.platform','win32'):
            self.assertEqual(solve(req())['status'],'LIMITS_UNAVAILABLE')
    def test_service_real_concurrent(self):
        with SolverService() as service:
            jobs=[service.submit(req(rid=f'job-{i}')) for i in range(4)]
            answers=[j.future.result(timeout=10) for j in jobs]
        self.assertTrue(all(a['status']=='OK' for a in answers))
        self.assertEqual({a['request_id'] for a in answers},{f'job-{i}' for i in range(4)})
    def test_service_bounded(self):
        entered=threading.Event();release=threading.Event()
        def blocked(value,policy,event):
            entered.set();release.wait(2)
            return response(value,'CANCELLED')
        with patch('isolated_solver.client.solve',side_effect=blocked):
            service=SolverService(max_workers=1,max_pending=1)
            first=service.submit(req())
            self.assertTrue(entered.wait(1))
            try:self.assertEqual(service.submit(req(rid='second')).future.result()['status'],'BUSY')
            finally:release.set();service.close()
    def test_service_cancel_and_close(self):
        service=SolverService(max_workers=1)
        service.close()
        self.assertEqual(service.submit(req()).future.result()['status'],'CLOSED')
    def test_snapshot_immutable_to_caller(self):
        entered=threading.Event();release=threading.Event()
        def blocked(value,policy,event):
            entered.set();release.wait(2)
            return response(value,'OK',result={'n':value['params']['n']},quality='EXACT')
        with patch('isolated_solver.client.solve',side_effect=blocked):
            service=SolverService(max_workers=1)
            value=req();job=service.submit(value)
            self.assertTrue(entered.wait(1));value['params']['n']=100
            release.set()
            try:self.assertEqual(job.future.result(timeout=2)['result']['n'],3)
            finally:service.close()

class HandoffTests(unittest.TestCase):
    def test_old_success_cannot_replace_new_failure(self):
        gate=LatestOnly()
        old=gate.select('old')
        current=gate.select('new')
        self.assertFalse(gate.accepts(old,response(req(rid='old'),'OK',result={'answer':42})))
        self.assertTrue(gate.accepts(current,response(req(rid='new'),'INVALID_INPUT')))
    def test_request_id_must_match(self):
        gate=LatestOnly();ticket=gate.select('a')
        self.assertFalse(gate.accepts(ticket,response(req(rid='b'),'OK')))
    def test_reused_id_still_has_new_generation(self):
        gate=LatestOnly();first=gate.select('same');second=gate.select('same')
        self.assertFalse(gate.accepts(first,response(req(rid='same'),'OK')))
        self.assertTrue(gate.accepts(second,response(req(rid='same'),'OK')))
    def test_invalidation(self):
        gate=LatestOnly();ticket=gate.select('a');gate.invalidate()
        self.assertFalse(gate.accepts(ticket,response(req(rid='a'),'OK')))

class ReferenceTests(unittest.TestCase):
    def test_bfs_exhaustive(self):
        n=4;possible=[(u,v) for u in range(n) for v in range(n) if u!=v];count=0
        for mask in range(1<<len(possible)):
            edges=[e for i,e in enumerate(possible) if mask>>i&1]
            for source in range(n):
                result,_=execute(req('BFS',{'n':n,'edges':[list(e) for e in edges],'source':source}))
                self.assertEqual(result['distances'],path_reference(n,[(u,v,1) for u,v in edges],source))
                count+=1
        COUNTS['BFS_vs_simple_paths']=count
    def test_dijkstra_exhaustive(self):
        n=3;possible=[(u,v) for u in range(n) for v in range(n) if u!=v];count=0
        for ws in itertools.product([None,0,2],repeat=len(possible)):
            edges=[(u,v,w) for (u,v),w in zip(possible,ws) if w is not None]
            for source in range(n):
                result,_=execute(req('DIJKSTRA',{'n':n,'edges':[list(e) for e in edges],'source':source}))
                self.assertEqual(result['distances'],path_reference(n,edges,source));count+=1
        COUNTS['Dijkstra_vs_simple_paths']=count
    def test_bellman_exhaustive(self):
        n=3;possible=[(u,v) for u in range(n) for v in range(n) if u!=v];count=0
        for ws in itertools.product([None,-1,2],repeat=len(possible)):
            edges=[(u,v,w) for (u,v),w in zip(possible,ws) if w is not None]
            for source in range(n):
                r=req('BELLMAN_FORD',{'n':n,'edges':[list(e) for e in edges],'source':source})
                negative=has_reachable_negative_cycle(n,edges,source)
                if negative:self.assertEqual(error_status(r),'NEGATIVE_CYCLE')
                else:
                    result,_=execute(r)
                    self.assertEqual(result['distances'],path_reference(n,edges,source))
                count+=1
        COUNTS['Bellman_Ford_vs_paths_and_cycles']=count
    def test_dfs_exhaustive(self):
        n=3;possible=list(itertools.product(range(n),repeat=2));count=0
        for mask in range(1<<len(possible)):
            edges=[e for i,e in enumerate(possible) if mask>>i&1]
            adj=[[] for _ in range(n)]
            for u,v in edges:adj[u].append(v)
            for source in range(n):
                seen=set();order=[];finish=[];parents=[None]*n
                def walk(u):
                    seen.add(u);order.append(u)
                    for v in adj[u]:
                        if v not in seen:parents[v]=u;walk(v)
                    finish.append(u)
                walk(source)
                result,_=execute(req('DFS',{'n':n,'edges':[list(e) for e in edges],'source':source}))
                self.assertEqual((result['discovery_order'],result['finish_order'],result['parents']),(order,finish,parents));count+=1
        COUNTS['DFS_vs_recursive_reference']=count
    def test_topological_exhaustive(self):
        n=4;possible=[(u,v) for u in range(n) for v in range(n) if u!=v];count=0
        permutations=list(itertools.permutations(range(n)))
        for mask in range(1<<len(possible)):
            edges=[e for i,e in enumerate(possible) if mask>>i&1]
            valid=[]
            for order in permutations:
                rank={v:i for i,v in enumerate(order)}
                if all(rank[u]<rank[v] for u,v in edges):valid.append(list(order))
            r=req('TOPOLOGICAL_SORT',{'n':n,'edges':[list(e) for e in edges]})
            if valid:self.assertIn(execute(r)[0]['order'],valid)
            else:self.assertEqual(error_status(r),'CYCLE_DETECTED')
            count+=1
        COUNTS['topological_vs_all_permutations']=count

class TrackingResult(unittest.TextTestResult):
    def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
    def addSuccess(self,test):self.rows.append({'test':test.id(),'status':'PASS','detail':''});super().addSuccess(test)
    def addFailure(self,test,err):self.rows.append({'test':test.id(),'status':'FAIL','detail':str(err[1])});super().addFailure(test,err)
    def addError(self,test,err):self.rows.append({'test':test.id(),'status':'ERROR','detail':str(err[1])});super().addError(test,err)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in [ProtocolTests,GraphCases,ProcessTests,HandoffTests,ReferenceTests])
    with (args.out/'test-log.txt').open('w') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=TrackingResult).run(suite)
    report={'python':platform.python_version(),'platform':platform.platform(),'test_functions':result.testsRun,
            'passed':sum(r['status']=='PASS' for r in result.rows),'failures':len(result.failures),'errors':len(result.errors),
            'reference_comparisons':COUNTS,'worker_capability_observation':CAPABILITIES,
            'scope':'Standalone candidate on Linux; no GUI/OCR/VLM, no P0 regression rerun, no security sandbox certification',
            'tests':result.rows}
    (args.out/'test-results.json').write_text(json.dumps(report,indent=2))
    with (args.out/'test-results.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['test','status','detail']);writer.writeheader();writer.writerows(result.rows)
    print(json.dumps({k:v for k,v in report.items() if k!='tests'},indent=2))
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
