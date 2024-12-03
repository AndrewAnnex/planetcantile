import json
import math
import os
import urllib.request
import warnings
from pathlib import Path
from functools import cached_property, lru_cache
from dataclasses import dataclass, field, asdict
import json

import numpy as np
from httpx import RemoteProtocolError

import pyproj.exceptions
from pyproj import CRS, Transformer, Proj

import morecantile
from morecantile.utils import meters_per_unit
from morecantile.models import crs_axis_inverted, variableMatrixWidth
import pyproj.exceptions
from pyproj import CRS, Transformer, Proj
from pyproj.crs import Ellipsoid, GeographicCRS, PrimeMeridian
from pyproj.crs.datum import CustomDatum, CustomEllipsoid
from pyproj.crs.coordinate_system import Ellipsoidal2DCS, Cartesian2DCS
from pyproj.crs.coordinate_operation import MercatorAConversion, EquidistantCylindricalConversion, PolarStereographicAConversion, PolarStereographicBConversion
from pyproj.crs.enums import Ellipsoidal2DCSAxis, Cartesian2DCSAxis
from pyproj.aoi import AreaOfInterest, BBox

# this api is currently pretty terrible to use 
from planet_crs_registry_client import Client, api
from  planet_crs_registry_client.models.wkt import WKT
from planet_crs_registry_client.api.browse_by_solar_body import get_solar_bodies_ws_solar_bodies_get
from planet_crs_registry_client.api.browse_by_solar_body import get_solar_body_ws_solar_bodies_solar_body_get


# 
CachedCRS = lru_cache(CRS.from_user_input)
CachedTransformer = lru_cache(Transformer.from_crs)

matrix_scale_quad     = [1,1]
matrix_scale_platecur = [2,1]
axis_lon_lat               = ["Lon", "Lat"]
axis_east_north            = ["easting", "northing"]

WGS84_CRS = CachedCRS(4326)

UNIT_DEGREE = "degree"

cs_long_lat = Ellipsoidal2DCS(
    axis=Ellipsoidal2DCSAxis.LONGITUDE_LATITUDE
).to_wkt(version='WKT2_2019')

cs_lat_long = Ellipsoidal2DCS(
    axis=Ellipsoidal2DCSAxis.LATITUDE_LONGITUDE
).to_wkt(version='WKT2_2019')

cs_en = Cartesian2DCS(
    axis=Cartesian2DCSAxis.EASTING_NORTHING
).to_wkt(version='WKT2_2019')
cs_en_psuedo = str(cs_en)
cs_en_psuedo = cs_en_psuedo.replace('(E)', 'easting (X)')
cs_en_psuedo = cs_en_psuedo.replace('(N)', 'northing (Y)')

cs_ne = Cartesian2DCS(
    axis=Cartesian2DCSAxis.NORTHING_EASTING
).to_wkt(version='WKT2_2019')
cs_ne_psuedo = str(cs_ne)
cs_ne_psuedo = cs_ne_psuedo.replace('(E)', 'easting (X)')
cs_ne_psuedo = cs_ne_psuedo.replace('(N)', 'northing (Y)')

cs_en_polar_north = Cartesian2DCS(
    axis=Cartesian2DCSAxis.NORTH_POLE_EASTING_SOUTH_NORTHING_SOUTH
).to_wkt(version='WKT2_2019')

cs_en_polar_south = Cartesian2DCS(
    axis=Cartesian2DCSAxis.SOUTH_POLE_EASTING_NORTH_NORTHING_NORTH
).to_wkt(version='WKT2_2019')


psuedo_mercator_usage = 'USAGE[SCOPE["Web mapping and visualisation."],AREA["World between 85.06 S and 85.06 N."],BBOX[-85.0511287,-180.0,85.0511287,180.0]]'
# TODO look into better mercator stuff
mercator_usage = 'USAGE[SCOPE["Very small scale conformal mapping."],AREA["World between 85.06 S and 85.06 N."],BBOX[-85.0511287,-180.0,85.0511287,180.0]]'
# https://spatialreference.org/ref/epsg/3857/prettywkt2.txt
# https://desktop.arcgis.com/en/arcmap/latest/map/projections/mercator.htm
psuedo_mercator = \
        'CONVERSION["Popular Visualisation Pseudo-Mercator",' \
        'METHOD["Popular Visualisation Pseudo Mercator",' \
        'ID["EPSG",1024]],' \
        'PARAMETER["Latitude of natural origin",0,' \
        'ANGLEUNIT["degree",0.0174532925199433],' \
        'ID["EPSG",8801]],' \
        'PARAMETER["Longitude of natural origin",0,' \
        'ANGLEUNIT["degree",0.0174532925199433],' \
        'ID["EPSG",8802]],' \
        'PARAMETER["False easting",0,' \
        'LENGTHUNIT["metre",1],' \
        'ID["EPSG",8806]],' \
        'PARAMETER["False northing",0,' \
        'LENGTHUNIT["metre",1],' \
        'ID["EPSG",8807]]]' 


