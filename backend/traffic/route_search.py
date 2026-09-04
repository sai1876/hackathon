"""Dijkstra on NetworkX directed-edge states; bounded diverse alternatives."""
from heapq import heappush, heappop
from itertools import count
from math import isfinite
from time import perf_counter
from traffic.turn_costs import turn_cost

def search(graph,start,end,config,penalized=frozenset()):
    counter=count(); initial=(start,None); distances={initial:0}; parents={}; heap=[(0,next(counter),initial)]
    while heap:
        score,_,state=heappop(heap)
        if score!=distances[state]: continue
        node,previous=state
        if node==end:
            result=[]
            while state!=initial:
                before,edge=parents[state]; result.append(edge); state=before
            return list(reversed(result))
        for u,v,k,data in graph.out_edges(node,keys=True,data=True):
            edge=(u,v,k); cost=data['current_cost_sec']
            if not isfinite(cost): continue
            turn,_=turn_cost(graph,previous,edge,config)
            score2=score+cost+turn+(cost*.75 if data.get('external_id',edge) in penalized else 0)
            target=(v,edge)
            if score2<distances.get(target,float('inf')):
                distances[target]=score2; parents[target]=(state,edge); heappush(heap,(score2,next(counter),target))
    raise RuntimeError('No drivable route exists inside the loaded road area.')

def alternatives(graph,start,end,config,limit=3):
    started=perf_counter();paths=[search(graph,start,end,config)]; graph.graph["route_compute_ms"]=(perf_counter()-started)*1000; alternate_start=perf_counter();penalized=set()
    for _ in range(6):
        if len(paths)>=limit: break
        for edge in paths[-1]: penalized.add(graph.edges[edge].get('external_id',edge))
        candidate=search(graph,start,end,config,penalized)
        # A shortest edge-state walk can revisit nodes; never return a looping detour.
        nodes=[start]+[e[1] for e in candidate]
        if len(set(nodes))!=len(nodes): break
        weights={graph.edges[e].get('external_id',e):graph.edges[e]['length_m'] for e in candidate}
        total=sum(weights.values()) or 1
        if any(sum(w for eid,w in weights.items() if eid in {graph.edges[e].get('external_id',e) for e in p})/total>.85 for p in paths):
            for edge in candidate: penalized.add(graph.edges[edge].get('external_id',edge))
            continue
        base_score=lambda p:sum(graph.edges[e]['current_cost_sec']+turn_cost(graph,p[i-1] if i else None,e,config)[0] for i,e in enumerate(p))
        if base_score(candidate)>base_score(paths[0])*2: break
        paths.append(candidate)
    graph.graph["alternatives_ms"]=(perf_counter()-alternate_start)*1000
    return paths
