from dataclasses import dataclass
from heapq import heappop, heappush
from .astar import RoadGraph

@dataclass
class Candidate:
    path:list[str]; cost:float

def k_routes(graph:RoadGraph,start:str,goal:str,k:int=3,blocked:set[str]|None=None):
    blocked=blocked or set(); results=[]; seen=set(); candidates=[]; candidate_seen=set()
    base,cost=graph.astar(start,goal,blocked)
    if not base:return []
    results.append(Candidate(base,cost)); seen.add(tuple(base))
    for _ in range(1,k):
        previous=results[-1]
        for i in range(len(previous.path)-1):
            spur=previous.path[i]; root=previous.path[:i+1]
            removed_edges={(item.path[i], item.path[i + 1]) for item in results if len(item.path) > i + 1 and item.path[:i + 1] == root}
            local_block=set(blocked)|set(root[:-1])
            spur_path,spur_cost=graph.astar(spur,goal,local_block,blocked_edges=removed_edges)
            if not spur_path: continue
            candidate_path=root[:-1]+spur_path
            candidate_key=tuple(candidate_path)
            if candidate_key in seen or candidate_key in candidate_seen: continue
            total=sum(_edge_weight(graph,a,b) for a,b in zip(candidate_path,candidate_path[1:]))
            heappush(candidates,(total,candidate_key,candidate_path)); candidate_seen.add(candidate_key)
        if not candidates: break
        cost,path_key,path=heappop(candidates)
        results.append(Candidate(path,cost)); seen.add(path_key)
    return results

def _edge_weight(graph,a,b):
    return next(e.weight for e in graph.adj[a] if e.to==b)
