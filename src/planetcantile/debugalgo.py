from titiler.core.algorithm import BaseAlgorithm
from rio_tiler.models import ImageData
from PIL import Image, ImageOps, ImageDraw, ImageFont
import numpy as np
from planetcantile.defaults import planetary_tms
from functools import cached_property, lru_cache
from pydantic import Field

fnt = ImageFont.load_default(size=28)

class DebugTile(BaseAlgorithm):

    title: str = "Debug"
    description: str = "Create tiles with boarders to have some sort of visual, order of coords is z-x-y"

    # parameters
    input_tms: str = Field(default="WebMercatorQuad")

    # metadata
    input_nbands: int = 1
    input_shape: int = 256
    output_nbands: int = 3
    output_dtype: str = "uint8"



    @cached_property
    def tms(self):
        return planetary_tms.get(self.input_tms)
    
    def zoom_for_res(self, res: float):
        return self.tms.zoom_for_res(res)

    def __call__(self, img: ImageData) -> ImageData:
        """Encode """
        bounds_tms_crs = img.bounds
        # determine resolution
        height = bounds_tms_crs.top - bounds_tms_crs.bottom
        width = bounds_tms_crs.right - bounds_tms_crs.left
        height_res = np.abs(height / self.input_shape)
        width_res =  np.abs(width / self.input_shape)
        res  = np.max((height_res, width_res))
        # get the zoom
        zoom = self.zoom_for_res(res)
        # get the tile for the centroid
        tile = self.tms._tile(
            np.mean((bounds_tms_crs.right, bounds_tms_crs.left)), 
            np.mean((bounds_tms_crs.top, bounds_tms_crs.bottom)),
            zoom
        )
        x, y, z = tile
        print(x, y, z, flush=True)
        msg = f"{z}-{x}-{y}"
        first_dim = img.array.shape[0]
        if first_dim < 3:
            _img = img.array.squeeze()
            _img = Image.fromarray(_img)
        else:
            _img = Image.fromarray(img.array, "RGB")
        _img = ImageOps.expand(_img, border=2, fill="black")
        # draw tile labels
        draw = ImageDraw.Draw(_img)
        draw.text((self.input_shape/10, self.input_shape/2.5), msg, fill="white", font=fnt)
        out_array = np.array(_img)
        #print(out_array.shape, flush=True)
        return ImageData(
            out_array,
            img.mask,
            assets=img.assets,
            crs=img.crs,
            bounds=img.bounds,
        )