import pytest
import planetcantile
import morecantile
from morecantile.commons import BoundingBox, Tile

def test_planetcantile_defaults():
    assert planetcantile.planetary_tms is not None


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


def tets_mars_north_pole():
    mnps  = planetcantile.planetary_tms.get('MarsNorthPolarSphere')
    assert mnps is not None