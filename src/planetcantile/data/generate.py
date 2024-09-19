import json
import math
import os
import urllib.request
import warnings
from pathlib import Path
from functools import cached_property
from dataclasses import dataclass, field, asdict
import json

import numpy as np

import pyproj.exceptions
from pyproj import CRS, Transformer, Proj

import morecantile
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

matrix_scale_quad     = [1,1]
matrix_scale_platecur = [2,1]
axis_lon_lat               = ["Lon", "Lat"]
axis_east_north            = ["easting", "northing"]

WGS84_CRS = CRS.from_epsg(4326)

UNIT_DEGREE = "degree"

cs_long_lat = Ellipsoidal2DCS(
    axis=Ellipsoidal2DCSAxis.LONGITUDE_LATITUDE
).to_wkt(version='WKT2_2019')

cs_en = Cartesian2DCS(
    axis=Cartesian2DCSAxis.EASTING_NORTHING
).to_wkt(version='WKT2_2019')
cs_en_psuedo = str(cs_en)
cs_en_psuedo = cs_en_psuedo.replace('(E)', 'easting (X)')
cs_en_psuedo = cs_en_psuedo.replace('(N)', 'northing (Y)')


cs_en_polar_north = Cartesian2DCS(
    axis=Cartesian2DCSAxis.NORTH_POLE_EASTING_SOUTH_NORTHING_SOUTH
).to_wkt(version='WKT2_2019')

cs_en_polar_south = Cartesian2DCS(
    axis=Cartesian2DCSAxis.SOUTH_POLE_EASTING_NORTH_NORTHING_NORTH
).to_wkt(version='WKT2_2019')

# cs_en_polar = str(cs_en)
# cs_en_polar = cs_en_polar.replace('(E)', 'E')
# cs_en_polar = cs_en_polar.replace('(N)', 'N')

psuedo_mercator_usage = 'USAGE[SCOPE["Web mapping and visualisation."],AREA["World between 85.06 S and 85.06 N."],BBOX[-85.85.0511287,-180.0,85.0511287,180.0]]'
# TODO look into better mercator stuff
mercator_usage = 'USAGE[SCOPE["Very small scale conformal mapping."],AREA["World between 85.06 S and 85.06 N."],BBOX[-85.85.0511287,-180.0,85.0511287,180.0]]'
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


def convert_crs(crs: CRS, geodetic=True, scope="unknown.", coalesce: bool = False)-> CRS:
    name = crs.name.rstrip()
    if name[-1] != ' ':
        name = f'{name} '
    datum = crs.datum.to_wkt(version='WKT2_2019')
    remark = f'REMARK["{crs.remarks}{" Coalesced" if coalesce else ''}"]'
    tmp_wkt = f'GEOGCRS["{name}XY",{datum},{cs_long_lat},SCOPE["{scope}"],AREA["Whole of {scope}"],BBOX[-90,-180,90,180],{remark}]'
    coord_type = 'geodetic' if geodetic else 'planetocentric'
    tmp_wkt = tmp_wkt.replace('longitude', f'{coord_type} longitude (Lon)')
    tmp_wkt = tmp_wkt.replace('latitude', f'{coord_type} latitude (Lat)')
    return CRS.from_wkt(tmp_wkt)

def create_converted_crs(wktobj: WKT, coalesce: bool = False):
    bodyname = wktobj.solar_body
    old_code = wktobj.code
    old_crs = CRS.from_wkt(wktobj.wkt)
    geodetic = not str(old_code).endswith('2')
    return convert_crs(old_crs, geodetic=geodetic, scope=bodyname, coalesce=coalesce)


def determine_FE_FN(crs: CRS, in_north=True):
    transformer = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
    forward = transformer.transform(45, 80.0 if in_north else -80.0)
    asint = int(abs(forward[0]))
    digits = len(str(asint))
    assert digits > 1
    f = round(asint,-(digits-1))
    forward = (f, f)
    # determine invserse to get the latitude
    backward = transformer.transform(*forward, direction='INVERSE')
    # return the (FE, FN), and latitude limit
    return forward, backward[-1]


def convert_crs_equidistantcylindrical(wktobj: WKT, coalesce: bool = False)-> CRS:
    bodyname = wktobj.solar_body
    # get the CRS   
    crs = CRS.from_wkt(wktobj.wkt)
    name = crs.name.rstrip()
    name = f'{name} / Equidistant Cylindrical'
    # construct basegeogcrs
    datum = crs.datum
    basegeogcrs = f'BASEGEOGCRS["{datum.name}",{datum.to_wkt(version='WKT2_2019')}]'
    # construct the conversion
    conversion = equidistant_cylindrical
    # construct the coordinate system, easting (X) and northing (Y) so re-use psuedo's cs
    cs = cs_en_psuedo
    # construct the usage
    usage = f'SCOPE["{bodyname} graticule coordinates expressed in simple Cartesian form."],AREA["Whole of {bodyname}"],BBOX[-90,-180,90,180]'
    # make the new remark
    remark = f'REMARK["{crs.remarks}{" Coalesced" if coalesce else ''}"]'
    tmp_wkt = f'PROJCRS["{name}",{basegeogcrs},{conversion},{cs},{usage},{remark}]'
    return CRS.from_wkt(tmp_wkt)


def convert_crs_north_polar(wktobj: WKT)-> CRS:
    # get the CRS   
    crs = CRS.from_wkt(wktobj.wkt)
    name = crs.name.rstrip()
    # construct basegeogcrs
    datum = crs.datum
    basegeogcrs = f'BASEGEOGCRS["{datum.name}",{datum.to_wkt(version='WKT2_2019')}]'
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
    (FE, FN), latitude = determine_FE_FN(CRS.from_wkt(tmp_wkt), in_north=True)
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
    return CRS.from_wkt(final_wkt)

