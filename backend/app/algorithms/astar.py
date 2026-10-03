from dataclasses import dataclass
from heapq import heappush, heappop
from math import hypot

@dataclass(frozen=True)
class Edge:
    to: str
    weight: float
    risk: float = 0.0

class RoadGraph:
    def __init__(self):
        self.adj: dict[str, list[Edge]] = {}
        self.pos: dict[str, tuple[float,float]] = {}
    def add_node(self, node, lat, lon):
        self.pos[node] = (lat, lon); self.adj.setdefault(node, [])
    def add_edge(self, a, b, weight, risk=0.0):
        self.adj.setdefault(a, []).append(Edge(b, weight, risk))
        self.adj.setdefault(b, []).append(Edge(a, weight, risk))
    def heuristic(self, a, b):
        # Edge weights are arbitrary operational costs (not meters), so a
        # geographic-distance heuristic cannot be proven admissible. Returning
        # zero preserves optimality while the real-road production path uses a
        # routing provider rather than this demo graph.
        return 0.0
    def astar(self, start, goal, blocked=None, penalty=0.0, blocked_edges=None):
        blocked = blocked or set()
        blocked_edges = blocked_edges or set()
        pq=[(0.0,start)]; g={start:0.0}; parent={}
        while pq:
            _,u=heappop(pq)
            if u==goal:
                path=[u]
                while u in parent: u=parent[u]; path.append(u)
                return path[::-1],g[goal]
            for e in self.adj.get(u,[]):
                if e.to in blocked: continue
                if (u, e.to) in blocked_edges: continue
                ng=g[u]+e.weight+penalty*e.risk
                if ng<g.get(e.to,float('inf')):
                    g[e.to]=ng; parent[e.to]=u
                    heappush(pq,(ng+self.heuristic(e.to,goal),e.to))
        return [], float('inf')


def build_demo_graph():
    g=RoadGraph()
    nodes={
      'A':(12.9712,77.5940),'B':(12.9720,77.5970),'C':(12.9735,77.6000),
      'D':(12.9690,77.5980),'E':(12.9670,77.6010),'F':(12.9650,77.6040),
      'G':(12.9690,77.6060),'H':(12.9720,77.6070),'I':(12.9750,77.6050),'J':(12.9760,77.6000),
      'K':(12.9680,77.5920),'L':(12.9650,77.5960)
    }
    for n,(la,lo) in nodes.items(): g.add_node(n,la,lo)
    edges=[('A','B',2.0,.1),('B','C',2.0,.7),('C','J',2.3,.8),('J','I',1.7,.1),('I','H',1.8,.1),
           ('A','D',2.5,.1),('D','E',2.0,.2),('E','F',2.1,.1),('F','G',2.0,.1),('G','H',2.0,.2),
           ('A','K',2.1,.1),('K','L',2.0,.1),('L','F',2.8,.1),('D','J',2.8,.2),('E','G',2.6,.15),
           ('B','D',1.9,.2),('C','I',3.0,.1)]
    for e in edges:g.add_edge(*e)
    return g
