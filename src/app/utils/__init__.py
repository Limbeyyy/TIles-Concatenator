from core import globals
from tkinter import messagebox
import cv2
from datetime import datetime, timedelta
import tkinter.filedialog


def required_odds(n_h_folds, n_v_folds):
    n_odds_required = max(n_h_folds, n_v_folds)
    odds = []
    counter = 0
    while len(odds) < n_odds_required:
        if counter % 2 != 0:
            odds.append(counter)
        counter += 1

    return odds


def save_image(image, filepath):
    # cv2.imwrite(f"{str(datetime.now())}.jpg", image)
    cv2.imwrite(filepath, image)


def get_savefile_path():
    files = [
        ("Image File", "*.jpg"),
        ("Image File", "*.jpeg"),
        ("Image File", "*.png"),
    ]
    file = tkinter.filedialog.asksaveasfile(filetypes=files, defaultextension=files)

    return file


def filter_latlons(latlons: str):
    latlons_split = latlons.splitlines()
    cnt = latlons_split.count("")
    for _ in range(cnt):
        latlons_split.remove("")
    return latlons_split


def filter_kodes(kodes: str):
    kodes_split = kodes.splitlines()
    cnt = kodes_split.count("")
    for _ in range(cnt):
        kodes_split.remove("")
    return kodes_split


def show_comption_time(n_v_folds, n_h_folds, surplus=10, show=True):
    duration = n_v_folds * n_h_folds * (globals.REFRESH_DURATION + 1) + surplus
    if not show:
        return duration

    if duration < 60:
        duration = f"{duration} seconds"
    else:
        minute = int(duration / 60)
        second = duration - (minute * 60)
        duration = f"{minute} minutes {second} seconds"

    messagebox.showinfo("Estimated Time", f"Expected duration is {duration}.")


def update_progress_msg(root, widget, msg):
    widget.config(text=msg)
    root.update()


def guide():
    messagebox.showinfo(
        "Guidelines",
        """
        1)\tSelect mode: with or without authentication.
        2)\tWhile entering kataho codes make sure to insert 
        \tkataho code above the upper limit at first then the
        \torder for other kataho codes doesn't matter.
        3)\tWhen you click generate button, you need to 
        \tprovide the filepath where the image will be saved.
        4)\tSee progress status and the estimated future time 
        \tto complete.
        """,
    )