#https://spatialreference.org/ref/epsg/3395/prettywkt2.txt
mercator_a = MercatorAConversion().to_wkt(version='WKT2_2019').replace('unknown', 'World Mercator')

equidistant_cylindrical =  EquidistantCylindricalConversion().to_wkt(version='WKT2_2019').replace('unknown', 'World Equidistant Cylindrical')


## Polar Projections 
polar_a_south = PolarStereographicAConversion(
    latitude_natural_origin=-90,
    scale_factor_natural_origin=1.0
).to_wkt(version='WKT2_2019').replace('unknown', 'Universal Polar Stereographic South')

polar_a_north = PolarStereographicAConversion(
    latitude_natural_origin=90,
    scale_factor_natural_origin=1.0
).to_wkt(version='WKT2_2019').replace('unknown', 'Universal Polar Stereographic North')

polar_north_usage = 'USAGE[SCOPE["North Polar Area {}"],AREA["{} between 80.0 N and 90.00 N."],BBOX[80.0,-180.0,90.0,180.0]]'
polar_south_usage = 'USAGE[SCOPE["South Polar Area {}"],AREA["{} between 80.0 S and 90.00 S."],BBOX[-90.0,-180.0,-80.0,180.0]]'


def coalesing_coefficients(z):
    bottom = 2 ** np.arange(1, z+1)
    return np.concatenate((bottom[::-1], bottom))


def coalesing_tile_rows(z):
    max_row = 2 ** (z + 1) - 1
    top_min_rows = np.concatenate(([0], 2 ** np.arange(z-1)))
    top_max_rows = np.cumsum(top_min_rows)
    bot_max_rows = max_row - top_min_rows
    bot_min_rows = max_row - top_max_rows
    min_rows = np.hstack((top_min_rows, bot_min_rows[::-1]))
    max_rows = np.hstack((top_max_rows, bot_max_rows[::-1]))
    return min_rows, max_rows


def get_variable_matrix_widths(z):
    coefficients = coalesing_coefficients(z)
    if len(coefficients) == 0:
        return []
    min_rows, max_rows = coalesing_tile_rows(z)
    for c, min_r, max_r in zip(coefficients, min_rows, max_rows):
        yield variableMatrixWidth(coalesce = c.item(), minTileRow=min_r.item(), maxTileRow=max_r.item())

def get_geo_type(crs: CRS):
    geotype = 'GEODCRS' if 'Ocentric' in crs.name else 'GEOGCRS'
    return geotype

def convert_crs(crs: CRS, scope="unknown.", coalesce: bool = False)-> CRS:
    # if the CRS is a 00 code, it is a "spherical ellipsoid" so use "GEOGCRS" but use geodetic coord type
    # if ths CRS is a 01 code, it is an "ellipsoid" so use "GEOGCRS" and use geodetic coord type
    # if the CRS is a 02 code, it is an "ellipsoid" but use geocentric coord type and "GEODCRS"
    name = crs.name.rstrip()
    if name[-1] != ' ':
        name = f'{name} '
    datum = crs.datum.to_wkt(version='WKT2_2019')
    remark = f'REMARK["{crs.remarks}{" Coalesced" if coalesce else ''}"]'
    # GEODCRS is use by all ocentric coordinates
    GEO_TYPE = get_geo_type(crs)
    tmp_wkt = f'{GEO_TYPE}["{name}XY",{datum},{cs_long_lat},SCOPE["{scope}"],AREA["Whole of {scope}"],BBOX[-90,-180,90,180],{remark}]'
    coord_type = 'geodetic' if GEO_TYPE == 'GEOGCRS' else 'planetocentric'
    paren_name_lon = '(Lon)' if GEO_TYPE == 'GEOGCRS' else '(V)'
    paren_name_lat = '(Lat)' if GEO_TYPE == 'GEOGCRS' else '(U)'
    tmp_wkt = tmp_wkt.replace('longitude', f'{coord_type} longitude {paren_name_lon}')
    tmp_wkt = tmp_wkt.replace('latitude', f'{coord_type} latitude {paren_name_lat}')
    return CachedCRS(tmp_wkt)

def create_converted_crs(wktobj: WKT, coalesce: bool = False):
    bodyname = wktobj.solar_body
    old_code = wktobj.code
    old_crs = CachedCRS(wktobj.wkt)
    return convert_crs(old_crs, scope=bodyname, coalesce=coalesce)


def _bisect_laititude(transformer: callable, low=80.0, high=90.0, tolerance=1e-6, reverse=False):
    """
    Finds the lowest latitude for the given pole that works
    :param func: The function to evaluate.
    :param low: The lower bound to start the search (known to return infinity).
    :param high: The upper bound to start the search (known not to return infinity).
    :param tolerance: The precision of the result.
    :return: The largest value that does not return infinity.
    """
    is_north = low > 0
    while np.abs(high - low) > tolerance:
        mid = (low + high) / 2
        coord = (mid, 45) if reverse else (45, mid)
        result = transformer.transform(*transformer.transform(*coord), direction='INVERSE')
        res = result[1 if reverse else 0]
        if math.isinf(res):
            # move the lower boundary to the mid so consider values above this
            if is_north:
                low = mid
            else:
                high = mid
        else:
            # We had an okay mid point so we can move the upper boundary down
            if is_north:
                high = mid   
            else:
                low = mid
    # The smallest value that returns inf is slightly above 'low'
    return high

