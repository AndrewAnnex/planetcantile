from typing import Callable

from .defaults import planetary_tms
from .topoalgo import TopographyQuantizer

from titiler.core.factory import TilerFactory, TMSFactory, AlgorithmFactory
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.extensions import cogViewerExtension
from titiler.core.algorithm import Algorithms
from titiler.core.algorithm import algorithms as default_algorithms
from fastapi import FastAPI


algorithms: Algorithms = default_algorithms.register({"toporgb": TopographyQuantizer})
PostProcessParams: Callable = algorithms.dependency

tms = TMSFactory(supported_tms=planetary_tms)
algos = AlgorithmFactory(supported_algorithm=algorithms)
cog = TilerFactory(
    supported_tms=planetary_tms,
    process_dependency=PostProcessParams,
    extensions=[
        cogViewerExtension()
    ]
)

app = FastAPI(
    title="Planetcantile",
    description="A Cloud Optimized GeoTIFF tile server for Planetary Data"
)

app.include_router(cog.router, tags=["Cloud Optimized GeoTIFF"])
app.include_router(tms.router, tags=["Tiling Schemes"])
app.include_router(algos.router, tags=["Algorithms"])
add_exception_handlers(app, DEFAULT_STATUS_CODES)

@app.get("/healthz", description="Health Check", tags=["Health Check"])
def ping():
    """Health check."""
    return {"ping": "pong!"}
