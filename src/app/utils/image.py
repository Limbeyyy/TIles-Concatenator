import base64
from datetime import datetime, timedelta
import time
from tkinter import messagebox
import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from core import configs
from core import globals

# from core.globals import CROP_RIGHT, CROP_LEFT
from kataho.kataho import KatahoSDK
from utils.distance import move_point_by_distance
from utils.map import drag_map
from utils import update_progress_msg, show_comption_time


def crop_image(img, crop_top, crop_bottom, crop_left=0, crop_right=0):
    """
    Crop an image with individual top, bottom, left, and right pixel values.
    
    Args:
        img:         numpy array (H, W, C)
        crop_top:    pixels to remove from top
        crop_bottom: pixels to remove from bottom
        crop_left:   pixels to remove from left  (default 0)
        crop_right:  pixels to remove from right (default 0)
    
    Returns:
        Cropped numpy array
    """
    h, w = img.shape[:2]

    top    = int(crop_top)
    bottom = int(crop_bottom)
    left   = int(crop_left)
    right  = int(crop_right)

    # Safety clamp — never crop more than the image has
    top    = min(top,    h // 2)
    bottom = min(bottom, h // 2)
    left   = min(left,   w // 2)
    right  = min(right,  w // 2)

    y_start = top
    y_end   = h - bottom if bottom > 0 else h
    x_start = left
    x_end   = w - right  if right  > 0 else w

    return img[y_start:y_end, x_start:x_end]

    
def image_crop(image, CROP_BUTTON, CROP_TOP) -> np.ndarray:
    # image tile crop
    # top = 121
    # button = 120
    # right = 86
    # left = 85
    image = image[CROP_TOP:-CROP_BUTTON, globals.CROP_LEFT : -globals.CROP_RIGHT, :]

    return image


def b64_to_image(image_b64, i = None) -> np.ndarray:
    image_bytes = base64.b64decode(image_b64)
    image_np = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_np, cv2.IMREAD_COLOR)

    # cv2.imwrite(f"../../data/24-dec-10/temp{i}.jpg", image)
    # exit()
    return image


def snap_crop_tile(
    driver,
    left_top: tuple[float, float],
    kode_input_field,
    odds,
    n_v_folds,
    n_h_folds,
    H_DIST,
    V_DIST,
    CROP_BUTTON,
    CROP_TOP,
    root,
    progress_message,
    is_ward_plus_2=False,
):
    image_tiles = []

    remaining_duration = show_comption_time(n_v_folds, n_h_folds, 5, False)
    if not isinstance(remaining_duration, (int, float)):
        messagebox.showinfo(
            "Error", f"Expected int or float, got {type(remaining_duration)}."
        )
        return

    estimated_time = datetime.now() + timedelta(seconds=remaining_duration)
    if not is_ward_plus_2:
        for v_idx, v_fold in enumerate(odds[:n_v_folds]):
            h_image_tiles = []
            for h_idx, h_fold in enumerate(odds[:n_h_folds]):
                msg = f"Running:{v_idx+1}/{n_v_folds}, {h_idx+1}/{n_h_folds} | Expected at: {str(estimated_time)[11:-7]}"
                update_progress_msg(root, progress_message, msg)

                latlon_v_half = move_point_by_distance(
                    *left_top,
                    V_DIST * (globals.N_V_BOX / 2) * v_fold,  # V_DIST*2.5*v_fold,
                    configs.RELOCATE_DIRECTIONS_MAPPING["south"],  # 180
                )
                latlon_h_half = move_point_by_distance(
                    *left_top,
                    H_DIST * (globals.N_H_BOX / 2) * h_fold,
                    configs.RELOCATE_DIRECTIONS_MAPPING["east"],
                )

                kode = KatahoSDK.lat_lng_to_kataho(
                    f"{latlon_v_half[0]},{latlon_h_half[1]}"
                )
                # print(f"{v_idx+1},{h_idx+1}/{n_v_folds},{n_h_folds} running for {kode}", end='\r')

                drag_map(kode_input_field, kode)

                # screenshot
                image_b64 = driver.get_screenshot_as_base64()
                image = b64_to_image(image_b64, f"{v_idx+1}{h_idx+1}")
                image = image_crop(image, CROP_BUTTON, CROP_TOP)
                h_image_tiles.append(image)
                # print(f"{v_idx+1},{h_idx+1}/{n_v_folds},{n_h_folds} completed for {kode}")
            image_tiles.append(h_image_tiles)
        nr, nc = np.array(image_tiles).shape[:2]
    else:
        tops, buttons = [], []
        for v_idx, v_fold in enumerate(odds[:n_v_folds]):
            latlon_v_half = move_point_by_distance(
                *left_top,
                V_DIST * (globals.N_V_BOX / 2) * v_fold,  # V_DIST*2.5*v_fold,
                configs.RELOCATE_DIRECTIONS_MAPPING["south"],  # 180
            )
            lat = latlon_v_half[0]
            d_top, d_button = get_delta_lat_crop(lat)
            CROP_TOP = (
                total_top
                if (
                    total_top := configs.MAP_CONFIG_NO_AUTH["ward+2"]["crop_top"]
                    + d_top
                )
                > 0
                else 0
            )
            CROP_BUTTON = configs.MAP_CONFIG_NO_AUTH["ward+2"]["crop_button"] + d_button

            tops.append(CROP_TOP)
            buttons.append(CROP_BUTTON)
        avg_top_crop = int(round(sum(tops) / len(tops), 0))
        avg_button_crop = int(round(sum(buttons) / len(buttons), 0))

        for h_idx, h_fold in enumerate(odds[:n_h_folds]):
            v_image_tiles = []
            for v_idx, v_fold in enumerate(odds[:n_v_folds]):
                msg = f"Running: {h_idx+1}/{n_h_folds}, {v_idx+1}/{n_v_folds} | Expected at: {str(estimated_time)[11:-7]}"
                update_progress_msg(root, progress_message, msg)

                latlon_v_half = move_point_by_distance(
                    *left_top,
                    V_DIST * (globals.N_V_BOX / 2) * v_fold,  # V_DIST*2.5*v_fold,
                    configs.RELOCATE_DIRECTIONS_MAPPING["south"],  # 180
                )
                latlon_h_half = move_point_by_distance(
                    *left_top,
                    H_DIST * (globals.N_H_BOX / 2) * h_fold,
                    configs.RELOCATE_DIRECTIONS_MAPPING["east"],
                )

                kode = KatahoSDK.lat_lng_to_kataho(
                    f"{latlon_v_half[0]},{latlon_h_half[1]}"
                )
                # print(f"{v_idx+1},{h_idx+1}/{n_v_folds},{n_h_folds} running for {kode}", end='\r')

                drag_map(kode_input_field, kode)

                # screenshot
                image_b64 = driver.get_screenshot_as_base64()
                image = b64_to_image(image_b64, f"{v_idx+1}{h_idx+1}")
                # image = image_crop(image, CROP_BUTTON=19, CROP_TOP=8)

                # lat = latlon_v_half[0]
                # d_top, d_button = get_delta_lat_crop(lat)
                # CROP_TOP = (
                #     total_top
                #     if (
                #         total_top := configs.MAP_CONFIG_NO_AUTH["ward+2"]["crop_top"]
                #         - d_top
                #     )
                #     > 0
                #     else 0
                # )
                # CROP_BUTTON = (
                #     configs.MAP_CONFIG_NO_AUTH["ward+2"]["crop_button"] - d_button
                # )
                # print(d_top, d_button, CROP_TOP, CROP_BUTTON)
                image = image_crop(image, int(avg_button_crop), int(avg_top_crop))

                v_image_tiles.append(image)
                # print(f"{v_idx+1},{h_idx+1}/{n_v_folds},{n_h_folds} completed for {kode}")
                # if n_v_folds is 1, relocate to distant point
                print("moving ")

                def relocate_for_functioning(lat, lon):
                    delta = 0.2

                    lat_idx = np.argmax(np.abs(configs.MIN_MAX_LAT - lat))
                    lon_idx = np.argmax(np.abs(configs.MIN_MAX_LON - lon))

                    new_lat = lat - delta if lat_idx else lat + delta
                    new_lon = lon - delta if lon_idx else lon + delta

                    kode = KatahoSDK.lat_lng_to_kataho(f"{new_lat},{new_lon}")

                    drag_map(kode_input_field, kode)

                relocate_for_functioning(latlon_v_half[0], latlon_h_half[1])
            image_tiles.append(v_image_tiles)

        nc, nr = np.array(image_tiles).shape[:2]
    update_progress_msg(root, progress_message, "Tiles Collected")
    return image_tiles, nr, nc


def check_hw_allignment(image_tiles):
    heights, widths = [], []

    for v_image in image_tiles:
        for image in v_image:
            h, w, _ = image.shape
            heights.append(h)
            widths.append(w)

    assert len(set(heights)) == len(set(widths)) == 1

    height = heights[0]
    width = widths[0]
    return height, width


def concat_tiles(image_tiles, n_v_folds, n_h_folds, is_ward_plus_2=False):
    height, width = check_hw_allignment(image_tiles)

    full_image = np.zeros((height * n_v_folds, width * n_h_folds, 3))
    if not is_ward_plus_2:
        for v_idx, v_image in enumerate(image_tiles):
            for h_idx, image in enumerate(v_image):
                full_image[
                    height * v_idx : height * (v_idx + 1),
                    width * h_idx : width * (h_idx + 1),
                    :,
                ] = image
    else:
        for h_idx, h_image in enumerate(image_tiles):
            for v_idx, image in enumerate(h_image):
                full_image[
                    height * v_idx : height * (v_idx + 1),
                    width * h_idx : width * (h_idx + 1),
                    :,
                ] = image

    return full_image


def get_delta_pixel_crop(lon):
    delta_lon = lon - globals.MIN_LONGITUDE
    additional_pixels = int(round(delta_lon / globals.CROP_FACTOR, 0))
    return globals.CROP_TOP_BUTTON_MIN + additional_pixels


def get_delta_lat_crop(latitude):
    try:
        df = pd.read_csv("../../data/24-dec-9/lat-long-pixel_diff.csv")
        df.dropna(inplace=True)

        latitudes = df[" lat"].to_numpy()
        diff = latitudes - latitude

        idx = np.argmin(np.abs(diff))
        top_pixel_delta = df[" top_pixel_diff"].to_numpy()[idx]
        button_pixel_delta = df[" button_pixel_diff"].to_numpy()[idx]
    except Exception as e:
        print(f"Error: {e}")
    return top_pixel_delta, button_pixel_delta


# for `ward+2`, add grids and x-y labels
def decorate_image(full_image, nr_, nc):
    # full_image = cv2.cvtColor(full_image, cv2.COLOR_BGR2RGB)
    img_shape = full_image.shape[:2]

    fig, ax = plt.subplots(figsize=(img_shape[1] / 100, img_shape[0] / 100 * 1.25))

    ax.imshow(full_image)

    # major and minor ticks defination
    major_ticks_x = full_image.shape[1] // 10  # Distance between major ticks
    major_ticks = full_image.shape[0] // 10  # Distance between major ticks
    # minor_ticks_x = 8  # Distance between minor ticks
    # minor_ticks = 11  # Distance between minor ticks

    n_x_ele = len(range(0, full_image.shape[1], major_ticks_x))
    elements_x = [
        ele if i // n_x_ele < 0.5 else ele + 1
        for i, ele in enumerate(range(0, full_image.shape[1], major_ticks_x))
    ]
    labels_x = [
        str(8 * idx - 1) if idx != 0 else str(8 * idx) for idx in range(n_x_ele)
    ]

    ax.set_xticks(elements_x, minor=True)
    ax.set_xticklabels(labels=labels_x, fontdict={"color": "red", "size": 15})

    n_y_ele = len(range(0, full_image.shape[0], major_ticks))
    elements = [
        ele if i // n_y_ele < 0.5 else ele + 1
        for i, ele in enumerate(range(0, full_image.shape[0], major_ticks))
    ]
    labels = [
        str(10 * idx - 1) if idx != 0 else str(10 * idx) for idx in range(n_y_ele)
    ]

    ax.set_yticks(elements, minor=True)
    ax.set_yticklabels(labels=labels, fontdict={"color": "blue", "size": 15})

    ax.grid(axis="x", which="major", color="red", linestyle="-", linewidth=0.5)
    ax.grid(axis="y", which="major", color="blue", linestyle="-", linewidth=0.5)

    # Customize tick labels
    ax.xaxis.set_major_locator(ticker.MultipleLocator(major_ticks_x))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(major_ticks))

    plt.tick_params(axis="x", which="both", labeltop=True, labelbottom=True)
    plt.tick_params(axis="y", which="both", labelleft=True, labelright=True)

    plt.show(block=False)
    plt.pause(0.3)
    plt.close()

    full_image = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8)
    full_image = full_image.reshape(fig.canvas.get_width_height()[::-1] + (3,))

    return full_image