def determine_FE_FN(crs: CRS, in_north=True, initial_latitude: float = 80.0):
    """
    This is supposed to determine correct false easting and northings for the polar stereographic
    projections but I am no longer sure this makes any good sense or not

    :param crs: _description_
    :param in_north: _description_, defaults to True
    :param initial_latitude: _description_, defaults to 80.0
    :return: _description_
    """
    if not in_north:
        initial_latitude = -np.abs(initial_latitude)
    transformer = CachedTransformer(crs.geodetic_crs, crs, always_xy=True, allow_ballpark=False)
    forward = transformer.transform(45, initial_latitude)
    asint = int(abs(forward[0]))
    digits = len(str(asint))
    assert digits > 1
    f = round(asint,-(digits-1))
    forward = (f, f)
    # determine invserse to get the latitude
    backward = transformer.transform(*forward, direction='INVERSE')
    final_latitude = backward[-1]
    # latitude can be inf/-inf, if so you need to find a latitude (closer to respective poll that doesn't return inf)
    if math.isinf(final_latitude):
        if in_north:
            _lat = _bisect_laititude(transformer, low=80.0, high=90.0)
        else: 
            _lat = _bisect_laititude(transformer, low=-90.0, high=-80.0)
        return determine_FE_FN(crs, in_north=in_north, initial_latitude=_lat)
    # return the (FE, FN), and latitude limit
    return forward, final_latitude


def convert_crs_equidistantcylindrical(wktobj: WKT, coalesce: bool = False)-> CRS:
    bodyname = wktobj.solar_body
    # get the CRS   
    crs = CachedCRS(wktobj.wkt)
    name = crs.name.rstrip()
    name = f'{name} / Equidistant Cylindrical'
    # construct basegeogcrs
    datum = crs.datum
    basegeogcrs = f'BASE{get_geo_type(crs)}["{datum.name}",{datum.to_wkt(version='WKT2_2019')}]'
    # construct the conversion
    conversion = equidistant_cylindrical
    # construct the coordinate system, easting (X) and northing (Y) so re-use psuedo's cs
    cs = cs_en_psuedo
    # construct the usage
    usage = f'SCOPE["{bodyname} graticule coordinates expressed in simple Cartesian form."],AREA["Whole of {bodyname}"],BBOX[-90,-180,90,180]'
    # make the new remark
    remark = f'REMARK["{crs.remarks}{" Coalesced" if coalesce else ''}"]'
    tmp_wkt = f'PROJCRS["{name}",{basegeogcrs},{conversion},{cs},{usage},{remark}]'
    return CachedCRS(tmp_wkt)


def convert_crs_north_polar(wktobj: WKT)-> CRS:
    # get the CRS   
    crs = CachedCRS(wktobj.wkt)
    name = crs.name.rstrip()
    # construct basegeogcrs
    datum = crs.datum
    basegeogcrs = f'BASE{get_geo_type(crs)}["{datum.name}",{datum.to_wkt(version='WKT2_2019')}]'
    # construct the conversion # TODO add false northing and easting
    conversion = polar_a_north
    # construct the coordinate system
    cs = cs_en_polar_north
    # construct the usage
    usage = polar_north_usage.format(wktobj.solar_body, wktobj.solar_body)
    # make the new remark
    remark = f'REMARK["{crs.remarks}"]'
    # make the new id
    #_id = f'ID["IAU",{new_id},2015]'
    tmp_wkt = f'PROJCRS["{name}",{basegeogcrs},{conversion},{cs},{usage},{remark}]'
    # construct false northing and easting
    (FE, FN), latitude = determine_FE_FN(CachedCRS(tmp_wkt), in_north=True)
    ################################################################################
    # construct final wkt
    _polar_north_usage = 'USAGE[SCOPE["North Polar Area {}"],AREA["{} between {} N and 90.00 N."],BBOX[{},-180.0,90.0,180.0]]'.format(wktobj.solar_body, wktobj.solar_body, latitude, latitude)
    _polar_a_north = PolarStereographicAConversion(
        latitude_natural_origin=90.0,
        longitude_natural_origin=0.0,
        scale_factor_natural_origin=1.0,
        false_easting=FE,
        false_northing=FN,
    ).to_wkt(version='WKT2_2019').replace('unknown', 'Universal Polar Stereographic North')
    final_wkt = f'PROJCRS["{name}",{basegeogcrs},{_polar_a_north},{cs},{_polar_north_usage},{remark}]'
    ##################################################################################
    return CachedCRS(final_wkt)

