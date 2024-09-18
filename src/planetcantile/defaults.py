import importlib.resources as importlib_resources
from copy import copy
from functools import lru_cache

from morecantile import TileMatrixSets

@lru_cache
def get_jsons(v: int = 4):
    return importlib_resources.files(f"planetcantile.data.v{v}").glob("*.json")

@lru_cache
def get_planetcantile_tms(v: int = 4):
    return TileMatrixSets({p.stem: p for p in get_jsons(v)})

planetary_tms = get_planetcantile_tms(v=4)