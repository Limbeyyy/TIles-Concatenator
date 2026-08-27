import numpy as np
from core.globals import N_H_BOX, TOKEN


NO_AUTH_MAP_URL = f"https://kataho.app/api/third-party/{TOKEN}/map-api"
MAP_URL = f"https://kataho.app/login"

MIN_MAX_LAT = np.array([26.3475375, 29.9728125])
MIN_MAX_LON = np.array([80.3652031, 88.1864843])

LEVELS = ["country", "district", "municiplaity", "ward", "ward+1", "ward+2"]
LAYERS_BTN_MAPPING = {
    "openstreetmap": "openstreetmap",
    "satellite": "satellite",
    "terrain": "terrain",
    "hybrid": "hybrid",
    "googlesatellite": "googlesatellite",
    "googlemaps": "googlemaps",
}
LAYERS = list(LAYERS_BTN_MAPPING.keys())
RELOCATE_DIRECTIONS_MAPPING = {"north": 0, "east": 90, "south": 180, "west": 270}
RELOCATE_DIRECTIONS = list(RELOCATE_DIRECTIONS_MAPPING.keys())
RELOCATE_DISTANCE = 10000


MAP_CONFIG_NO_AUTH = {
    "country": {"zoom_type": "none", "zoom_value": 0},
    "district": {"zoom_type": "out", "zoom_value": 2},
    "municiplaity": {
        "zoom_type": "out",
        "zoom_value": 2,
        "n_h_box": 15,
        "n_v_box": 5,
        "crop_left": 85,
        "crop_right": 86,
        "crop_top_button_min": 122,  # 118
    },
    "ward": {
        "zoom_type": "out",
        "zoom_value": 1,
        "n_h_box": 7,
        "n_v_box": 2,
        "crop_left": 144,
        "crop_right": 144,
        "crop_top_button_min": 184,
    },
    "ward+1": {
        "zoom_type": "none",
        "zoom_value": 0,
        "n_h_box": 3,
        "n_v_box": 1,
        "crop_left": 261,
        "crop_right": 261,
        "crop_top_button_min": 184,
    },
    "ward+2": {
        "zoom_type": "in",
        "zoom_value": 1,
        "n_h_box": 1,
        "n_v_box": 1,
        "crop_left": 488,
        "crop_right": 500,
        "crop_top": 8,
        "crop_button": 19,
        "crop_top_button_min": 188,
    },
}

MAP_CONFIG_AUTH = {
    "country": {"zoom_type": "none", "zoom_value": 0},
    "district": {"zoom_type": "out", "zoom_value": 2},
    "municiplaity": {
        "zoom_type": "in",
        "zoom_value": 5 - 1,
        "n_h_box": 15,
        "n_v_box": 5,
        "crop_left": 85,
        "crop_right": 86,
        "crop_top_button_min": 122,  # 118
    },
    "ward": {
        "zoom_type": "in",
        "zoom_value": 6 - 1,
        "n_h_box": 7,
        "n_v_box": 2,
        "crop_left": 144,
        "crop_right": 144,
        "crop_top_button_min": 188,  # 184
    },
    "ward+1": {
        "zoom_type": "in",
        "zoom_value": 7 - 1,
        "n_h_box": 3,
        "n_v_box": 1,
        "crop_left": 261,
        "crop_right": 261,
        "crop_top_button_min": 188,  # 184
    },
    "ward+2": {
        "zoom_type": "in",
        "zoom_value": 8 - 1,
        "n_h_box": 1,
        "n_v_box": 1,
        "crop_left": 488,
        "crop_right": 500,
        "crop_top": 8,
        "crop_button": 19,
        "crop_top_button_min": 188,
    },
}