def convert_crs_south_polar(wktobj: WKT)-> CRS:
    # get the CRS   
    crs = CachedCRS(wktobj.wkt)
    name = crs.name.rstrip()
    # construct basegeogcrs
    datum = crs.datum
    basegeogcrs = f'BASE{get_geo_type(crs)}["{datum.name}",{datum.to_wkt(version='WKT2_2019')}]'
    # construct the conversion # TODO add false northing and easting
    conversion = polar_a_south
    # construct the coordinate system
    cs = cs_en_polar_south
    # construct the usage
    usage = polar_south_usage.format(wktobj.solar_body, wktobj.solar_body)
    # make the new remark
    remark = f'REMARK["{crs.remarks}"]'
    # make the new id
    tmp_wkt = f'PROJCRS["{name}",{basegeogcrs},{conversion},{cs},{usage},{remark}]'
    # construct false northing and easting
    (FE, FN), latitude = determine_FE_FN(CachedCRS(tmp_wkt), in_north=False)
    ################################################################################
    # construct final wkt
    _polar_south_usage = 'USAGE[SCOPE["South Polar Area {}"],AREA["{} between {} S and 90.00 S."],BBOX[-90.0,-180.0,{},180.0]]'.format(wktobj.solar_body, wktobj.solar_body, latitude, latitude)
    _polar_a_south = PolarStereographicAConversion(
        latitude_natural_origin=-90.0,
        longitude_natural_origin=0.0,
        scale_factor_natural_origin=1.0,
        false_easting=FE,
        false_northing=FN,
    ).to_wkt(version='WKT2_2019').replace('unknown', 'Universal Polar Stereographic South')
    final_wkt = f'PROJCRS["{name}",{basegeogcrs},{_polar_a_south},{cs},{_polar_south_usage},{remark}]'
    ##################################################################################
    return CachedCRS(final_wkt)

def convert_crs_psuedo_mercator(crs: CRS)-> CRS:
    name = crs.name.rstrip()
    name = f'{name} / Pseudo-Mercator'
    # construct basegeogcrs
    datum = crs.datum
    basegeogcrs = f'BASE{get_geo_type(crs)}["{datum.name}",{datum.to_wkt(version='WKT2_2019')}]'
    # construct the conversion
    conversion = psuedo_mercator
    # construct the coordinate system
    cs = cs_en_psuedo
    # construct the usage
    usage = psuedo_mercator_usage
    # make the new remark
    remark = f'REMARK["{crs.remarks}"]'
    # make the new id
    #_id = f'ID["IAU",{new_id},2015]'
    tmp_wkt = f'PROJCRS["{name}",{basegeogcrs},{conversion},{cs},{usage},{remark}]'
    return CachedCRS(tmp_wkt)

def convert_crs_world_mercator(crs: CRS)-> CRS:
    name = crs.name.rstrip()
    name = f'{name} / World Mercator'
    # construct basegeogcrs
    datum = crs.datum
    basegeogcrs = f'BASE{get_geo_type(crs)}["{datum.name}",{datum.to_wkt(version='WKT2_2019')}]'
    # construct the conversion
    conversion = mercator_a
    # construct the coordinate system
    cs = cs_en
    # construct the usage
    usage = mercator_usage
    # make the new remark
    remark = f'REMARK["{crs.remarks}"]'
    # make the new id
    #_id = f'ID["IAU",{new_id},2015]'
    tmp_wkt = f'PROJCRS["{name}",{basegeogcrs},{conversion},{cs},{usage},{remark}]'
    return CachedCRS(tmp_wkt)


