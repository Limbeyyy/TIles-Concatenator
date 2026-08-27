import math
import time
from tkinter import messagebox
import selenium.webdriver.support.expected_conditions as EC

from core import globals
from kataho.kataho import KatahoSDK
from selenium.webdriver.common import by
from selenium.webdriver.common.action_chains import ActionChains

def enter_email(wait, email=''):
    try:
        email_field = wait.until(EC.element_to_be_clickable((by.By.ID, 'email')))
        email_field.send_keys(email)
    except Exception as e:
        print(e)

def enter_password(wait, password=''):
    try:
        password_field = wait.until(EC.element_to_be_clickable((by.By.ID, 'password')))
        password_field.send_keys(password)
    except Exception as e:
        print(e)
    
def click_login_btn(wait):
    try:
        login_btn = wait.until(EC.element_to_be_clickable((by.By.ID, "load-page-button")))
        login_btn.click()
    except Exception as e:
        print(e)

def click_org_map(wait):
    try:
        org_map_btn = wait.until(EC.element_to_be_clickable((by.By.PARTIAL_LINK_TEXT, "Organization Map")))
        org_map_btn.click()
    except Exception as e:
        print(e)
    

def click_ok_alert(wait):
    if globals.OK_CLICK and globals.LOCAL:
        try:
            ok_btn = wait.until(EC.element_to_be_clickable((by.By.CSS_SELECTOR, 'button.dismissButton')))
            ok_btn.click()
        except Exception as e:
            print(e)

def activate_grid(wait):
    if globals.GRID_CLICK:
        try:
            grid = wait.until(EC.element_to_be_clickable((by.By.CLASS_NAME, 'map-control')))
            grid.click()
            time.sleep(1)
        except Exception as e:
            print(e)

def select_hybrid_map(wait):
    if globals.MAP_SELECT:
        try:
            map_sidebar = wait.until(EC.element_to_be_clickable((by.By.ID, 'layer-control')))
            map_sidebar.click()

            time.sleep(0.5)
            
            hybrid_map = wait.until(EC.element_to_be_clickable((by.By.ID, 'btn-hybrid')))
            hybrid_map.click()
            
            close_sidebar = wait.until(EC.element_to_be_clickable((by.By.ID, 'close-sidebar')))
            close_sidebar.click()
        except Exception as e:
            print(e)

def select_map_layer(wait, map_layer_id):
    if not globals.MAP_SELECT:
        print("select_map_layer: globals.MAP_SELECT is False — skipping entirely")
        return False
    try:
        map_sidebar = wait.until(EC.element_to_be_clickable((by.By.ID, 'layer-control')))
        map_sidebar.click()
        time.sleep(0.5)

        hybrid_map = wait.until(EC.element_to_be_clickable((by.By.ID, map_layer_id)))
        hybrid_map.click()

        close_sidebar = wait.until(EC.element_to_be_clickable((by.By.ID, 'close-sidebar')))
        close_sidebar.click()
        return True   # ← report success explicitly
    except Exception as e:
        print(f"select_map_layer FAILED for '{map_layer_id}': {e}")
        return False  # ← report failure explicitly, don't swallow silently
    

def set_map_layer_direct(driver, layer_name):
    """
    Directly swaps the active Leaflet tile layer using the site's own
    tileLayerUrls config, bypassing the sidebar click UI entirely.
    layer_name must be one of: 'openstreetmap', 'satellite', 'terrain', 'hybrid'
    Returns True on success, False on failure.
    """
    result = driver.execute_script(f"""
        try {{
            const m = window.__MAP_INSTANCE__;
            if (!m) return {{success: false, error: 'no map instance'}};

            const cfg = window.tileLayerUrls && window.tileLayerUrls['{layer_name}'];
            if (!cfg) return {{success: false, error: 'layer not found in tileLayerUrls'}};

            // Remove all existing tile layers
            m.eachLayer(layer => {{
                if (layer._url) m.removeLayer(layer);
            }});

            // Add the requested one
            L.tileLayer(cfg.url, {{
                attribution: cfg.attribution,
                maxZoom: cfg.maxZoom
            }}).addTo(m);

            return {{success: true, url: cfg.url, maxZoom: cfg.maxZoom}};
        }} catch (e) {{
            return {{success: false, error: e.toString()}};
        }}
    """)
    return result


    
def wait_for_map_load(wait):
    try:
        map = wait.until(EC.element_to_be_clickable((by.By.ID, 'map')))
        # map = driver.find_element(by.By.ID, 'map')
        # map.click()
        return map
    except Exception as e:
        print(e)


def zoom_out_map(driver):
    actions = ActionChains(driver)

    for _ in range(globals.ZOOM_LEVEL):
        for _ in range(2):
            actions.context_click().perform()
            time.sleep(0.01)
        time.sleep(1)

def zoom_in_map(driver):
    actions = ActionChains(driver)

    for _ in range(globals.ZOOM_LEVEL):
        actions.double_click().perform()
        time.sleep(1)


def get_kode_input_field(wait):
    try:
        kode_input_field = wait.until(
            EC.element_to_be_clickable((by.By.ID, 'katahocode'))
        )
        # kode_input_field = driver.find_element(by.By.ID, 'katahocode')
        
        return kode_input_field
    except Exception as e:
        pass


def drag_map(kode_input_field, kode):
    kode_input_field.clear()
    time.sleep(0.1)
    kode_input_field.send_keys(kode)
    time.sleep(globals.REFRESH_DURATION)


def str_to_tup(latlon:str) -> tuple[float, float]:
    lat, lon = latlon.split(',')
    return (float(lat), float(lon))


def kode_to_latlng(kode) -> tuple[float, float]:
    lat, lon = str_to_tup(KatahoSDK.kataho_to_lat_lng(kode))
    return (lat, lon)


def minmax_latlon(latlons):
    lats = []
    lons = []
    for lat, lon in latlons:
        lats.append(lat)
        lons.append(lon)

    left_top, right_buttom = (max(lats), min(lons)), (min(lats), max(lons))
    right_top = (max(lats), max(lons))

    return left_top, right_buttom, right_top, (min(lons) + max(lons))/2


def latlon_to_kode(point) -> str:
    return KatahoSDK.lat_lng_to_kataho(f"{point[0]},{point[1]}")

