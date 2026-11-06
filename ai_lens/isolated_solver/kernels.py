"""Five fixed graph operations, integer weights, explicit assumptions and budgets."""
from collections import deque
import heapq
from .protocol import SolverError, integer

ALGORITHMS = frozenset({'BFS', 'DFS', 'DIJKSTRA', 'BELLMAN_FORD', 'TOPOLOGICAL_SORT'})

def graph(params, weighted, source_required, force_directed=False):
    allowed = {'n', 'edges', 'directed'} | ({'source'} if source_required else set())
    if set(params)-allowed or not {'n', 'edges'} <= set(params):
        raise SolverError('INVALID_INPUT', 'missing/unknown graph parameters')
    n = integer(params['n'], 'n', 1, 2000)
    directed = params.get('directed', True)
    if type(directed) is not bool:
        raise SolverError('INVALID_INPUT', 'directed must be boolean')
    if force_directed and not directed:
        raise SolverError('INVALID_INPUT', 'topological order requires a directed graph')
    edges = params['edges']
    if type(edges) is not list:
        raise SolverError('INVALID_INPUT', 'edges must be a list')
    if len(edges) > 10000:
        raise SolverError('LIMIT_EXCEEDED', 'at most 10000 input edges')
    adj = [[] for _ in range(n)]
    expanded = []
    for edge in edges:
        if type(edge) is not list or len(edge) != (3 if weighted else 2):
            raise SolverError('INVALID_INPUT', 'edges must explicitly match weighted/unweighted arity')
        u = integer(edge[0], 'edge source', 0, n-1)
        v = integer(edge[1], 'edge target', 0, n-1)
        w = integer(edge[2], 'edge weight') if weighted else 1
        if abs(w) > 10**12:
            raise SolverError('LIMIT_EXCEEDED', 'edge magnitude exceeds 10^12')
        adj[u].append((v,w))
        expanded.append((u,v,w))
        if not directed:
            adj[v].append((u,w))
            expanded.append((v,u,w))
    source = integer(params.get('source'), 'source', 0, n-1) if source_required else None
    return n, adj, expanded, source

def verify_distances(n, edges, source, dist, parent):
    """Feasible edge inequalities plus a tight rooted predecessor tree certificate."""
    if dist[source] != 0 or parent[source] is not None:
        return False
    tight = set()
    for u,v,w in edges:
        if dist[u] is not None:
            if dist[v] is None or dist[v] > dist[u]+w:
                return False
            if dist[v] == dist[u]+w:
                tight.add((u,v))
    rooted = {source}
    for v in range(n):
        if dist[v] is None:
            if parent[v] is not None:
                return False
            continue
        trail = set()
        curr = v
        while curr not in rooted:
            if curr in trail or parent[curr] is None or (parent[curr],curr) not in tight:
                return False
            trail.add(curr)
            curr = parent[curr]
        rooted.update(trail)
    return True

def shortest(name, params):
    weighted = name != 'BFS'
    n, adj, edges, source = graph(params, weighted, True)
    if name == 'DIJKSTRA' and any(w < 0 for _,_,w in edges):
        raise SolverError('INVALID_INPUT', 'Dijkstra requires all weights nonnegative; use BELLMAN_FORD')
    if name == 'BELLMAN_FORD' and n*len(edges) > 2000000:
        raise SolverError('LIMIT_EXCEEDED', 'Bellman-Ford exceeds two million relaxations budget')
    dist, parent = [None]*n, [None]*n
    dist[source] = 0
    if name == 'BFS':
        queue = deque([source])
        while queue:
            u = queue.popleft()
            for v,_ in adj[u]:
                if dist[v] is None:
                    dist[v], parent[v] = dist[u]+1, u
                    queue.append(v)
    elif name == 'DIJKSTRA':
        heap = [(0,source)]
        while heap:
            current,u = heapq.heappop(heap)
            if dist[u] != current:
                continue
            for v,w in adj[u]:
                cand = current+w
                if dist[v] is None or cand < dist[v]:
                    dist[v], parent[v] = cand,u
                    heapq.heappush(heap,(cand,v))
    else:
        for _ in range(n-1):
            changed = False
            for u,v,w in edges:
                if dist[u] is not None:
                    candidate = dist[u]+w
                    if dist[v] is None or candidate < dist[v]:
                        dist[v], parent[v] = candidate,u
                        changed = True
            if not changed:
                break
        if any(dist[u] is not None and (dist[v] is None or dist[v] > dist[u]+w)
               for u,v,w in edges):
            raise SolverError('NEGATIVE_CYCLE', 'negative cycle is reachable from the requested source')
    if not verify_distances(n,edges,source,dist,parent):
        raise SolverError('INTERNAL_ERROR', 'shortest-path certificate check failed')
    return {'distances':dist, 'parents':parent, 'source':source,
            'unreachable':None}, 'CERTIFICATE_CHECKED'

def dfs(params):
    n,adj,edges,source = graph(params,False,True)
    seen = {source}
    parents = [None]*n
    order, finish = [source], []
    stack = [(source,iter(adj[source]))]
    while stack:
        u,it = stack[-1]
        try:
            v,_ = next(it)
        except StopIteration:
            finish.append(u)
            stack.pop()
            continue
        if v not in seen:
            seen.add(v)
            parents[v] = u
            order.append(v)
            stack.append((v,iter(adj[v])))
    positions = {v:i for i,v in enumerate(order)}
    edge_set = {(u,v) for u,v,_ in edges}
    checked = (len(order)==len(set(order))==len(finish) and set(order)==set(finish)
               and all(v in seen for u,v,_ in edges if u in seen)
               and all(v==source or (parents[v],v) in edge_set
                       and positions[parents[v]]<positions[v] for v in order))
    if not checked:
        raise SolverError('INTERNAL_ERROR','DFS structural check failed')
    return {'discovery_order':order,'finish_order':finish,'parents':parents,'source':source}, 'INVARIANTS_CHECKED'

def topological(params):
    n,adj,edges,_ = graph(params,False,False,True)
    indegree=[0]*n
    for _,v,_ in edges:
        indegree[v]+=1
    heap=[v for v in range(n) if indegree[v]==0]
    heapq.heapify(heap)
    order=[]
    while heap:
        u=heapq.heappop(heap)
        order.append(u)
        for v,_ in adj[u]:
            indegree[v]-=1
            if indegree[v]==0:
                heapq.heappush(heap,v)
    if len(order)!=n:
        raise SolverError('CYCLE_DETECTED','graph contains a directed cycle; no topological ordering')
    rank={v:i for i,v in enumerate(order)}
    if len(rank)!=n or any(rank[u]>=rank[v] for u,v,_ in edges):
        raise SolverError('INTERNAL_ERROR','topological certificate check failed')
    return {'order':order}, 'CERTIFICATE_CHECKED'

def execute(req):
    name=req['algorithm']
    if name not in ALGORITHMS:
        raise SolverError('UNSUPPORTED_ALGORITHM', 'operation is not in the fixed registry')
    params=req['params']
    if name in {'BFS','DIJKSTRA','BELLMAN_FORD'}:
        return shortest(name,params)
    if name=='DFS':
        return dfs(params)
    return topological(params)