@dataclass()
class Tmsparams(object):
    # crs_wkt object from planetarycrsregistry
    crs_wkt: WKT
    # Tile Matrix Set coordinate reference system
    crs: CRS
    # Width of each tile of this tile matrix in pixels (default is 256).
    tile_width: int = 256
    # Height of each tile of this tile matrix in pixels (default is 256).
    tile_height: int = 256
    # Tile Matrix Set minimum zoom level (default is 0).
    minzoom: int = 0
    # Tile Matrix Set maximum zoom level (default is 30).
    maxzoom: int = 30

    def __post_init__(self):
        # update the minimum zoom level to 1 for coalesced grids
        if self.coalesce:
            self.minzoom = 1
        # update the crs if geocentric:
        if self.is_geocentric() and not self.is_sphere():
            wkt2 = self.crs.to_wkt(version='WKT2_2019').replace('GEOGCRS', 'GEODCRS')
            if 'planetocentric longitude' not in wkt2:
                wkt2 = wkt2.replace('longitude', 'planetocentric longitude (V)')
                wkt2 = wkt2.replace('latitude', 'planetocentric latitude (U)')
            wkt2 = wkt2.replace('ellipsoidal', 'spherical')
            self.crs = CachedCRS(wkt2)


    @property
    def coalesce(self):
        # Coalesce is only desireable for Geographic or EquidistantCylindrical projections 
        return 'Coalesced' in self.crs.remarks

    @property
    def geographic_crs(self):
        if self.is_geocentric(): 
            if self.is_non_projected():
                return self.crs 
            else:
                wkt2 = self.crs.geodetic_crs.to_wkt(version='WKT2_2019').replace('GEOGCRS', 'GEODCRS')
                if 'planetocentric longitude' not in wkt2:
                    wkt2 = wkt2.replace('longitude', 'planetocentric longitude (V)')
                    wkt2 = wkt2.replace('latitude', 'planetocentric latitude (U)')
                wkt2 = wkt2.replace('ellipsoidal', 'spherical')
                return CachedCRS(wkt2)
        elif self.is_sphere():
            # we have a spherical ellipsoid so force to use geographic coordinates
            wkt2 = self.crs.geodetic_crs.to_wkt(version='WKT2_2019').replace('GEODCRS', 'GEOGCRS')
            return CachedCRS(wkt2)
        else:
            geo_crs = self.crs.geodetic_crs
            return geo_crs     
    
    @property
    def extent_crs(self):
        return self.geographic_crs

    def is_non_projected(self)-> bool:
        return self.crs.coordinate_operation is None
    
    def is_projected(self)-> bool:
        return not self.is_non_projected()

    def is_equidistant(self)-> bool:
        co = self.crs.coordinate_operation
        if co is None:
            # all geographic/geocentric CRSs are treated as equidistant
            return True
        else:
            # only true if Equidistant is actually in the name
            return 'Equidistant' in co.method_name
  
    def is_polar(self)-> bool:
        co = self.crs.coordinate_operation
        if co is not None:
            return 'Polar' in co.method_name
        else:
            return False
        
    def is_polar_north(self)-> bool:
        is_polar = self.is_polar()
        if is_polar:
            return 'North' in self.crs.coordinate_operation.name
    
    def is_polar_south(self)-> bool:
        is_polar = self.is_polar()
        if is_polar:
            return 'South' in self.crs.coordinate_operation.name
    
    def is_web_mercator(self)-> bool:
        co = self.crs.coordinate_operation
        if co is not None:
            return 'Pseudo Mercator' in co.method_name
        else: 
            return False
        
    def is_mercator_varient_a(self)-> bool:
        co = self.crs.coordinate_operation
        if co is not None:
            return 'Mercator (variant A)' == co.method_name
        else: 
            return False
        
    def get_ellipsoid_kind(self)-> str:
        if self.is_sphere():
            return 'Sphere'
        elif self.is_geocentric():
            return 'Ocentric'
        else:
            return 'Ographic'
        
    def get_projection_name(self)-> str:
        kind = self.get_ellipsoid_kind()
        if self.coalesce:
            kind = f'{kind}Coalesced'
        if self.is_polar_north():
            return f'NorthPolar{kind}'
        elif self.is_polar_south():
            return f'SouthPolar{kind}'
        elif self.is_web_mercator():
            return f'WebMercator{kind}'
        elif self.is_mercator_varient_a():
            return f'Mercator{kind}'
        elif self.is_non_projected():
            # TODO differentiate better?
            return f'Geographic{kind}'
        else:
            return f'EquidistantCylindrical{kind}'
        
    def is_sphere(self):
        return 'Sphere' in self.crs.datum.ellipsoid.name

    def is_geocentric(self):
        return not self.is_sphere() and 'Ocentric' in self.crs.to_wkt()
    
    def is_geographic(self):
        return not self.is_sphere() and 'Ographic' in self.crs.to_wkt()
    
    @property
    def id(self)-> str:
        body = self.crs_wkt.solar_body
        projection = self.get_projection_name()
        return f'{body}{projection}'.replace(' ','')
    
    @property
    def title(self)-> str:
        ellispoid_name = self.crs.ellipsoid.name
        axes = ''.join(self.ordered_axes)
        projection_name = self.get_projection_name()
        return f"{ellispoid_name} {axes} {projection_name}"

    @property
    def matrix_scale(self)-> list[int]:
        if self.is_equidistant():
            return [2, 1]
        else:
            return [1, 1]

    @property
    def ordered_axes(self)-> list[str]:
        if self.is_web_mercator():
            return ["X", "Y"]
        elif self.is_polar() or self.is_mercator_varient_a():
            return ["E", "N"]
        elif self.is_non_projected():
            return ["Lon", "Lat"]
        else:
            return ["E", "N"]
        
    @staticmethod
    def get_coord_order(crs: CRS):
        coord_sys = crs.coordinate_system
        axis_list = coord_sys.axis_list
        first = axis_list[0]
        if first.direction == 'north':
            return 'YX'
        else: 
            return 'XY'

    
    @property
    def extent(self)-> tuple[float, float, float, float]:
        # TODO I might not actually need the extent 
        area_of_use = self.crs.area_of_use
        if self.is_web_mercator() or self.is_mercator_varient_a():
            # need to ensure the point of origins are identical x and y
            extent_crs = self.extent_crs
            transformer = CachedTransformer(extent_crs, self.crs, always_xy=True, allow_ballpark=False)
            if self.get_coord_order(extent_crs) == 'YX':
                # pyproj/proj doesn't respect axis order for geocentric coordinates
                if self.is_geocentric():
                    min_x, _   = transformer.transform(0, -180)
                    min_lat, _ = transformer.transform(0, min_x, direction='INVERSE')
                else:
                    min_x, _ = transformer.transform(-180, 0)
                    _, min_lat = transformer.transform(0, min_x, direction='INVERSE')
            else:
                min_x, _ = transformer.transform(-180, 0)
                _, min_lat = transformer.transform(0, min_x, direction='INVERSE')
            bounds = (-180, min_lat, 180, -min_lat)
            return bounds
        elif area_of_use is not None and not self.is_polar():
            return area_of_use.bounds
        else:
            # need to manually define these
            if self.is_polar_north():
                (FE, FN), around_80_north = determine_FE_FN(self.crs, in_north=True)
                return (-180, around_80_north, 180, 90) #return (0, 0, 2*FE, 2*FN)
            elif self.is_polar_south():
                (FE, FN), around_80_south = determine_FE_FN(self.crs, in_north=False)
                return (-180, -90, 180, around_80_south)
            else:
                return (-180, -90, 180, 90)

    @staticmethod
    def _add_coalesce_to_tms(tms: morecantile.TileMatrixSet) -> morecantile.TileMatrixSet:
        for z in range(1, tms.maxzoom + 1):
            variableMatrixWidths = list(get_variable_matrix_widths(z-1))
            if len(variableMatrixWidths) > 0:
                tms.matrix(z).variableMatrixWidths = variableMatrixWidths
        # well actually the tms is already updated but might as well return
        return tms 
        
    def make_tms(self)-> morecantile.TileMatrixSet:
        tms = morecantile.TileMatrixSet.custom(
            id=self.id,
            title=self.title,
            crs=self.crs,
            geographic_crs=self.geographic_crs,
            extent_crs=self.extent_crs,
            extent=self.extent,
            ordered_axes=self.ordered_axes,
            minzoom=self.minzoom,
            maxzoom=self.maxzoom,
            matrix_scale=self.matrix_scale
        )
        if self.coalesce:
            tms = self._add_coalesce_to_tms(tms)
        return tms
    
    def make_tms_dict(self)-> dict:
        tms_dict = self.make_tms().model_dump(exclude_none=True)
        # make any adjustments here needed before saving as json to disk
        crs_wkt = self.crs.to_wkt(version='WKT2_2019').replace('GEOGCRS', get_geo_type(self.crs))
        gcrs_wkt = self.geographic_crs.to_wkt(version='WKT2_2019').replace('GEOGCRS', get_geo_type(self.crs))            
        tms_dict['crs'] = crs_wkt
        tms_dict['_geographic_crs'] = gcrs_wkt
        tms_dict['orderedAxes'] = self.ordered_axes
        # cleanup pointOfOrigins for all mercator codes, this is driven currently by the precision limits for the area_of_use 
        matrices = tms_dict['tileMatrices']
        if self.is_web_mercator() or self.is_mercator_varient_a():
            for m in matrices:
                x, y = m['pointOfOrigin']
                m['pointOfOrigin'] = (x, -x)
        # if a coalesced grid relabel the tile id's to be as expected
        if self.coalesce:
            for m in matrices:
                m['id'] = str(int(m['id'])-1)
        # exclude any zoom levels where 1 cm cannot be well resolved via approximation 2.5 mm
        mmpu = (1.0 / (meters_per_unit(self.crs) * 1000)) 
        matrices = [m for m in matrices if m['cellSize'] >= (2.5 * mmpu)]
        # return a new dict to re-order as needed
        return dict(
            id=tms_dict['id'],
            title=tms_dict['title'],
            crs=tms_dict['crs'],
            orderedAxes=tms_dict['orderedAxes'],
            tileMatrices=matrices,
        )


