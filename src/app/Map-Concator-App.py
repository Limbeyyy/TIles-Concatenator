import logging
import math
import os
import time
import tkinter as tk
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText

from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import WebDriverException

from core import configs, globals
from kataho.core.kataho_olc import decode, recoverNearest
from utils import distance, image, map as map_
from utils import (
    required_odds,
    save_image,
    get_savefile_path,
    show_comption_time,
    filter_kodes,
    update_progress_msg,
    guide,
)

# =========================
# GLOBALS
# =========================
MAP_CONFIGS        = None
locked_zoom        = None
adjustable_zoom    = None
corners            = None   # TL, TR, BR, BL
driver             = None
MUNICIPAL_ZOOM_DEFAULT = None   # captured from browser on first map load
BROWSER_MAP_STATE  = None   # populated in select_area() from live browser
OBSERVATION_TABLE  = []     # built in select_area() for ward level
CALIBRATION_DRIVER = None   # kept alive after ward calibration
CALIBRATION_WAIT   = None   # kept alive after ward calibration
OBSERVATION_TABLE_H = []   # add near the other globals at the top of the file
SELECTED_MAP_LAYER = None   # add near your other globals at the top of the file

FLAT_V_DELTA = 0
FLAT_H_DELTA = 0

# =========================
# LOGGING SETUP
# =========================
def get_appdata_dir(app_name: str):
    if os.name == "nt":  # Windows
        base = os.getenv("LOCALAPPDATA")
        if not base:
            raise EnvironmentError("LOCALAPPDATA not found on Windows")
    else:  # Linux / macOS
        base = os.path.expanduser("~/.local/share")
    path = os.path.join(base, app_name, "logs")
    os.makedirs(path, exist_ok=True)
    return path


app_log_dir = get_appdata_dir(globals.APP_NAME)
os.makedirs(app_log_dir, exist_ok=True)

