import pytest
import planetcantile

def test_planetcantile_defaults():
    assert planetcantile.planetary_tms is not None


def test_mars():
    tms = planetcantile.planetary_tms.get('MarsGeographicSphere')
    assert tms is not None
    assert tms.tile(0.0, 0.0, 1) is not None
    assert tms.bbox is not None
    assert len(list(tms.tiles(-45.0, -45.0, 45.0, 45.0, zooms=[4]))) > 1

def test_mars_web_mercator():
    tms_wm_sphere = planetcantile.planetary_tms.get('MarsWebMercatorSphere')
    assert tms_wm_sphere is not None
    # TODO I want to be far more ambitious here and actually write good tests here 
    # so I can verify the TMSs are correct to various expectations


def tets_mars_north_pole():
    mnps  = planetcantile.planetary_tms.get('MarsNorthPolarSphere')
    assert mnps is not None