def make_crs_objs(crss_wkts: dict[str, WKT]):
    # 31 and 32 and 36 and 37 exist to correspond to 01, 02
    valid_code_postfixs = ['00', '01', '02']
    for valid_code in valid_code_postfixs:
        if valid_code in crss_wkts.keys():
            current_wkt = crss_wkts[valid_code]
            converted_crs = create_converted_crs(current_wkt)
            coalesced_converted_crs  = create_converted_crs(current_wkt, coalesce=True)
            # TODO should I retain explicitly geocentric/ spheroid codes? How?
            yield current_wkt, converted_crs
            yield current_wkt, coalesced_converted_crs
            yield current_wkt, convert_crs_world_mercator(converted_crs)
            yield current_wkt, convert_crs_psuedo_mercator(converted_crs)
            yield current_wkt, convert_crs_north_polar(current_wkt)
            yield current_wkt, convert_crs_south_polar(current_wkt)
            yield current_wkt, convert_crs_equidistantcylindrical(current_wkt)
            yield current_wkt, convert_crs_equidistantcylindrical(current_wkt, coalesce=True)
            
def make_tms_objs(crss_wkts: dict[str, WKT]):
    for wkt, crs in make_crs_objs(crss_wkts):
        yield Tmsparams(crs_wkt=wkt, crs=crs)


def add_coalesce_to_tms(tms: morecantile.TileMatrixSet) -> morecantile.TileMatrixSet:
    for z in range(1, tms.maxzoom + 1):
        variableMatrixWidths = list(get_variable_matrix_widths(z-1))
        if len(variableMatrixWidths) > 0:
            tms.matrix(z).variableMatrixWidths = variableMatrixWidths
    # well actually the tms is already updated but might as well return
    return tms 


