from core import globals
from math import radians, sin, cos, sqrt, atan2, asin, degrees, ceil
from utils import map as map_

def haversine(coord1, coord2):
    # Radius of Earth in kilometers
    R = globals.R_km
    
    # Coordinates in radians
    lat1, lon1 = radians(coord1[0]), radians(coord1[1])
    lat2, lon2 = radians(coord2[0]), radians(coord2[1])
    
    # Differences in coordinates
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    # Haversine formula
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    # Distance in kilometers
    distance = R * c
    return distance * 1000  # Convert to meters

def move_point_by_distance(
    lat, lon, distance_in_meters, bearing
):
    """
    bearing: The direction of movement (in degrees). 0° = North, 90° = East, 180° = South, 270° = West.
    """
    # Radius of the Earth in meters
    R = globals.R_m
    
    # Convert latitude and longitude from degrees to radians
    lat = radians(lat)
    lon = radians(lon)
    
    # Convert bearing to radians
    bearing = radians(bearing)
    
    # Calculate the new latitude
    new_lat = asin(
        sin(lat) * cos(distance_in_meters / R) +
        cos(lat) * sin(distance_in_meters / R) * cos(bearing)
    )
    
    # Calculate the new longitude
    new_lon = lon + atan2(
        sin(bearing) * sin(distance_in_meters / R) * cos(lat),
        cos(distance_in_meters / R) - sin(lat) * sin(new_lat)
    )
    
    # Convert back to degrees
    new_lat = degrees(new_lat)
    new_lon = degrees(new_lon)
    
    return new_lat, new_lon

def calculate_folds(
        left_top: tuple[float, float], 
        right_buttom: tuple[float, float],
        H_DIST: float,
        V_DIST: float
    ):
    horizontal_distance = haversine(left_top, (left_top[0], right_buttom[1]))
    vertical_distance = haversine(left_top, (right_buttom[0], left_top[1]))

    # determine the number of tiles in the right and down side of left top point
    n_h_folds = ceil(horizontal_distance / (H_DIST*globals.N_H_BOX))   # 7.5*2=15
    n_v_folds = ceil(vertical_distance / (V_DIST*globals.N_V_BOX))      # 2.5*2

    return n_h_folds, n_v_folds

def calcualte_distant_point(
        left_top: tuple[float, float],
        dist: float = 10000.0,
        angle: float=180.0
) -> tuple[float, float]:
    distant_point = move_point_by_distance(
        *left_top, 
        dist, 
        angle
    )
    return distant_point

def halfway_distance(left_top: tuple[float, float], right_buttom: tuple[float, float]):
    return haversine(left_top, right_buttom) / 2

def height(point1: tuple[float, float], point2: tuple[float, float]):
    return haversine(point1, point2)

def width(point1: tuple[float, float], point2: tuple[float, float]):
    return haversine(point1, point2)

def bearning_angle(
        left_top: tuple[float, float], 
        right_top: tuple[float, float],
        right_buttom: tuple[float, float],
    ):
    h = height(right_top, right_buttom)
    w = width(left_top, right_top)

    return degrees(atan2(h, w)) + 90.0

def distance_between_h_blocks(kode1, kode2):
    return haversine(map_.kode_to_latlng(kode1), map_.kode_to_latlng(kode2))

def distance_between_v_blocks(kode1, kode2):
    return haversine(map_.kode_to_latlng(kode1), map_.kode_to_latlng(kode2))

def get_hv_dist(left_top, right_buttom, right_top):
    half_diag_dist = halfway_distance(left_top, right_buttom)

    # calculate bearing
    bearning_angle_val = bearning_angle(left_top, right_top, right_buttom)

    # find point in this distance and angle
    central_point = calcualte_distant_point(left_top, half_diag_dist, bearning_angle_val)

    # grab first three word of code
    # construct kode for distance calculation
    kode = map_.latlon_to_kode(central_point)
    kode_prefix = ' '.join(kode.split()[:-1]).strip()

    # smallest box distance
    h_dist = distance_between_h_blocks(kode_prefix + ' ०१००', kode_prefix + ' ०२००')
    v_dist = distance_between_v_blocks(kode_prefix + ' ००००', kode_prefix + ' ०००१')

    return h_dist, v_dist, globals.N_H_SMALL_BOXES*h_dist, globals.N_V_SMALL_BOXES*v_dist