import pytest
import planetcantile

def test_planetcantile_defaults():
    assert planetcantile.planetary_tms is not None


def test_mars():
    tms = planetcantile.planetary_tms.get('MarsIAU49900GeographicQuad')
    assert tms is not None
    assert tms.tile(0.0, 0.0, 1) is not None
    assert tms.bbox is not None
    assert len(list(tms.tiles(-45.0, -45.0, 45.0, 45.0, zooms=[4]))) > 1
