import json
import importlib.resources

import tests.data

import pytest
import planetcantile

from cogeo_mosaic.mosaic import MosaicJSON
from cogeo_mosaic.backends import MosaicBackend
from cogeo_mosaic.backends.file import FileBackend

def test_mosaic_json():
    mars_tms_wm_sphere = planetcantile.planetary_tms.get('MarsWebMercatorSphere')
    with importlib.resources.path(tests.data, 'stac_asset.json') as data_path:
        with open(data_path, 'r') as f:
            stac_asset = json.load(f)
    stac_asset['properties']['path'] = stac_asset['assets']['dtm']['href']
    mosaic_json = MosaicJSON.from_features(
        [stac_asset,],
        minzoom=7, 
        maxzoom=30, 
        tilematrixset=mars_tms_wm_sphere,
    )

    assert mosaic_json is not None
    assert mosaic_json.tilematrixset == mars_tms_wm_sphere
    assert len(mosaic_json.tiles) > 0

    with MosaicBackend("mosaic.json", mosaic_def=mosaic_json, tms=mars_tms_wm_sphere) as mosaic:
        assert isinstance(mosaic, FileBackend)
        # TODO Why are both tms and tilematrixset around?
        assert mosaic.tms == mars_tms_wm_sphere
        #assert mosaic.tilematrixset == mars_tms_wm_sphere # this actually disappeared
        # 
        assert mosaic.crs == mars_tms_wm_sphere.rasterio_geographic_crs
        assert mosaic.geographic_crs == mars_tms_wm_sphere.rasterio_geographic_crs
        assert len(mosaic.assets_for_point(77.28, 18, mars_tms_wm_sphere.geographic_crs)) > 0
        assert len(mosaic.assets_for_bbox(77.2, 17.5, 77.4, 18.5, mars_tms_wm_sphere.geographic_crs)) > 0
        assert len(mosaic.assets_for_point(77.25, 18.0)) > 0
        assert len(mosaic.assets_for_bbox(77.2, 17.5, 77.4, 18.5)) > 0