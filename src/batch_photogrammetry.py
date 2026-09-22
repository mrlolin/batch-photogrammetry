#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
import csv
from datetime import datetime
import shutil
from collections import deque

from PyQt6.QtWidgets import (
    QApplication, QWidget, QFileDialog, QDialog,
    QGridLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QMessageBox, QAbstractItemView,
    QLineEdit, QLabel, QTextEdit, QRadioButton, QButtonGroup, QSpinBox,
    QSpacerItem, QSizePolicy, 
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor


# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
APP_ROOT = Path(__file__).resolve().parent.parent

ASSET_DIR = APP_ROOT / "assets"
SCRIPT_DIR = APP_ROOT / "scripts"
CONFIG_DIR = APP_ROOT / "config"

RUNTIME_DIR = APP_ROOT / "batch_photogrammetry_runtime"
RUNTIME_DIR.mkdir(exist_ok=True)


log_folder = RUNTIME_DIR / "log"
os.makedirs(log_folder, exist_ok=True)



CONFIG_FILE = RUNTIME_DIR / "config.json"
EXPORT_FILE = CONFIG_DIR / "depth_export.xml"
BLENDER_FILE = SCRIPT_DIR / "blender_script.py"
RENDER_SCENE  = ASSET_DIR / "blender" / "turntable_scene.blend"
DATA_FILE = RUNTIME_DIR / "data_output.csv"
MASK_FILE = CONFIG_DIR / "maskReconReg.rsbox"
RENDER_SCRIPT = SCRIPT_DIR / "turntable_render.py"
TEMP_MASK = RUNTIME_DIR / "temp_mask.png"



def find_executable(name, common_paths=None):
    """Find an executable using PATH and a list of common installation paths."""

    # First check the system PATH
    path_result = shutil.which(name)
    if path_result:
        return path_result

    # Then check known/common installation locations
    if common_paths:
        for path in common_paths:
            path = Path(path)

            if path.exists():
                return str(path)

    return ""


def find_realityscan():
    """Find RealityScan installation."""

    common_paths = [
        r"C:\Program Files\Epic Games\RealityScan_2.0\RealityScan.exe",
        r"C:\Program Files\Epic Games\RealityScan\RealityScan.exe",
    ]

    return find_executable("RealityScan.exe", common_paths)


def find_blender():
    """Find Blender installation."""

    common_paths = [
        r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    ]

    return find_executable("blender.exe", common_paths)


def find_ffmpeg():
    """Find FFmpeg installation."""

    common_paths = [
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
    ]

    return find_executable("ffmpeg.exe", common_paths)



default_rs_location = find_realityscan()
default_bl_location = find_blender()
default_ffmpeg_location = find_ffmpeg()



# ----------------------------------------------------------------------
def load_config():

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to load config: {e}")
    return {
        "reality_scan": default_rs_location,
        "blender": default_bl_location,
        "ffmpeg": default_ffmpeg_location
    }


# ----------------------------------------------------------------------
def save_config(config: dict):

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except OSError  as e:
        print(f"⚠️ Failed to save config: {e}")


# ----------------------------------------------------------------------
# HELPER SCRIPTS
# ----------------------------------------------------------------------
def save_rs_default_export():

    if Path(EXPORT_FILE).is_file():
        return
    setting_xml = '''
<Configuration id="{2D5793BC-A65D-4318-A1B9-A05044608385}">
  <entry key="eiExportImageList" value="0"/>
  <entry key="calexTrans" value="0"/>
  <entry key="eiExportFileNaming" value="5"/>
  <entry key="eiExportMasks" value="true"/>
  <entry key="calexHasDisabled" value="0x0"/>
  <entry key="hasCalexFilePath" value="1"/>
  <entry key="calexHasUndistort" value="0"/>
  <entry key="calexFileFormat" value="Export Depth and Mask Images"/>
  <entry key="calexExportUndistorted" value="false"/>
  <entry key="calexFileFormatId" value="{0ABB46B2-4FAA-4CE1-AA39-D96128D39BD9}"/>
  <entry key="calexHasImageExport" value="-1"/>
  <entry key="hasRadianceFieldsTransAABB" value="0"/>
  <entry key="hasCalexFileName" value="0"/>
  <entry key="eiExportDepths" value="false"/>
</Configuration>
'''
    root = ET.fromstring(setting_xml)
    tree = ET.ElementTree(root)
    try:
        with open(EXPORT_FILE, 'wb') as f:
            tree.write(f, encoding='utf-8', xml_declaration=True)
    except OSError  as e:
        print(f"⚠️ Failed to save depth export xml: {e}")
    
def save_mask_reg():
    if Path(MASK_FILE).is_file():
        return
    mask_region="""<ReconstructionRegion globalCoordinateSystem="NONE" globalCoordinateSystemWkt="NONE" globalCoordinateSystemName="NONE"
   isGeoreferenced="0" isLatLon="0" yawPitchRoll="0 -0 -0">
  <widthHeightDepth>0.2 0.2 0.2</widthHeightDepth>
  <Header magic="5395016" version="2"/>
  <CentreEuclid>
    <centre>0 0 0.1</centre>
  </CentreEuclid>
  <Residual s="1.00801206821472" ownerId="{3EF45083-6F69-4B6D-9F9D-ABF43BFA45C9}">
    <R>1 1.27069199025572e-33 2.56811527393476e-17 0 1 -4.94795542533734e-17 -2.56811527393476e-17 4.94795542533734e-17 1</R>
    <t>1.41713441213278e-10 1.79535350654608e-11 2.80793122087175e-09</t>
  </Residual>
</ReconstructionRegion>
"""
    try:
        with open(MASK_FILE, "w", encoding="utf-8") as f:
            f.write(mask_region)
    except OSError  as e:
        print(f"⚠️ Failed to save mask region script: {e}")


# ----------------------------------------------------------------------
# Helper UI – choose sub‑folders
# ----------------------------------------------------------------------
class SubFolderChooser(QDialog):

    def __init__(self, base_path: Path, parent: QWidget = None):

        super().__init__(parent)
        self.setWindowTitle("Select Nodules")
        self.resize(400, 300)

        self.base_path = base_path
        self.selected_paths = []

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.list_widget)

        for child in sorted(self.base_path.iterdir()):
            if child.is_dir():
                item = QListWidgetItem(child.name)
                item.setData(Qt.ItemDataRole.UserRole, str(child))
                self.list_widget.addItem(item)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def accept(self):

        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No selection", "Please select at least one folder")
            return
        self.selected_paths = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]
        super().accept()