def is_sphere(crs: CRS):
    return 'Sphere' in crs.datum.ellipsoid.name

def is_geocentric(crs: CRS):
    return not is_sphere(crs) and 'Ocentric' in crs.to_wkt()

def is_geographic(crs: CRS):
    return not is_sphere(crs) and 'Ographic' in crs.to_wkt()

def get_ellipsoid_kind(crs: CRS)-> str:
    if is_sphere(crs):
        return 'Sphere'
    elif is_geocentric(crs):
        return 'Ocentric'
    else:
        return 'Ographic'

def get_coord_order(crs: CRS):
    coord_sys = crs.coordinate_system
    axis_list = coord_sys.axis_list
    first = axis_list[0]
    if first.direction == 'north':
        return 'YX'
    else: 
        return 'XY'

def get_max_zoom(crs: CRS, aspect: int = 2)-> int:
    min_size_m = 0.005 # 5 mm
    max_zoom = 2
    circumference_meters = (2 * math.pi * crs.ellipsoid.semi_major_metre)
    # TODO this is almost correct but may need to use the 2:1 or quad switch here also
    while circumference_meters/(256*aspect*2**max_zoom) >= min_size_m:
        max_zoom+=1
    if max_zoom > 30:
        max_zoom = 30
    return max_zoom



def make_tms(crss_wkts: dict[str, WKT]):
    valid_code_postfixs = ['00', '01', '02', 
                           '10', '11', '12', 
                           '30', '31', '32',
                           '35', '36', '37',
                           '90']
    for valid_code in valid_code_postfixs:
        if valid_code in crss_wkts.keys():
            current_wkt_obj = crss_wkts[valid_code]
            current_wkt = current_wkt_obj.wkt
            body_name = current_wkt_obj.solar_body.replace(" ", "")
            crs = CRS.from_user_input(current_wkt)
            match valid_code:
                case '90':
                    # mercator codes
                    id = f'{body_name}Mercator{get_ellipsoid_kind(crs)}'
                    # compute the needed extent
                    transformer = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True, allow_ballpark=False)
                    min_x, _ = transformer.transform(-180, 0)
                    _, min_lat = transformer.transform(0, min_x, direction='INVERSE')
                    tms_mercator = morecantile.TileMatrixSet.custom(
                        extent=[-180, min_lat, 180, -min_lat], # todo use custom logic above to determine best min/max latitude
                        extent_crs=crs.geodetic_crs,
                        matrix_scale=matrix_scale_quad,
                        crs = crs,
                        orderedAxes=["E", "N"],
                        id = id,
                        title = id,
                        maxzoom = get_max_zoom(crs, aspect=1)
                    )
                    yield tms_mercator
                    # TODO web mercator custom
                case '00' | '01' | '02':
                    # Geographic codes
                    id = f'{body_name}Geographic{get_ellipsoid_kind(crs)}'
                    tms_geographic = morecantile.TileMatrixSet.custom(
                        extent=[-180, -90, 180, 90],
                        extent_crs=crs.geodetic_crs,
                        matrix_scale=matrix_scale_platecur,
                        crs = crs,
                        orderedAxes=["Lat", "Lon"],
                        id = id,
                        title = id,
                        maxzoom = get_max_zoom(crs, aspect=2)
                    )
                    yield tms_geographic
                    # make the coalesced tms
                    id = f'{tms_geographic.id}Coalesced'
                    tms_geographic_coalesced = morecantile.TileMatrixSet.custom(
                        extent=[-180, -90, 180, 90],
                        extent_crs=crs.geodetic_crs,
                        matrix_scale=matrix_scale_platecur,
                        crs = crs,
                        orderedAxes=["Lat", "Lon"],
                        id = id,
                        title = id,
                        maxzoom = get_max_zoom(crs, aspect=2),
                        minzoom = 1
                    )
                    tms_geographic_coalesced = add_coalesce_to_tms(tms_geographic_coalesced)
                    yield tms_geographic_coalesced
                    # TODO coalesced tmss 
                case '10' | '11' | '12':
                    # Equirectangular codes
                    id = f'{body_name}EquidistantCylindrical{get_ellipsoid_kind(crs)}'
                    tms_equidistant = morecantile.TileMatrixSet.custom(
                        extent = [-180, -90, 180, 90],
                        extent_crs = crs.geodetic_crs,
                        matrix_scale = matrix_scale_platecur,
                        crs = crs,
                        orderedAxes = ["E", "N"],
                        id = id,
                        title = id,
                        maxzoom = get_max_zoom(crs, aspect=2)
                    )
                    yield tms_equidistant
                     # make the coalesced tms
                    id = f'{tms_equidistant.id}Coalesced'
                    tms_equidistant_coalesced = morecantile.TileMatrixSet.custom(
                        extent = [-180, -90, 180, 90],
                        extent_crs = crs.geodetic_crs,
                        matrix_scale = matrix_scale_platecur,
                        crs = crs,
                        orderedAxes = ["E", "N"],
                        id = id,
                        title = id,
                        maxzoom = get_max_zoom(crs, aspect=2),
                        minzoom = 1
                    )
                    tms_equidistant_coalesced = add_coalesce_to_tms(tms_equidistant_coalesced)
                    yield tms_equidistant_coalesced
                case '30' | '31' | '32':
                    # North Polar codes
                    try:
                        (FE, FN), around_80_north = determine_FE_FN(crs, in_north=True)
                    except RecursionError:
                        around_80_north = 80.0
                    id = f'{body_name}NorthPolar{get_ellipsoid_kind(crs)}'
                    tms_northpolar = morecantile.TileMatrixSet.custom(
                        extent = [-180, around_80_north, 180, 90],
                        extent_crs = crs.geodetic_crs,
                        #extent = [0, 0, 2*FE, 2*FN],
                        matrix_scale = matrix_scale_quad,
                        crs = crs,
                        orderedAxes = ["E", "N"],
                        id = id,
                        title = id,
                        maxzoom = get_max_zoom(crs, aspect=1)
                    )
                    yield tms_northpolar
                case '35' | '36' | '37':
                    # South Polar codes
                    try:
                        (FE, FN), around_80_south = determine_FE_FN(crs, in_north=False)
                    except RecursionError:
                        around_80_south = -80.0
                    id = f'{body_name}SouthPolar{get_ellipsoid_kind(crs)}'
                    tms_southpolar = morecantile.TileMatrixSet.custom(
                        extent=[-180, -90, 180, around_80_south],
                        extent_crs=crs.geodetic_crs,
                        #extent = [0, 0, 2*FE, 2*FN],
                        matrix_scale = matrix_scale_quad,
                        crs = crs,
                        orderedAxes = ["E", "N"],
                        id = id,
                        title = id,
                        maxzoom = get_max_zoom(crs, aspect=1)
                    )
                    yield tms_southpolar
                case _:
                    pass

