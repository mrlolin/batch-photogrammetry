#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import csv
import re
import time
import math
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import shutil
import cv2
import numpy as np
from PIL import Image

def load_image(image_path):
    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")  # handles CMYK / 16-bit safely
            return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"⚠️  Could not read {image_path}: {e}")
        return None


def cmd_exec(cmd):
    subprocess.run(
        cmd,         
        # creationflags=subprocess.CREATE_NO_WINDOW
        # if os.name == "nt" else 0,
        shell=True
    )


def write_pp3(target_pp3, dcp_path):
    pp3_text = f"""[Version]
AppVersion=5.10
Version=348


[Resize]
Enabled=true
Scale=0.58999999999999997
AppliesTo=Full image
Method=Lanczos
DataSpecified=4
Width=900
Height=900
LongEdge=4000
ShortEdge=2669
AllowUpscaling=false


[ColorManagement]
Enabled=True
WorkingProfile=Default
InputProfile=Custom
InputProfileFile={dcp_path}
"""
    with open(target_pp3, "w") as f:
        f.write(pp3_text)


def blue_ratio(image_path):
    LOWER_BLUE = np.array([100, 200, 150])
    UPPER_BLUE = np.array([200, 255, 255])
    # LOWER_BLUE = np.array([75, 80, 150])
    # UPPER_BLUE = np.array([90, 255, 255])
    img = load_image(image_path)
    if img is None:
        return 0.0

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, LOWER_BLUE, UPPER_BLUE)
    blue_pixels = cv2.countNonZero(mask)
    total_pixels = img.shape[0] * img.shape[1]

    return blue_pixels / total_pixels



RAWTHERAPEE = r"C:\Program Files\RawTherapee\5.12\rawtherapee-cli.exe"
INGEST_DIR = r"Z:\ingest\PMNHH_Photos\RAW\reference-object"
PROFILE_DIR = r"Z:\pmn-hh\01_dev\color_charts"
WORK_DIR = r'Z:\pmn-hh\02_work'

CC_CSV =  Path(INGEST_DIR) / "cc.csv"


profiles = [f for f in os.listdir(PROFILE_DIR) if os.path.isfile(os.path.join(PROFILE_DIR, f))]


input_nodules="NOD000"

nodule_list = input_nodules.split("\n")
# nodule_list = ["NOD284"]

def color_correct(nodule_list):            
    with open(CC_CSV, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=",")
        nodule_cc_dict = {}
        for row in reader:
            nodule_cc_dict[row[1]] = {
                "date" : row[0],
                "cc_profile" : Path(row[2]).stem
            } 

    nodule_fullpath_list = []

    for dir in os.listdir(INGEST_DIR):
        if dir.startswith("2025"):
            nodule_dir = os.listdir(Path(INGEST_DIR) / dir)
            for nod_dir in nodule_dir:
                nod_dir_fullpath = Path(INGEST_DIR) / dir / nod_dir
                if os.path.isdir(nod_dir_fullpath):
                    
                    nodule_fullpath_list.append(str(nod_dir_fullpath))

    to_cc = {}

    for nod in nodule_list:
        nod_dict = nodule_cc_dict.get(nod)
        if nod_dict == None:
            print(f"Cannot find profile for {nod}")
            continue
        print(f"Found nodule: {nod}")

        profile = nodule_cc_dict.get(nod).get("cc_profile")

        profile_path = Path(PROFILE_DIR) / f"{profile}.pp3"
        if not profile_path.exists():
            print(f"Cannot find profile for {nod}")
            dcp_path = Path(PROFILE_DIR) / f"{profile}.dcp"
            if dcp_path.exists():
                print(f"Found dcp for {nod}. Writing out pp3 file")
                write_pp3(profile_path, dcp_path)
            else:
                print(f"Did not find pp3 or dcp file for {nod}")
                continue
        else:
            print(f"Found profile for {nod}")
        # raw_dir = Path(INGEST_DIR) / 

        for nod_dir in nodule_fullpath_list:
            # if nod in nod_dir:
            if re.search(r'\b' + nod + r'\b', nod_dir):

                to_cc[nod] ={
                    "profile": str(profile_path),
                    "nodule_dir": nod_dir
                }

    cmd_list = []
    for nod in to_cc:
        nod_work_dir = Path(WORK_DIR) / nod
        os.makedirs(nod_work_dir, exist_ok=True)
        nodule_dir = to_cc.get(nod).get("nodule_dir")
        cc_profile = Path(to_cc.get(nod).get("profile"))
        ingest_images = os.listdir(nodule_dir)


        for img in ingest_images:
            input_img = Path(nodule_dir) / img
            tif_img = img.replace(".CR2", ".tif")
            output_img = Path(nod_work_dir) / tif_img

            cmd = [Path(RAWTHERAPEE), "-Y", "-p",
                cc_profile, "-o",
                output_img,
                "-t", "-b8",
                "-c", input_img]

            cmd_list.append(cmd)

    with ThreadPoolExecutor(max_workers=10) as pool:
        pool.map(cmd_exec, cmd_list)


