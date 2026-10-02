from dataclasses import dataclass
from .astar import RoadGraph

@dataclass
class Candidate:
    path:list[str]; cost:float

def k_routes(graph:RoadGraph,start:str,goal:str,k:int=3,blocked:set[str]|None=None):
    blocked=blocked or set(); results=[]; seen=set()
    base,cost=graph.astar(start,goal,blocked)
    if not base:return []
    results.append(Candidate(base,cost)); seen.add(tuple(base))
    for _ in range(1,k):
        best=None
        for prev in results:
            for i in range(len(prev.path)-1):
                spur=prev.path[i]; root=prev.path[:i+1]
                local_block=set(blocked)|set(root[:-1])
                # bounded perturbation creates diverse candidates without exponential path enumeration
                p,c=graph.astar(spur,goal,local_block,penalty=0.35+0.15*i)
                if not p: continue
                candidate=root[:-1]+p
                if tuple(candidate) in seen: continue
                total=sum(_edge_weight(graph,a,b) for a,b in zip(candidate,candidate[1:]))
                item=Candidate(candidate,total)
                if best is None or item.cost<best.cost: best=item
        if not best: break
        results.append(best); seen.add(tuple(best.path))
    return results

def _edge_weight(graph,a,b):
    return next(e.weight for e in graph.adj[a] if e.to==b)
