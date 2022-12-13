import importlib.resources as importlib_resources
from copy import copy
from typing import Dict

from morecantile import TileMatrixSet, TileMatrixSets


def to_tms(path):
    with importlib_resources.as_file(path) as src:
        tms = TileMatrixSet.parse_file(src)
    return tms


planetary_tms_jsons = importlib_resources.files('planetcantile.data').glob('*.json')
planetary_tms_dict: Dict[str, TileMatrixSet] = {
    p.stem: to_tms(p) for p in planetary_tms_jsons
}

planetary_tms = TileMatrixSets(copy(planetary_tms_dict))