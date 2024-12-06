import pytest
import planetcantile
import morecantile
from pyproj import CRS, Transformer
from pyproj.enums import WktVersion
import numpy as np
from morecantile.commons import BoundingBox, Tile
from rio_tiler.utils import CRS_to_uri
from rasterio import crs as rcrs

from planetcantile.data.generate import Tmsparams, convert_crs, get_geo_type

def test_make_mars_sphere():
    mars_geographic_sphere_crs = CRS.from_user_input('IAU_2015:49900')
    # test converting the crs
    mars_geographic_sphere_crs_converted = convert_crs(mars_geographic_sphere_crs, scope='Mars')
    # kick tires
    assert 'Mars' in mars_geographic_sphere_crs_converted.to_wkt()
    assert mars_geographic_sphere_crs_converted.to_authority() is not None
    # convert to rasterio
    mars_geographic_sphere_rcrs_converted = rcrs.CRS.from_wkt(mars_geographic_sphere_crs_converted.to_wkt())
    assert mars_geographic_sphere_rcrs_converted.to_authority() is not None
    # make the TMS params object
    #mars_geographic_sphere_tmsp = Tmsparams(crs_wkt=)

@pytest.mark.parametrize("code", ['IAU_2015:49900', 'IAU_2015:49902'])
def test_various_mars_basic(code):
    # make crs 
    crs = CRS.from_user_input(code)
    # check sanity
    assert crs.to_authority() is not None
    # convert to expectations
    converted = convert_crs(crs, scope='Mars')
    # test to authority
    breakpoint()
    assert converted.to_authority() is not None
    # test rasterio's to authority
    rasterio_crs = rcrs.CRS.from_wkt(converted.to_wkt())
    assert rasterio_crs.to_authority() is not None