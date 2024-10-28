from titiler.core.algorithm import BaseAlgorithm
from rio_tiler.models import ImageData
from PIL import Image, ImageOps
import numpy as np

class DebugTile(BaseAlgorithm):

    title: str = "Debug"
    description: str = "Create tiles with boarders to have some sort of visual"

    # metadata
    input_nbands: int = 1
    output_nbands: int = 3
    output_dtype: str = "uint8"

    def __call__(self, img: ImageData) -> ImageData:
        """Encode """
        first_dim = img.array.shape[0]
        if first_dim < 3:
            _img = img.array.squeeze()
            _img = Image.fromarray(_img)
        else:
            _img = Image.fromarray(img.array, "RGB")
        _img = ImageOps.expand(_img, border=2, fill="black")
        out_array = np.array(_img)
        print(out_array.shape, flush=True)
        return ImageData(
            out_array,
            img.mask,
            assets=img.assets,
            crs=img.crs,
            bounds=img.bounds,
        )