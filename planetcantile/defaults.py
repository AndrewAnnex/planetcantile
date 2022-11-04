import importlib.resources as importlib_resources
import pathlib

from morecantile import TileMatrixSet
from morecantile import tms


def to_tms(path):
    with importlib_resources.as_file(path) as src:
        tms = TileMatrixSet.parse_file(src)
    return tms

planet_tms_jsons = importlib_resources.files('planetcantile.data').glob('*.json')
planet_tmss = map(to_tms, planet_tms_jsons)

planetary_tms = tms.register(*planet_tms_jsons, overwrite=True)