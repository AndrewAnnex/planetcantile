import os
import pathlib
import sys

# This is the main object we want users to import from this file
planetary_tms = None

planetcantile_tms_dir = pathlib.Path(__file__).parent.joinpath("data") / "v4"
planetcantile_tms_paths = sorted(list(pathlib.Path(planetcantile_tms_dir).glob("*.json")))

# grab TILEMATRIXSET_DIRECTORY
user_tms_dir = os.environ.get("TILEMATRIXSET_DIRECTORY", None)
# if none and morecantile hasn't been imported yet we can inject planetcantile TMSs into morecantile directly
if not user_tms_dir and 'morecantile' not in sys.modules:
    # set the environment variable temporarily
    os.environ["TILEMATRIXSET_DIRECTORY"] = str(planetcantile_tms_dir.expanduser().resolve())
    from morecantile.defaults import tms 
    planetary_tms = tms
    # unset the environment variable
    os.environ.pop("TILEMATRIXSET_DIRECTORY", None)
else:
    # user has set a custom TILEMATRIXSET_DIRECTORY, so we will do more work to include planetcantile
    import morecantile.defaults
    from morecantile import TileMatrixSets
    from morecantile.defaults import default_tms as morecantile_default_tms
    planetary_tms = TileMatrixSets({
            **{p.stem: p for p in planetcantile_tms_paths},
            **morecantile_default_tms
        })
    # override morecantile's tms object
    morecantile.defaults.tms = planetary_tms