logging.basicConfig(
    filename=f"{app_log_dir}/activity.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger()

# ADD — so logs appear in terminal/console in real time:
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
LOGGER.addHandler(console_handler)



# =========================
# PIXEL TO LAT/LNG CONVERSION (WEB MERCATOR)
# =========================
def pixel_to_latlng(x, y, center_lat, center_lng, zoom, width, height):
    """
    Convert pixel coordinates to lat/lng using Google Maps Web Mercator projection.
    CRITICAL: x, y must be in the SAME coordinate space as width, height.
    """
    TILE_SIZE = 256
    scale = 2 ** zoom

    def latlng_to_world(lat, lng):
        siny = math.sin(math.radians(lat))
        siny = min(max(siny, -0.9999), 0.9999)
        wx = TILE_SIZE * (0.5 + lng / 360.0) * scale
        wy = TILE_SIZE * (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * scale
        return wx, wy

    def world_to_latlng(wx, wy):
        lng = (wx / (TILE_SIZE * scale) - 0.5) * 360.0
        lat_rad = math.pi - 2.0 * math.pi * (wy / (TILE_SIZE * scale))
        lat = math.degrees(math.atan(math.sinh(lat_rad)))
        return lat, lng

    center_wx, center_wy = latlng_to_world(center_lat, center_lng)
    offset_x = x - (width / 2.0)
    offset_y = y - (height / 2.0)
    world_x = center_wx + offset_x
    world_y = center_wy + offset_y
    return world_to_latlng(world_x, world_y)


# =========================
# DRIVER HELPERS
# =========================
def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

        // Capture the first Leaflet map instance created, regardless of
        // whether the app stores it in a reachable variable.
        (function() {
            window.__MAP_INSTANCE__ = null;
            window.__MAP_LIB__ = null;

            const patchLeaflet = () => {
                if (window.L && L.Map && !L.Map.__patched) {
                    const orig = L.Map.prototype.initialize;
                    L.Map.prototype.initialize = function(...args) {
                        const r = orig.apply(this, args);
                        window.__MAP_INSTANCE__ = this;
                        window.__MAP_LIB__ = 'leaflet';
                        return r;
                    };
                    L.Map.__patched = true;
                    return true;
                }
                return false;
            };

            const patchMapLibre = () => {
                const lib = window.maplibregl || window.mapboxgl;
                if (lib && lib.Map && !lib.Map.__patched) {
                    const OrigMap = lib.Map;
                    const Wrapped = function(...args) {
                        const inst = new OrigMap(...args);
                        window.__MAP_INSTANCE__ = inst;
                        window.__MAP_LIB__ = 'maplibre';
                        return inst;
                    };
                    Wrapped.prototype = OrigMap.prototype;
                    lib.Map = Wrapped;
                    lib.Map.__patched = true;
                    return true;
                }
                return false;
            };

            // Libraries may load async, so poll until one appears.
            const poll = setInterval(() => {
                if (patchLeaflet() || patchMapLibre()) {
                    clearInterval(poll);
                }
            }, 20);
            setTimeout(() => clearInterval(poll), 20000);
        })();
        """
    })
    return driver


def wait_for_google_map(driver, timeout=30):
    """
    Waits for the Google map instance to be ready.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            ready = driver.execute_script("""
                if (typeof L === 'undefined') return false;
                if (!document.querySelector('.leaflet-container')) return false;
                for (const key in window) {
                    try {
                        const v = window[key];
                        if (v && v instanceof L.Map) {
                            window.__MAP_INSTANCE__ = v;
                            return true;
                        }
                    } catch (e) {}
                }
                return false;
            """)
            if ready:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def wait_for_tiles_loaded(driver, timeout=8):
    """
    Waits until Leaflet has no tiles still in the 'loading' state,
    or until timeout. Prevents capturing screenshots mid-load (black/blank tiles).
    """
    start = time.time()
    while time.time() - start < timeout:
        still_loading = driver.execute_script("""
            return document.querySelectorAll('.leaflet-tile-loading').length > 0;
        """)
        if not still_loading:
            return True
        time.sleep(0.15)
    LOGGER.warning("  Tiles still loading after timeout — capturing anyway")
    return False



def read_browser_map_state(driver):
    """
    Auto-detects Leaflet / MapLibre / Google and reads map state accordingly.
    """
    state = driver.execute_script("""
        // 1. Try Google first (legacy)
        const mapDiv = document.getElementById('map');
        let m = null;

        if (mapDiv && mapDiv.__gm && mapDiv.__gm.map) {
            m = mapDiv.__gm.map;
            if (typeof m.getMapTypeId === 'function') {
                const center = m.getCenter();
                return {
                    lib: 'google',
                    zoom: m.getZoom(),
                    mapType: m.getMapTypeId(),
                    centerLat: center ? center.lat() : null,
                    centerLng: center ? center.lng() : null,
                    tilt: m.getTilt(),
                    heading: m.getHeading(),
                    zoomType: m.getZoom() > 12 ? 'in' : 'out',
                };
            }
        }

        // 2. Try our injected Leaflet/MapLibre hook (see create_driver patch)
        if (window.__MAP_INSTANCE__ && window.__MAP_LIB__) {
            const inst = window.__MAP_INSTANCE__;
            const lib  = window.__MAP_LIB__;

            if (lib === 'leaflet') {
                const c = inst.getCenter();
                return {
                    lib: 'leaflet',
                    zoom: inst.getZoom(),
                    mapType: 'osm',
                    centerLat: c.lat,
                    centerLng: c.lng,
                    tilt: 0,
                    heading: 0,
                    zoomType: inst.getZoom() > 12 ? 'in' : 'out',
                };
            }
            if (lib === 'maplibre') {
                const c = inst.getCenter();
                return {
                    lib: 'maplibre',
                    zoom: inst.getZoom(),
                    mapType: 'osm',
                    centerLat: c.lat,
                    centerLng: c.lng,
                    tilt: inst.getPitch ? inst.getPitch() : 0,
                    heading: inst.getBearing ? inst.getBearing() : 0,
                    zoomType: inst.getZoom() > 12 ? 'in' : 'out',
                };
            }
        }

        // 3. Last resort: raw Leaflet global search (in case our hook
        //    fired too late or the app stores the map elsewhere)
        if (typeof L !== 'undefined') {
            for (const key in window) {
                try {
                    const v = window[key];
                    if (v && v instanceof L.Map) {
                        window.__MAP_INSTANCE__ = v;
                        window.__MAP_LIB__ = 'leaflet';
                        const c = v.getCenter();
                        return {
                            lib: 'leaflet-scan',
                            zoom: v.getZoom(),
                            mapType: 'osm',
                            centerLat: c.lat,
                            centerLng: c.lng,
                            tilt: 0, heading: 0,
                            zoomType: v.getZoom() > 12 ? 'in' : 'out',
                        };
                    }
                } catch (e) {}
            }
        }

        return null;
    """)
    return state

def clean_browser_ui(driver):
    driver.execute_script("""
        // ONLY remove elements we explicitly injected by known IDs
        const injectedIds = [
            'coord-info',
            'coord-display',
            'rect-overlay', 
            'rect-box',
            'zoom-adjust-container',
            'capture-highlight',
            'start-drawing-btn',
            'zoom-label',
        ];
        injectedIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.remove();
        });

        // Remove overlays inside map div only
        const mapDiv = document.getElementById('map');
        if (mapDiv) {
            mapDiv.querySelectorAll(
                '#rect-overlay, #capture-highlight, #rect-box'
            ).forEach(el => el.remove());
        }
        // DO NOT touch generic body > div — kills map UI
    """)

def read_browser_map_state(driver):
    state = driver.execute_script("""
        function findLeafletMap() {
            if (window.__MAP_INSTANCE__ instanceof L.Map) return window.__MAP_INSTANCE__;
            for (const key in window) {
                try {
                    const v = window[key];
                    if (v && v instanceof L.Map) { window.__MAP_INSTANCE__ = v; return v; }
                } catch (e) {}
            }
            return null;
        }
        const m = findLeafletMap();
        if (!m) return null;
        const c = m.getCenter();
        return {
            zoom:      m.getZoom(),
            mapType:   'osm',
            centerLat: c.lat,
            centerLng: c.lng,
            tilt:      0,
            heading:   0,
            zoomType:  m.getZoom() > 12 ? "in" : "out",
        };
    """)
    return state


# =========================
# CALIBRATION FUNCTIONS
# =========================


def measure_seam_delta(tile_top, tile_bottom, search_range=40):
    import numpy as np

    # Guard against mismatched screenshot dimensions (e.g. scrollbar
    # appearing/disappearing between the two captures shifts width by
    # a few px). Clip both to the smaller common width first.
    if tile_top.shape[1] != tile_bottom.shape[1]:
        min_w = min(tile_top.shape[1], tile_bottom.shape[1])
        LOGGER.warning(
            f"  Tile width mismatch: top={tile_top.shape[1]}px, "
            f"bottom={tile_bottom.shape[1]}px — clipping to {min_w}px"
        )
        tile_top    = tile_top[:, :min_w]
        tile_bottom = tile_bottom[:, :min_w]

    comparison_rows = 30
    edge_top    = tile_top[-comparison_rows:].astype(np.float32)
    edge_bottom = tile_bottom[:comparison_rows].astype(np.float32)

    scores = {}
    for delta in range(-search_range, search_range + 1):
        if delta < 0:
            shifted_top    = edge_top[abs(delta):]
            shifted_bottom = edge_bottom[:len(shifted_top)]
        elif delta > 0:
            shifted_bottom = edge_bottom[delta:]
            shifted_top    = edge_top[:len(shifted_bottom)]
        else:
            shifted_top, shifted_bottom = edge_top, edge_bottom
        if shifted_top.shape[0] == 0:
            continue
        scores[delta] = float(np.mean(np.abs(shifted_top - shifted_bottom)))

    best_delta = min(scores, key=scores.get)
    best_score = scores[best_delta]
    mirror_score = scores.get(-best_delta, float('inf'))

    if abs(mirror_score - best_score) < 0.5:  # nearly tied — sign is ambiguous
        LOGGER.warning(
            f"  Ambiguous seam match: delta={best_delta} (score={best_score:.2f}) "
            f"vs mirror={-best_delta} (score={mirror_score:.2f}) — sign unreliable"
        )

    LOGGER.info(f"  Seam delta measured: {best_delta}px (MAE score: {best_score:.2f})")
    return best_delta


def measure_horizontal_seam_delta(tile_left, tile_right, search_range=20):
    import numpy as np

    if tile_left.shape[0] != tile_right.shape[0]:
        min_h = min(tile_left.shape[0], tile_right.shape[0])
        LOGGER.warning(
            f"  Tile height mismatch: left={tile_left.shape[0]}px, "
            f"right={tile_right.shape[0]}px — clipping to {min_h}px"
        )
        tile_left  = tile_left[:min_h]
        tile_right = tile_right[:min_h]

    comparison_cols = 30
    edge_right = tile_left[:, -comparison_cols:].astype(np.float32)
    edge_left  = tile_right[:, :comparison_cols].astype(np.float32)
    
    best_delta = 0
    best_score = float('inf')

    for delta in range(-search_range, search_range + 1):
        if delta < 0:
            shifted_right = edge_right[:, abs(delta):]
            shifted_left  = edge_left[:, :shifted_right.shape[1]]
        elif delta > 0:
            shifted_left  = edge_left[:, delta:]
            shifted_right = edge_right[:, :shifted_left.shape[1]]
        else:
            shifted_right = edge_right
            shifted_left  = edge_left

        if shifted_right.shape[1] == 0:
            continue
        score = float(np.mean(np.abs(shifted_right - shifted_left)))
        if score < best_score:
            best_score = score
            best_delta = delta

    LOGGER.info(f"  Horizontal seam delta measured: {best_delta}px (MAE score: {best_score:.2f})")
    return best_delta

def run_calibration_2d(driver, wait, latitudes, longitudes, base_crop_top, base_crop_bottom, v_dist_approx):
    """
    Builds a 2D vertical observation grid: for each (lat, lng) sample point,
    measure the vertical seam delta between the tile there and the tile
    directly south of it. Returns: list of [lat, lng, delta]
    """
    observation_table = []
    kode_input_field  = map_.get_kode_input_field(wait)

    for lat in latitudes:
        for lng in longitudes:
            LOGGER.info(f"V-Calibrating at lat={lat:.5f}, lng={lng:.5f}")

            point_1 = (lat, lng)
            kode_1  = map_.latlon_to_kode(point_1)
            map_.drag_map(kode_input_field, kode_1)
            time.sleep(globals.REFRESH_DURATION)
            clean_browser_ui(driver)
            time.sleep(0.2)

            wait_for_tiles_loaded(driver)
            screenshot_1 = driver.get_screenshot_as_base64()
            tile_1 = image.image_crop(
                image.b64_to_image(screenshot_1, f"cal_{lat}_{lng}_1"),
                base_crop_bottom, base_crop_top
            )

            point_2 = distance.calcualte_distant_point(point_1, dist=v_dist_approx, angle=180)
            kode_2  = map_.latlon_to_kode(point_2)
            map_.drag_map(kode_input_field, kode_2)
            time.sleep(globals.REFRESH_DURATION)
            clean_browser_ui(driver)
            time.sleep(0.2)

            wait_for_tiles_loaded(driver)
            screenshot_2 = driver.get_screenshot_as_base64()
            tile_2 = image.image_crop(
                image.b64_to_image(screenshot_2, f"cal_{lat}_{lng}_2"),
                base_crop_bottom, base_crop_top
            )

            delta = measure_seam_delta(tile_1, tile_2)
            observation_table.append([lat, lng, delta])
            LOGGER.info(f"  ✓ Recorded: lat={lat:.5f}, lng={lng:.5f}, delta={delta}px")

    LOGGER.info(f"2D vertical calibration complete. {len(observation_table)} entries.")
    return observation_table


def run_horizontal_calibration_2d(driver, wait, latitudes, longitudes, h_dist_approx):
    """
    2D horizontal observation grid: for each (lat, lng) sample point, measure
    the horizontal seam delta between the tile there and the tile directly
    east of it. Returns: list of [lat, lng, delta]
    """
    observation_table = []
    kode_input_field  = map_.get_kode_input_field(wait)

    for lat in latitudes:
        for lng in longitudes:
            LOGGER.info(f"H-Calibrating at lat={lat:.5f}, lng={lng:.5f}")

            point_1 = (lat, lng)
            kode_1  = map_.latlon_to_kode(point_1)
            map_.drag_map(kode_input_field, kode_1)
            time.sleep(globals.REFRESH_DURATION)
            clean_browser_ui(driver)
            time.sleep(0.2)

            wait_for_tiles_loaded(driver)
            screenshot_1 = driver.get_screenshot_as_base64()
            tile_1 = image.image_crop(
                image.b64_to_image(screenshot_1, f"calh_{lat}_{lng}_1"),
                globals.CROP_TOP_BUTTON_MIN, globals.CROP_TOP_BUTTON_MIN
            )

            point_2 = distance.calcualte_distant_point(point_1, dist=h_dist_approx, angle=90)
            kode_2  = map_.latlon_to_kode(point_2)
            map_.drag_map(kode_input_field, kode_2)
            time.sleep(globals.REFRESH_DURATION)
            clean_browser_ui(driver)
            time.sleep(0.2)

            wait_for_tiles_loaded(driver)
            screenshot_2 = driver.get_screenshot_as_base64()
            tile_2 = image.image_crop(
                image.b64_to_image(screenshot_2, f"calh_{lat}_{lng}_2"),
                globals.CROP_TOP_BUTTON_MIN, globals.CROP_TOP_BUTTON_MIN
            )

            delta = measure_horizontal_seam_delta(tile_1, tile_2)
            observation_table.append([lat, lng, delta])
            LOGGER.info(f"  ✓ Recorded: lat={lat:.5f}, lng={lng:.5f}, delta={delta}px")

    LOGGER.info(f"2D horizontal calibration complete. {len(observation_table)} entries.")
    return observation_table


def run_combined_calibration_2d(driver, wait, latitudes, longitudes, base_crop_top, base_crop_bottom):
    """
    Captures ONE n×n grid of screenshots (n² navigations instead of the
    old 4n² from separate vertical+horizontal passes), then derives both
    vertical and horizontal seam deltas from adjacent cells in that shared
    grid.

    Returns:
        (vertical_table, horizontal_table)
        vertical_table:   list of [lat, lng, delta]  — delta measured between
                           this cell and the cell directly SOUTH of it
        horizontal_table: list of [lat, lng, delta]  — delta measured between
                           this cell and the cell directly EAST of it
    """
    kode_input_field = map_.get_kode_input_field(wait)
    grid = {}  # (row_idx, col_idx) -> cropped tile image

    total = len(latitudes) * len(longitudes)
    count = 0

    for r, lat in enumerate(latitudes):
        for c, lng in enumerate(longitudes):
            count += 1
            LOGGER.info(f"Grid capture {count}/{total}: lat={lat:.5f}, lng={lng:.5f}")

            kode = map_.latlon_to_kode((lat, lng))
            map_.drag_map(kode_input_field, kode)
            time.sleep(globals.REFRESH_DURATION)

            clean_browser_ui(driver)
            wait_for_tiles_loaded(driver)
            time.sleep(0.2)

            screenshot = driver.get_screenshot_as_base64()
            raw = image.b64_to_image(screenshot, f"grid_{r}_{c}")
            grid[(r, c)] = image.image_crop(raw, base_crop_bottom, base_crop_top)

    vertical_table = []
    horizontal_table = []

    # Vertical deltas: cell (r, c) vs cell (r+1, c) — same column, one row south
    for r in range(len(latitudes) - 1):
        for c, lng in enumerate(longitudes):
            delta = measure_seam_delta(grid[(r, c)], grid[(r + 1, c)])
            vertical_table.append([latitudes[r], lng, delta])
            LOGGER.info(f"  V: row {r}->{r+1}, lng={lng:.5f}, delta={delta}px")

    # Horizontal deltas: cell (r, c) vs cell (r, c+1) — same row, one column east
    for r, lat in enumerate(latitudes):
        for c in range(len(longitudes) - 1):
            delta = measure_horizontal_seam_delta(grid[(r, c)], grid[(r, c + 1)])
            horizontal_table.append([lat, longitudes[c], delta])
            LOGGER.info(f"  H: lat={lat:.5f}, col {c}->{c+1}, delta={delta}px")

    LOGGER.info(
        f"Combined calibration complete: {len(vertical_table)} vertical, "
        f"{len(horizontal_table)} horizontal entries from {total} grid captures "
        f"(vs {total * 4} navigations under the old separate-pass approach)."
    )
    return vertical_table, horizontal_table


def smooth_observation_table(table, window=3):
    import numpy as np
    if len(table) < window:
        return table
    vals = [d for _, d in table]
    smoothed = []
    for i in range(len(vals)):
        lo = max(0, i - window // 2)
        hi = min(len(vals), i + window // 2 + 1)
        smoothed.append(int(np.median(vals[lo:hi])))
    return [[table[i][0], smoothed[i]] for i in range(len(table))]




def resolve_flat_delta(observation_table):
    """
    The seam-delta measurement is prone to sign ambiguity on repetitive
    map textures (near-symmetric correlation at +delta and -delta).
    Magnitude is reliable; sign often isn't. Resolve to ONE flat delta
    by taking the median absolute magnitude and the majority sign.
    """
    if not observation_table:
        return 0
    import numpy as np
    deltas = [row[-1] for row in observation_table]  # last column is delta
    magnitude = int(np.median([abs(d) for d in deltas]))
    positive_count = sum(1 for d in deltas if d > 0)
    negative_count = sum(1 for d in deltas if d < 0)
    sign = 1 if positive_count >= negative_count else -1
    resolved = sign * magnitude
    LOGGER.info(
        f"  Resolved flat delta: magnitude={magnitude}px, "
        f"sign_votes=(+{positive_count}/-{negative_count}), resolved={resolved}px"
    )
    return resolved




def get_calibrated_crop(latitude, longitude, base_crop_top, base_crop_bottom):
    if not OBSERVATION_TABLE:
        return base_crop_top, base_crop_bottom

    delta_clamped = max(-base_crop_top, min(base_crop_bottom, FLAT_V_DELTA))

    adjusted_top    = base_crop_top    + delta_clamped
    adjusted_bottom = base_crop_bottom - delta_clamped

    LOGGER.info(
        f"  V-Calibration: lat={latitude:.5f}, lng={longitude:.5f}, "
        f"flat_delta={FLAT_V_DELTA}px, clamped_delta={delta_clamped}px, "
        f"adj_top={adjusted_top}, adj_bottom={adjusted_bottom}"
    )
    return adjusted_top, adjusted_bottom


def get_calibrated_crop_horizontal(latitude, longitude, base_crop_left, base_crop_right):
    if not OBSERVATION_TABLE_H:
        return base_crop_left, base_crop_right

    delta_clamped = max(-base_crop_left, min(base_crop_right, FLAT_H_DELTA))

    adjusted_left  = base_crop_left  + delta_clamped
    adjusted_right = base_crop_right - delta_clamped

    LOGGER.info(
        f"  H-Calibration: lat={latitude:.5f}, lng={longitude:.5f}, "
        f"flat_delta={FLAT_H_DELTA}px, clamped_delta={delta_clamped}px, "
        f"adj_left={adjusted_left}, adj_right={adjusted_right}"
    )
    return adjusted_left, adjusted_right


# =========================
# SELECT AREA FUNCTION
# =========================
def select_area():
    """
    Open map, allow user to draw rectangle, convert pixel coordinates to lat/lng.
    - Captures browser map state on first load (replaces all config-sourced values)
    - Uses CONTINUOUS LIVE TRACKING of center/zoom
    - Auto-detects level (municipal/ward) from zoom comparison
    - Runs observation table calibration automatically for ward level
    - Keeps browser alive for generate_from_selected_area() if ward level
    """
    update_progress_msg(root, progress_message, "Opening map for selection…")

    DRIVER = create_driver()

    global corners, locked_zoom, adjustable_zoom, center_lat, center_lng, map_type
    global OBSERVATION_TABLE, CALIBRATION_DRIVER, CALIBRATION_WAIT
    global MUNICIPAL_ZOOM_DEFAULT, BROWSER_MAP_STATE, SELECTED_MAP_LAYER

    try:
        # ── Login flow ──
        DRIVER.get("https://kataho.app/login")
        wait = WebDriverWait(DRIVER, 15)

        map_.enter_email(wait, email_entry.get())
        map_.enter_password(wait, password_entry.get())
        map_.click_login_btn(wait)

        WebDriverWait(DRIVER, 20).until(lambda d: "/login" not in d.current_url)
        DRIVER.get("https://kataho.app/organization/organization-maps")
        time.sleep(3)
        libs = DRIVER.execute_script("""
            return {
                leaflet: typeof L !== 'undefined',
                maplibre: typeof maplibregl !== 'undefined',
                mapboxgl: typeof mapboxgl !== 'undefined',
                openlayers: typeof ol !== 'undefined',
                hasLeafletContainer: !!document.querySelector('.leaflet-container'),
                hasMaplibreCanvas: !!document.querySelector('.maplibregl-canvas'),
            };
        """)
        print(libs)

        update_progress_msg(root, progress_message, "Waiting for map to load…")

        if not wait_for_google_map(DRIVER, timeout=30):
            messagebox.showerror("Error", "Map did not load or map div not found.")
            return

        # Give the map extra time to fully initialize
        time.sleep(2)


        # ── Lock scrollbar off so viewport width/height never jitters
        #    between screenshots taken later during calibration ──
        DRIVER.execute_script("""
            document.documentElement.style.overflow = 'hidden';
            document.body.style.overflow = 'hidden';
            document.body.style.margin = '0';
        """)

        # Force map interaction to ensure it's fully loaded
        DRIVER.execute_script("""
            const mapDiv = document.getElementById('map');
            if (mapDiv) {
                const evt = new MouseEvent('mousemove', {
                    bubbles: true, cancelable: true, view: window
                });
                mapDiv.dispatchEvent(evt);
            }
        """)
        time.sleep(1)


        # ── Lock in the layer choice for this whole session, BEFORE
        # attempting the click. This must be captured regardless of
        # whether the click below succeeds, so generate_from_selected_area()
        # always has the user's real intent to work with. ──
        SELECTED_MAP_LAYER = selected_layer.get()
        LOGGER.info(f"Locked layer for this session: {SELECTED_MAP_LAYER}")
        LOGGER.info(f"  (Layer dropdown value = {selected_layer.get()}, SELECTED_MAP_LAYER = {SELECTED_MAP_LAYER})")

        result = map_.set_map_layer_direct(DRIVER, SELECTED_MAP_LAYER)
        time.sleep(1.5)
        if result and result.get('success'):
            LOGGER.info(f"✓ Layer set to: {SELECTED_MAP_LAYER} | url={result['url']} maxZoom={result['maxZoom']}")
        else:
            LOGGER.error(f"✗ Layer switch to '{SELECTED_MAP_LAYER}' failed: {result.get('error') if result else 'no result'}")

        

        # ============================================
        # CAPTURE BROWSER MAP STATE ON FIRST LOAD
        # Called here before user pans/zooms anything —
        # this is the true municipal default zoom.
        # Replaces ALL config-sourced values (zoom, layer, zoom type).
        # ============================================
        BROWSER_MAP_STATE = read_browser_map_state(DRIVER)

        if BROWSER_MAP_STATE:
            MUNICIPAL_ZOOM_DEFAULT = BROWSER_MAP_STATE['zoom']
            LOGGER.info("=" * 60)
            LOGGER.info("BROWSER MAP STATE ON LOAD (sourced live from browser)")
            LOGGER.info("=" * 60)
            LOGGER.info(f"  Zoom Level : {BROWSER_MAP_STATE['zoom']}")
            LOGGER.info(f"  Zoom Type  : {BROWSER_MAP_STATE['zoomType']}")
            LOGGER.info(f"  Map Type   : {BROWSER_MAP_STATE['mapType']}")
            LOGGER.info(f"  Center Lat : {BROWSER_MAP_STATE['centerLat']}")
            LOGGER.info(f"  Center Lng : {BROWSER_MAP_STATE['centerLng']}")
            LOGGER.info(f"  Tilt       : {BROWSER_MAP_STATE['tilt']}")
            LOGGER.info(f"  Heading    : {BROWSER_MAP_STATE['heading']}")
            LOGGER.info("=" * 60)
        else:
            LOGGER.warning("Could not read browser map state — using fallback defaults")
            MUNICIPAL_ZOOM_DEFAULT = 12
            BROWSER_MAP_STATE = {
                'zoom': 12, 'mapType': 'roadmap', 'zoomType': 'out',
                'centerLat': None, 'centerLng': None, 'tilt': 0, 'heading': 0,
            }

        update_progress_msg(
            root, progress_message,
            f"Municipal zoom locked at {MUNICIPAL_ZOOM_DEFAULT} "
            f"(type={BROWSER_MAP_STATE['mapType']}). "
            f"Pan/zoom as needed, then click the button."
        )

        # ============================================
        # CONTINUOUS LIVE TRACKING (Updates every 100ms)
        # ============================================
        DRIVER.execute_script("""
        window.dynamicMapState = {
            centerLat: null, centerLng: null, zoom: null, mapType: null
        };
        window.isTrackingMap = true;

        function findLeafletMap() {
            if (window.__MAP_INSTANCE__ instanceof L.Map) return window.__MAP_INSTANCE__;
            for (const key in window) {
                try {
                    const v = window[key];
                    if (v && v instanceof L.Map) {
                        window.__MAP_INSTANCE__ = v;
                        return v;
                    }
                } catch (e) {}
            }
            return null;
        }

        const mapInstance = findLeafletMap();
        const mapDiv = document.getElementById('map');

        if (mapInstance) {
            const trackingInterval = setInterval(() => {
                if (!window.isTrackingMap) {
                    clearInterval(trackingInterval);
                    return;
                }
                try {
                    const center = mapInstance.getCenter();
                    if (center) {
                        // Leaflet: center.lat / center.lng are PROPERTIES, not methods
                        window.dynamicMapState.centerLat = center.lat;
                        window.dynamicMapState.centerLng = center.lng;
                        window.dynamicMapState.zoom = mapInstance.getZoom();
                        window.dynamicMapState.mapType = 'osm';

                        const infoBox = document.getElementById('coord-info');
                        if (infoBox) {
                            const rect = mapDiv.getBoundingClientRect();
                            infoBox.innerHTML = `
                                <strong style="color:lime">📍 LIVE Tracking:</strong><br>
                                <em style="color:#ffff00">🔄 Updating continuously...</em><br><br>
                                Lat: ${window.dynamicMapState.centerLat.toFixed(6)}<br>
                                Lng: ${window.dynamicMapState.centerLng.toFixed(6)}<br>
                                Zoom: ${window.dynamicMapState.zoom.toFixed(2)}<br>
                                Type: ${window.dynamicMapState.mapType}<br>
                                Map: ${Math.round(rect.width)}×${Math.round(rect.height)}px<br><br>
                                <em>Pan/zoom freely!</em><br>
                                <em>Click button to lock values</em>
                            `;
                        }
                    }
                } catch (e) { console.error('Error tracking map:', e); }
            }, 100);
        } else {
            console.error('❌ Could not find Leaflet map instance for tracking');
        }
    """)

        # ============================================
        # RECTANGLE DRAWING FUNCTION (Stops tracking)
        # ============================================
        DRIVER.execute_script("""
            window.activateRectangleDrawing = function() {
                window.isTrackingMap = false;

                const infoBox = document.getElementById('coord-info');
                if (infoBox && window.dynamicMapState.centerLat) {
                    const mapDiv = document.getElementById('map');
                    const rect = mapDiv.getBoundingClientRect();
                    infoBox.innerHTML = `
                        <strong style="color:lime">🔒 LOCKED:</strong><br>
                        <em style="color:#ffff00">✓ Values frozen</em><br><br>
                        Lat: ${window.dynamicMapState.centerLat.toFixed(6)}<br>
                        Lng: ${window.dynamicMapState.centerLng.toFixed(6)}<br>
                        Zoom: ${window.dynamicMapState.zoom.toFixed(2)}<br>
                        Type: ${window.dynamicMapState.mapType}<br>
                        Map: ${Math.round(rect.width)}×${Math.round(rect.height)}px<br><br>
                        <em style="color:#ff6">✏️ Draw rectangle now</em>
                    `;
                }

                if (window.__RECT_ACTIVE__) {
                    const existingOverlay = document.querySelector('#rect-overlay');
                    if (existingOverlay) existingOverlay.remove();
                }

                window.__RECT_ACTIVE__ = true;
                window.__RECT__ = null;

                const mapDiv = document.getElementById("map");
                const overlay = document.createElement("div");
                overlay.id = "rect-overlay";
                overlay.style.position = "absolute";
                overlay.style.left = "0";
                overlay.style.top = "0";
                overlay.style.width = "100%";
                overlay.style.height = "100%";
                overlay.style.zIndex = "9999";
                overlay.style.cursor = "crosshair";
                overlay.style.pointerEvents = "auto";

                const box = document.createElement("div");
                box.id = "rect-box";
                box.style.position = "absolute";
                box.style.border = "3px solid red";
                box.style.background = "rgba(255,0,0,0.15)";
                box.style.pointerEvents = "none";
                overlay.appendChild(box);

                const coordDisplay = document.createElement("div");
                coordDisplay.id = 'coord-display';
                coordDisplay.style.position = "fixed";

                coordDisplay.style.bottom = "10px";
                coordDisplay.style.right = "10px";
                coordDisplay.style.background = "rgba(0,0,0,0.9)";
                coordDisplay.style.color = "lime";
                coordDisplay.style.padding = "10px";
                coordDisplay.style.borderRadius = "5px";
                coordDisplay.style.zIndex = "10001";
                coordDisplay.style.fontFamily = "monospace";
                coordDisplay.style.fontSize = "11px";
                coordDisplay.style.display = "none";
                document.body.appendChild(coordDisplay);

                let startX, startY, drawing = false;

                overlay.addEventListener("mousedown", e => {
                    e.preventDefault(); e.stopPropagation();
                    drawing = true;
                    startX = e.offsetX; startY = e.offsetY;
                    box.style.left = startX + "px"; box.style.top = startY + "px";
                    box.style.width = "0px"; box.style.height = "0px";
                    box.style.display = "block"; coordDisplay.style.display = "block";
                    const mapRect = mapDiv.getBoundingClientRect();
                    window.__DRAWING_MAP_RECT__ = {
                        width: Math.round(mapRect.width), height: Math.round(mapRect.height)
                    };
                    window.__LOCKED_CENTER_LAT__ = window.dynamicMapState.centerLat;
                    window.__LOCKED_CENTER_LNG__ = window.dynamicMapState.centerLng;
                    window.__LOCKED_ZOOM__ = window.dynamicMapState.zoom;
                    window.__LOCKED_MAP_TYPE__ = window.dynamicMapState.mapType;
                });

                overlay.addEventListener("mousemove", e => {
                    if (!drawing) return;
                    e.preventDefault(); e.stopPropagation();
                    const currentX = e.offsetX; const currentY = e.offsetY;
                    const x = Math.min(startX, currentX); const y = Math.min(startY, currentY);
                    const w = Math.abs(currentX - startX); const h = Math.abs(currentY - startY);
                    box.style.left = x + "px"; box.style.top = y + "px";
                    box.style.width = w + "px"; box.style.height = h + "px";
                    coordDisplay.innerHTML =
                        '<strong>Drawing Rectangle:</strong><br>' +
                        'Start: (' + Math.round(startX) + ', ' + Math.round(startY) + ')<br>' +
                        'Current: (' + Math.round(currentX) + ', ' + Math.round(currentY) + ')<br>' +
                        'Size: ' + Math.round(w) + '×' + Math.round(h) + ' px<br>' +
                        'Locked Zoom: ' + window.__LOCKED_ZOOM__.toFixed(2);
                });

                overlay.addEventListener("mouseup", e => {
                    if (!drawing) return;
                    e.preventDefault(); e.stopPropagation();
                    const endX = e.offsetX; const endY = e.offsetY;
                    const x1 = Math.round(Math.min(startX, endX));
                    const y1 = Math.round(Math.min(startY, endY));
                    const x2 = Math.round(Math.max(startX, endX));
                    const y2 = Math.round(Math.max(startY, endY));
                    window.__RECT__ = [x1, y1, x2, y2];
                    const mapRect = mapDiv.getBoundingClientRect();
                    window.__ACTUAL_MAP_DIMS__ = [Math.round(mapRect.width), Math.round(mapRect.height)];
                    drawing = false;
                    coordDisplay.innerHTML =
                        '<strong style="color:lime">✓ CAPTURED</strong><br>' +
                        'Rectangle: (' + x1 + ', ' + y1 + ') → (' + x2 + ', ' + y2 + ')<br>' +
                        'Size: (' + (x2-x1) + '×' + (y2-y1) + ') px<br>' +
                        'Locked Zoom: ' + window.__LOCKED_ZOOM__.toFixed(2) + '<br>' +
                        'Locked Type: ' + window.__LOCKED_MAP_TYPE__;
                });

                overlay.addEventListener("click", e => { e.preventDefault(); e.stopPropagation(); });
                mapDiv.appendChild(overlay);
            }
        """)

        # ============================================
        # START DRAWING BUTTON
        # ============================================
        DRIVER.execute_script("""
            (function() {
                const startButton = document.createElement('button');
                startButton.id = 'start-drawing-btn';
                startButton.textContent = '🖱️ START DRAWING RECTANGLE';
                startButton.style.position = 'fixed';
                startButton.style.bottom = '20px';
                startButton.style.left = '50%';
                startButton.style.transform = 'translateX(-50%)';
                startButton.style.padding = '20px 40px';
                startButton.style.fontSize = '18px';
                startButton.style.fontWeight = 'bold';
                startButton.style.backgroundColor = '#4CAF50';
                startButton.style.color = 'white';
                startButton.style.border = 'none';
                startButton.style.borderRadius = '8px';
                startButton.style.cursor = 'pointer';
                startButton.style.zIndex = '10003';
                startButton.style.boxShadow = '0 6px 12px rgba(0,0,0,0.4)';
                startButton.style.transition = 'all 0.3s';
                startButton.style.textTransform = 'uppercase';
                startButton.style.letterSpacing = '1px';

                startButton.addEventListener('mouseenter', () => {
                    startButton.style.backgroundColor = '#45a049';
                    startButton.style.transform = 'translateX(-50%) scale(1.05)';
                    startButton.style.boxShadow = '0 8px 16px rgba(0,0,0,0.5)';
                });
                startButton.addEventListener('mouseleave', () => {
                    startButton.style.backgroundColor = '#4CAF50';
                    startButton.style.transform = 'translateX(-50%) scale(1)';
                    startButton.style.boxShadow = '0 6px 12px rgba(0,0,0,0.4)';
                });
                startButton.addEventListener('click', () => {
                    startButton.style.opacity = '0';
                    startButton.style.transform = 'translateX(-50%) scale(0.9)';
                    setTimeout(() => { startButton.remove(); }, 300);
                    window.activateRectangleDrawing();
                });
                document.body.appendChild(startButton);
            })();
        """)

        # Wait for rectangle to be drawn
        rect_data = None
        attempts = 0
        for _ in range(120):
            rect_data = DRIVER.execute_script("""
                return {
                    rect: window.__RECT__,
                    dims: window.__ACTUAL_MAP_DIMS__,
                    dpr: window.devicePixelRatio,
                    lockedCenterLat: window.__LOCKED_CENTER_LAT__,
                    lockedCenterLng: window.__LOCKED_CENTER_LNG__,
                    lockedZoom: window.__LOCKED_ZOOM__,
                    lockedMapType: window.__LOCKED_MAP_TYPE__,
                    mapRect: (function() {
                        const mapDiv = document.getElementById('map');
                        if (!mapDiv) return null;
                        const r = mapDiv.getBoundingClientRect();
                        return {
                            width: Math.round(r.width), height: Math.round(r.height),
                            left: r.left, top: r.top
                        };
                    })()
                };
            """)

            zoom     = rect_data.get('lockedZoom')
            map_type = rect_data.get('lockedMapType', 'unknown')

            # ── Save locked zoom as global for generate step ──
            global locked_zoom
            locked_zoom = zoom
            LOGGER.info(f"locked_zoom saved as global: {locked_zoom}")


            if rect_data and rect_data.get('rect'):
                LOGGER.info(f"Rectangle captured after {attempts} attempts ({attempts * 0.5}s)")
                break
            time.sleep(0.5)
            attempts += 1

        if not rect_data or not rect_data.get('rect'):
            messagebox.showerror("Error", "No rectangle drawn within timeout period.")
            return

        # ============================================
        # ADJUSTABLE ZOOM UI
        # ============================================
        update_progress_msg(root, progress_message, "Waiting for adjustable zoom from Map UI...")

        DRIVER.execute_script("""
        (function() {
            const zoomContainer = document.createElement('div');
            zoomContainer.id = 'zoom-adjust-container';
            zoomContainer.style.position = 'fixed';
            zoomContainer.style.bottom = '20px';
            zoomContainer.style.right = '20px';
            zoomContainer.style.backgroundColor = 'rgba(255,255,255,0.95)';
            zoomContainer.style.padding = '15px 20px';
            zoomContainer.style.borderRadius = '8px';
            zoomContainer.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
            zoomContainer.style.zIndex = '10003';
            zoomContainer.style.textAlign = 'center';
            zoomContainer.style.fontFamily = 'Arial, sans-serif';
            zoomContainer.style.minWidth = '220px';

            const title = document.createElement('div');
            title.textContent = '🔍 Adjust Tile Zoom';
            title.style.marginBottom = '10px'; title.style.fontSize = '16px';
            title.style.fontWeight = 'bold'; title.style.color = '#333';
            zoomContainer.appendChild(title);

            const zoomLabel = document.createElement('div');
            zoomLabel.id = 'zoom-label';
            zoomLabel.textContent = 'Click + or - to adjust';
            zoomLabel.style.marginBottom = '12px'; zoomLabel.style.fontWeight = 'bold';
            zoomLabel.style.fontSize = '18px'; zoomLabel.style.color = '#4CAF50';
            zoomContainer.appendChild(zoomLabel);

            const btnContainer = document.createElement('div');
            btnContainer.style.display = 'flex'; btnContainer.style.justifyContent = 'center';
            btnContainer.style.gap = '10px'; btnContainer.style.marginBottom = '12px';

            const zoomOutBtn = document.createElement('button');
            zoomOutBtn.textContent = '−';
            zoomOutBtn.style.cssText = 'padding:10px 20px;font-size:20px;font-weight:bold;cursor:pointer;background:#f44336;color:white;border:none;border-radius:4px;transition:all 0.2s;';

            const zoomInBtn = document.createElement('button');
            zoomInBtn.textContent = '+';
            zoomInBtn.style.cssText = 'padding:10px 20px;font-size:20px;font-weight:bold;cursor:pointer;background:#2196F3;color:white;border:none;border-radius:4px;transition:all 0.2s;';

            btnContainer.appendChild(zoomOutBtn);
            btnContainer.appendChild(zoomInBtn);
            zoomContainer.appendChild(btnContainer);

            const confirmBtn = document.createElement('button');
            confirmBtn.textContent = '✓ Confirm Zoom';
            confirmBtn.style.cssText = 'padding:10px 20px;font-size:14px;font-weight:bold;cursor:pointer;background:#4CAF50;color:white;border:none;border-radius:4px;width:100%;transition:all 0.2s;';
            zoomContainer.appendChild(confirmBtn);
            document.body.appendChild(zoomContainer);

            window.adjustableZoom = null;
            let tempZoomValue = window.__LOCKED_ZOOM__ || 18;

            zoomOutBtn.addEventListener('click', () => {
                tempZoomValue -= 1;
                zoomLabel.textContent = 'Zoom: ' + tempZoomValue;
                zoomLabel.style.color = '#FF9800';
            });
            zoomInBtn.addEventListener('click', () => {
                tempZoomValue += 1;
                zoomLabel.textContent = 'Zoom: ' + tempZoomValue;
                zoomLabel.style.color = '#FF9800';
            });
            zoomOutBtn.addEventListener('mouseenter', () => { zoomOutBtn.style.background = '#d32f2f'; zoomOutBtn.style.transform = 'scale(1.05)'; });
            zoomOutBtn.addEventListener('mouseleave', () => { zoomOutBtn.style.background = '#f44336'; zoomOutBtn.style.transform = 'scale(1)'; });
            zoomInBtn.addEventListener('mouseenter', () => { zoomInBtn.style.background = '#1976D2'; zoomInBtn.style.transform = 'scale(1.05)'; });
            zoomInBtn.addEventListener('mouseleave', () => { zoomInBtn.style.background = '#2196F3'; zoomInBtn.style.transform = 'scale(1)'; });
            confirmBtn.addEventListener('mouseenter', () => { confirmBtn.style.background = '#45a049'; confirmBtn.style.transform = 'scale(1.02)'; });
            confirmBtn.addEventListener('mouseleave', () => { confirmBtn.style.background = '#4CAF50'; confirmBtn.style.transform = 'scale(1)'; });

            confirmBtn.addEventListener('click', () => {
                window.adjustableZoom = tempZoomValue;
                zoomLabel.textContent = '✓ Zoom: ' + window.adjustableZoom + ' (Confirmed)';
                zoomLabel.style.color = '#4CAF50';
                const successMsg = document.createElement('div');
                successMsg.textContent = '✓ Zoom confirmed!';
                successMsg.style.cssText = 'margin-top:10px;padding:8px;background:#4CAF50;color:white;border-radius:4px;font-size:12px;';
                zoomContainer.appendChild(successMsg);
                zoomInBtn.disabled = true; zoomOutBtn.disabled = true; confirmBtn.disabled = true;
                zoomInBtn.style.opacity = '0.5'; zoomOutBtn.style.opacity = '0.5'; confirmBtn.style.opacity = '0.5';
                zoomInBtn.style.cursor = 'not-allowed'; zoomOutBtn.style.cursor = 'not-allowed'; confirmBtn.style.cursor = 'not-allowed';
                setTimeout(() => { zoomContainer.remove(); }, 2000);
            });
        })();
        """)

        # Poll for adjustable zoom
        adjustable_zoom = None
        timeout = 60
        start_time = time.time()
        while time.time() - start_time < timeout:
            zoom_val = DRIVER.execute_script("return window.adjustableZoom;")
            if zoom_val is not None:
                adjustable_zoom = zoom_val
                break
            time.sleep(0.5)

        if adjustable_zoom is None:
            messagebox.showerror("Error", "User did not confirm zoom in time!")
            raise Exception("User did not confirm zoom in time")

        LOGGER.info(f"Using TILE adjustable zoom: {adjustable_zoom}")

        max_zoom = DRIVER.execute_script("""
            const m = window.__MAP_INSTANCE__;
            return m ? m.getMaxZoom() : null;
        """)
        LOGGER.info(f"Layer max zoom: {max_zoom}")

        if adjustable_zoom > max_zoom:
            LOGGER.warning(f"Requested zoom {adjustable_zoom} exceeds layer max {max_zoom}, clamping")
            adjustable_zoom = max_zoom

        # ------------ Rect Values ---------------------
        rect = rect_data['rect']
        actual_dims = rect_data['dims']
        dpr         = rect_data['dpr']
        map_rect    = rect_data['mapRect']

        center_lat  = rect_data.get('lockedCenterLat')
        center_lng  = rect_data.get('lockedCenterLng')
        zoom        = rect_data.get('lockedZoom')
        map_type    = rect_data.get('lockedMapType', 'unknown')

        # ── Save locked zoom as global for generate step ──
        locked_zoom = zoom
        LOGGER.info(f"locked_zoom saved as global: {locked_zoom}")

        map_width  = actual_dims[0]
        map_height = actual_dims[1]

        BROWSER_MAP_STATE['mapWidth']  = actual_dims[0]
        BROWSER_MAP_STATE['mapHeight'] = actual_dims[1]
        x1, y1, x2, y2 = rect

        LOGGER.info("=" * 60)
        LOGGER.info("RECTANGLE SELECTION WITH LOCKED VALUES")
        LOGGER.info("=" * 60)
        LOGGER.info(f"Rectangle: ({x1}, {y1}) to ({x2}, {y2}) [CSS pixels]")
        LOGGER.info(f"Map dimensions: {map_width}×{map_height} CSS pixels")
        LOGGER.info(f"Device pixel ratio: {dpr}")
        LOGGER.info(f"Physical pixels: {map_width * dpr:.0f}×{map_height * dpr:.0f}")
        LOGGER.info(f"LOCKED map center: ({center_lat}, {center_lng})")
        LOGGER.info(f"LOCKED zoom level: {zoom}")
        LOGGER.info(f"LOCKED map type: {map_type}")

        if map_rect and (map_rect['width'] != map_width or map_rect['height'] != map_height):
            LOGGER.warning(f"DIMENSION MISMATCH! Drawing: {map_width}×{map_height}, "
                           f"Current: {map_rect['width']}×{map_rect['height']}")

        rect_width    = x2 - x1
        rect_height   = y2 - y1
        rect_center_x = (x1 + x2) / 2
        rect_center_y = (y1 + y2) / 2

        LOGGER.info(f"Rectangle size: {rect_width} x {rect_height} pixels")
        LOGGER.info(f"Rectangle center pixels: ({rect_center_x}, {rect_center_y})")
        LOGGER.info(f"Map center pixels: ({map_width/2}, {map_height/2})")

        offset_x = rect_center_x - (map_width / 2)
        offset_y = rect_center_y - (map_height / 2)
        LOGGER.info(f"Rectangle offset from map center: ({offset_x:.1f}, {offset_y:.1f}) pixels")

        LOGGER.info("-" * 60)
        LOGGER.info("CORNER CONVERSIONS (using LOCKED center/zoom):")

        tl_lat, tl_lng = pixel_to_latlng(x1, y1, center_lat, center_lng, zoom, map_width, map_height)
        LOGGER.info(f"Top-Left:     pixel({x1}, {y1}) -> ({tl_lat}, {tl_lng})")

        tr_lat, tr_lng = pixel_to_latlng(x2, y1, center_lat, center_lng, zoom, map_width, map_height)
        LOGGER.info(f"Top-Right:    pixel({x2}, {y1}) -> ({tr_lat}, {tr_lng})")

        br_lat, br_lng = pixel_to_latlng(x2, y2, center_lat, center_lng, zoom, map_width, map_height)
        LOGGER.info(f"Bottom-Right: pixel({x2}, {y2}) -> ({br_lat}, {br_lng})")

        bl_lat, bl_lng = pixel_to_latlng(x1, y2, center_lat, center_lng, zoom, map_width, map_height)
        LOGGER.info(f"Bottom-Left:  pixel({x1}, {y2}) -> ({bl_lat}, {bl_lng})")

        rect_center_lat, rect_center_lng = pixel_to_latlng(
            rect_center_x, rect_center_y, center_lat, center_lng, zoom, map_width, map_height
        )
        LOGGER.info(f"Rectangle center lat/lng: ({rect_center_lat}, {rect_center_lng})")

        tl = (tl_lat, tl_lng)
        tr = (tr_lat, tr_lng)
        br = (br_lat, br_lng)
        bl = (bl_lat, bl_lng)
        corners = [tl, tr, br, bl]

        lat_span = abs(tl_lat - bl_lat)
        lng_span = abs(tl_lng - tr_lng)
        LOGGER.info(f"Geographic span: Δlat={lat_span:.6f}°, Δlng={lng_span:.6f}°")
        LOGGER.info("=" * 60)

        # Visual verification highlight
        DRIVER.execute_script(f"""
            (function() {{
                const oldHighlight = document.getElementById('capture-highlight');
                if (oldHighlight) oldHighlight.remove();
                const mapDiv = document.getElementById('map');
                const highlight = document.createElement('div');
                highlight.id = 'capture-highlight';
                highlight.style.position = 'absolute';
                highlight.style.left = '{x1}px'; highlight.style.top = '{y1}px';
                highlight.style.width = '{x2 - x1}px'; highlight.style.height = '{y2 - y1}px';
                highlight.style.border = '4px solid lime';
                highlight.style.background = 'rgba(0,255,0,0.2)';
                highlight.style.zIndex = '10002'; highlight.style.pointerEvents = 'none';
                const label = document.createElement('div');
                label.style.cssText = 'position:absolute;top:5px;left:5px;background:lime;color:black;padding:5px;font-family:monospace;font-size:12px;font-weight:bold;';
                label.textContent = 'CAPTURED: ({x1},{y1}) to ({x2},{y2}) = {x2-x1}×{y2-y1}px';
                highlight.appendChild(label);
                mapDiv.appendChild(highlight);
            }})();
        """)
        time.sleep(2)

        # ============================================
        # AUTO LEVEL DETECTION BASED ON LOCKED ZOOM
        # Compares locked zoom (at draw time) against
        # MUNICIPAL_ZOOM_DEFAULT (captured on first load).
        # ============================================
        LOGGER.info("=" * 60)
        LOGGER.info("AUTO LEVEL DETECTION")
        LOGGER.info("=" * 60)
        LOGGER.info(f"Municipal zoom (on load)   : {MUNICIPAL_ZOOM_DEFAULT}")
        LOGGER.info(f"Locked zoom (at draw time) : {zoom}")

        # Write browser-sourced values to globals (replaces config reads)
        globals.ZOOM_TYPE      = BROWSER_MAP_STATE['zoomType']   # "in" or "out"
        globals.ZOOM_LEVEL     = int(BROWSER_MAP_STATE['zoom'])
        globals.SELECTED_LAYER = BROWSER_MAP_STATE['mapType']     # "roadmap"/"satellite"/etc.

        # Level detection: zoom increased beyond default → ward level
        if zoom > MUNICIPAL_ZOOM_DEFAULT:
            detected_level = "ward"
            LOGGER.info(f"Locked zoom {zoom} > municipal default {MUNICIPAL_ZOOM_DEFAULT} → WARD level")
        else:
            detected_level = "municipal"
            LOGGER.info(f"Locked zoom {zoom} <= municipal default {MUNICIPAL_ZOOM_DEFAULT} → MUNICIPAL level")

        LOGGER.info(f"Detected level: {detected_level.upper()}")

        # ============================================
        # AUTO CALIBRATION — Ward level only
        # Uses the SAME open browser, no second instance
        # ============================================
        if detected_level == "ward":
            update_progress_msg(root, progress_message,
                                "Ward level detected → running auto-calibration...")
            LOGGER.info("Ward level → starting observation table calibration")

            try:
                h_dist, v_dist, H_DIST, V_DIST = distance.get_hv_dist(tl, br, tr)

                # ── Compute both axes' bounds BEFORE building any sample grids ──
                min_lat = min(tl[0], bl[0])
                max_lat = max(tl[0], tr[0])
                min_lng = min(tl[1], bl[1])
                max_lng = max(tr[1], br[1])

                n_samples_2d = 3
                cal_latitudes_2d = [
                    min_lat + i * (max_lat - min_lat) / (n_samples_2d - 1)
                    for i in range(n_samples_2d)
                ]
                cal_longitudes_2d = [
                    min_lng + i * (max_lng - min_lng) / (n_samples_2d - 1)
                    for i in range(n_samples_2d)
                ]

                LOGGER.info(f"Calibration latitudes: {[round(l, 5) for l in cal_latitudes_2d]}")
                LOGGER.info(f"Calibration longitudes: {[round(l, 5) for l in cal_longitudes_2d]}")
                LOGGER.info(f"V_DIST for calibration: {V_DIST:.4f}m")

                base_top    = globals.CROP_TOP_BUTTON_MIN
                base_bottom = globals.CROP_TOP_BUTTON_MIN

                OBSERVATION_TABLE, OBSERVATION_TABLE_H = run_combined_calibration_2d(
                    DRIVER, wait, cal_latitudes_2d, cal_longitudes_2d,
                    base_top, base_bottom
                )
                LOGGER.info(f"✓ Vertical observation table: {len(OBSERVATION_TABLE)} entries")
                LOGGER.info(f"  Table: {OBSERVATION_TABLE}")
                LOGGER.info(f"✓ Horizontal observation table: {len(OBSERVATION_TABLE_H)} entries")
                LOGGER.info(f"  Table: {OBSERVATION_TABLE_H}")

                global FLAT_V_DELTA, FLAT_H_DELTA
                FLAT_V_DELTA = resolve_flat_delta(OBSERVATION_TABLE)
                FLAT_H_DELTA = resolve_flat_delta(OBSERVATION_TABLE_H)

                CALIBRATION_DRIVER = DRIVER
                CALIBRATION_WAIT   = wait

                update_progress_msg(root, progress_message,
                                    f"Calibration done! {len(OBSERVATION_TABLE)} entries. "
                                    f"Browser kept open.")

            except Exception as cal_err:
                LOGGER.error(f"Calibration failed (non-fatal): {cal_err}", exc_info=True)
                OBSERVATION_TABLE = []
                OBSERVATION_TABLE_H = []
                CALIBRATION_DRIVER = None
                CALIBRATION_WAIT   = None
                update_progress_msg(root, progress_message,
                                    "Calibration failed — proceeding without observation table.")
        else:
            # Municipal level — skip calibration entirely
            OBSERVATION_TABLE  = []
            CALIBRATION_DRIVER = None
            CALIBRATION_WAIT   = None
            LOGGER.info("Municipal level → observation table skipped")
            update_progress_msg(root, progress_message,
                                "Municipal level detected — no calibration needed.")

        # ============================================
        # KATAHO CODES
        # ============================================
        kodes = [
            map_.latlon_to_kode(tl),
            map_.latlon_to_kode(tr),
            map_.latlon_to_kode(br),
            map_.latlon_to_kode(bl),
        ]

        LOGGER.info("Kataho codes generated:")
        for i, kode in enumerate(kodes):
            LOGGER.info(f"  {i+1}. {kode}")

        kode_input.config(state="normal")
        kode_input.delete("1.0", tk.END)
        kode_input.insert(tk.END, "\n".join(kodes))
        kode_input.config(state="disabled")

        update_progress_msg(root, progress_message, "Area selected successfully!")

        # ============================================
        # FINAL MESSAGEBOX
        # ============================================
        level_info = (
            f"Level: WARD (zoom={zoom})\n"
            f"Observation table: {len(OBSERVATION_TABLE)} entries\n"
            f"Browser kept open for Generate Tiles."
            if detected_level == "ward"
            else
            f"Level: MUNICIPAL (zoom={zoom})\n"
            f"No calibration needed."
        )

        messagebox.showinfo(
            "Selection Complete",
            f"Rectangle selected!\n\n"
            f"Size: {rect_width:.0f} x {rect_height:.0f} CSS pixels\n"
            f"Physical: {rect_width * dpr:.0f} x {rect_height * dpr:.0f} pixels\n"
            f"Geographic span: {lat_span:.6f}° x {lng_span:.6f}°\n\n"
            f"Using LOCKED center: ({center_lat:.5f}, {center_lng:.5f})\n"
            f"Using LOCKED zoom: {zoom}\n"
            f"Map Type: {map_type}\n\n"
            f"Using TILE zoom: {adjustable_zoom}\n\n"
            f"{level_info}\n\n"
            f"Check log for details."
        )

        # Only quit browser if municipal (ward keeps it open for generation)
        if detected_level != "ward":
            DRIVER.quit()

    except Exception as e:
        messagebox.showerror("Error", f"Failed to select area: {str(e)}")
        LOGGER.error(f"Error in select_area: {str(e)}", exc_info=True)
        try:
            DRIVER.quit()
        except Exception:
            pass
        CALIBRATION_DRIVER = None
        CALIBRATION_WAIT   = None


# =========================
# UI HELPERS
# =========================
def toggle_password():
    if password_entry.cget("show") == "*":
        password_entry.config(show="")
        toggle_button.config(text="Mask")
    else:
        password_entry.config(show="*")
        toggle_button.config(text="Show")


def validate_num_input(val: str):
    return val.isnumeric()


def validate_alpha_input(val: str):
    return val.isalpha()


def init_browser(driver, url):
    driver.maximize_window()
    driver.get(url)
    time.sleep(0.4)


def update_widget_mode(mode):
    email_entry.config(state=mode)
    password_entry.config(state=mode)
    toggle_button.config(state=mode)


def show_selection():
    global MAP_CONFIGS
    match selected.get():
        case "A":
            update_widget_mode("normal")
            MAP_CONFIGS = configs.MAP_CONFIG_AUTH
        case "NA":
            email_entry.delete(0, "end")
            password_entry.delete(0, "end")
            update_widget_mode("disabled")
            MAP_CONFIGS = configs.MAP_CONFIG_NO_AUTH
    changes_with_level_selection("")



def navigate_map_to(driver, lat, lng, zoom):
    """Force map to navigate to exact lat/lng via JS — Leaflet version."""
    result = driver.execute_script(f"""
        const m = window.__MAP_INSTANCE__;
        if (!m) return false;
        m.setView([{lat}, {lng}], {zoom}, {{animate: false}});
        return true;
    """)
    return result


# =========================
# MAIN GENERATION FUNCTION (LEGACY)
# =========================
def main(latlons: list[tuple[float, float]], logger: logging.Logger):
    """Main function to generate map tiles and stitch them together (legacy mode)."""
    left_top, right_buttom, right_top, central_lon = map_.minmax_latlon(latlons)
    CROP_BUTTON = CROP_TOP = image.get_delta_pixel_crop(central_lon)
    H_DIST = haversine(left_top, right_top)   # top-left to top-right = full width
    V_DIST = haversine(left_top, right_buttom)   # top-left to bottom-left = full height
    h_dist = H_DIST              # keep for compatibility
    v_dist = V_DIST

    filepath = get_savefile_path()
    if filepath is None:
        messagebox.showerror("Filepath Error", "Filepath is not selected.")
        return

    outpath.config(text=filepath.name)
    n_h_folds, n_v_folds = distance.calculate_folds(left_top, right_buttom, H_DIST, V_DIST)
    odds = required_odds(n_h_folds, n_v_folds)
    distant_point = distance.calcualte_distant_point(
        left_top,
        dist=float(relocate_distance_entry.get()),
        angle=configs.RELOCATE_DIRECTIONS_MAPPING[selected_direction.get()],
    )

    show_comption_time(n_v_folds, n_h_folds)
    update_progress_msg(root, progress_message, "Initializing browser.")

    if selected_level.get() == configs.LEVELS[5]:
        DRIVER.fullscreen_window()
        time.sleep(1)
        options = webdriver.ChromeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        DRIVER = webdriver.Chrome(options=options)
    else:
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        DRIVER = webdriver.Chrome(options=options)

    wait = WebDriverWait(DRIVER, 3)

    match selected.get().upper():
        case "A":
            init_browser(DRIVER, configs.MAP_URL)
            if not email_entry.get().strip() and not password_entry.get().strip():
                messagebox.showerror("Error", "Credentials not provided.")
                return
            update_progress_msg(root, progress_message, "Authenticating.")
            map_.enter_email(wait, email_entry.get().strip())
            map_.enter_password(wait, password_entry.get().strip())
            map_.click_login_btn(wait)
            if DRIVER.current_url != globals.REQ_URL_AFTER_LOGIN:
                messagebox.showerror("Error", "Authentication error.")
                return
            update_progress_msg(root, progress_message, "Loading map.")
            map_.click_org_map(wait)
            time.sleep(1)
        case "NA":
            init_browser(DRIVER, configs.NO_AUTH_MAP_URL)
        case _:
            messagebox.showerror("Error", f"{selected.get().upper()} is not valid.")
            return

    # ── Go full-screen so screenshots don't include browser chrome
    #    and every tile is captured at the max, consistent viewport ──
    update_progress_msg(root, progress_message, "Switching to full screen...")
    DRIVER.fullscreen_window()
    time.sleep(1.5)
    LOGGER.info("Switched to full screen (fullscreen_window)")

    # Verify it actually took
    is_fullscreen = DRIVER.execute_script("return window.innerHeight === screen.height;")
    LOGGER.info(f"Fullscreen check: innerHeight={DRIVER.execute_script('return window.innerHeight')}, "
                f"fullscreen_likely={is_fullscreen}")   

    update_progress_msg(root, progress_message, "Changing map.")
    map_.select_map_layer(wait, configs.LAYERS_BTN_MAPPING[selected_layer.get()])
    time.sleep(1.5)

    update_progress_msg(root, progress_message, "Activating grid.")
    map_.activate_grid(wait)
    time.sleep(1.5)

    update_progress_msg(root, progress_message, "Adjusting Zoom level.")
    if globals.ZOOM_TYPE == "out":
        map_.zoom_out_map(DRIVER)
    elif globals.ZOOM_TYPE == "in":
        map_.zoom_in_map(DRIVER)
    time.sleep(1.5)

    update_progress_msg(root, progress_message, "Relocating.")
    manual_config_duration = config_delay_entry.get()
    update_progress_msg(root, progress_message,
                        f"Waiting {manual_config_duration} seconds for manual configurations.")
    time.sleep(float(manual_config_duration))

    kode_input_field = map_.get_kode_input_field(wait)
    kode = map_.latlon_to_kode(distant_point)
    map_.drag_map(kode_input_field, kode)

    data = image.snap_crop_tile(
        DRIVER, left_top, kode_input_field, odds, n_v_folds, n_h_folds,
        H_DIST, V_DIST, CROP_BUTTON, CROP_TOP, root, progress_message,
        is_ward_plus_2=True if selected_level.get() == configs.LEVELS[5] else False,
    )
    if data is None:
        return

    image_tiles, nr, nc = data
    full_image = image.concat_tiles(
        image_tiles, n_v_folds, n_h_folds,
        is_ward_plus_2=True if selected_level.get() == configs.LEVELS[5] else False,
    )
    save_image(full_image, filepath.name)
    logger.info(f"Image saved at {filepath.name}")
    update_progress_msg(root, progress_message, "Completed.")
    DRIVER.quit()


def update_globals():
    globals.SELECTED_LEVEL      = selected_level.get().strip()
    # REMOVED: globals.RELOCATE_DISTANCE — widget deleted

    url = url_entry.get().strip()
    if url:
        if selected.get() == "A":
            configs.MAP_URL = url
        elif selected.get() == "NA":
            configs.NO_AUTH_MAP_URL = url

    if MAP_CONFIGS is None:
        raise Exception("MAP_CONFIGS is None.")

    globals.N_H_BOX             = MAP_CONFIGS[selected_level.get()]["n_h_box"]
    globals.N_V_BOX             = MAP_CONFIGS[selected_level.get()]["n_v_box"]
    globals.CROP_TOP_BUTTON_MIN = MAP_CONFIGS[selected_level.get()]["crop_top_button_min"]
    globals.CROP_LEFT           = MAP_CONFIGS[selected_level.get()]["crop_left"]
    globals.CROP_RIGHT          = MAP_CONFIGS[selected_level.get()]["crop_right"]

    if BROWSER_MAP_STATE:
        globals.ZOOM_TYPE      = BROWSER_MAP_STATE['zoomType']
        globals.ZOOM_LEVEL     = int(BROWSER_MAP_STATE['zoom'])
        globals.SELECTED_LAYER = BROWSER_MAP_STATE['mapType']

        
# AFTER — only updates what still exists:
def changes_with_level_selection(value):
    if MAP_CONFIGS is None:
        return
    # Zoom type and zoom level are sourced from browser at runtime
    # Only MAP_CONFIGS structural values (N_H_BOX etc.) are still used here
    LOGGER.info(f"Level changed to: {selected_level.get()}")


def haversine(p1, p2):
    R = 6371000
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# =========================
# GENERATE FUNCTION
# =========================
def generate_from_selected_area():
    """
    Generates map tiles following the documented algorithm.
    Uses values captured in select_area():
    - corners, adjustable_zoom, map_type (from browser lock)
    - BROWSER_MAP_STATE (zoom, zoomType, mapType — replaces config)
    - OBSERVATION_TABLE (ward level calibration)
    - CALIBRATION_DRIVER (reused browser if ward level)
    """
    global adjustable_zoom, corners, locked_zoom, center_lat, center_lng, map_type
    global CALIBRATION_DRIVER, CALIBRATION_WAIT
    global SELECTED_MAP_LAYER

    # STEP 1: Validate
    if not corners or len(corners) != 4:
        messagebox.showerror("Error", "4 corners not set! Please select area first.")
        return
    if adjustable_zoom is None:
        messagebox.showerror("Error", "Adjustable zoom not set!")
        return
    if not BROWSER_MAP_STATE:
        messagebox.showerror("Error", "Please run Select Area before generating.")
        return

    # STEP 2: Extract coordinates
    tl, tr, br, bl = corners
    LOGGER.info("=" * 60)
    LOGGER.info("MAP TILE GENERATION - FOLLOWING ALGORITHM")
    LOGGER.info("=" * 60)
    LOGGER.info(f"Corners: TL={tl}, TR={tr}, BR={br}, BL={bl}")
    LOGGER.info(f"Tile Zoom: {adjustable_zoom}, Map Type: {SELECTED_MAP_LAYER}")

    min_lat = min(tl[0], tr[0], br[0], bl[0])
    max_lat = max(tl[0], tr[0], br[0], bl[0])
    min_lng = min(tl[1], tr[1], br[1], bl[1])
    max_lng = max(tl[1], tr[1], br[1], bl[1])

    center_lat_val = (max_lat + min_lat) / 2
    center_lng_val = (max_lng + min_lng) / 2   # add this if not already present

    left_top     = tl
    right_bottom = br
    right_top    = tr
    central_lon  = (min_lng + max_lng) / 2

    # STEP 3: Update globals from browser state (not config)
    globals.ZOOM_TYPE      = BROWSER_MAP_STATE['zoomType']
    globals.ZOOM_LEVEL     = int(BROWSER_MAP_STATE['zoom'])
    globals.SELECTED_LAYER = SELECTED_MAP_LAYER
    LOGGER.info(f"Browser-sourced: zoom={globals.ZOOM_LEVEL}, "
                f"type={globals.ZOOM_TYPE}, layer={globals.SELECTED_LAYER}")

    try:
        update_globals()  # writes N_H_BOX, N_V_BOX, CROP_* from MAP_CONFIGS by level
    except Exception as e:
        LOGGER.warning(f"update_globals partial failure: {e}")

    # STEP 4: Crop parameters
    raw_crop = image.get_delta_pixel_crop(central_lon)
    LOGGER.info(f"get_delta_pixel_crop returned: {raw_crop}")

    # Use globals from MAP_CONFIGS instead — these are calibrated per level
    CROP_TOP    = globals.CROP_TOP_BUTTON_MIN
    CROP_BUTTON = globals.CROP_TOP_BUTTON_MIN
    LOGGER.info(f"Crop parameters: top={CROP_TOP}, bottom={CROP_BUTTON}")

    # STEP 5: Distances + zoom-adjusted tile grid
    H_DIST = haversine(left_top, right_top)   # top-left to top-right = full width
    V_DIST = haversine(left_top, right_bottom)   # top-left to bottom-left = full height
    h_dist = H_DIST              # keep for compatibility
    v_dist = V_DIST
    LOGGER.info(f"Bounding box: H_DIST={H_DIST:.2f}m, V_DIST={V_DIST:.2f}m")
    LOGGER.info(f"TRUE Bounding box: H_DIST={H_DIST:.1f}m, V_DIST={V_DIST:.1f}m")

    center_lat_val = (max_lat + min_lat) / 2

    def meters_per_pixel(zoom, lat):
        return (156543.03392 * math.cos(math.radians(lat))) / (2 ** zoom)

    mpp_capture = meters_per_pixel(int(adjustable_zoom), center_lat_val)
    LOGGER.info(f"Formula mpp_capture={mpp_capture:.6f} m/px")

    map_w = BROWSER_MAP_STATE.get('mapWidth', 1280)
    map_h = BROWSER_MAP_STATE.get('mapHeight', 541)

    tile_w_px = map_w - (globals.CROP_LEFT + globals.CROP_RIGHT)
    tile_h_px = map_h - (CROP_TOP + CROP_BUTTON)

    TILE_H = tile_w_px * mpp_capture
    TILE_V = tile_h_px * mpp_capture
    n_h_folds = max(1, math.ceil(H_DIST / TILE_H))
    n_v_folds = max(1, math.ceil(V_DIST / TILE_V))


    # ── Center the capture grid on the rectangle's actual center,
    # instead of anchoring it at the rectangle's NW corner. This keeps
    # your selection centered within the capture area on every axis,
    # rather than pushed toward one edge when the rectangle is smaller
    # than a full tile. ──
    total_capture_width  = n_h_folds * TILE_H
    total_capture_height = n_v_folds * TILE_V

    rect_center_point = (center_lat_val, center_lng_val)

    # Move from rectangle center to the NW corner of the (possibly larger)
    # total capture area
    grid_origin = distance.calcualte_distant_point(
        rect_center_point, dist=total_capture_width / 2, angle=270  # west
    )
    grid_origin = distance.calcualte_distant_point(
        grid_origin, dist=total_capture_height / 2, angle=0  # north
    )
    LOGGER.info(f"Grid origin (centered): {grid_origin} "
                f"(total capture: {total_capture_width:.1f}m x {total_capture_height:.1f}m)")

    
    LOGGER.info(f"Recalculated — TILE_H={TILE_H:.1f}m TILE_V={TILE_V:.1f}m")
    LOGGER.info(f"Recalculated — Grid: {n_h_folds}h x {n_v_folds}v")
    LOGGER.info(f"capture zoom={adjustable_zoom}, mpp={mpp_capture:.4f}m/px")
    LOGGER.info(f"tile_w_px={tile_w_px}, tile_h_px={tile_h_px}")
    LOGGER.info(f"TILE_H={TILE_H:.1f}m, TILE_V={TILE_V:.1f}m")
    LOGGER.info(f"H_DIST={H_DIST:.1f}m, V_DIST={V_DIST:.1f}m")
    LOGGER.info(f"Grid: {n_h_folds}h x {n_v_folds}v = {n_h_folds*n_v_folds} tiles")
    
    # STEP 6: Output file
    filepath = get_savefile_path()
    if not filepath:
        messagebox.showerror("Error", "No output file selected.")
        return
    outpath.config(text=filepath.name)

    # STEP 7: Distant point (auto-derived)
    # STEP 7: Odds + timing
    odds = required_odds(n_h_folds, n_v_folds)
    show_comption_time(n_v_folds, n_h_folds)

    # STEP 9: Single distant point calculation — SW of top-left
    relocate_dir  = 225
    relocate_dist = math.sqrt(H_DIST**2 + V_DIST**2) / 2
    distant_point = distance.calcualte_distant_point(grid_origin, dist=relocate_dist, angle=relocate_dir)
    
    LOGGER.info(f"Relocate: {relocate_dist:.2f}m at {relocate_dir}° → {distant_point}")

    # STEP 10: Browser — reuse calibration browser if ward level, else open new
    is_ward = bool(OBSERVATION_TABLE)  # ward level produced a calibration table

    if CALIBRATION_DRIVER:
        update_progress_msg(root, progress_message, "Reusing calibration browser...")
        DRIVER = CALIBRATION_DRIVER
        wait   = CALIBRATION_WAIT
        already_authenticated = True
        LOGGER.info("Reusing CALIBRATION_DRIVER — skipping login")
    else:
        update_progress_msg(root, progress_message, "Initializing browser...")
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--log-level=3")
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        DRIVER = webdriver.Chrome(options=options)
        wait   = WebDriverWait(DRIVER, 15)
        already_authenticated = False

    try:
        # STEP 11: Authenticate only if new browser
        if not already_authenticated:
            update_progress_msg(root, progress_message, "Authenticating...")
            DRIVER.get("https://kataho.app/login")
            map_.enter_email(wait, email_entry.get())
            map_.enter_password(wait, password_entry.get())
            map_.click_login_btn(wait)
            WebDriverWait(DRIVER, 20).until(lambda d: "/login" not in d.current_url)
            DRIVER.get("https://kataho.app/organization/organization-maps")
            if not wait_for_google_map(DRIVER, timeout=30):
                messagebox.showerror("Error", "Map did not load.")
                return
            time.sleep(2)


        # STEP 12: Set map layer — reuse the value locked during select_area().
        # Do NOT re-read the dropdown here; the layer choice made before
        # Select Area is what defines this whole capture session.
        if not already_authenticated:
            # ── For municipal level, add extra wait for layers to load before setting ──
            time.sleep(2)

            # ── Retry layer setting if it fails on first attempt ──
            result = None
            for attempt in range(3):
                result = map_.set_map_layer_direct(DRIVER, SELECTED_MAP_LAYER)
                if result and result.get('success'):
                    LOGGER.info(f"✓ Layer set to: {SELECTED_MAP_LAYER} | url={result['url']} maxZoom={result['maxZoom']}")
                    break
                else:
                    LOGGER.warning(f"  Layer switch attempt {attempt+1}/3 failed, retrying...")
                    time.sleep(1.5)

            if not (result and result.get('success')):
                LOGGER.error(f"✗ Layer switch to '{SELECTED_MAP_LAYER}' failed after retries: {result.get('error') if result else 'no result'}")
        else:
            LOGGER.info(f"Reusing calibration browser — layer already set to {SELECTED_MAP_LAYER}")



        # STEP 13: Activate grid
        update_progress_msg(root, progress_message, "Activating grid...")

        # ── Remove rect-overlay before clicking grid button ──
        DRIVER.execute_script("""
            const overlay = document.getElementById('rect-overlay');
            if (overlay) overlay.remove();
            const highlight = document.getElementById('capture-highlight');
            if (highlight) highlight.remove();
            const coordInfo = document.getElementById('coord-info');
            if (coordInfo) coordInfo.remove();
        """)
        time.sleep(0.3)

        map_.activate_grid(wait)
        time.sleep(1.5)
        

        # ── Go full-screen so screenshots don't include browser chrome
        # and every tile is captured at the max, consistent viewport ──
        update_progress_msg(root, progress_message, "Switching to full screen...")
        DRIVER.fullscreen_window()
        time.sleep(1.5)
        LOGGER.info("Switched to full screen (fullscreen_window)")

        # Verify it actually took
        is_fullscreen = DRIVER.execute_script("return window.innerHeight === screen.height;")
        LOGGER.info(f"Fullscreen check: innerHeight={DRIVER.execute_script('return window.innerHeight')}, "
                    f"fullscreen_likely={is_fullscreen}")
        

        # STEP 14: Set zoom
        update_progress_msg(root, progress_message, f"Setting zoom to {adjustable_zoom}...")
        DRIVER.execute_script(f"""
            const m = window.__MAP_INSTANCE__;
            if (m) {{ m.setZoom({int(adjustable_zoom)}); }}
        """)
        time.sleep(1.5)


        # ── Measure actual mpp from live browser ──
        point_a = grid_origin
        point_b = distance.calcualte_distant_point(grid_origin, dist=1000.0, angle=90)

        navigate_map_to(DRIVER, point_a[0], point_a[1], int(adjustable_zoom))
        time.sleep(globals.REFRESH_DURATION)
        state_a = DRIVER.execute_script("""
            const m = window.__MAP_INSTANCE__;
            if (!m) return null;
            const c = m.getCenter();
            return {lat: c.lat, lng: c.lng};
        """)
        navigate_map_to(DRIVER, point_b[0], point_b[1], int(adjustable_zoom))
        time.sleep(globals.REFRESH_DURATION)
        state_b = DRIVER.execute_script("""
            const m = window.__MAP_INSTANCE__;
            if (!m) return null;
            const c = m.getCenter();
            return {lat: c.lat, lng: c.lng};
        """)

        if state_a and state_b:
            TILE_SIZE = 256
            scale = 2 ** int(adjustable_zoom)

            def latlng_to_world_px(lat, lng):
                siny = math.sin(math.radians(lat))
                siny = min(max(siny, -0.9999), 0.9999)
                wx = TILE_SIZE * (0.5 + lng / 360.0) * scale
                wy = TILE_SIZE * (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * scale
                return wx, wy

            wx_a, _ = latlng_to_world_px(state_a['lat'], state_a['lng'])
            wx_b, _ = latlng_to_world_px(state_b['lat'], state_b['lng'])
            pixel_diff = abs(wx_b - wx_a)

            if pixel_diff > 0:
                measured_mpp = 1000.0 / pixel_diff
                LOGGER.info(f"Measured mpp={measured_mpp:.6f} m/px (formula={mpp_capture:.6f})")
                mpp_capture = measured_mpp
            else:
                LOGGER.warning("mpp measurement failed — using formula")

        # STEP 15: Manual config wait
        manual_config_duration = 5  # seconds
        if manual_config_duration > 0:
            update_progress_msg(root, progress_message,
                                f"Waiting {manual_config_duration}s for manual config...")
            time.sleep(manual_config_duration)

        # STEP 16: Relocate to distant point
        update_progress_msg(root, progress_message, "Relocating to starting position...")
        kode_input_field = map_.get_kode_input_field(wait)
        kode = map_.latlon_to_kode(distant_point)
        map_.drag_map(kode_input_field, kode)
        time.sleep(1.5)
        LOGGER.info(f"Relocated to: {distant_point}")
        time.sleep(globals.REFRESH_DURATION)

        # ✅ Verify map actually moved to new center
        actual_center = DRIVER.execute_script("""
            const m = window.__MAP_INSTANCE__;
            if (!m) return null;
            const c = m.getCenter();
            return c ? {lat: c.lat, lng: c.lng} : null;
        """)
           

        # ============================================
        # STEP 17: CAPTURE TILES  
        # ============================================
                
        all_lats = [tl[0], tr[0], br[0], bl[0]]
        all_lngs = [tl[1], tr[1], br[1], bl[1]]
        left_top  = (max(all_lats), min(all_lngs))  # max lat = north, min lng = west
        LOGGER.info(f"Tile origin (true top-left): {left_top}")

        # Placeholder — grid_origin will be computed after tile calibration
        grid_origin = left_top

        image_tiles = []
        tile_count  = 0

        half_h = TILE_H / 2
        half_v = TILE_V / 2
        # ✅ Initialize before loop so it's always bound
        tile_center = None

        # Get actual map div size at capture time
        actual_map_dims = DRIVER.execute_script("""
            const mapDiv = document.getElementById('map');
            if (!mapDiv) return null;
            const r = mapDiv.getBoundingClientRect();
            return {w: Math.round(r.width), h: Math.round(r.height)};
        """)
        if actual_map_dims:
            map_w = actual_map_dims['w']
            map_h = actual_map_dims['h']
            BROWSER_MAP_STATE['mapWidth']  = map_w
            BROWSER_MAP_STATE['mapHeight'] = map_h
            LOGGER.info(f"Actual map div at capture time: {map_w}x{map_h}")

        LOGGER.info(f"Crops: top={CROP_TOP} bottom={CROP_BUTTON} left={globals.CROP_LEFT} right={globals.CROP_RIGHT}")
        LOGGER.info(f"Effective tile size after crop: {tile_w_px}x{tile_h_px}px")

        # ── Pre-compute grid_origin based on initial tile estimate ──
        # (will be refined after calibration)
        initial_n_h = max(1, int(H_DIST / (tile_w_px * mpp_capture)))
        initial_n_v = max(1, int(V_DIST / (tile_h_px * mpp_capture)))
        initial_total_w = initial_n_h * (tile_w_px * mpp_capture)
        initial_total_h = initial_n_v * (tile_h_px * mpp_capture)

        rect_center = ((min_lat + max_lat) / 2, (min_lng + max_lng) / 2)
        grid_origin = distance.calcualte_distant_point(
            rect_center, dist=initial_total_w / 2, angle=270
        )
        grid_origin = distance.calcualte_distant_point(
            grid_origin, dist=initial_total_h / 2, angle=0
        )

        # ── Calibrate tile size from a real screenshot BEFORE the main loop ──
        navigate_map_to(DRIVER, grid_origin[0], grid_origin[1], int(adjustable_zoom))
        time.sleep(globals.REFRESH_DURATION)
        clean_browser_ui(DRIVER)
        time.sleep(0.3)

        wait_for_tiles_loaded(DRIVER)


        DRIVER.execute_script(
            "document.body.style.display='none';"
            "document.body.offsetHeight;"
            "document.body.style.display='';"
        )
        time.sleep(0.1)
        cal_screenshot = DRIVER.get_screenshot_as_base64()
        cal_image      = image.b64_to_image(cal_screenshot)
        cal_cropped    = image.crop_image(
            cal_image,
            crop_top=CROP_TOP, crop_bottom=CROP_BUTTON,
            crop_left=globals.CROP_LEFT, crop_right=globals.CROP_RIGHT
        )
        actual_tile_h_px = cal_cropped.shape[0]
        actual_tile_w_px = cal_cropped.shape[1]
        LOGGER.info(f"Calibration tile raw={cal_image.shape} cropped={cal_cropped.shape}")

        # Recalculate tile coverage from actual pixel size
        TILE_H = actual_tile_w_px * mpp_capture
        TILE_V = actual_tile_h_px * mpp_capture
        half_h = TILE_H / 2
        half_v = TILE_V / 2
        n_h_folds = max(1, int(H_DIST / TILE_H))
        n_v_folds = max(1, int(V_DIST / TILE_V))

        # ── Refine grid_origin with calibrated tile sizes ──
        total_capture_width  = n_h_folds * TILE_H
        total_capture_height = n_v_folds * TILE_V

        rect_center_point = ((min_lat + max_lat) / 2, (min_lng + max_lng) / 2)

        # Move from rectangle center to the NW corner of the (possibly larger)
        # total capture area
        grid_origin = distance.calcualte_distant_point(
            rect_center_point, dist=total_capture_width / 2, angle=270  # west
        )
        grid_origin = distance.calcualte_distant_point(
            grid_origin, dist=total_capture_height / 2, angle=0  # north
        )
        LOGGER.info(f"CALIBRATED TILE_H={TILE_H:.1f}m TILE_V={TILE_V:.1f}m")
        LOGGER.info(f"Grid origin (refined, centered): {grid_origin} (total capture: {total_capture_width:.1f}m x {total_capture_height:.1f}m)")
        LOGGER.info(f"CALIBRATED grid={n_h_folds}h x {n_v_folds}v = {n_h_folds*n_v_folds} tiles")

        col_origins = []
        for h_idx in range(n_h_folds):
            east_dist  = (TILE_H * h_idx) + half_h
            col_origin = distance.calcualte_distant_point(grid_origin, dist=east_dist, angle=90)
            col_origins.append(col_origin)
        LOGGER.info(f"Column origins computed: {len(col_origins)} columns")


        for v_idx in range(n_v_folds):
            south_dist = (TILE_V * v_idx) + half_v
            h_image_tiles = []

            for h_idx in range(n_h_folds):
                # Move south from THIS column's top-edge origin
                tile_center = distance.calcualte_distant_point(
                    col_origins[h_idx], dist=south_dist, angle=180
                )
                tile_count += 1

                LOGGER.info("=" * 40)
                LOGGER.info(f"TILE {tile_count} | row={v_idx} col={h_idx}")
                LOGGER.info(f"  tile_center : {tile_center}")
                LOGGER.info(f"  east_dist   : {east_dist:.2f}m")
                LOGGER.info(f"  south_dist  : {south_dist:.2f}m")
                LOGGER.info("=" * 40)


                #  Refresh kode input field each tile (stale element fix)
                # ✅ Navigate via JS directly — bypasses broken kode input
                nav_success = navigate_map_to(
                    DRIVER, 
                    tile_center[0], 
                    tile_center[1], 
                    int(adjustable_zoom)
                )
                if not nav_success:
                    LOGGER.warning(f"JS navigation failed at tile {tile_count} — trying kode fallback")
                    try:
                        kode_input_field = map_.get_kode_input_field(wait)
                        map_.drag_map(kode_input_field, tile_kode)
                    except Exception as e:
                        LOGGER.error(f"Fallback drag_map also failed: {e}")

                time.sleep(globals.REFRESH_DURATION)

                # Verify map moved
                try:
                    actual_center = DRIVER.execute_script("""
                        const m = window.__MAP_INSTANCE__;
                        if (!m) return null;
                        const c = m.getCenter();
                        return c ? {lat: c.lat, lng: c.lng} : null;
                    """)
                    if actual_center and tile_center is not None:
                        LOGGER.info(
                            f"  Map center after drag: "
                            f"({actual_center['lat']:.6f}, {actual_center['lng']:.6f}) "
                            f"expected ({tile_center[0]:.6f}, {tile_center[1]:.6f})"
                        )
                    elif actual_center:
                        LOGGER.info(
                            f"  Map center after drag: "
                            f"({actual_center['lat']:.6f}, {actual_center['lng']:.6f})"
                        )
                    else:
                        LOGGER.warning(f"  Map center unreadable at tile {tile_count}")
                except Exception as e:
                    LOGGER.warning(f"  Center verify failed: {e}")

                # Verify zoom
                actual_zoom = DRIVER.execute_script("""
                    const m = window.__MAP_INSTANCE__;
                    return m ? m.getZoom() : null;
                """)
                if actual_zoom != int(adjustable_zoom):
                    LOGGER.warning(f"Zoom mismatch: expected {adjustable_zoom}, got {actual_zoom}")
                    DRIVER.execute_script(f"""
                        const m = window.__MAP_INSTANCE__;
                        if (m) m.setZoom({int(adjustable_zoom)});
                    """)
                    time.sleep(0.5)

                update_progress_msg(root, progress_message,
                                    f"Capturing tile {tile_count}/{n_h_folds * n_v_folds} "
                                    f"(row {v_idx+1}/{n_v_folds}, col {h_idx+1}/{n_h_folds})")

                clean_browser_ui(DRIVER)
                time.sleep(0.3)  # increased from 0.15

                wait_for_tiles_loaded(DRIVER)
                # Force repaint before screenshot
                DRIVER.execute_script(
                    "document.body.style.display='none';"
                    "document.body.offsetHeight;"
                    "document.body.style.display='';"
                )
                time.sleep(0.1)

                # Refresh field after clean_browser_ui (it may remove map UI elements)
                try:
                    kode_input_field = map_.get_kode_input_field(wait)
                except Exception as e:
                    LOGGER.warning(f"Post-clean field refresh failed: {e}")

                screenshot_base64 = DRIVER.get_screenshot_as_base64()
                tile_image = image.b64_to_image(screenshot_base64)

                if is_ward and OBSERVATION_TABLE and OBSERVATION_TABLE_H:
                    adj_top, adj_bottom = get_calibrated_crop(tile_center[0], tile_center[1], CROP_TOP, CROP_BUTTON)
                    adj_left, adj_right = get_calibrated_crop_horizontal(tile_center[0], tile_center[1], globals.CROP_LEFT, globals.CROP_RIGHT)

                    cropped_tile = image.crop_image(
                        tile_image,
                        crop_top=adj_top, crop_bottom=adj_bottom,
                        crop_left=adj_left, crop_right=adj_right
                    )
                else:
                    cropped_tile = image.crop_image(
                        tile_image,
                        crop_top=CROP_TOP, crop_bottom=CROP_BUTTON,
                        crop_left=globals.CROP_LEFT, crop_right=globals.CROP_RIGHT
                    )

                # ── Catch size drift immediately, not 300 tiles later at stitch time ──
                expected_shape = image_tiles[0][0].shape if image_tiles and image_tiles[0] else None
                if expected_shape and cropped_tile.shape != expected_shape:
                    LOGGER.error(
                        f"  ✗ TILE {tile_count} SIZE MISMATCH: got {cropped_tile.shape}, "
                        f"expected {expected_shape} (row={v_idx}, col={h_idx}, "
                        f"lat={tile_center[0]:.6f}, lng={tile_center[1]:.6f})"
                    )
                    if is_ward and OBSERVATION_TABLE and OBSERVATION_TABLE_H:
                        LOGGER.error(f"    Crop values used: top={adj_top} bottom={adj_bottom} "
                                     f"left={adj_left} right={adj_right} "
                                     f"(base: top={CROP_TOP} bottom={CROP_BUTTON} "
                                     f"left={globals.CROP_LEFT} right={globals.CROP_RIGHT})")
                    # Force-resize to expected shape so the run can still complete
                    # rather than crashing 300 tiles in — pad or center-crop as needed.
                    import numpy as np
                    from PIL import Image as PILImage
                    cropped_tile = np.array(
                        PILImage.fromarray(cropped_tile).resize(
                            (expected_shape[1], expected_shape[0])
                        )
                    )

                h_image_tiles.append(cropped_tile)
            image_tiles.append(h_image_tiles)
        # STEP 18: Stitch tiles
        update_progress_msg(root, progress_message, "Stitching tiles...")
        if not image_tiles or not image_tiles[0]:
            messagebox.showerror("Error", "No tiles captured!")
            return

        import numpy as np
        sample_tile    = image_tiles[0][0]
        height, width  = sample_tile.shape[:2]
        full_image     = np.zeros((height * n_v_folds, width * n_h_folds, 3), dtype=np.uint8)

        for v_index, row_tiles in enumerate(image_tiles):
            for h_index, tile in enumerate(row_tiles):
                full_image[
                    height * v_index : height * (v_index + 1),
                    width  * h_index : width  * (h_index + 1),
                    :
                ] = tile

        LOGGER.info("✓ All tiles stitched")


        # STEP 18b: Crop final image to exact rectangle bounds
        # The stitched image covers slightly more than the rectangle due to tile alignment
        # Calculate pixel offset of rectangle TL within the stitched image

        # Top-left of stitched image = left_top (tile origin)
        # Rectangle TL = tl (from corners)
        # Convert geographic offset to pixels

        stitch_origin = grid_origin  # (max_lat, min_lng) — center of tile grid

        # Offset in meters from stitch origin to rectangle TL
        offset_north = haversine(tl, (stitch_origin[0], tl[1]))  # lat diff → meters
        offset_west  = haversine(tl, (tl[0], stitch_origin[1]))  # lng diff → meters

        # These should be ~0 since left_top == tl, but recalculate to be safe
        rect_lat_span = haversine(tl, bl)   # full rectangle height in meters
        rect_lng_span = haversine(tl, tr)   # full rectangle width in meters

        # Pixels per meter in stitched image
        px_per_meter_h = (width  * n_h_folds) / H_DIST
        px_per_meter_v = (height * n_v_folds) / V_DIST

        # Rectangle bounds in stitched image pixels
        rect_px_x1 = int(offset_west  * px_per_meter_h)
        rect_px_y1 = int(offset_north * px_per_meter_v)
        rect_px_x2 = int(rect_px_x1 + rect_lng_span * px_per_meter_h)
        rect_px_y2 = int(rect_px_y1 + rect_lat_span * px_per_meter_v)

        LOGGER.info(f"Stitched image size: {full_image.shape}")
        LOGGER.info(f"Rectangle crop in stitched px: ({rect_px_x1},{rect_px_y1}) to ({rect_px_x2},{rect_px_y2})")

        # Clamp to image bounds
        rect_px_x1 = max(0, rect_px_x1)
        rect_px_y1 = max(0, rect_px_y1)
        rect_px_x2 = min(full_image.shape[1], rect_px_x2)
        rect_px_y2 = min(full_image.shape[0], rect_px_y2)

        full_image = full_image[rect_px_y1:rect_px_y2, rect_px_x1:rect_px_x2]
        LOGGER.info(f"Final cropped image size: {full_image.shape}")

        # STEP 19: Save
        update_progress_msg(root, progress_message, "Saving image...")
        save_image(full_image, filepath.name)
        LOGGER.info(f"✓ Image saved: {filepath.name}")
        update_progress_msg(root, progress_message, "Completed!")

        messagebox.showinfo(
            "Success",
            f"Map successfully generated!\n\n"
            f"📦 Coverage Area:\n"
            f"   {min_lat:.6f} to {max_lat:.6f} (lat)\n"
            f"   {min_lng:.6f} to {max_lng:.6f} (lng)\n\n"
            f"📊 Tile Grid: {n_h_folds} × {n_v_folds} = {n_h_folds * n_v_folds} tiles\n"
            f"🔍 Zoom: {adjustable_zoom}\n"
            f"🗺️  Type: {SELECTED_MAP_LAYER}\n"
            f"🧭 Level: {'WARD (calibrated)' if is_ward else 'MUNICIPAL'}\n\n"
            f"💾 Saved to:\n{filepath.name}"
        )

    except Exception as e:
        messagebox.showerror("Error", f"Failed: {str(e)}")
        LOGGER.error(f"Error: {str(e)}", exc_info=True)
    finally:
        DRIVER.quit()
        CALIBRATION_DRIVER = None
        CALIBRATION_WAIT   = None
        LOGGER.info("Browser closed")


# =========================
# GUI SETUP
# =========================
root = tk.Tk()
root.title(globals.APP_NAME)


def set_app_icon(root, icon_path):
    try:
        icon_path = os.path.abspath(icon_path)
        if os.name == "nt" and icon_path.lower().endswith(".ico"):
            root.iconbitmap(icon_path)
        else:
            icon = tk.PhotoImage(file=icon_path)
            root.iconphoto(True, icon)
    except Exception as e:
        print(f"[WARN] Icon not set: {e}")


set_app_icon(root, globals.ICONPATH)
root.resizable(width=False, height=False)

# Authentication Frame
auth_frame = tk.Frame(root)
auth_frame.pack(padx=5, pady=5, fill=tk.X)

email_label = tk.Label(auth_frame, text="Email")
email_label.grid(row=0, column=0, padx=17, pady=10, sticky="w")
email_entry = tk.Entry(auth_frame, width=50)
email_entry.grid(row=0, column=1, padx=5, pady=10)

password_label = tk.Label(auth_frame, text="Password")
password_label.grid(row=1, column=0, padx=17, pady=10, sticky="w")
password_entry = tk.Entry(auth_frame, width=50, show="*")
password_entry.grid(row=1, column=1, padx=5, pady=10)
toggle_button = tk.Button(auth_frame, text="Show", command=toggle_password)
toggle_button.grid(row=1, column=2, padx=5, pady=5, sticky="e")

update_widget_mode("disabled")

# Mode Frame
mode_frame = tk.Frame(root)
mode_frame.pack(padx=5, pady=5, fill=tk.X)
selected = tk.StringVar(value="NA")

tk.Radiobutton(mode_frame, text="Authentication",    value="A",  variable=selected, command=show_selection).grid(row=0, column=0, padx=10, pady=10, sticky="w")
tk.Radiobutton(mode_frame, text="Non-Authentication", value="NA", variable=selected, command=show_selection).grid(row=0, column=1, padx=10, pady=10, sticky="w")

# Delay Frame
delay_frame = tk.Frame(root)
delay_frame.pack(padx=5, pady=5, fill=tk.X)

selected_level     = tk.StringVar()
selected_level.set(configs.LEVELS[2])


tk.Label(delay_frame, text="Config Delay: ").grid(row=0, column=0, padx=10, pady=10, sticky="w")
config_delay_entry = tk.Entry(delay_frame, width=5)
config_delay_entry.grid(row=0, column=1, padx=5, pady=10, sticky="e")
config_delay_entry.insert(0, "5")
tk.Label(delay_frame, text="seconds").grid(row=0, column=2, padx=5, pady=10, sticky="w")

tk.Label(delay_frame, text="Map Delay: ").grid(row=1, column=0, padx=10, pady=10, sticky="w")
map_refresh_delay_entry = tk.Entry(delay_frame, width=5)
map_refresh_delay_entry.grid(row=1, column=1, padx=10, pady=10, sticky="e")
map_refresh_delay_entry.insert(0, "5")
tk.Label(delay_frame, text="seconds").grid(row=1, column=2, padx=10, pady=10, sticky="w")

tk.Label(delay_frame, text="Level").grid(row=2, column=0, padx=10, pady=1, sticky="w")
level_dropdown = tk.OptionMenu(delay_frame, selected_level, *configs.LEVELS, command=changes_with_level_selection)
level_dropdown.grid(row=3, column=0, padx=10, pady=1, sticky="w")

selected_layer = tk.StringVar()
selected_layer.set(configs.LAYERS_BTN_MAPPING and list(configs.LAYERS_BTN_MAPPING.keys())[0] or "")

tk.Label(delay_frame, text="Layer").grid(row=2, column=1, padx=10, pady=1, sticky="w")
layer_dropdown = tk.OptionMenu(delay_frame, selected_layer, *configs.LAYERS_BTN_MAPPING.keys())
layer_dropdown.grid(row=3, column=1, padx=10, pady=1, sticky="w")


show_selection()

# URL Frame
url_frame = tk.Frame(root)
url_frame.pack(padx=5, pady=5, fill=tk.X)
tk.Label(url_frame, text="Map URL:   ").grid(row=0, column=0, padx=10, pady=10, sticky="w")
url_entry = tk.Entry(url_frame, width=55)
url_entry.grid(row=0, column=1, padx=10, pady=10, sticky="w")

# Input Frame
input_frame = tk.Frame(root)
input_frame.pack(padx=5, pady=5, fill=tk.X)
input_frame.grid_columnconfigure(0, weight=2)
input_frame.grid_columnconfigure(1, weight=6)
input_frame.grid_columnconfigure(2, weight=3)

tk.Label(input_frame, text="Kataho codes").grid(row=0, column=0, padx=10, pady=10, sticky="w")
kode_input = ScrolledText(input_frame, width=30, height=5, state="disabled")
kode_input.grid(row=0, column=1, padx=5, pady=10)
tk.Button(input_frame, text="Select Area", width=9, command=select_area).grid(row=1, column=2, padx=5, pady=5, sticky="e")

tk.Button(root, text="Generate Tiles", command=generate_from_selected_area, width=20).pack(pady=10)

# Output Path Frame
outpath_frame = tk.Frame(root)
outpath_frame.pack(padx=5, pady=5, fill=tk.X)
tk.Label(outpath_frame, text="Filepath: ").grid(row=0, column=0, padx=10, pady=10, sticky="w")
outpath = tk.Label(outpath_frame, text="", width=41)
outpath.grid(row=0, column=1, columnspan=1, padx=10, pady=10, sticky="w")

# Progress Frame
progress_frame = tk.Frame(root)
progress_frame.pack(padx=5, pady=5, fill=tk.X)
tk.Label(progress_frame, text="Progress: ").grid(row=0, column=0, padx=10, pady=10, sticky="w")
progress_message = tk.Label(progress_frame, text="", width=41)
progress_message.grid(row=0, column=1, columnspan=1, padx=10, pady=10, sticky="w")
tk.Button(progress_frame, text="Help", width=7, height=1, command=guide).grid(row=0, column=2, padx=5, pady=10, sticky="e")

root.mainloop()