def main():
    # TODO:
    # 1. Adjust _geographic_crs's to be LongLat/XY order possibly, possibly .geodetic_crs is doing something non-ideal right now that means the TMSs are not using geocentric long/lat yet when given sphereical bodies
    #  It may be that this is working as expected and that I don't need to actually differentiate these as only the geoid is needed to define the new projections
    # 9. Look again how 1026 compares to 1024 and Mercator varient A
    # 10. Geocentric codes are all suspect at the moment due to coordinate axis swap issue, possible bug in proj with certain codes
    # 11. Will want to rexamine how custom my custom codes truely are to reduce logic here, maybe a lot of it can go away eventually
    # 12. Why did I use WKT2 everywhere? I should have use projjson internally. consider a refactor
    #valid_code_postfixs = {'00', '01', '02'}
    valid_code_postfixs = {'00', '01', '02', 
                           '10', '11', '12', 
                           '30', '31', '32',
                           '35', '36', '37',
                           '90'}
    client = Client(base_url='http://voparis-vespa-crs.obspm.fr:8080/')
    # get all the bodies
    bodies = get_solar_bodies_ws_solar_bodies_get.sync(client=client)
    for body in bodies:
        try:
            print(body)
            crss_wkts = get_solar_body_ws_solar_bodies_solar_body_get.sync(body, client=client)
            # sort by code
            crss_wkts = sorted(crss_wkts, key= lambda _: _.code)
            # grab the 00, 01, 02, 30, 35 codes. 01 and 02 codes may not be there
            crss_wkts = {str(_.code)[-2:]: _ for _ in crss_wkts if str(_.code)[-2:] in valid_code_postfixs}
            # convert to tms params
            # tmsparams = list(make_tms_objs(crss_wkts))
            # for tmsp in tmsparams:
            #     tms_dict = tmsp.make_tms_dict()
            #     with open(f"./v4/{tms_dict['id']}.json", "w") as dst:
            #         json.dump(tms_dict, dst, indent=4)
            #         print(f"wrote {dst.name}")
            
            for tms in make_tms(crss_wkts):
                with open(f"./v4/{tms.id}.json", "w") as dst:
                    model_dict = tms.model_dump(exclude_none=True)
                    # offset the tilematrix indexes for the coalesced grids
                    if 'Coalesced' in model_dict['id']:
                        for m in model_dict['tileMatrices']:
                            m['id'] = str(int(m['id'])-1)
                    # update the point of origin for mercator codes to be 1:1
                    if 'Mercator' in model_dict['id']:
                        for m in model_dict['tileMatrices']:
                            m['pointOfOrigin'] = (m['pointOfOrigin'][0], -m['pointOfOrigin'][0])
                    json.dump(model_dict, dst, indent=4)
                    print(f"wrote {dst.name}")


        except pyproj.exceptions.ProjError as pe:
            print(f'Failure with body {body} in constructing proj exceptions')
            raise pe
        except RemoteProtocolError as rpe:
            print(f'Failure queriying as the server disconnected without a response for {body}', rpe)
        

if __name__ == '__main__':
    main()