# ----------------------------------------------------------------------
# Worker thread – runs commands via subprocess and streams output
# ----------------------------------------------------------------------
class ProcessWorker(QThread):

    line_received = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(self, commands, workers=1):
        super().__init__()

        # ✅ Normalize input
        if commands and isinstance(commands[0], str):
            commands = [commands]

        self.commands = deque(commands)
        self.workers = max(1, int(workers))
        self._stop_requested = False
        self._active = {}
    def run(self):
        exit_codes = []

        try:
            # Start initial workers
            for wid in range(self.workers):
                if not self.commands:
                    break
                self._start_process(wid)

            while self._active and not self._stop_requested:
                for wid, proc in list(self._active.items()):
                    line = proc.stdout.readline()
                    if line:
                        self.line_received.emit(
                            f"[W{wid}] {line.rstrip()}"
                        )
                        continue

                    # Process ended
                    if proc.poll() is not None:
                        exit_codes.append(proc.returncode)
                        self._cleanup_process(wid)

                        # Start next job if available
                        if self.commands:
                            self._start_process(wid)

        except Exception as exc:
            self.line_received.emit(f"[ERROR] {exc}")
            self.finished.emit(-1)
            return

        if self._stop_requested:
            self._terminate_all()

        self.finished.emit(max(exit_codes) if exit_codes else 0)

    def _start_process(self, wid):
        cmd = self.commands.popleft()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW
            if os.name == "nt" else 0,
            encoding="utf-8"
        )
        self._active[wid] = proc

    def _cleanup_process(self, wid):
        proc = self._active.pop(wid)
        if proc.stdout:
            proc.stdout.close()

    def stop(self):
        self._stop_requested = True
        self._terminate_all()

    def _terminate_all(self):
        for proc in self._active.values():
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(3)
                except Exception:
                    proc.kill()



