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


gcs_mars_2000_ellipsoid = 'ELLIPSOID["Mars_2000_Sphere_IAU_IAG",3396190,0.0,LENGTHUNIT["metre",1]],ID["ESRI",106971]]'
gcs_mars_2000_sphere_datum = f'DATUM["D_Mars_2000_Sphere",{gcs_mars_2000_ellipsoid},PRIMEM["Reference_Meridian",0,ANGLEUNIT["degree",0.0174532925199433,ID["EPSG",9122]]]'
gcs_mars_2000_sphere = CRS(f"""GEOGCRS["GCS_Mars_2000_Sphere",{gcs_mars_2000_sphere_datum},CS[ellipsoidal,2],AXIS["latitude",north,ORDER[1],ANGLEUNIT["degree",0.0174532925199433,ID["EPSG",9122]]],AXIS["longitude",east,ORDER[2],ANGLEUNIT["degree",0.0174532925199433,ID["EPSG",9122]]]]""")

moon_2000_ellipsoid = 'SPHEROID["Moon_2000_IAU_IAG",1737400.0,0.0,LENGTHUNIT["metre",1]]'
moon_2000_datum = f'DATUM["D_Moon_2000_Sphere",{moon_2000_ellipsoid},PRIMEM["Greenwich",0],UNIT["Decimal_Degree",0.0174532925199433]]'
moon_2000_sphere = CRS(f'GEOGCS["Moon_2000",{moon_2000_datum},CS[ellipsoidal,2],AXIS["latitude",north,ORDER[1],ANGLEUNIT["degree",0.0174532925199433,ID["EPSG",9122]]],AXIS["longitude",east,ORDER[2],ANGLEUNIT["degree",0.0174532925199433,ID["EPSG",9122]]]]')

# uber tuple of all TmsMatrixSets to generate, if you want something new add it here
crss = (
    Tmsparam(
        crs=gcs_mars_2000_sphere,
        extent=(-180.0, -90.0, 180.0, 90.0),
        title="GCS_Mars_2000_Sphere TileMatrixSet",
        identifier="GCS_Mars_2000_Sphere",
        maxzoom=22,  # set lower for 200mpp MOLA
        geographic_crs=gcs_mars_2000_sphere
    ),
    Tmsparam(
        crs=moon_2000_sphere,
        extent=(-180.0, -90.0, 180.0, 90.0),
        title="Moon_2000_Sphere TileMatrixSet",
        identifier="Moon_2000_Sphere",
        maxzoom=22,
        geographic_crs=moon_2000_sphere
    ),


)

for tmsp in crss:
    # create the tms object
    tms = morecantile.TileMatrixSet.custom(**asdict(tmsp))
    _d = json.loads(tms.json(exclude_none=True))  # get to pretty printed json
    with open(f'./{tmsp.crs.name}_tms.json', 'w') as dst:
        # dump to json
        json.dump(_d, dst, indent=4, ensure_ascii=False)
        print(f'wrote {dst.name}')
