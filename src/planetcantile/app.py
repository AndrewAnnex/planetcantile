import os

os.environ['GDAL_HTTP_MULTIPLEX']='YES'
os.environ['GDAL_HTTP_MERGE_CONSECUTIVE_RANGES']='YES'
os.environ['GDAL_DISABLE_READDIR_ON_OPEN']='EMPTY_DIR'
os.environ['GDAL_CACHEMAX']='200'
os.environ['GDAL_INGESTED_BYTES_AT_OPEN']='50000'
os.environ['CPL_VSIL_CURL_CACHE_SIZE']='200000000'
os.environ['CPL_VSIL_CURL_ALLOWED_EXTENSIONS']=".tif,.TIF,.tiff"
os.environ['VSI_CACHE']='TRUE'
os.environ['VSI_CACHE_SIZE']="5000000"

from typing import Callable

from .defaults import planetary_tms
from .topoalgo import TopographyQuantizer
from .debugalgo import DebugTile, fnt

from io import BytesIO

from PIL import Image, ImageOps, ImageDraw
from starlette.requests import Request
from starlette.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

from rio_tiler.io import STACReader
from titiler.core.factory import TilerFactory, TMSFactory, AlgorithmFactory, MultiBaseTilerFactory, ColorMapFactory
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.extensions import cogViewerExtension, stacViewerExtension, stacExtension
from titiler.core.algorithm import Algorithms
from titiler.core.algorithm import algorithms as default_algorithms
from cogeo_mosaic.backends import MosaicBackend
from titiler.mosaic.factory import MosaicTilerFactory
from titiler.mosaic.errors import MOSAIC_STATUS_CODES
from starlette.middleware.cors import CORSMiddleware
from titiler.application.settings import ApiSettings
from fastapi import FastAPI

# When true: /docs, /redoc, and the COG/STAC viewer extensions are active.
# Requires a CSP header on every HTML response, added by CSPMiddleware below.
# In the proxied deployment, nginx handles
# the CSP instead; set this only for standalone deployments.
UI_ENABLED = os.getenv("TITILER_UI_ENABLED", "false").lower() == "true"

UI_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'sha256-QOOQu4W1oxGqd2nbXbxiA1Di6OHQOLQD+o+G9oWL8YY='; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "img-src 'self' data: blob: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
    "connect-src 'self'; "
    "font-src 'self' https://fonts.gstatic.com; "
    "worker-src blob:; "
    "object-src 'none'; "
    "frame-ancestors 'none';"
)

class CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        if "text/html" in response.headers.get("content-type", ""):
            response.headers["Content-Security-Policy"] = UI_CSP
        return response

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
        ] if UI_ENABLED else [],
    )
cog = TilerFactory(
    router_prefix="/cog",
    supported_tms=planetary_tms,
    process_dependency=PostProcessParams,
    extensions=[
        *([cogViewerExtension()] if UI_ENABLED else []),
        stacExtension(),
    ]
)
mosaic = MosaicTilerFactory(
    backend=MosaicBackend,
    router_prefix="/mosaicjson",
    supported_tms=planetary_tms,
    process_dependency=PostProcessParams,
)

colormap = ColorMapFactory()

app = FastAPI(
    title="Planetcantile",
    description="A Cloud Optimized GeoTIFF tile server for Planetary Data",
    docs_url="/docs" if UI_ENABLED else None,
    redoc_url="/redoc" if UI_ENABLED else None,
)
app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
)
if UI_ENABLED:
    app.add_middleware(CSPMiddleware)

app.include_router(cog.router, prefix='/cog', tags=["Cloud Optimized GeoTIFF"])
app.include_router(stac.router, prefix="/stac", tags=["SpatioTemporal Asset Catalog"])
app.include_router(mosaic.router, prefix="/mosaicjson",tags=["MosaicJSON"])
app.include_router(algos.router, tags=["Algorithms"])
app.include_router(tms.router, tags=["Tiling Schemes"])
app.include_router(colormap.router, tags=["ColorMaps"])
add_exception_handlers(app, DEFAULT_STATUS_CODES)
add_exception_handlers(app, MOSAIC_STATUS_CODES)

@app.get("/debug/{z}/{x}/{y}.png")
async def debug(z: int, x: int , y: int):
    "Serve tiles with xyz tile encoded onto image"
    img = Image.new("RGBA", (256, 256))
    img = ImageOps.expand(img, border=1, fill="black")
    draw = ImageDraw.Draw(img)
    msg = f"{z}-{x}-{y}"
    w, h = 127, 256/2.5
    draw.text((25, h), msg, fill="white", font=fnt)
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return Response(img_io.read(), media_type="image/png")

@app.get("/healthz", description="Health Check", tags=["Health Check"])
def ping():
    """Health check."""
    return {"ping": "pong!"}

