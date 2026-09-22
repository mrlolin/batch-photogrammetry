#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Nodule Image Processor - PyQt6 GUI

Dependencies:
    pip install PyQt6 opencv-python numpy pillow

The application keeps the original processing stages:
    1. Color correct
    2. Make loop folders
    3. Find loop images
    4. Rename images
    5. Move / rename
    6. Copy slate

Processing runs in a worker thread so the GUI remains responsive.
"""

import csv
import os
import re
import shutil
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def load_image(image_path):
    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)
    except Exception as e:
        raise RuntimeError(f"Could not read {image_path}: {e}") from e


def cmd_exec(cmd):
    """Run a command without opening a console window on Windows."""
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    # subprocess.run accepts a list directly. This is safer than shell=True.
    result = subprocess.run(
        [str(x) for x in cmd],
        creationflags=creationflags,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}):\n"
            f"{' '.join(str(x) for x in cmd)}\n"
            f"{result.stderr.strip()}"
        )

    return result


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
    target_pp3.parent.mkdir(parents=True, exist_ok=True)
    with open(target_pp3, "w", encoding="utf-8") as f:
        f.write(pp3_text)


def blue_ratio(image_path):
    LOWER_BLUE = np.array([100, 200, 150])
    UPPER_BLUE = np.array([200, 255, 255])

    img = load_image(image_path)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, LOWER_BLUE, UPPER_BLUE)

    blue_pixels = cv2.countNonZero(mask)
    total_pixels = img.shape[0] * img.shape[1]

    return blue_pixels / total_pixels if total_pixels else 0.0


def find_rawtherapee():
    """Try common Windows locations and PATH."""
    candidates = []

    # PATH first.
    path_result = shutil.which("rawtherapee-cli.exe")
    if path_result:
        candidates.append(Path(path_result))

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get(
        "ProgramFiles(x86)", r"C:\Program Files (x86)"
    )

    roots = [
        Path(program_files) / "RawTherapee",
        Path(program_files_x86) / "RawTherapee",
    ]

    for root in roots:
        if root.exists():
            # Prefer rawtherapee-cli.exe anywhere under the RawTherapee folder.
            try:
                candidates.extend(root.glob("**/rawtherapee-cli.exe"))
            except OSError:
                pass

    # Deduplicate while preserving order.
    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate not in seen and candidate.is_file():
            seen.add(candidate)
            return str(candidate)

    return ""


# ---------------------------------------------------------------------------
# Processing engine
# ---------------------------------------------------------------------------

class ProcessingEngine:
    def __init__(self, config, log_callback, progress_callback, stop_callback):
        self.config = config
        self.log = log_callback
        self.progress = progress_callback
        self.is_stopped = stop_callback

        self.ingest_dir = Path(config["ingest_dir"])
        self.profile_dir = Path(config["profile_dir"])
        self.work_dir = Path(config["work_dir"])
        self.rawtherapee = Path(config["rawtherapee"])

        self.cc_csv = self.ingest_dir / "cc.csv"

    def check_stop(self):
        if self.is_stopped():
            raise InterruptedError("Processing stopped by user.")

    def color_correct(self, nodule_list):
        if not self.cc_csv.exists():
            raise FileNotFoundError(f"Cannot find color-chart CSV: {self.cc_csv}")

        with open(self.cc_csv, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=",")
            nodule_cc_dict = {}

            for row_number, row in enumerate(reader, start=1):
                if len(row) < 3:
                    self.log(f"Skipping malformed cc.csv row {row_number}")
                    continue

                nodule_cc_dict[row[1]] = {
                    "date": row[0],
                    "cc_profile": Path(row[2]).stem,
                }

        nodule_fullpath_list = []

        if not self.ingest_dir.exists():
            raise FileNotFoundError(
                f"Cannot find ingest directory: {self.ingest_dir}"
            )

        for date_dir in self.ingest_dir.iterdir():
            if date_dir.is_dir():
                for nod_dir in date_dir.iterdir():
                    if nod_dir.is_dir():
                        nodule_fullpath_list.append(nod_dir)

        to_cc = {}

        for nod in nodule_list:
            self.check_stop()

            nod_dict = nodule_cc_dict.get(nod)
            if nod_dict is None:
                self.log(f"Cannot find profile for {nod}")
                continue

            self.log(f"Found nodule: {nod}")

            profile = nod_dict["cc_profile"]
            profile_path = self.profile_dir / f"{profile}.pp3"

            if not profile_path.exists():
                dcp_path = self.profile_dir / f"{profile}.dcp"

                if dcp_path.exists():
                    self.log(f"Found DCP for {nod}. Writing PP3 file")
                    write_pp3(profile_path, dcp_path)
                else:
                    self.log(
                        f"Did not find PP3 or DCP for {nod}: "
                        f"{profile}"
                    )
                    continue
            else:
                self.log(f"Found profile for {nod}")

            for nod_dir in nodule_fullpath_list:
                # Match the NOD as a complete token.
                if re.search(r"\b" + re.escape(nod) + r"\b", str(nod_dir)):
                    to_cc[nod] = {
                        "profile": str(profile_path),
                        "nodule_dir": nod_dir,
                    }
                    break

        cmd_list = []

        for nod, data in to_cc.items():
            self.check_stop()

            nod_work_dir = self.work_dir / nod
            nod_work_dir.mkdir(parents=True, exist_ok=True)

            nodule_dir = Path(data["nodule_dir"])
            cc_profile = Path(data["profile"])

            ingest_images = [
                p for p in nodule_dir.iterdir()
                if p.is_file()
            ]

            for input_img in ingest_images:
                # Preserve the original extension conversion behavior.
                tif_img = input_img.name.replace(".CR2", ".tif")
                output_img = nod_work_dir / tif_img

                cmd = [
                    self.rawtherapee,
                    "-Y",
                    "-p",
                    cc_profile,
                    "-o",
                    output_img,
                    "-t",
                    "-b8",
                    "-c",
                    input_img,
                ]
                cmd_list.append((nod, input_img.name, cmd))

        if not cmd_list:
            self.log("No color-correction jobs found.")
            return

        self.log(
            f"Starting {len(cmd_list)} RawTherapee jobs "
            f"with up to 10 workers..."
        )

        completed = 0
        with ThreadPoolExecutor(max_workers=10) as pool:
            future_map = {
                pool.submit(cmd_exec, cmd): (nod, filename)
                for nod, filename, cmd in cmd_list
            }

            for future in as_completed(future_map):
                self.check_stop()
                nod, filename = future_map[future]

                try:
                    future.result()
                    self.log(f"Color corrected: {nod}/{filename}")
                except Exception as e:
                    self.log(
                        f"ERROR color correcting {nod}/{filename}: {e}"
                    )

                completed += 1
                self.progress(completed, len(cmd_list))

    def make_loop_folders(self, nodule_list):
        total = max(len(nodule_list) * 11, 1)
        done = 0

        for nod in nodule_list:
            self.check_stop()

            nod_path = self.work_dir / nod
            nod_path.mkdir(parents=True, exist_ok=True)

            for i in range(10):
                loop_folder = nod_path / f"{nod}_loop_{i:02d}"
                loop_folder.mkdir(parents=True, exist_ok=True)
                done += 1
                self.progress(done, total)

            extra_folder = nod_path / f"{nod}_extras"
            extra_folder.mkdir(parents=True, exist_ok=True)
            done += 1
            self.progress(done, total)

    def find_loop_images(self, nodule_list):
        BLUE_THRESHOLD = 0.01

        for x, nod in enumerate(nodule_list):
            self.check_stop()

            self.log(
                f"Processing {nod} ({x + 1}/{len(nodule_list)})..."
            )

            nod_path = self.work_dir / nod

            if not nod_path.exists():
                self.log(f"No images found for {nod}")
                continue

            nod_images = sorted(
                [
                    p for p in nod_path.iterdir()
                    if p.is_file() and p.suffix.lower() == ".tif"
                ],
                key=lambda p: p.name,
            )

            self.log(f"Found {len(nod_images)} TIFF images.")

            loop_marker_list = []
            count = 0

            for i, img_path in enumerate(nod_images):
                self.check_stop()

                try:
                    ratio = blue_ratio(img_path)
                except Exception as e:
                    self.log(f"ERROR reading {img_path.name}: {e}")
                    continue

                is_blue = ratio >= BLUE_THRESHOLD

                if is_blue:
                    count += 1
                    self.log(
                        f"Found loop marker #{count}: "
                        f"{img_path.name} ({ratio:.2f})"
                    )
                    loop_marker_list.append((img_path.name, i))

                self.progress(i + 1, max(len(nod_images), 1))

            if not loop_marker_list:
                self.log(f"No loop markers found in {nod}.")
                continue

            for i, loop_marker in enumerate(loop_marker_list):
                self.check_stop()

                if i == len(loop_marker_list) - 1:
                    range_end = len(nod_images)
                else:
                    range_end = loop_marker_list[i + 1][1]

                range_start = loop_marker[1] + 1
                loop_images = nod_images[range_start:range_end]

                loop_dir = f"{nod}_loop_{i:02d}"
                loop_folder = nod_path / loop_dir
                loop_folder.mkdir(parents=True, exist_ok=True)

                for img in loop_images:
                    self.check_stop()

                    src_path = nod_path / img.name
                    dest_path = loop_folder / img.name

                    if src_path.exists():
                        shutil.move(str(src_path), str(dest_path))

                # Move the blue marker to extras.
                extra_dir = f"{nod}_extras"
                extra_folder = nod_path / extra_dir
                extra_folder.mkdir(parents=True, exist_ok=True)

                loop_marker_path = nod_path / loop_marker[0]
                dest_extra_path = extra_folder / loop_marker[0]

                if loop_marker_path.exists():
                    shutil.move(
                        str(loop_marker_path),
                        str(dest_extra_path),
                    )

                self.log(
                    f"{nod}: created {loop_dir} "
                    f"({len(loop_images)} images)"
                )

    def rename_images(self, nodule_list):
        for x, nod in enumerate(nodule_list):
            self.check_stop()

            nod_path = self.work_dir / nod

            if not nod_path.exists():
                self.log(f"No images found for {nod}")
                continue

            loop_folders = [
                p for p in nod_path.iterdir()
                if p.is_dir()
            ]

            for loop_dir in loop_folders:
                self.check_stop()

                for input_name in list(loop_dir.iterdir()):
                    if input_name.is_file() and input_name.suffix.lower() == ".tif":
                        output_name = loop_dir / f"{loop_dir.name}_{input_name.name}"

                        if output_name.exists():
                            self.log(
                                f"Skipping existing file: "
                                f"{output_name.name}"
                            )
                            continue

                        input_name.rename(output_name)
                        self.log(
                            f"Renamed: {input_name.name} -> "
                            f"{output_name.name}"
                        )

    def move_rename(self, nodule_list):
        for nod in nodule_list:
            self.check_stop()

            nod_dir = self.work_dir / nod

            if not nod_dir.exists():
                self.log(f"No images found for {nod}")
                continue

            exist_files = []
            new_imgs = []

            for entry in nod_dir.iterdir():
                self.check_stop()

                if entry.is_dir() and (
                    "loop" in entry.name or "extra" in entry.name
                ):
                    for img in entry.iterdir():
                        if img.is_file():
                            exist_files.append(
                                (entry.name, img.name)
                            )

                elif entry.is_file() and entry.suffix.lower() == ".tif":
                    new_imgs.append(entry)

            for img in new_imgs:
                self.check_stop()

                for folder_name, existing_name in exist_files:
                    if img.name in existing_name:
                        src_file = nod_dir / img.name
                        dest_file = nod_dir / folder_name / existing_name

                        if dest_file.exists():
                            self.log(
                                f"Skipping existing destination: "
                                f"{dest_file}"
                            )
                            continue

                        shutil.move(str(src_file), str(dest_file))
                        self.log(
                            f"Moved {src_file.name} -> "
                            f"{folder_name}/{existing_name}"
                        )
                        break

    def copy_slate(self, nodule_list):
        extras_root = self.work_dir / "_extras"
        extras_root.mkdir(parents=True, exist_ok=True)

        for nod in nodule_list:
            self.check_stop()

            nod_path = self.work_dir / nod

            if not nod_path.exists():
                self.log(f"No images found for {nod}")
                continue

            extras_dirs = [
                p for p in nod_path.iterdir()
                if p.is_dir() and "extra" in p.name
            ]

            if not extras_dirs:
                self.log(f"No extras folder found for {nod}")
                continue

            extras_path = extras_dirs[0]

            slate_files = [
                p for p in extras_path.iterdir()
                if p.is_file()
            ]

            if not slate_files:
                self.log(f"No slate found for {nod}")
                continue

            slate_path = slate_files[0]
            dest_path = extras_root / slate_path.name

            shutil.copyfile(str(slate_path), str(dest_path))
            self.log(f"Copied slate: {slate_path.name}")


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class Worker(QObject):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished = pyqtSignal()
    stopped = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, config, stages):
        super().__init__()
        self.config = config
        self.stages = stages
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True
        self.log_signal.emit("Stop requested. Finishing current operation...")

    def is_stopped(self):
        return self._stop_requested

    @pyqtSlot()
    def run(self):
        try:
            rawtherapee = self.config["rawtherapee"]

            if not rawtherapee or not Path(rawtherapee).exists():
                raise FileNotFoundError(
                    "RawTherapee executable was not found."
                )

            work_dir = Path(self.config["work_dir"])
            work_dir.mkdir(parents=True, exist_ok=True)

            nodule_list = [
                line.strip()
                for line in self.config["nodule_text"].splitlines()
                if line.strip()
            ]

            if not nodule_list:
                raise ValueError("No NODs were entered.")

            # De-duplicate while preserving order.
            nodule_list = list(dict.fromkeys(nodule_list))

            self.log_signal.emit(
                f"Starting processing for {len(nodule_list)} NOD(s): "
                f"{', '.join(nodule_list)}"
            )

            def check_stop():
                if self._stop_requested:
                    return True
                return False

            engine = ProcessingEngine(
                self.config,
                self.log_signal.emit,
                self.progress_signal.emit,
                check_stop,
            )

            # The order here is deliberately explicit.
            if self.stages["color_correct"]:
                self.log_signal.emit("=== COLOR CORRECTION ===")
                engine.color_correct(nodule_list)

            if self.stages["make_loop_folders"]:
                self.log_signal.emit("=== MAKE LOOP FOLDERS ===")
                engine.make_loop_folders(nodule_list)

            if self.stages["find_loop_images"]:
                self.log_signal.emit("=== FIND LOOP IMAGES ===")
                engine.find_loop_images(nodule_list)

            if self.stages["rename_images"]:
                self.log_signal.emit("=== RENAME IMAGES ===")
                engine.rename_images(nodule_list)

            if self.stages["move_rename"]:
                self.log_signal.emit("=== MOVE / RENAME ===")
                engine.move_rename(nodule_list)

            if self.stages["copy_slate"]:
                self.log_signal.emit("=== COPY SLATE ===")
                engine.copy_slate(nodule_list)

            if self._stop_requested:
                self.stopped.emit()
            else:
                self.log_signal.emit("=== PROCESSING COMPLETE ===")
                self.finished.emit()

        except InterruptedError:
            self.stopped.emit()
        except Exception:
            self.error.emit(traceback.format_exc())


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.thread = None
        self.worker = None

        self.setWindowTitle("Nodule Image Processor")
        self.resize(1050, 800)

        self.build_ui()
        self.detect_rawtherapee()

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)

        # ---------------------------------------------------------------
        # Configuration
        # ---------------------------------------------------------------
        config_group = QGroupBox("Configuration")
        config_layout = QFormLayout(config_group)

        self.ingest_edit = QLineEdit()
        self.profile_edit = QLineEdit()
        self.work_edit = QLineEdit()
        self.rawtherapee_edit = QLineEdit()

        config_layout.addRow(
            "Ingest directory:",
            self.path_row(self.ingest_edit, self.choose_ingest),
        )
        config_layout.addRow(
            "Profile directory:",
            self.path_row(self.profile_edit, self.choose_profile),
        )
        config_layout.addRow(
            "Work directory:",
            self.path_row(self.work_edit, self.choose_work),
        )
        config_layout.addRow(
            "RawTherapee:",
            self.path_row(self.rawtherapee_edit, self.choose_rawtherapee),
        )

        main_layout.addWidget(config_group)

        # ---------------------------------------------------------------
        # NOD input
        # ---------------------------------------------------------------
        nod_group = QGroupBox("NODs to process")
        nod_layout = QVBoxLayout(nod_group)

        nod_help = QLabel(
            "Enter one NOD per line. Duplicate entries are automatically removed."
        )
        nod_layout.addWidget(nod_help)

        self.nodule_edit = QPlainTextEdit()
        self.nodule_edit.setPlaceholderText(
            "NOD000\nNOD284\nNOD301"
        )
        self.nodule_edit.setMaximumHeight(130)
        nod_layout.addWidget(self.nodule_edit)

        main_layout.addWidget(nod_group)

        # ---------------------------------------------------------------
        # Processing stages
        # ---------------------------------------------------------------
        stage_group = QGroupBox("Processing stages")
        stage_layout = QVBoxLayout(stage_group)

        self.color_correct_cb = QCheckBox("Color correct with RawTherapee")
        self.make_loops_cb = QCheckBox("Create loop folders")
        self.find_loops_cb = QCheckBox("Find loop markers and move images")
        self.rename_cb = QCheckBox("Rename images")
        self.move_rename_cb = QCheckBox("Move / rename remaining images")
        self.copy_slate_cb = QCheckBox("Copy slate to _extras")

        # Sensible default workflow based on the original script.
        self.color_correct_cb.setChecked(True)
        self.make_loops_cb.setChecked(True)
        self.find_loops_cb.setChecked(True)
        self.rename_cb.setChecked(True)

        for checkbox in (
            self.color_correct_cb,
            self.make_loops_cb,
            self.find_loops_cb,
            self.rename_cb,
            self.move_rename_cb,
            self.copy_slate_cb,
        ):
            stage_layout.addWidget(checkbox)

        main_layout.addWidget(stage_group)

        # ---------------------------------------------------------------
        # Buttons
        # ---------------------------------------------------------------
        button_layout = QHBoxLayout()

        self.run_button = QPushButton("▶ Run Selected")
        self.stop_button = QPushButton("■ Stop")
        self.stop_button.setEnabled(False)

        self.run_button.clicked.connect(self.start_processing)
        self.stop_button.clicked.connect(self.stop_processing)

        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addStretch()

        main_layout.addLayout(button_layout)

        # ---------------------------------------------------------------
        # Progress
        # ---------------------------------------------------------------
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)

        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)

        main_layout.addWidget(progress_group)

        # ---------------------------------------------------------------
        # Log
        # ---------------------------------------------------------------
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)

        font = QFont("Consolas")
        font.setPointSize(9)
        self.log_edit.setFont(font)

        log_layout.addWidget(self.log_edit)

        main_layout.addWidget(log_group, stretch=1)

    def path_row(self, line_edit, callback):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        button = QPushButton("...")
        button.setFixedWidth(35)
        button.clicked.connect(callback)

        layout.addWidget(line_edit)
        layout.addWidget(button)

        return widget

    # ---------------------------------------------------------------
    # Directory selectors
    # ---------------------------------------------------------------

    def choose_ingest(self):
        self.choose_directory(self.ingest_edit)

    def choose_profile(self):
        self.choose_directory(self.profile_edit)

    def choose_work(self):
        self.choose_directory(self.work_edit)

    def choose_directory(self, edit):
        path = QFileDialog.getExistingDirectory(
            self,
            "Select directory",
            edit.text() or str(Path.home()),
        )
        if path:
            edit.setText(path)

    def choose_rawtherapee(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select RawTherapee CLI executable",
            self.rawtherapee_edit.text()
            or r"C:\Program Files",
            "Executable (*.exe);;All files (*)",
        )
        if path:
            self.rawtherapee_edit.setText(path)

    def detect_rawtherapee(self):
        detected = find_rawtherapee()

        if detected:
            self.rawtherapee_edit.setText(detected)
            self.append_log(f"Auto-detected RawTherapee: {detected}")
        else:
            self.append_log(
                "RawTherapee was not automatically detected. "
                "Use the browse button to select rawtherapee-cli.exe."
            )

    # ---------------------------------------------------------------
    # Logging / progress
    # ---------------------------------------------------------------

    def append_log(self, message):
        self.log_edit.appendPlainText(message)

    @pyqtSlot(int, int)
    def update_progress(self, current, total):
        if total <= 0:
            self.progress_bar.setValue(0)
            return

        percent = int((current / total) * 100)
        self.progress_bar.setValue(max(0, min(100, percent)))
        self.progress_label.setText(
            f"{current:,} / {total:,} ({percent}%)"
        )

    # ---------------------------------------------------------------
    # Processing
    # ---------------------------------------------------------------

    def collect_config(self):
        return {
            "ingest_dir": self.ingest_edit.text().strip(),
            "profile_dir": self.profile_edit.text().strip(),
            "work_dir": self.work_edit.text().strip(),
            "rawtherapee": self.rawtherapee_edit.text().strip(),
            "nodule_text": self.nodule_edit.toPlainText(),
        }

    def collect_stages(self):
        return {
            "color_correct": self.color_correct_cb.isChecked(),
            "make_loop_folders": self.make_loops_cb.isChecked(),
            "find_loop_images": self.find_loops_cb.isChecked(),
            "rename_images": self.rename_cb.isChecked(),
            "move_rename": self.move_rename_cb.isChecked(),
            "copy_slate": self.copy_slate_cb.isChecked(),
        }

    def validate_config(self):
        config = self.collect_config()
        stages = self.collect_stages()

        if not config["ingest_dir"]:
            QMessageBox.warning(
                self, "Missing directory", "Please select an ingest directory."
            )
            return False

        if not config["profile_dir"]:
            QMessageBox.warning(
                self, "Missing directory", "Please select a profile directory."
            )
            return False

        if not config["work_dir"]:
            QMessageBox.warning(
                self, "Missing directory", "Please select a work directory."
            )
            return False

        if not config["nodule_text"].strip():
            QMessageBox.warning(
                self, "Missing NODs", "Please enter at least one NOD."
            )
            return False

        if stages["color_correct"]:
            if not config["rawtherapee"]:
                QMessageBox.warning(
                    self,
                    "RawTherapee required",
                    "Color correction is enabled, but RawTherapee was not found.",
                )
                return False

            if not Path(config["rawtherapee"]).exists():
                QMessageBox.warning(
                    self,
                    "RawTherapee not found",
                    f"Cannot find:\n{config['rawtherapee']}",
                )
                return False

        return True

    def start_processing(self):
        if not self.validate_config():
            return

        stages = self.collect_stages()

        if not any(stages.values()):
            QMessageBox.warning(
                self,
                "No stages selected",
                "Select at least one processing stage.",
            )
            return

        # Warn because several stages move or rename files.
        destructive = (
            stages["find_loop_images"]
            or stages["rename_images"]
            or stages["move_rename"]
        )

        if destructive:
            answer = QMessageBox.question(
                self,
                "Confirm file changes",
                "Some selected stages will move and/or rename files.\n\n"
                "Make sure you have a backup or are working on the intended data.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if answer != QMessageBox.StandardButton.Yes:
                return

        self.log_edit.clear()
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting...")

        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.thread = QThread()
        self.worker = Worker(self.collect_config(), stages)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)

        self.worker.log_signal.connect(self.append_log)
        self.worker.progress_signal.connect(self.update_progress)

        self.worker.finished.connect(self.processing_finished)
        self.worker.stopped.connect(self.processing_stopped)
        self.worker.error.connect(self.processing_error)

        self.worker.finished.connect(self.thread.quit)
        self.worker.stopped.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)

        self.thread.finished.connect(self.thread_cleanup)

        self.thread.start()

    def stop_processing(self):
        if self.worker:
            self.worker.request_stop()
            self.stop_button.setEnabled(False)

    def processing_finished(self):
        self.progress_bar.setValue(100)
        self.progress_label.setText("Complete")
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        QMessageBox.information(
            self,
            "Complete",
            "Processing completed successfully.",
        )

    def processing_stopped(self):
        self.progress_label.setText("Stopped")
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.append_log("=== PROCESSING STOPPED ===")

    def processing_error(self, error_text):
        self.progress_label.setText("Error")
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        self.append_log("=== ERROR ===")
        self.append_log(error_text)

        QMessageBox.critical(
            self,
            "Processing error",
            "Processing failed.\n\n"
            "See the log for the full traceback.",
        )

    def thread_cleanup(self):
        if self.worker:
            self.worker.deleteLater()
        if self.thread:
            self.thread.deleteLater()

        self.worker = None
        self.thread = None

    def closeEvent(self, event):
        if self.worker:
            answer = QMessageBox.question(
                self,
                "Processing in progress",
                "Processing is still running. Stop it and exit?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            self.worker.request_stop()

        event.accept()


def main():
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
