import json
import math
import os
import urllib.request
from dataclasses import dataclass, field, asdict
import json

from pyproj import CRS, Transformer, Proj
WGS84_CRS = CRS.from_epsg(4326)
import morecantile
from morecantile.models import crs_axis_inverted

# try to add Area of Use to each CRS first
# use the .name and .area_of_use.bounds

matrix_scale_mercator = [1, 1]
matrix_scale_platecur = [2, 1]


def CRS_to_info(crs: CRS)-> tuple[str]:
    """Convert CRS to URI."""
    authority = "EPSG"
    code = "4326"
    version = "0"
    # attempt to grab the authority, version, and code from the CRS
    authority_code = crs.to_authority(min_confidence=20)
    if authority_code is not None:
        authority, code = authority_code
        # if we have a version number in the authority, split it out
        if "_" in authority:
            authority, version = authority.split("_")
    return authority, version, code


def CRS_to_uri(crs: CRS) -> str:
    """Convert CRS to URI."""
    authority, version, code = CRS_to_info(crs)
    return f"http://www.opengis.net/def/crs/{authority}/{version}/{code}"


def CRS_to_urn(crs: CRS)-> str:
    """Convert CRS to URN."""
    authority, version, code = CRS_to_info(crs)
    if version == '0':
        version = ''
    return f"urn:ogc:def:crs:{authority}:{version}:{code}"

@dataclass()
class Tmsparam(object):
    # Bounding box of the Tile Matrix Set, (left, bottom, right, top).
    extent: tuple[float, float, float, float]
    # Tile Matrix Set coordinate reference system
    crs: CRS
    # Width of each tile of this tile matrix in pixels (default is 512).
    tile_width: int = 512
    # Height of each tile of this tile matrix in pixels (default is 512).
    tile_height: int = 512
    # Tiling schema coalescence coefficient, below you can just pass in either matrix_scale lists defined above
    matrix_scale: list = field(default_factory=lambda: matrix_scale_platecur)
    # Extent's coordinate reference system, as a pyproj CRS object.
    extent_crs: CRS | None = None
    # Tile Matrix Set minimum zoom level (default is 0).
    minzoom: int = 0
    # Tile Matrix Set maximum zoom level (default is 30).
    # TODO: find doc page on going from min/max zoom to GSD/degree per pixel
    maxzoom: int = 30
    # Tile Matrix Set title (default is 'Custom TileMatrixSet')
    title: str = "Custom TileMatrixSet"
    # Tile Matrix Set identifier (default is 'Custom')
    identifier: str = "Custom"
    # Geographic (lat,lon) coordinate reference system (default is EPSG:4326)
    geographic_crs: CRS = WGS84_CRS

    def __post_init__(self):
        # try to get the geographic_crs
        self.geographic_crs = self.crs.geodetic_crs

# Grab the wkts that mirror the OCG source and parse out just the GeogCRS in a hacktastic way.
with urllib.request.urlopen('https://raw.githubusercontent.com/pdssp/planet_crs_registry/main/data/result.wkts') as response:
    resp = response.read().decode(response.headers.get_content_charset())

# Parse all the CRSs from the list
allcrss = []
acceptable_projections = ('Equirectangular', 'North Polar', 'South Polar')
for wkt_str in resp.split(os.linesep + os.linesep):
    if 'TRIAXIAL' not in wkt_str and 'Westing' not in wkt_str:  # insanely hacky
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
        identifier = f'{authority}_{version}_{code}'
        geographic_crs = crs_obj.geodetic_crs
        # Set the extent 
        clon_180 = "clon = 180" in crs
        co = crs_obj.coordinate_operation
        matrix_scale = [2, 1]
        if co:
            prj = Proj(crs_obj)
            if co.name == "North Polar":
                minx, _ = prj(-90,0)
                _, miny = prj(0,0)
                maxx, _ = prj(90,0)
                _, maxy = prj(180,0)
                matrix_scale = [1, 1]
                extent = (minx, miny, maxx, maxy)
            elif co.name == "South Polar":
                minx, _ = prj(-90, 0)
                _, miny = prj(180, 0)
                maxx, _ = prj(90, 0)
                _, maxy = prj(0, 0)
                matrix_scale = [1, 1]
                extent = (minx, miny, maxx, maxy)
            elif clon_180:
                minx, miny = prj(0.0, -90.0)
                maxx, maxy = prj(359.99999, 90.0)# todo 360.0 wraps to 0 long
                extent = (minx, miny, math.fabs(minx), maxy)
            else:
                minx, miny = prj(-180, -90)
                maxx, maxy = prj(180, 90)
                extent = (minx, miny, maxx, maxy)
        else:
            # if clon == 180 we have a 0-360 longitude crs
            extent = (0.0, -90.0, 360.0, 90.0) if clon_180 else (-180.0, -90.0, 180.0, 90.0)
        tmsp = Tmsparam(
            crs=crs_obj,
            extent=extent,
            extent_crs=crs_obj,
            title=title,
            identifier=identifier,
            matrix_scale=matrix_scale,
            geographic_crs=geographic_crs
        )
        crss.append(tmsp)
    else:
        pass
        #print(f'Could not find authority for {crs_obj.to_wkt()}')

for tmsp in crss:
    # create the tms object
    tms = morecantile.TileMatrixSet.custom(**asdict(tmsp))
    tmsj = tms.dict(exclude_none=True)
    # Include URN to the planetary projections; _geographic_crs is needed by downstream libs, e.g., morecantile 
    tmsj['supportedCRS'] = tmsj['boundingBox']['crs'] = CRS_to_urn(tmsj['boundingBox']['crs'])
    tmsj['_geographic_crs'] = CRS_to_urn(tms._geographic_crs)
    with open(f'./{tmsp.identifier}.json', 'w') as dst:
        json.dump(tmsj, dst, indent=4, ensure_ascii=True)
        print(f'wrote {dst.name}')
