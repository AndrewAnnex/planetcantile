import pytest
import planetcantile
import morecantile
from pyproj import CRS, Transformer
import numpy as np
from morecantile.commons import BoundingBox, Tile
from rio_tiler.utils import CRS_to_uri
from rasterio import crs as rcrs


def test_planetcantile_defaults():
    assert planetcantile.planetary_tms is not None

@pytest.mark.skip
def test_earth_coalesced():
    # some tests borrowed from morecantile
    tms = planetcantile.planetary_tms.get('EarthGeographicOgraphicCoalesced')
    assert tms is not None

    matrix_0 = tms.matrix(0)
    assert matrix_0.variableMatrixWidths is None
    assert matrix_0.matrixWidth == 4

    matrix_1 = tms.matrix(1)
    assert matrix_1.variableMatrixWidths is not None
    assert matrix_1.matrixWidth == 8
    assert matrix_1.get_coalesce_factor(0) == 2
    assert matrix_1.get_coalesce_factor(3) == 2

    matrix_2 = tms.matrix(2)
    assert matrix_2.variableMatrixWidths is not None
    assert matrix_2.matrixWidth == 16
    assert matrix_2.get_coalesce_factor(0) == 4
    assert matrix_2.get_coalesce_factor(1) == 2
    assert matrix_2.get_coalesce_factor(3) == 1
    assert matrix_2.get_coalesce_factor(6) == 2
    assert matrix_2.get_coalesce_factor(7) == 4

    bounds = tms.xy_bounds(0, 0, 0)
    assert bounds == BoundingBox(-180, 0, -90, 90)

    bounds = tms.xy_bounds(1, 1, 0)
    assert bounds == BoundingBox(-90, -90, 0, 0)

    bounds = tms.xy_bounds(0, 0, 1)
    assert bounds == BoundingBox(-180, 45, -90, 90)

    # tile for index 0,0 and 1,0 should have the same bounds
    assert tms.xy_bounds(0, 0, 1) == tms.xy_bounds(1, 0, 1)
    assert tms.xy_bounds(2, 0, 1) == tms.xy_bounds(3, 0, 1)
    assert tms.xy_bounds(4, 0, 1) == tms.xy_bounds(5, 0, 1)
    assert tms.xy_bounds(6, 0, 1) == tms.xy_bounds(7, 0, 1)

    assert tms.xy_bounds(0, 1, 1) != tms.xy_bounds(1, 1, 1)
    assert tms.xy_bounds(2, 1, 1) != tms.xy_bounds(3, 1, 1)

    assert tms.xy_bounds(0, 3, 1) == tms.xy_bounds(1, 3, 1)
    assert tms.xy_bounds(2, 3, 1) == tms.xy_bounds(3, 3, 1)
    assert tms.xy_bounds(4, 3, 1) == tms.xy_bounds(5, 3, 1)
    assert tms.xy_bounds(6, 3, 1) == tms.xy_bounds(7, 3, 1)

    # crs and geographic crs are the same
    assert tms.xy_bounds(0, 0, 0) == tms.bounds(0, 0, 0)
    assert tms.xy_bounds(1, 1, 0) == tms.bounds(1, 1, 0)
    assert tms.xy_bounds(0, 0, 1) == tms.bounds(0, 0, 1)

    tiles = tms.tiles(-180, -90, 180, 90, [0])
    assert len(list(tiles)) == 8

    tiles = tms.neighbors(Tile(0, 3, 1))
    assert tiles == [
        Tile(x=0, y=2, z=1),
        Tile(x=1, y=2, z=1),
        Tile(x=2, y=2, z=1),
        Tile(x=2, y=3, z=1),
    ]

    # Ignore coalescence and return alias
    assert tms.tile(-150, 90, 2, ignore_coalescence=True) == Tile(1, 0, 2)
    assert tms.tile(150, -90, 2, ignore_coalescence=True) == Tile(14, 7, 2)


def test_mars_sphere():
    tms_sphere = planetcantile.planetary_tms.get('MarsGeographicSphere')
    assert not tms_sphere.rasterio_geographic_crs.is_epsg_code
    assert not tms_sphere.rasterio_crs.is_epsg_code


def test_mars_sphere_geocentric_geographic():
    tms_sphere = planetcantile.planetary_tms.get('MarsGeographicSphere')
    tms_ocentric = planetcantile.planetary_tms.get('MarsGeographicOcentric')
    tms_ographic = planetcantile.planetary_tms.get('MarsGeographicOgraphic')
    assert tms_sphere.geographic_crs.ellipsoid.inverse_flattening == 0.0
    assert tms_ocentric.geographic_crs.ellipsoid.inverse_flattening > 0.0
    assert tms_ographic.geographic_crs.ellipsoid.inverse_flattening > 0.0
    assert '4326' not in tms_sphere.geographic_crs.to_wkt()
    assert '4326' not in tms_sphere.rasterio_geographic_crs.to_wkt()