def convert_crs_south_polar(wktobj: WKT)-> CRS:
    # get the CRS   
    crs = CRS.from_wkt(wktobj.wkt)
    name = crs.name.rstrip()
    # construct basegeogcrs
    datum = crs.datum
    basegeogcrs = f'BASEGEOGCRS["{datum.name}",{datum.to_wkt(version='WKT2_2019')}]'
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
    (FE, FN), latitude = determine_FE_FN(CRS.from_wkt(tmp_wkt), in_north=False)
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
    return CRS.from_wkt(final_wkt)

def convert_crs_psuedo_mercator(crs: CRS)-> CRS:
    name = crs.name.rstrip()
    name = f'{name} / Pseudo-Mercator'
    # construct basegeogcrs
    datum = crs.datum
    basegeogcrs = f'BASEGEOGCRS["{datum.name}",{datum.to_wkt(version='WKT2_2019')}]'
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
    return CRS.from_wkt(tmp_wkt)

def convert_crs_world_mercator(crs: CRS)-> CRS:
    name = crs.name.rstrip()
    name = f'{name} / World Mercator'
    # construct basegeogcrs
    datum = crs.datum
    basegeogcrs = f'BASEGEOGCRS["{datum.name}",{datum.to_wkt(version='WKT2_2019')}]'
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
    return CRS.from_wkt(tmp_wkt)


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

    @property
    def coalesce(self):
        # Coalesce is only desireable for Geographic or EquidistantCylindrical projections 
        return 'Coalesced' in self.crs.remarks

    @property
    def geographic_crs(self):
        # TODO this seems may need some work...
        return self.crs.geodetic_crs
    
    @property
    def extent_crs(self):
        return self.geographic_crs

    def is_non_projected(self)-> bool:
        return self.crs.coordinate_operation is None

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
        #breakpoint()
        return not self.is_sphere() and 'Ocentric' in self.crs.to_wkt()
    
    def is_geographic(self):
        return not self.is_sphere() and 'Ographic' in self.crs.to_wkt()
    
    @property
    def id(self)-> str:
        body = self.crs_wkt.solar_body
        projection = self.get_projection_name()
        return f'{body}{projection}'
    
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
    
    @property
    def extent(self)-> tuple[float, float, float, float]:
        # TODO I might not actually need the extent 
        area_of_use = self.crs.area_of_use
        if self.is_web_mercator() or self.is_mercator_varient_a():
            # need to ensure the point of origins are identical x and y
            transformer = Transformer.from_crs(self.extent_crs, self.crs, always_xy=True, allow_ballpark=False)
            min_x, _ = transformer.transform(-180,0)
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
        for z in range(1, tms.maxzoom+1):
            variableMatrixWidths = list(get_variable_matrix_widths(z))
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
        tms_dict['crs'] = self.crs.to_wkt(version='WKT2_2019')
        tms_dict['orderedAxes'] = self.ordered_axes
        tms_dict['_geographic_crs'] = self.geographic_crs.to_wkt(version='WKT2_2019')
        # cleanup pointOfOrigins for all mercator codes, this is driven currently by the precision limits for the area_of_use 
        matrices = tms_dict['tileMatrices']
        if self.is_web_mercator() or self.is_mercator_varient_a():
            for m in matrices:
                x, y = m['pointOfOrigin']
                m['pointOfOrigin'] = (x, -x)
        # return a new dict to re-order as needed
        return dict(
            id=tms_dict['id'],
            title=tms_dict['title'],
            crs=tms_dict['crs'],
            orderedAxes=tms_dict['orderedAxes'],
            tileMatrices=matrices,
            _geographic_crs=tms_dict['_geographic_crs']
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


def main():
    # TODO:
    # 1. Adjust _geographic_crs's to be LongLat/XY order possibly, possibly .geodetic_crs is doing something non-ideal right now that means the TMSs are not using geocentric long/lat yet
    #  It may be that this is working as expected and that I don't need to actually differentiate these as only the geoid is needed to define the new projections
    # 4. TESTS FOR GOODNESS SAKE

    valid_code_postfixs = {'00', '01', '02'}
    client = Client(base_url='http://voparis-vespa-crs.obspm.fr:8080/')
    # get all the bodies
    #bodies = get_solar_bodies_ws_solar_bodies_get.sync(client=client)
    bodies = ['Moon', 'Mars']
    for body in bodies:
        try:
            crss_wkts = get_solar_body_ws_solar_bodies_solar_body_get.sync(body, client=client)
            # sort by code
            crss_wkts = sorted(crss_wkts, key= lambda _: _.code)
            # grab the 00, 01, 02, 30, 35 codes. 01 and 02 codes may not be there
            crss_wkts = {str(_.code)[-2:]: _ for _ in crss_wkts if str(_.code)[-2:] in valid_code_postfixs}
            # conver to tms params
            tmsparams = list(make_tms_objs(crss_wkts))
            for tmsp in tmsparams:
                #breakpoint()
                tms_dict = tmsp.make_tms_dict()
                with open(f"./v4/{tms_dict['id']}.json", "w") as dst:
                    json.dump(tms_dict, dst, indent=4, ensure_ascii=True)
                    print(f"wrote {dst.name}")
        except pyproj.exceptions.ProjError as pe:
            print(f'Failure with body {body} in constructing proj exceptions')
            for wkt in crss_wkts.values():
                print(wkt)
            print(pe.__traceback__)
            pass
        

if __name__ == '__main__':
    main()