import os

os.environ['GDAL_HTTP_MULTIPLEX']='YES'
os.environ['GDAL_HTTP_MERGE_CONSECUTIVE_RANGES']='YES'
os.environ['GDAL_DISABLE_READDIR_ON_OPEN']='EMPTY_DIR'
os.environ['GDAL_CACHEMAX']='200'
os.environ['CPL_VSIL_CURL_CACHE_SIZE']='200000000'
os.environ['CPL_VSIL_CURL_ALLOWED_EXTENSIONS']=".tif,.TIF,.tiff"
os.environ['VSI_CACHE']='TRUE'
os.environ['VSI_CACHE_SIZE']="5000000"

from typing import Callable

from .defaults import planetary_tms
from .topoalgo import TopographyQuantizer
from .debugalgo import DebugTile

from io import BytesIO

from PIL import Image, ImageOps, ImageDraw
from starlette.responses import Response

from rio_tiler.io import STACReader
from titiler.core.factory import TilerFactory, TMSFactory, AlgorithmFactory, MultiBaseTilerFactory
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.extensions import cogViewerExtension, stacViewerExtension, stacExtension
from titiler.core.algorithm import Algorithms
from titiler.core.algorithm import algorithms as default_algorithms
from titiler.mosaic.factory import MosaicTilerFactory
from titiler.mosaic.errors import MOSAIC_STATUS_CODES
from starlette.middleware.cors import CORSMiddleware
from titiler.application.settings import ApiSettings
from fastapi import FastAPI

api_settings = ApiSettings()

algo_dict = {
    "toporgb": TopographyQuantizer,
    "debug": DebugTile
}

algorithms: Algorithms = default_algorithms.register(algo_dict)
PostProcessParams: Callable = algorithms.dependency

tms = TMSFactory(supported_tms=planetary_tms)
algos = AlgorithmFactory(supported_algorithm=algorithms)
stac = MultiBaseTilerFactory(
        router_prefix="/stac",
        reader=STACReader,
        supported_tms=planetary_tms,
        process_dependency=PostProcessParams,
        extensions=[
            stacViewerExtension(),
        ],
    )
cog = TilerFactory(
    router_prefix="/cog",
    supported_tms=planetary_tms,
    process_dependency=PostProcessParams,
    extensions=[
        cogViewerExtension(),
        stacExtension(),
    ]
)
mosaic = MosaicTilerFactory(
    router_prefix="/mosaicjson",
    supported_tms=planetary_tms,
    process_dependency=PostProcessParams,
)

app = FastAPI(
    title="Planetcantile",
    description="A Cloud Optimized GeoTIFF tile server for Planetary Data"
)
app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
)

app.include_router(cog.router, prefix='/cog', tags=["Cloud Optimized GeoTIFF"])
app.include_router(stac.router, prefix="/stac", tags=["SpatioTemporal Asset Catalog"])
app.include_router(mosaic.router, prefix="/mosaicjson",tags=["MosaicJSON"])
app.include_router(algos.router, tags=["Algorithms"])
app.include_router(tms.router, tags=["Tiling Schemes"])
add_exception_handlers(app, DEFAULT_STATUS_CODES)
add_exception_handlers(app, MOSAIC_STATUS_CODES)

@app.get("/debug/{z}/{x}/{y}.png")
async def debug(z: int, x: int , y: int):
    "Serve scrambled tiles from two basemaps."
    img = Image.new("RGBA", (254, 254))
    img = ImageOps.expand(img, border=1, fill="black")
    draw = ImageDraw.Draw(img)
    msg = f"x/y/z: {x}/{y}/{z}"
    w, h = 127, 127
    draw.text(((255 - w) / 2, (255 - h) / 2), msg, fill="black")
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return Response(img_io.read(), media_type="image/png")

@app.get("/healthz", description="Health Check", tags=["Health Check"])
def ping():
    """Health check."""
    return {"ping": "pong!"}

