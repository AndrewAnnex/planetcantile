import importlib.resources as importlib_resources
from copy import copy

from morecantile import TileMatrixSets

planetary_tms_jsons = importlib_resources.files("planetcantile.data.v2").glob("*.json")
planetary_tms_path_dict = {p.stem: p for p in planetary_tms_jsons}

planetary_tms = TileMatrixSets(copy(planetary_tms_path_dict))