def make_loop_folders(nodule_list):
    for nod in nodule_list:
        for i in range(0,10):
            loop_folder = Path(WORK_DIR) / nod / f"{nod}_loop_{i:02}"
            # print(loop_folder)
            os.makedirs(loop_folder, exist_ok=True)
        extra_folder = Path(WORK_DIR) / nod / f"{nod}_extras"
        os.makedirs(extra_folder, exist_ok=True)


def find_loop_images(nodule_list):
    BLUE_THRESHOLD = 0.01

    for x, nod in enumerate(nodule_list):
        print(nod)
        loop_marker_list = []

        nod_path = Path(WORK_DIR) / nod
        if os.path.exists(nod_path):
            
            nod_images = [
                p for p in nod_path.iterdir()
                if p.is_file() and p.suffix.lower() == ".tif"
            ]
            print(f"Processing {len(nod_images)} images in {nod} ({x+1}/{len(nodule_list)})...\n")
            count = 0
            for i, img_path in enumerate(nod_images):
                ratio = blue_ratio(img_path)
                is_blue = ratio >= BLUE_THRESHOLD
                if is_blue:
                    count += 1 
                    print(f"Found loop marker #{count}: {img_path.name} ({round(ratio,2)})")
                    loop_marker_list.append((img_path.name, i))

            loop_images = {}
            for i, loop_markers in enumerate(loop_marker_list): 
                if i == len(loop_marker_list) -1:
                    range_end = len(nod_images)
                else:
                    range_end = loop_marker_list[i+1][1]
                range_start = loop_markers[1] + 1
                loop_images = nod_images[range_start:range_end]
                loop_dir = f"{nod}_loop_{i:02d}"
                loop_folder = Path(WORK_DIR) / nod / loop_dir
                os.makedirs(loop_folder, exist_ok=True)
                for img in loop_images:
                    src_path = os.path.join(str(nod_path), img.name)
                    dest_path =  os.path.join(str(nod_path), loop_dir, img.name)
                    shutil.move(src_path, dest_path)
                loop_markers_path = loop_markers[0]
                extra_dir = f"{nod}_extras"
                extra_folder = Path(WORK_DIR) / nod / extra_dir
                os.makedirs(extra_folder, exist_ok=True)
                src_extra_path = os.path.join(str(nod_path), loop_markers_path)
                dest_extra_path =  os.path.join(str(nod_path), extra_dir, loop_markers_path)
                shutil.move(src_extra_path, dest_extra_path)
        else:
            print(f"No images found for {nod}")


def rename_images(nodule_list):
    for nod in nodule_list:
        nod_path = Path(WORK_DIR) / nod
        if os.path.exists(nod_path):
            loop_folders = os.listdir(nod_path)
            
            for loops in loop_folders:
                loop_dir = Path(nod_path) / loops
                if os.path.isdir(loop_dir):
                    image_list = os.listdir(loop_dir)
                    for images in image_list:
                        input_name = Path(loop_dir) / images
                        if Path(input_name).suffix == ".tif":
                            output_name = Path(loop_dir) /f"{loops}_{images}"
                            os.rename(input_name, output_name)
        else:
            print(f"No images found for {nod}")



def move_rename(nodule_list):
    for nod in nodule_list:
        nod_dir = Path(WORK_DIR) / nod
        sub_dir = os.listdir(nod_dir)
        exist_files = []
        new_imgs = []
        for files in sub_dir:
            loop_dir = Path(nod_dir) / files
            if os.path.isdir(loop_dir) and "loop" in files or "extra" in files:
                exist_imgs = os.listdir(loop_dir)
                for img in exist_imgs:
                    exist_files.append("/".join([files, img]))
            if Path(files).suffix == ".tif":
                new_imgs.append(files)

        for img in new_imgs:
            for exists_img in exist_files:
                if img in exists_img:
                    src_file = os.path.join(str(nod_dir), img)
                    dest_file = os.path.join(str(nod_dir), exists_img)
                    shutil.move(src_file, dest_file)
                    print(f"Moved {src_file} -> {dest_file}")


def copy_slate(nodule_list):
    for nod in nodule_list:
        nod_path = Path(WORK_DIR) / nod
        if os.path.exists(nod_path):
            sub_dir = os.listdir(nod_path)
            for dir in sub_dir:
                if "extra" in dir:
                    extras_folder = dir
            extras_path = Path(nod_path) / extras_folder
            slate = os.listdir(extras_path)[0]

            slate_path = Path(extras_path) / slate
            
            dest_path = Path(WORK_DIR) / "_extras" / slate 
            shutil.copyfile(slate_path, dest_path)            
        else:
            print(f"No images found for {nod}")





num_nodule = 3
nodule_time_min = 25
wait_sec = (num_nodule * nodule_time_min) *60
work_time = (len(nodule_list)*10)/60
wait_hrs = wait_sec/60/60
total_time = wait_hrs + work_time


# print(f"Wait Time: {math.floor(wait_hrs)}h {round((wait_hrs%1)*60,2)}min")
# print(f"Work Time: {math.floor(work_time)}h {round((work_time%1)*60,2)}min")
# print(f"Total Time: {math.floor(total_time)}h {round((total_time%1)*60,2)}min")
# time.sleep(wait_sec)

# color_correct(nodule_list)


# find_loop_images(nodule_list)

rename_images(nodule_list)





# copy_slate(nodule_list)

# move_rename(nodule_list)


