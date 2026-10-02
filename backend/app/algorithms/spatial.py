from collections import defaultdict
class SpatialGrid:
    """Uniform grid spatial index: expected O(1+c) local candidate lookup."""
    def __init__(self, cell_size=0.002): self.cell_size=cell_size; self.cells=defaultdict(list)
    def _cell(self,lat,lon): return (int(lat/self.cell_size),int(lon/self.cell_size))
    def add(self,key,lat,lon): self.cells[self._cell(lat,lon)].append((key,lat,lon))
    def nearest(self,lat,lon,radius_cells=1):
        c=self._cell(lat,lon); best=None; bestd=float('inf')
        for dx in range(-radius_cells,radius_cells+1):
            for dy in range(-radius_cells,radius_cells+1):
                for item in self.cells.get((c[0]+dx,c[1]+dy),[]):
                    d=(item[1]-lat)**2+(item[2]-lon)**2
                    if d<bestd:bestd=d;best=item
        return best
