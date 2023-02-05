from titiler.core.algorithm import BaseAlgorithm
from rio_tiler.models import ImageData
from numpy import stack, uint8

quantizers = {
    'anyrock': {
        "min"       : -9000.0,
        "resolution": 0.00204682,
        "rScaler"   : 134.14039552,
        "gScaler"   : 0.52398592,
        "bScaler"   : 0.00204682
    },
    'mercury': {
        "min"       : -6000.0,
        "resolution": 0.00066221,
        "rScaler"   : 43.39859456,
        "gScaler"   : 0.16952576,
        "bScaler"   : 0.00066221
    },
    'venus'  : {
        "min"       : -4000.0,
        "resolution": 0.00102341,
        "rScaler"   : 67.07019776,
        "gScaler"   : 0.26199296,
        "bScaler"   : 0.00102341
    },
    'earth'  : {
        "min"       : -11500.0,
        "resolution": 0.001264215,
        "rScaler"   : 82.85126656,
        "gScaler"   : 0.32363776,
        "bScaler"   : 0.00126421
    },
    'moon'   : {
        "min"       : -9500.0,
        "resolution": 0.001264215,
        "rScaler"   : 82.85126656,
        "gScaler"   : 0.32363776,
        "bScaler"   : 0.00126421
    },
    'mars'   : {
        "min"       : -8500.0,
        "resolution": 0.00178993,
        "rScaler"   : 117.30485248,
        "gScaler"   : 0.45822208,
        "bScaler"   : 0.00178993
    }
}


class TopographyQuantizer(BaseAlgorithm):

    # Parameters
    body: str = "anyrock"
    # metadata
    input_nbands: int = 1
    output_nbands: int = 3
    output_dtype: str = "uint8"

    def __call__(self, img: ImageData) -> ImageData:
        """Encode DEM into RGB"""
        quantizer = quantizers.get(self.body, "anyrock")
        z = img.data[0]
        z -= quantizer["min"]
        z /= quantizer["resolution"]
        d_z = z / 256
        dd_z = z // 256
        ddd_z = dd_z // 256
        b = (d_z - dd_z) * 256
        g = ((dd_z / 256) - ddd_z) * 256
        r = ((ddd_z / 256) - (ddd_z // 256)) * 256
        arr = stack([r, g, b]).astype(uint8)

        return ImageData(
            arr,
            img.mask,
            assets=img.assets,
            crs=img.crs,
            bounds=img.bounds,
        )
