import json
import os
import urllib.request

from pyproj import CRS
WGS84_CRS = CRS.from_epsg(4326)
import morecantile

from dataclasses import dataclass, field, asdict
import json
# try to add Area of Use to each CRS first
# use the .name and .area_of_use.bounds

matrix_scale_mercator = [1, 1]
matrix_scale_platecur = [2, 1]

@dataclass()
class Tmsparam(object):
    # Bounding box of the Tile Matrix Set, (left, bottom, right, top).
    extent: tuple[float, float, float, float]
    # Tile Matrix Set coordinate reference system
    crs: CRS
    # Width of each tile of this tile matrix in pixels (default is 256).
    tile_width: int = 256
    # Height of each tile of this tile matrix in pixels (default is 256).
    tile_height: int = 256
    # Tiling schema coalescence coefficient, below you can just pass in either matrix_scale lists defined above
    matrix_scale: list = field(default_factory=lambda: matrix_scale_platecur)
    # Extent's coordinate reference system, as a pyproj CRS object.
    extent_crs: CRS | None = None
    # Tile Matrix Set minimum zoom level (default is 0).
    minzoom: int = 0
    # Tile Matrix Set maximum zoom level (default is 24).
    # TODO: find doc page on going from min/max zoom to GSD/degree per pixel
    maxzoom: int = 24
    # Tile Matrix Set title (default is 'Custom TileMatrixSet')
    title: str = "Custom TileMatrixSet"
    # Tile Matrix Set identifier (default is 'Custom')
    identifier: str = "Custom"
    # Geographic (lat,lon) coordinate reference system (default is EPSG:4326)
    geographic_crs: CRS = WGS84_CRS

    def __post_init__(self):
        # try to get the geographic_crs
        geographic_crs = self.crs.geodetic_crs

# Grab the wkts that mirror the OCG source and parse out just the GeogCRS in a hacktastic way.
with urllib.request.urlopen('https://raw.githubusercontent.com/pdssp/planet_crs_registry/main/data/result.wkts') as response:
    resp = response.read().decode(response.headers.get_content_charset())

# Parse all the GeoCRSs from the list
geocrss = []
for wkt_str in resp.split(os.linesep + os.linesep):
    if 'GEOGCRS' in wkt_str[:7] and 'TRIAXIAL' not in wkt_str:  # insanely hacky
        geocrss.append(wkt_str)

# Build a dynamic crss list
crss = []
for crs in geocrss:
    crs_obj = CRS(crs)
    title = crs_obj.name
    auth = crs_obj.to_authority(min_confidence=25)
    if auth is not None:
        authority_version, code = auth
        authority, version = authority_version.split('_')
        identifier = f'{authority}_{code}_{version}'
        
        tmsp = Tmsparam(
            crs=crs_obj,
            extent=(-180.0, -90.0, 180.0, 90.0),  # Hardcoded domains, ever differ?
            title=title,
            identifier=identifier,
            maxzoom=22,  # set lower for 200mpp MOLA
            geographic_crs=crs_obj
        )
        crss.append(tmsp)
    else:
        print(f'Could not find authority for {crs_obj.to_wkt()}')

for tmsp in crss:
    # create the tms object
    tms = morecantile.TileMatrixSet.custom(**asdict(tmsp))
    _d = json.loads(tms.json(exclude_none=True))  # get to pretty printed json
    with open(f'./{tmsp.identifier}_tms.json', 'w') as dst:
        # dump to json
        json.dump(_d, dst, indent=4, ensure_ascii=False)
        print(f'wrote {dst.name}')
