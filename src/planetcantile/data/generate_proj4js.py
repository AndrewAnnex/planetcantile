import pyproj
import json

from planet_crs_registry_client import Client, api
from  planet_crs_registry_client.models.wkt import WKT
from planet_crs_registry_client.api.browse_by_solar_body import get_solar_bodies_ws_solar_bodies_get
from planet_crs_registry_client.api.browse_by_solar_body import get_solar_body_ws_solar_bodies_solar_body_get

def custom_json_dumps(data):
    def process_value(val):
        if isinstance(val, str):
            # Return the string with quotes
            return f'"{val}"'
        elif isinstance(val, (int, float, bool)):
            # Return numbers and booleans without quotes
            return str(val).lower()  # lower() ensures booleans are correct
        elif isinstance(val, dict):
            # Recursively process dictionaries
            return custom_json_dumps(val)
        elif isinstance(val, list):
            # Recursively process lists
            return '[' + ', '.join(process_value(item) for item in val) + ']'
        else:
            raise TypeError(f"Unsupported data type: {type(val)}")

    # Iterate through the dictionary, constructing the JS-like object
    items = []
    for key, value in data.items():
        processed_value = process_value(value)
        items.append(f'    {key}: {processed_value}')

    # Join the processed items with commas and return as JS object
    return '{\n' + ',\n'.join(items) + '\n}'

def to_proj4js(pcrs_wkt):
    crs = pyproj.crs.CRS.from_wkt(pcrs_wkt.wkt)
    is_sphere = 'Sphere' in crs.ellipsoid.name
    export_name = f'{pcrs_wkt.solar_body}'.replace(' ', '')
    if is_sphere:
        return dict(
            a=crs.ellipsoid.semi_major_metre, 
            b=crs.ellipsoid.semi_major_metre, 
            ellipseName=crs.ellipsoid.name, 
            export_name=export_name+'Sphere'
        )
    else:
        return dict(
            a=crs.ellipsoid.semi_major_metre,
            rf=crs.ellipsoid.inverse_flattening, 
            ellipseName=crs.ellipsoid.name, 
            export_name=export_name
        )



if __name__ == '__main__':
    client = Client(base_url='http://voparis-vespa-crs.obspm.fr:8080/')
    valid_code_postfixs = {'00', '01'}
    bodies = get_solar_bodies_ws_solar_bodies_get.sync(client=client)
    #bodies = ['Moon', 'Earth', 'Mars']
    for body in bodies:
        crss_wkts = get_solar_body_ws_solar_bodies_solar_body_get.sync(body, client=client)
        # sort by code
        crss_wkts = sorted(crss_wkts, key= lambda _: _.code)
        # grab the 00, 01, codes. 
        crss_wkts = {str(_.code)[-2:]: _ for _ in crss_wkts if str(_.code)[-2:] in valid_code_postfixs}
        for _, crs_wkt in crss_wkts.items():
            as_dict = to_proj4js(crs_wkt)
            export_name = as_dict.pop('export_name')
            as_json = custom_json_dumps(as_dict)
            print(f"""
exports.{export_name} = {as_json};
            """)