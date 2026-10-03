from app.algorithms.astar import build_demo_graph
from app.algorithms.routes import k_routes

def test_astar_and_k_routes():
    g=build_demo_graph()
    path,cost=g.astar("A","H")
    assert path[0] == "A" and path[-1] == "H"
    assert cost == 8.8
    routes=k_routes(g,"A","H",3)
    assert len(routes)>=2
    assert len({tuple(r.path) for r in routes})==len(routes)
    assert all(routes[i].cost <= routes[i+1].cost for i in range(len(routes)-1))
