import json
import os
import urllib.request

from pyproj import CRS, Transformer
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

# Parse all the CRSs from the list
allcrss = []
acceptable_projections = ('Equirectangular', 'North Polar', 'South Polar')
for wkt_str in resp.split(os.linesep + os.linesep):
    if 'TRIAXIAL' not in wkt_str:  # insanely hacky
        if wkt_str.startswith('GEOGCRS') or any(_ in wkt_str for _ in acceptable_projections):
            allcrss.append(wkt_str)

# Build a dynamic crss list
crss = []
for crs in allcrss:
    crs_obj = CRS(crs)
    title = crs_obj.name
    auth = crs_obj.to_authority(min_confidence=25)
    if auth is not None:
        authority_version, code = auth
        authority, version = authority_version.split('_')
        identifier = f'{authority}_{code}_{version}'
        geographic_crs = crs_obj.geodetic_crs
        # get the extent, if clon == 180 we have a 0-360 longitude crs
        extent = (0.0, -90.0, 360.0, 90.0) if 'clon = 180' in crs else (-180.0, -90.0, 180.0, 90.0)
        # do some work to get extent from projected CRSs
        if crs_obj.is_projected:
            # todo: this doesn't work well with ographic geographic crss (those with inverse flattenings), fails ecq: Invalid latitude
            # looks to be an issue where the x and y is swapped, if the inverse_flattening is not 0.0 we would have to swap
            # this x and y swap is happening despite setting always_xy to True
            # another way is to check the coordinate_system, I see westing instead of easting
            if geographic_crs.coordinate_system.axis_list[0].abbrev == 'W':
                extent = (extent[1], extent[0], extent[3], extent[2])
            transformer = Transformer.from_crs(geographic_crs, crs_obj, authority='IAU', always_xy=True, allow_ballpark=False, accuracy=0.001)
            # todo this still fails errcheck=True
            extent = transformer.transform_bounds(*extent, densify_pts=51)
        
        tmsp = Tmsparam(
            crs=crs_obj,
            extent=extent,
            title=title,
            identifier=identifier,
            maxzoom=24,
            geographic_crs=geographic_crs
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
