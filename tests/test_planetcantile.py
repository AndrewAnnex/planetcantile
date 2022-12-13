import pytest
import planetcantile

def test_planetcantile_defaults():
    assert planetcantile.planetary_tms is not None
    