def test_mars_sphere_geocentric_geographic_equidistant_cylindrical():
    tms_sphere = planetcantile.planetary_tms.get('MarsEquidistantCylindricalSphere')
    tms_ocentric = planetcantile.planetary_tms.get('MarsEquidistantCylindricalOcentric')
    tms_ographic = planetcantile.planetary_tms.get('MarsEquidistantCylindricalOgraphic')
    assert tms_sphere.geographic_crs.ellipsoid.inverse_flattening == 0.0
    assert tms_ocentric.geographic_crs.ellipsoid.inverse_flattening > 0.0
    assert tms_ographic.geographic_crs.ellipsoid.inverse_flattening > 0.0

    iau_49900 = CRS.from_user_input('IAU_2015:49900')
    iau_49902 = CRS.from_user_input('IAU_2015:49902')
    iau_49901 = CRS.from_user_input('IAU_2015:49901')
    iau_49910 = CRS.from_user_input('IAU_2015:49910')
    iau_49912 = CRS.from_user_input('IAU_2015:49912')
    iau_49911 = CRS.from_user_input('IAU_2015:49911')

    # looks like always_xy is not respected here so feed in y x lat lon order
    # IAU 49902 is Ocentric
    t_00_10 = Transformer.from_crs(iau_49900, iau_49910, always_xy=True)
    t_02_12 = Transformer.from_crs(iau_49902, iau_49912, always_xy=True)
    t_01_11 = Transformer.from_crs(iau_49901, iau_49911, always_xy=True)

    # compute the expected coordinates from proj
    e_exp_sph, n_exp_sph = t_00_10.transform(0,45)
    e_exp_cen, n_exp_cen = t_02_12.transform(45,0)
    e_exp_geo, n_exp_geo = t_01_11.transform(45,0)

    e_sph, n_sph = tms_sphere._from_geographic.transform(0, 45)
    e_cen, n_cen = tms_ocentric._from_geographic.transform(45, 0)
    e_geo, n_geo = tms_ographic._from_geographic.transform(0, 45)

    # https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/Tutorials/pdf/individual_docs/17_frames_and_coordinate_systems.pdf
    # check against the reference CRSs
    assert n_sph == pytest.approx(n_exp_sph)
    assert n_cen == pytest.approx(n_exp_cen)
    assert n_geo == pytest.approx(n_exp_geo)


def test_mars_geographic_sphere():
    tms = planetcantile.planetary_tms.get('MarsGeographicSphere')
    assert tms is not None
    assert tms.tile(0.0, 0.0, 1) is not None
    assert tms.bbox is not None
    assert not tms.is_quadtree 
    assert not tms._invert_axis # x y order
    assert len(list(tms.tiles(-45.0, -45.0, 45.0, 45.0, zooms=[4]))) > 1

def test_mars_web_mercator():
    earth_mercator_tms = morecantile.tms.get("WebMercatorQuad")
    mars_tms_wm_sphere = planetcantile.planetary_tms.get('MarsWebMercatorSphere')
    mars_tms_wm_geocen = planetcantile.planetary_tms.get('MarsWebMercatorOcentric')
    mars_tms_wm_geogra = planetcantile.planetary_tms.get('MarsWebMercatorOgraphic')
    assert mars_tms_wm_sphere is not None
    assert mars_tms_wm_sphere.is_quadtree
    assert mars_tms_wm_sphere.quadkey(486, 332, 10) == "0313102310"
    assert mars_tms_wm_sphere.quadkey_to_tile("0313102310")  == Tile(486, 332, 10)
    # test tiles are equivalent numbers to earth
    pos = Tile(35, 40, 3)
    mars_tile = mars_tms_wm_sphere.tile(*pos)
    earth_tile = earth_mercator_tms.tile(*pos)
    assert mars_tile.x == earth_tile.x
    assert mars_tile.y == earth_tile.y
    assert mars_tile.z == earth_tile.z == 3
    # test something here
    assert 'axis order change' in mars_tms_wm_sphere._from_geographic.description
    assert 'axis order change' not in mars_tms_wm_geocen._from_geographic.description
    assert 'axis order change' in mars_tms_wm_geogra._from_geographic.description


def test_mars_north_pole():
    mnps  = planetcantile.planetary_tms.get('MarsNorthPolarSphere')
    assert mnps is not None
    assert mnps.xy(0.0, 90) is not None
    assert tuple(mnps.xy(0.0, 90)) == (400000.0, 400000.0)


def test_mars_north_pole():
    mnps  = planetcantile.planetary_tms.get('MarsSouthPolarSphere')
    assert mnps is not None
    assert mnps.xy(0.0, -90) is not None
    assert tuple(mnps.xy(0.0, -90)) == (400000.0, 400000.0)

#'MarsEquidistantCylindricalSphere', 'MarsWebMercatorSphere',
# @pytest.mark.parametrize("tms_name", ['MarsGeographicSphere',  'MarsEquidistantCylindricalOcentric'])
# def test_rasterio_geographic_crs_to_uri(tms_name):
#     mtms = planetcantile.planetary_tms.get(tms_name)
#     breakpoint()
#     assert mtms.geographic_crs.to_authority() is not None
#     assert mtms.rasterio_geographic_crs.to_authority()  is not None
#     assert rcrs.CRS.from_wkt(mtms.geographic_crs.to_wkt()).to_authority
#     rgcrs = mtms.rasterio_geographic_crs
#     uri = CRS_to_uri(rgcrs)
#     # okay uri can be none in the rasterio_geographic_crs is not detailed enough to cleanly become a iau crs
#     # for example CRS.from_wkt('GEOGCS["Mars (2015)",DATUM["Mars (2015)",SPHEROID["Mars (2015)",3396190,169.894447223612]],PRIMEM["Reference Meridian",0],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST]]')
#     # is too sparse 
#     # okay I actually think now this is due to the axis ordering swaps I perform resulting in a different result from rasterio's to_authority call
#     # although that doesn't make sense, as the geographic crs for any normal crs shouldn't depend on the axis order of the projection
#     assert uri is not None
#     assert 'IAU' in uri