# ----------------------------------------------------------------------
# Main window – UI + orchestration
# ----------------------------------------------------------------------
class MainWindow(QWidget):

    def __init__(self):

        super().__init__()
        self.window_title = "Batch Photogrammetry"
        self.setWindowTitle(self.window_title)
        self.resize(900, 700)

        save_rs_default_export()
        save_mask_reg()

        self.config = load_config()
        self.selected_folders = []
        self.folder_index = 0
        self.worker: ProcessWorker | None = None   
        self._batch_running = False          

        layout = QVBoxLayout(self)

        # ----- software paths --------------------------------------------
        self.lbl_rs   = QLabel("Reality Scan:")
        self.lbl_rs.setMinimumWidth(100)
        self.input_rs = QLineEdit(self.config.get("reality_scan", default_rs_location))
        self.input_rs.editingFinished.connect(self.update_config)

        self.lbl_bl   = QLabel("Blender:")
        self.lbl_bl.setMinimumWidth(100)
        self.input_bl = QLineEdit(self.config.get("blender", default_bl_location))
        self.input_bl.editingFinished.connect(self.update_config)

        self.lbl_ff   = QLabel("Ffmpeg:")
        self.lbl_ff.setMinimumWidth(100)
        self.input_ff = QLineEdit(self.config.get("ffmpeg", default_ffmpeg_location))
        self.input_ff.editingFinished.connect(self.update_config)


        config_layout   = QVBoxLayout()
        software_layout = QGridLayout()
        software_layout.addWidget(self.lbl_rs,   0, 0)
        software_layout.addWidget(self.input_rs, 0, 1)
        software_layout.addWidget(self.lbl_bl,   1, 0)
        software_layout.addWidget(self.input_bl, 1, 1)
        software_layout.addWidget(self.lbl_ff,   2, 0)
        software_layout.addWidget(self.input_ff, 2, 1)
        config_layout.addLayout(software_layout)
        layout.addLayout(config_layout)
        
        # ----- base paths --------------------------------------------
        self.lbl_base_dir    = QLabel("Base Folder:")
        self.lbl_base_dir.setMinimumWidth(100)
        self.lbl_base        = QLineEdit(self.config.get("base_dir", ""))
        self.lbl_base.editingFinished.connect(self.update_config)
        self.base_btn_choose = QPushButton("…")
        self.base_btn_choose.clicked.connect(self.choose_base_folder)


        base_dir_layout = QHBoxLayout()
        base_dir_layout.addWidget(self.lbl_base_dir)
        base_dir_layout.addWidget(self.lbl_base)
        base_dir_layout.addWidget(self.base_btn_choose)
        config_layout.addLayout(base_dir_layout)

        # ----- sub paths --------------------------------------------
        self.lbl_nodule_dir    = QLabel("Nodule Folders:")
        self.lbl_nodule_dir.setMinimumWidth(100)
        self.lbl_nodule        = QLineEdit(self.config.get("nodule_dirs", ""))
        self.lbl_nodule.editingFinished.connect(self.clean_newlines)
        self.lbl_nodule.editingFinished.connect(self.update_config)
        self.nodule_btn_choose = QPushButton("…")
        self.nodule_btn_choose.resize(10,10)
        self.nodule_btn_choose.clicked.connect(self.nodule_folder_chooser)
        
        nodule_dir_layout = QHBoxLayout()
        nodule_dir_layout.addWidget(self.lbl_nodule_dir)
        nodule_dir_layout.addWidget(self.lbl_nodule)
        nodule_dir_layout.addWidget(self.nodule_btn_choose)
        config_layout.addLayout(nodule_dir_layout)


        # ----- operation buttons --------------------------------------------
        self.rb_test   = QRadioButton("Test")
        self.rb_save   = QRadioButton("Save")
        self.rb_batch  = QRadioButton("Batch Process")
        self.rb_manual = QRadioButton("Manual Process: ")

        self.process_group = QButtonGroup(self)
        self.process_group.addButton(self.rb_save,   0)
        self.process_group.addButton(self.rb_batch,  1)
        self.process_group.addButton(self.rb_manual, 2)


        process_layout = QHBoxLayout()
        process_layout.addWidget(QLabel("Operation:"))
        process_layout.addWidget(self.rb_save)
        process_layout.addWidget(self.rb_batch)
        

        self.rb_ctrlPts    = QRadioButton("Export CtrlPts")
        self.rb_align      = QRadioButton("Align")
        self.rb_export     = QRadioButton("Export")
        self.rb_calculate  = QRadioButton("Calculate")
        self.rb_render     = QRadioButton("Render")

        self.manual_mode_group = QButtonGroup(self)
        self.manual_mode_group.addButton(self.rb_ctrlPts,   0)
        self.manual_mode_group.addButton(self.rb_align,     1)
        self.manual_mode_group.addButton(self.rb_export,    2)
        self.manual_mode_group.addButton(self.rb_calculate, 3)
        self.manual_mode_group.addButton(self.rb_render,    4)
        

        self.manual_widget = QWidget()
        manual_mode_layout = QHBoxLayout(self.manual_widget)
        manual_mode_layout.addWidget(self.rb_ctrlPts)
        manual_mode_layout.addWidget(self.rb_align)
        manual_mode_layout.addWidget(self.rb_export)
        manual_mode_layout.addWidget(self.rb_calculate)
        manual_mode_layout.addWidget(self.rb_render)
        
        spacer = QSpacerItem(20, 10, QSizePolicy.Policy.Expanding)
        
        manual_layout = QHBoxLayout()
        manual_layout.addWidget(self.rb_manual)
        manual_layout.addWidget(self.manual_widget, 2)
        
        layout.addLayout(process_layout)
        layout.addLayout(manual_layout)

        self._mode = "save"
        self.rb_ctrlPts.setChecked(True)
        self.rb_save.setChecked(True)
        self.manual_widget.setEnabled(False)

        self.rb_save.toggled.connect(lambda ch: self._set_mode("save",     ch))
        self.rb_batch.toggled.connect(lambda ch: self._set_mode("batch",   ch))
        self.rb_manual.toggled.connect(lambda ch: self._set_mode("manual", ch))

        self.rb_ctrlPts.toggled.connect(lambda ch: self._set_mode("export ctrlpts", ch))
        self.rb_align.toggled.connect(lambda ch: self._set_mode("align",            ch))
        self.rb_export.toggled.connect(lambda ch: self._set_mode("export",          ch))
        self.rb_calculate.toggled.connect(lambda ch: self._set_mode("calculate",    ch))
        self.rb_render.toggled.connect(lambda ch: self._set_mode("render",          ch))

        # self.process_group.addButton(self.rb_test, 3)
        # process_layout.addWidget(self.rb_test)
        # self.rb_test.toggled.connect(lambda ch: self._set_mode("test",     ch))

        # ----- console --------------------------------------------
        self.output_console = QTextEdit()
        self.output_console.setReadOnly(True)
        self.output_console.setPlaceholderText("…")
        self.auto_scroll = True

        bar = self.output_console.verticalScrollBar()
        bar.valueChanged.connect(self._on_scroll)

        layout.addWidget(self.output_console)

        # ----- start --------------------------------------------
        btn_layout     = QHBoxLayout()
        self.btn_start = QPushButton("Start Batch")
        self.btn_stop  = QPushButton("Stop Batch")
        self.btn_start.clicked.connect(self.start_batch)
        self.btn_stop.clicked.connect(self.stop_batch) 
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False) 
        

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop) 
        layout.addLayout(btn_layout)


        self.rs_exe      = self.input_rs.text()
        self.blender_exe = self.input_bl.text()
        self.ffmpeg_ext  = self.input_ff.text()


        if not hasattr(self, "log_file_path"):
            dt = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.log_file_path = os.path.join(log_folder, f"pmn-hh_tool_{dt}.log")


    # ------------------------------------------------------------------
    def update_config(self):

        self.config["reality_scan"] = self.input_rs.text().strip()
        self.config["blender"]      = self.input_bl.text().strip()
        self.config["ffmpeg"]       = self.input_ff.text().strip()
        self.config["base_dir"]     = self.lbl_base.text().strip()
        self.config["nodule_dirs"]  = self.lbl_nodule.text().strip()
        self.rs_exe      = self.input_rs.text().strip()
        self.blender_exe = self.input_bl.text().strip()
        self.ffmpeg_ext  = self.input_ff.text().strip()

        save_config(self.config)

    # ------------------------------------------------------------------
    def log(self, text: str):
        datefmt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_text = f"[{datefmt}] {text}"
        self.output_console.append(log_text)

        if hasattr(self, "log_file_path"):
            try:
                with open(self.log_file_path, "a", encoding="utf-8") as f:
                    f.write(f"{log_text}\n")
            except Exception as e:
                self.output_console.append(f"[{datefmt}] ERROR writing log file: {e}")
        
        if self.auto_scroll:
            self.output_console.moveCursor(QTextCursor.MoveOperation.End)
            self.output_console.ensureCursorVisible()
    
    # ------------------------------------------------------------------
    def _on_scroll(self, value):
        bar = self.output_console.verticalScrollBar()
        at_bottom = value == bar.maximum()
        self.auto_scroll = at_bottom



    # ------------------------------------------------------------------
    def choose_base_folder(self):

        config = load_config()
        config_dir = Path(self.lbl_base.text())
        base_dir = QFileDialog.getExistingDirectory(
            self,
            "Select the base directory",
            os.path.expanduser(config_dir),
            QFileDialog.Option.ShowDirsOnly,
        )

        if not base_dir:
            return
        base_path = Path(base_dir)
        self.log(f"Selected Base folder:")
        self.log(base_dir)
        self.lbl_base.setText(base_dir)

        self.update_config()


    # ------------------------------------------------------------------
    def nodule_folder_chooser(self):

        base_path = Path(self.lbl_base.text())
        chooser = SubFolderChooser(base_path, self)
        if chooser.exec() == QDialog.DialogCode.Accepted:
            self.log(f"✅ Selected {len(chooser.selected_paths)} nodules")
            
            nodules_dir = []
            for dir in chooser.selected_paths:
                nodules = dir.split("\\")[-1]
                nodules_dir.append(nodules)
                self.log(nodules)
            nodule_text = " ".join(nodules_dir)
            self.lbl_nodule.setText(str(nodule_text))
            config = load_config()
            config["nodule_dirs"] = nodule_text
            save_config(config)
        else:
            self.log("⚠️ No subfolders selected.")

    # ------------------------------------------------------------------
    def clean_newlines(self):
        text = self.lbl_nodule.text()
        if "\n" in text or "\r" in text:
            cleaned = text.replace("\n", " ").replace("\r", " ")
            self.lbl_nodule.blockSignals(True)
            self.lbl_nodule.setText(cleaned)
            self.lbl_nodule.blockSignals(False)

    # ------------------------------------------------------------------
    def _set_mode(self, mode_name: str, checked: bool):
        if checked:
            self._mode = mode_name
            if mode_name == "manual":
                mode_name = self.manual_mode_group.checkedButton().text()
                self._mode = mode_name.lower()

            self.log(f"🔧 Mode set to: {mode_name.title()}")
            self.manual_widget.setEnabled(self.rb_manual.isChecked())
            self.log(f"Nodules selected:")
            for nod in self.lbl_nodule.text().split(" "):
                nod_dir = Path(os.path.join(self.lbl_base.text(), nod))
                if  nod_dir.exists() and nod != "":
                    self.log(nod)
                else:
                    if nod != "":
                        self.log(f"🛑 {nod_dir} directory does not exist")



    def check_install(self, software):
        software_dict = {
            "blender": {
                "path": self.blender_exe,
                "name": "Blender"},
            "rs": {
                "path": self.rs_exe,
                "name": "Reality Scan"}
            }
        software_path = software_dict.get(software).get("path")
        software_name = software_dict.get(software).get("name")

        if not Path(software_path).exists():
            self.log("🛑 Batch cancelled by program.")
            self.log(f"⚠️ Failed to find {software_name} ⚠️")
            self.reset_selection()
            return True

    # ------------------------------------------------------------------
    def start_batch(self):
        if self.lbl_nodule.text() == "":
            self.log("⚠️ No subfolders selected")
            return
        self.selected_folders = []
        for dir in self.lbl_nodule.text().split(" "):
            nodule_dir = Path(os.path.join(self.lbl_base.text(), dir))
            if nodule_dir.exists() and dir != "":
                self.selected_folders.append(nodule_dir)
                self.log(dir)
            else:
                if dir != "":
                    self.log(fr"⚠️ {nodule_dir} does not exists")

        self.test_index               = 0
        self.save_proj_folder_index   = 0
        self.export_ctrlPts_index     = 0
        self.align_folder_index       = 0
        self.export_mesh_folder_index = 0
        self.calculate_folder_index   = 0
        self.render_folder_index      = 0
        self.current_loop_index       = 0
        self.current_folder_loops     = []

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)

        for btn in self.process_group.buttons() + self.manual_mode_group.buttons():
            btn.setEnabled(False)
 
        self._batch_running = True           

        self.log(f"🚀 Starting {self._mode} process…")

        if self.check_install("rs"):
            return 
        if self.check_install("blender"):
            return

        self.batch = False


        if self._mode == "test":
            self.test_function()
        if self._mode == "save":
            self.save_proj_for_folder()
        if self._mode == "batch":
            self.batch = True
            self.export_ctrlPts()

        if self._mode == "export ctrlpts":
            self.export_ctrlPts()
        if self._mode == "align":
            self.start_next_align_folder()
        if self._mode == "export":
            self.export_mesh()
        if self._mode == "calculate":
            self.calculate_mesh()
        if self._mode == "render":
            self.render_mesh()

    # ------------------------------------------------------------------
    def stop_batch(self):
        self.setWindowTitle(self.window_title)
        if self.worker is not None:
            self.log("🛑 Stop requested …")
            self.worker.stop()
        else:
            self.log("⚠️ No process is running.")
        for btn in self.process_group.buttons() + self.manual_mode_group.buttons():
            btn.setEnabled(True)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._batch_running = False      

    def reset_batch(self):
        self.setWindowTitle(self.window_title)
        self.log("🛑 Batch cancelled by user.")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.worker = None

    def reset_selection(self):
        self.setWindowTitle(self.window_title)
        for btn in self.process_group.buttons() + self.manual_mode_group.buttons():
            btn.setEnabled(True)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)



    # SAVE PROJECT FUNCTIONS
    # ----------------------------------------------------------------------
    def save_proj_for_folder(self):
        if self.save_proj_folder_index >= len(self.selected_folders):
            self.log("✅ All Nodules Saved.\n")    
            self.reset_selection()
            return

        folder      = self.selected_folders[self.save_proj_folder_index]
        nodule_name = Path(folder).name

        nodule_progress = f"{self.save_proj_folder_index + 1}/{len(self.selected_folders)}"
        update_text     = f"▶ Saving Nodule {nodule_progress} | [{folder}]"
        self.log(f"{update_text}")
        self.setWindowTitle(update_text)

        loop_folders = [
            os.path.join(folder, d)
            for d in os.listdir(folder)
            if os.path.isdir(os.path.join(folder, d)) and "loop" in d.lower()
        ]


        add_folder_args = []
        for lf in loop_folders:
            add_folder_args.extend(["-addFolder", lf])

        proj_file = fr"{folder}\{nodule_name}"
        if Path(proj_file + ".rsproj").exists():
            self.log(f"{proj_file} exists already. Skipping {nodule_name}.")
            self.save_proj_folder_finished()
            return


        cmd = [
            self.rs_exe,                                    ## variable to call Reality Scan executable
            "-headless",                                    ## Hides user interface
            "-reset", "cfg",                                ## Reset the user settings, (cfg - reset application settings)
            "-stdConsole",                                  ## Enables console redirection to the application standard output
            "-silent", "c:\\CrashReportFolder",             ## Suppress warning dialogs and uploading of the crash reports, stores report in the specified location
            "-newScene",                                    ## Create a new empty scene.
            "-set", "appIncSubdirs=true",                   ## Add all images to the specified folder, including subdirectories
            "-set", "appProcessActionTime=0",               ## Minimal process duration
            "-set", "sfmFeatureDetectionQuality=High",      ## Feature detection quality
            "-set", "sfmImageDownscaleFactor=2",            ## Image downscale factor. Lower for more accurate results
            *add_folder_args,                               ## Each loop directory
            "-save", proj_file,                             ## Save the current project to specified location, under NODxxx
            "-quit"                                         ## Quit the application. 
        ]

        self.worker = ProcessWorker(cmd)
        self.worker.line_received.connect(self.log)
        self.worker.finished.connect(lambda: self.save_proj_folder_finished())
        self.worker.start()

    def save_proj_folder_finished(self):
        folder = self.selected_folders[self.save_proj_folder_index]
        self.log(f"✅ Saved project for {folder}")

        self.save_proj_folder_index += 1
        if not self._batch_running:
            self.reset_batch()
            return

        self.save_proj_for_folder()


    # EXPORT CONTROL POINTS FUNCTIONS
    # ----------------------------------------------------------------------
    def export_ctrlPts(self):

        if self.export_ctrlPts_index >= len(self.selected_folders):
            self.log("✅ All control points exported.\n")
            if self.batch:
                self.start_next_align_folder()
            else:
                self.reset_selection()
            return
        current_folder = self.selected_folders[self.export_ctrlPts_index]
        folder = self.selected_folders[self.export_ctrlPts_index]
        nodule_progress = f"{self.export_ctrlPts_index + 1}/{len(self.selected_folders)}"
        update_text = f"▶ Exporting Nodule Control Points {nodule_progress} | [{folder}]"
        self.log(f"{update_text}")
        self.setWindowTitle(update_text)
        
        nodule_name    = current_folder.name
        controlPts_csv = current_folder / f"{nodule_name}_controlPts.csv"
        proj_file      = current_folder / f"{nodule_name}.rsproj"

        if Path(proj_file).exists():
            self.log(f"Found project file: {proj_file}")
        else:
            self.log(f"⚠️ Save file not found, skipping: {nodule_name}")
            self.export_ctrlPts_finished(controlPts_csv)
            return

        cmd = [
            self.rs_exe,                                
            "-headless", 
            "-reset", "cfg", 
            "-stdConsole",
            "-silent", "c:\\CrashReportFolder",
            "-load", fr"{folder}\{nodule_name}.rsproj",             ## Load saved project
            "-set", '"appProcessActionTime=0"',
            "-exportControlPointsMeasurements", controlPts_csv,     ## Export measurements of control points using the current setting
            "-quit"
        ]

        self.worker = ProcessWorker(cmd)
        self.worker.line_received.connect(self.log)
        self.worker.finished.connect(lambda: self.export_ctrlPts_finished(controlPts_csv))
        self.worker.start()

    def export_ctrlPts_finished(self, controlPts_csv):
        
        folder = self.selected_folders[self.export_ctrlPts_index]
        if Path(controlPts_csv).exists():
            datefmt = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

            with open(controlPts_csv, newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            for row in rows:
                if row:  # skip empty rows
                    basename_image_file = os.path.basename(row[0])
                    row[0] = os.path.join(os.path.basename(os.path.dirname(row[0])),basename_image_file)
            with open(controlPts_csv, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(rows)
            with open(controlPts_csv, newline="") as f:
                reader = csv.reader(f)
                controlPts_rows = list(reader)
            img_list = []
            for controlPts_row in controlPts_rows:
                if controlPts_row[0] != "":
                    basename_image_file = os.path.dirname(controlPts_row[0])
                    img_list.append(basename_image_file)
            point_count = {i:img_list.count(i) for i in img_list}
            constraints_num_list = []
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, newline='', encoding="utf-8") as f:
                    data_rows = list(csv.reader(f))
                data_header = data_rows[0]
            else:
                with open(DATA_FILE, "w", newline='', encoding="utf-8") as f:
                    header_rows = [["Filename",
                            "Nodule Name",
                            "Volume (cm3)",
                            "Surface Area (cm2)",
                            "Convex Hull Volume (cm3)",
                            "Convex Hull Surface Area (cm2)",
                            "Faces",
                            "Cruise",
                            "Zone",
                            "Station",
                            "Box Core / Multi-Tube",
                            "Collection Date",
                            "Processed Date",
                            "Total Input Images"]]
                    csv.writer(f).writerows(header_rows)
            max_index = 40
            if len(data_header) <= max_index:
                empty_to_add = max_index - len(data_header)
                spacers = [""] * empty_to_add
                data_header.extend(spacers)

            for loop in point_count:
                point_names = []
                for loop_row in controlPts_rows:
                    if loop_row: 
                        if loop_row[0].startswith(loop):
                            point_names.append(loop_row[1])
                point_names_count = {i:point_names.count(i) for i in point_names}
                pt_num =[]
                for pt_name in point_names_count:
                    pt_num.append(point_names_count[pt_name])
                pt_total = {i:pt_num.count(i) for i in pt_num}
                if len(pt_total) > 1:
                    self.log(point_names_count)
                    self.log(f"⚠️ Mismatch points in {loop}")
                nodule_name = loop.split("_")[0]
                loop_index = loop.split("_")[-1]

                ctrlPt_count = list(pt_total.keys())[0]
                constraints_num_list.append(ctrlPt_count)
                self.log(f"🔵 Loop #{loop_index} constraints: {ctrlPt_count}")

                found_col = 0
                for i, header in enumerate(data_header):
                    if header.endswith(f"loop {loop_index}"):
                        loop_column = i
                        found_col = True
                    if header == "Total Input Images":
                        input_img_index = i
                    if header == "Total Constraints":
                        total_constraints_index = i
                    if header == "Processed Date":
                        processed_date_index = i
                if not found_col:
                    col_index = sum(list([int(loop_index), total_constraints_index, 1]))
                    data_header[col_index] = f"constraints for loop {loop_index}"
                    loop_column = col_index
                    data_rows[0] = data_header

                found_row = 0
                for i, data_row in enumerate(data_rows):
                    if len(data_row) <= max_index:
                        empty_to_add = max_index - len(data_row)
                        spacers = [""] * empty_to_add
                        data_row.extend(spacers)
                    if len(data_row) > 1 and data_row[1] == nodule_name:
                        nod_row_index = i
                        found_row = True
                        data_row[loop_column] = ctrlPt_count
                        break
                if not found_row:
                    new_row = ["" , nodule_name]
                    new_row.extend([""] * 28)
                    new_row[loop_column] = ctrlPt_count
                    data_rows.append(new_row)

            total_tif = 0
            for loop_dir in os.listdir(folder):
                loop_dir_path = os.path.join(folder,loop_dir)
                if os.path.isdir(loop_dir_path) and "loop" in loop_dir:
                    loop_imgs = os.listdir(loop_dir_path)
                    for img in loop_imgs:
                        if img.endswith("tif"):
                            total_tif += 1
            total_cons = sum(constraints_num_list)
            data_row[processed_date_index] = datefmt
            data_row[total_constraints_index] = total_cons
            data_row[input_img_index] = total_tif
            with open(DATA_FILE, "w", newline='', encoding="utf-8") as f:
                csv.writer(f).writerows(data_rows)
            self.log(f"🔵 Total Input Images: {total_tif} ")
            self.log(f"🔵 Total Constraints: {total_cons} ")
            self.log(f"✅ Exported Control Points for {folder}")

            

        else:
            self.log(f"⚠️ Export for {folder} Control Points failed.")
        self.export_ctrlPts_index += 1

        if not self._batch_running:
            self.reset_batch()
            return

        self.export_ctrlPts()

    # ALIGN FUNCTIONS
    # ----------------------------------------------------------------------
    def align_next_loop(self):

        current_folder = self.selected_folders[self.align_folder_index]
        if self.current_loop_index >= len(self.current_folder_loops):
            self.log(f"✅ Finished all loops in {current_folder}.\n")
            self.align_folder_index += 1
            self.current_loop_index = 0
            self.start_next_align_folder()
            return

        folder = self.current_folder_loops[self.current_loop_index]
        folder_progress = f"{self.align_folder_index + 1}/{len(self.selected_folders)}"
        loop_progress = f"{self.current_loop_index + 1}/{len(self.current_folder_loops)}"
        update_text = f"▶ Aligning loop {loop_progress} | Folder {folder_progress} | [{folder}]"
        self.log(f"{update_text}")
        self.setWindowTitle(update_text)


        loop_img_ext = ".tif"

        images = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)) and f.endswith(loop_img_ext)]
        if images:
            self.log(f"Found {len(images)} files")
        else:
            self.log("⚠️ No images files found. Skipping to next folder.")
            self.align_process_finished()
            return

        for img in os.listdir(folder):
            if img.endswith(loop_img_ext):
                img_mask = img + ".mask.png"
                mask_path = os.path.join(folder, img_mask)
                if os.path.isfile(mask_path):
                    os.remove(mask_path)
    


        nodule_name    = current_folder.name
        controlPts_csv = current_folder / f"{nodule_name}_controlPts.csv"
        proj_file      = current_folder / f"{nodule_name}.rsproj"

        if Path(controlPts_csv).exists():
            LOOP_CSV = tmp_folder / "temp_loop.csv"
            if LOOP_CSV.exists():
                os.remove(LOOP_CSV)

            target_parent    = Path(folder).name

            loop_num = int(target_parent.split("_")[-1])
            loop_ctrl_points = set()

            with open(controlPts_csv, newline="", encoding="utf-8") as f:
                reader = csv.reader(f, delimiter=",")
                for row in reader:
                    if len(row) < 2:
                        continue

                    file_path     = row[0].strip()
                    control_point = row[1].strip()
                    
                    parent = Path(file_path).parent.name

                    if parent == target_parent:
                        loop_ctrl_points.add(control_point)
                        with open(LOOP_CSV, 'a', newline='') as csvfile:
                            writer = csv.writer(csvfile)
                            
                            full_path = os.path.join(current_folder, file_path)
                            writer.writerow([
                                full_path,
                                control_point,
                                row[2], row[3]
                                ])
                if not LOOP_CSV.exists():
                    self.log(f"No points found {folder}")
                    self.align_process_finished()
                    return

                with open(LOOP_CSV, 'r', newline='') as csvfile:
                    ctrlPt_count = sum(1 for line in csvfile) / 2

                loop_column = 15 + loop_num
                rows = []


            nodule_controlPts = sorted(loop_ctrl_points)[0:2]
            self.log(f"✅ Found Control Points: {nodule_controlPts}")
            self.log(f"✅ Control Points Count: {ctrlPt_count}")
            controlPt_1 = nodule_controlPts[0]
            controlPt_2 = nodule_controlPts[1]

            mask_offset = 0.02
            if "bot" in controlPt_1:
                mask_offset += 0.005 
            if "top" in controlPt_1:
                mask_offset -= 0.003
            self.log(f"Mask Offset: {mask_offset}")

            cmd = [
                self.rs_exe,
                "-headless", 
                "-reset", "cfg", 
                "-stdConsole",
                "-silent", "c:\\CrashReportFolder",
                "-newScene",
                "-set", '"appProcessActionTime=0"',
                "-set", "mvsPreviewDownscaleFactor=2",
                "-set", "sfmFeatureDetectionQuality=High",
                "-set", "sfmImageDownscaleFactor=1",                                
                "-addFolder", folder,                                               ## Add 1 loop images
                "-align",                                                           ## Align images using the current settings.
                "-importControlPointsMeasurements", LOOP_CSV,                       ## Import measurements of control points (CPs) using the current settings.
                "-defineDistance", f'{controlPt_1}', f'{controlPt_2}', '0.01',      ## Define a distance constraint between two control points, which automatically extracted from the exported csv.
                "-selectControlPoint", f'{controlPt_1}',                            ## Select a control point by its name.
                "-editControlPointSelection", "gpType=1",                           ## Sets the selected CP to be a Ground control. This would mean the control points plotted for this loop are on 0 z axis.
                "-selectControlPoint", f'{controlPt_2}',
                "-editControlPointSelection", "gpType=1",
                "-setReconstructionRegionByDensity",                                ## Set the reconstruction region to the part of the sparse point cloud with the highest density.
                "-calculatePreviewModel",                                           ## Calculate 3D mesh in the preview quality.
                "-update",                                                          ## Update all components and models by a rigid transformation to fit the actual constraints and control points.
                "-setReconstructionRegion", MASK_FILE,                              ## Import a reconstruction region from the box.rsbox file. This is an premade reconstruction region which 20x20x20cm.
                "-moveReconstructionRegion", "0", "0", f'{mask_offset}',            ## Move the reconstruction region along the region's axis. Depending on where the control points are plotted, top, middle, bot, this would move the mask up in the z axis by 2.5cm, 2cm, 1.7cm respectively.
                "-selectTrianglesOutsideReconReg",                                  ## Select triangles outside the reconstruction region.
                "-removeSelectedTriangles",                                         ## Create a new model with selected triangles left out.
                "-exportDepthAndMask", folder, EXPORT_FILE,                         ## Export depth maps and/or masks for selected images. This uses a defined setting explained below.
                "-quit"
            ]

        else:
            self.log(f"⚠️ No control point CSV file found at {controlPts_csv}")
            self.log("Using automatic masking.")

            cmd = [
                self.rs_exe,
                "-headless", "-reset", "cfg", "-stdConsole",
                "-silent", "c:\\CrashReportFolder",
                "-newScene",
                "-set", '"appProcessActionTime=0"',
                "-set", '"mvsPreviewDownscaleFactor=2"',
                "-set", "sfmFeatureDetectionQuality=Normal" ,
                "-set", "sfmImageDownscaleFactor=1" ,
                "-addFolder", folder,
                "-align",
                "-setReconstructionRegionByDensity",
                "-calculatePreviewModel",
                "-moveReconstructionRegion", "0", "0", "5",
                "-selectTrianglesOutsideReconReg",
                "-removeSelectedTriangles",
                "-exportDepthAndMask", folder, EXPORT_FILE,
                "-quit"
            ]



        self.worker = ProcessWorker(cmd)
        self.worker.line_received.connect(self.log)
        self.worker.finished.connect(lambda: self.align_process_finished())
        self.worker.start()


    # ------------------------------------------------------------------
    def align_process_finished(self):




        folder = self.current_folder_loops[self.current_loop_index]
        self.log(f"✅ Finished {folder}")
        self.current_loop_index += 1

        if not self._batch_running:
            self.reset_batch()
            return

        self.align_next_loop()


    def start_next_align_folder(self):

        if self.align_folder_index >= len(self.selected_folders):
            self.log("✅ All folders processed for alignment.")
            if self.batch:
                self.export_mesh()
            else:
                self.reset_selection()
            return

        current_folder = Path(self.selected_folders[self.align_folder_index])
        self.log(f"▶ Processing nodule {self.align_folder_index + 1}/{len(self.selected_folders)}: {current_folder}")

        self.current_folder_loops = [
            str(p) for p in current_folder.iterdir()
            if p.is_dir() and "loop" in p.name.lower()
        ]

        if not self.current_folder_loops:
            self.log(f"⚠️ No loop folders found in {current_folder}. Skipping.")
            self.align_process_finished()
            return

        self.align_next_loop()



    # EXPORT FUNCTIONS
    # ----------------------------------------------------------------------
    def export_mesh(self):

        if self.export_mesh_folder_index >= len(self.selected_folders):
            self.log("✅ All Nodules Exported.\n")
            if self.batch:
                self.calculate_mesh()
            else:
                self.reset_selection()
            return

        folder = self.selected_folders[self.export_mesh_folder_index]
        nodule_progress = f"{self.export_mesh_folder_index + 1}/{len(self.selected_folders)}"
        update_text = f"▶ Exporting Nodule {nodule_progress} | [{folder}]"
        self.log(f"{update_text}")
        self.setWindowTitle(update_text)
        
        nodule_name = Path(folder).name
        ctrlPt_csv = fr"{folder}\{nodule_name}_controlPts.csv"
        
        PROJ_FILE = fr"{folder}\{nodule_name}.rsproj"
        PROJ_FILE_models = fr"{folder}\{nodule_name}_withModels.rsproj"

        loop_folders = []
        for d in os.listdir(folder):
            loop_dir = os.path.join(folder, d)
            if os.path.isdir(loop_dir) and "loop" in d.lower():
                mask_exists = [
                    1
                    for d in os.listdir(loop_dir)
                    if "mask" in d]
                if len(mask_exists) > 1:
                    loop_folders.append(loop_dir)

        add_folder_args = []
        for lf in loop_folders:
            add_folder_args.extend(["-addFolder", lf])

        cmd = [self.rs_exe,
            "-headless", 
            "-reset", "cfg",
            "-stdConsole", 
            "-silent", "c:\\CrashReportFolder",
            "-set", "appProcessActionTime=0",
            "-load", PROJ_FILE,
            "-set", "mvsDecimationFactor=0.5",
            "-set", "mvsNormalDownscaleFactor=2",
            "-set", "unwrapMinTexResolution=2048",                              ## Sets texture size to 2K
            "-set", "sfmFeatureDetectionQuality=High" ,                         ## Sets feature detection quality to High
            "-set", "sfmImageDownscaleFactor=1",
            *add_folder_args,                                                   ## Adds all data sets and their masks
            "-deleteAllComponents",                                             ## Delete all components. This ensures a clean scene.
            "-align",
            "-update",
            "-setReconstructionRegionByDensity",
            "-calculateNormalModel",                                            ## Calculate 3D mesh in the normal quality.
            "-calculateTexture",                                                ## Calculate texture using the current settings.
            "-save", PROJ_FILE_models,                                          ## Save the current project to a new file.
            "-exportModel", "Model 1", fr"{folder}\{nodule_name}_mesh.obj",     ## Export a model (modelName from the project) as a file (fileName including path and file extension) using the current settings.
            "-quit"]

        self.worker = ProcessWorker(cmd)
        self.worker.line_received.connect(self.log)
        self.worker.finished.connect(lambda: self.export_mesh_process_finished())
        self.worker.start()


    # ----------------------------------------------------------------------
    def export_mesh_process_finished(self):

        folder = self.selected_folders[self.export_mesh_folder_index]
        self.log(f"✅ Exported Mesh for {folder}")
        self.export_mesh_folder_index += 1

        if not self._batch_running:
            self.reset_batch()
            return

        self.export_mesh()

    # CALCULATE FUNCTIONS
    # ----------------------------------------------------------------------
    def calculate_mesh(self):
        
        if self.calculate_folder_index >= len(self.selected_folders):
            self.log("✅ All Nodules Calculated.\n")
            if self.batch:
                self.render_mesh()
            else:
                self.reset_selection()
            return
        if not Path(BLENDER_FILE).is_file():
            return

        folder = self.selected_folders[self.calculate_folder_index]
        nodule_progress = f"{self.calculate_folder_index + 1}/{len(self.selected_folders)}"
        update_text = f"▶ Calculating Nodule {nodule_progress}: {folder}"
        self.log(f"{update_text}")
        self.setWindowTitle(update_text)

        cmd = [ self.blender_exe,
            "--background",
            "--python",
            BLENDER_FILE,
            "--",
            folder,
            DATA_FILE
            ]

        self.worker = ProcessWorker(cmd)
        self.worker.line_received.connect(self.log)
        self.worker.finished.connect(lambda: self.calculate_mesh_process_finished())
        self.worker.start()


    # ----------------------------------------------------------------------
    def calculate_mesh_process_finished(self):

        folder = self.selected_folders[self.calculate_folder_index]
        self.log(f"✅ Calculated Mesh for {folder}")
        self.calculate_folder_index += 1

        if not self._batch_running:
            self.reset_batch()
            return

        self.calculate_mesh()


    # RENDER FUNCTIONS
    # ----------------------------------------------------------------------
    def render_mesh(self):
        
        if self.render_folder_index >= len(self.selected_folders):
            self.log("✅ All Nodules Rendered.\n")
            self.reset_selection()
            return

        folder = self.selected_folders[self.render_folder_index]
        nodule_progress = f"{self.render_folder_index + 1}/{len(self.selected_folders)}"
        update_text = f"▶ Rendering Nodule {nodule_progress}: {folder}"
        self.log(f"{update_text}")
        self.setWindowTitle(update_text)

        nodule_name = Path(folder).name
        obj_file = folder / f"{nodule_name}_mesh.obj"

        if not Path(RENDER_SCENE).exists():
            self.log(f"⚠️ {RENDER_SCENE} does not exists. Cannot procced with rendering.")
            return
        if not Path(RENDER_SCRIPT).exists():
            self.log(f"⚠️ {RENDER_SCRIPT} does not exists. Cannot procced with rendering.")
            return

        workers = 4
        max_frame = 120
        total_frames = max_frame/workers
        
        cmd_list = []
        for i in range(workers):
            sframe = int((i * total_frames ) + 1)
            eframe = int((i + 1) * total_frames)

            cmd = [ self.blender_exe, 
                RENDER_SCENE,
                "--background", 
                "--python", RENDER_SCRIPT,
                "--",
                obj_file,
                DATA_FILE,
                "--anim",
                f"--sf={sframe}",
                f"--ef={eframe}",
                ]
            if i ==0:
                cmd.append("--first")
            cmd_list.append(cmd)


        self.worker = ProcessWorker(cmd_list, workers=workers)
        self.worker.line_received.connect(self.log)
        self.worker.finished.connect(lambda: self.make_mp4_from_renders())
        self.worker.start()


    def make_mp4_from_renders(self):

        folder = self.selected_folders[self.render_folder_index]
        nodule_name = Path(folder).name

        RENDER_DIR = os.path.join(folder, 
                            f"{nodule_name}_renders",
                            f"{nodule_name}_beauty.%04d.png")
        MP4_OUTPUT = os.path.join(folder,
                            f"{nodule_name}_turntable.mp4")


        cmd = [ default_ffmpeg_location, "-y",
            "-framerate", "60",
            "-i", RENDER_DIR,
            "-c:v", "libx265",
            "-vf", "format=yuv420p",
            "-preset", "medium",
            "-crf", "23",
            MP4_OUTPUT
        ]

        if Path(default_ffmpeg_location):
            self.worker = ProcessWorker(cmd)
            self.worker.line_received.connect(self.log)
            self.worker.finished.connect(lambda: self.render_mesh_process_finished())
            self.worker.start()

        else:
            self.log("⚠️ FFMPEG not found. Skipping mp4 conversion")
            self.render_mesh_process_finished()
            
    # ----------------------------------------------------------------------
    def render_mesh_process_finished(self):

        folder = self.selected_folders[self.render_folder_index]
        self.log(f"✅ Rendered Mesh for {folder}")
        self.render_folder_index += 1

        if not self._batch_running:
            self.reset_batch()
            return

        self.render_mesh()


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())



if __name__ == "__main__":
    main()
