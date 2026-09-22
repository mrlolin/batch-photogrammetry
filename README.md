# Batch Photogrammetry

Automated photogrammetry workflow for reconstructing 3D nodule models from photographic datasets and calculating geometric measurements.

The project provides a Python-based wrapper around **RealityScan** and **Blender** to automate the repetitive stages of the photogrammetry workflow. Manual control-point placement is retained as part of the process, while subsequent reconstruction, masking, model export, and geometric calculations are automated.

## Overview

The workflow is designed to process a series of photographic loops representing a nodule from different positions.

The general workflow is:

```text
Photographic Dataset
        │
        ▼
Create RealityScan Project
        │
        ▼
Manual Control-Point Placement
        │
        ▼
Export Control-Point Measurements
        │
        ▼
Generate Reconstruction Regions and Masks
        │
        ▼
Combine Loops and Reconstruct 3D Model
        │
        ▼
Export OBJ
        │
        ▼
Blender
        │
        ├── Surface Area
        ├── Volume
        ├── Convex Hull Surface Area
        └── Convex Hull Volume
```

The workflow deliberately separates the **manual preparation stage** from the automated processing stage. This allows the operator to make decisions about control-point placement where image visibility requires human judgement, while ensuring that the remaining processing uses consistent parameters.

For a detailed description of the methodology, see [`docs/methodology.md`](docs/methodology.md).

---

## Requirements

The workflow requires:

* Windows
* Python
* RealityScan
* Blender

RealityScan performs the photogrammetric reconstruction, while Blender is used to calculate geometric properties of the resulting mesh.

The Python script is intended to control the external applications rather than replace their underlying processing.

### Application discovery

The application paths can be configured manually, but the program attempts to locate the required applications automatically.

The search order is:

1. Previously saved configuration
2. Common installation locations
3. Executables available through the system `PATH`
4. Manual path selection if an executable cannot be found

Machine-specific configuration should not be committed to the repository.

---

## Input Dataset Structure

The minimum expected input structure is:

```text
base_directory/
└── NOD501/
    ├── NOD501/
    ├── NOD501_loop_00/
    │   ├── NOD501_loop_00_9Y5A4936.tif
    │   ├── ...
    │
    ├── NOD501_loop_01/
    │   ├── ...
    │
    └── NOD501_loop_...
```

Each `NODxxx_loop_XX` directory contains the photographic dataset for one loop.

The exact number of loops and images can vary between nodules.

An output CSV containing information associated with the nodule may also be used by the workflow. This information is supplementary to the photogrammetry process and is used to associate calculated measurements with the corresponding nodule.

---

## Workflow

### 1. Create the RealityScan Project

The first automated stage creates a new RealityScan project and imports the photographic datasets.

RealityScan is run in headless mode and configured with the processing parameters defined by the Python script.

The resulting `.rsproj` file is saved and becomes the starting point for the manual preparation stage.

### 2. Place Control Points

Two control points are manually placed for each photographic loop.

The control points:

* Must be visible in the relevant images.
* Must have unique names across the project.
* Must represent a consistent 1 cm separation.
* Must remain at the same physical reference positions throughout their loop.

The 1 cm distance is a fixed reference used to provide a consistent scale for positioning the predefined reconstruction region between loops and used to determine the scale of the calculated mesh.

Control points can be given the suffix:

* `top` — upper reference line
* no suffix — middle reference line
* `bot` — lower reference line

These names are used by the automated workflow to determine the appropriate reconstruction-region offset.

Once placed, the control-point pairs are constrained to 0.01 m in RealityScan.

For example:

```text
-defineDistance "point 0" "point 1" 0.01
```

### 3. Export Control-Point Measurements

The manually prepared project is loaded by the Python script and the control-point measurements are exported to CSV.

The original manually prepared project is not modified by the automated processing.

The exported measurements are used as input for the following stages.

### 4. Generate Reconstruction Masks

Each photographic loop is processed independently.

The loop is aligned and its control-point measurements are imported. The control points are assigned as RealityScan Ground Points, placing them on the ground plane (`Z = 0`).

A reconstruction region is initially generated from the density of the sparse point cloud. This is required by RealityScan before a preview model can be calculated.

The preview model is not used as the final model. Instead, it allows the workflow to establish the spatial relationship required to replace the automatically generated region with a predefined 20 × 20 × 20 cm reconstruction region. It is also the rough model to create the mask.

The predefined region is then offset according to the control-point position:

```text
top       → 2.5 cm
middle    → 2.0 cm
bot       → 1.7 cm
```

Geometry outside the reconstruction region is removed and depth maps/masks are exported for the loop.

This process is repeated for each loop.

### 5. Reconstruct the Final Model

Once all loop masks have been generated, the datasets are combined into a final RealityScan reconstruction.

The existing components are removed and the images and masks are processed using the defined reconstruction settings.

The resulting model is textured and exported as an OBJ file.

Example output:

```text
NOD501_mesh.obj
```

### 6. Calculate Geometric Measurements

The exported OBJ files are processed by Blender.

The script calculates:

* Face count
* Surface area
* Volume
* Convex-hull surface area
* Convex-hull volume

The reconstructed model uses metre-scale dimensions. Measurements are therefore converted to centimetres:

```text
1 m² = 10,000 cm²
1 m³ = 1,000,000 cm³
```

The convex-hull measurements are calculated by replacing the reconstructed mesh with its convex hull and repeating the area and volume calculations.

---

## Manual vs Automated Processing

The workflow intentionally contains both manual and automated stages.

### Manual

The operator is responsible for:

1. Reviewing the photographic dataset.
2. Selecting suitable images for control-point placement.
3. Placing the two control points for each loop.
4. Naming the control points correctly.
5. Defining the 1 cm distance constraints.

These steps require visual judgement because the visibility of the reference lines can vary between images.

### Automated

The Python workflow performs:

1. RealityScan project creation.
2. Importing photographic datasets.
3. Exporting control-point measurements.
4. Creating loop reconstructions.
5. Applying control-point constraints.
6. Positioning reconstruction regions.
7. Generating masks and depth maps.
8. Combining the loop datasets.
9. Reconstructing the final 3D model.
10. Exporting the OBJ.
11. Calculating geometric measurements in Blender.

This separation minimises manual intervention while retaining human judgement where it is required.

---

## Repository Structure

```text
batch-photogrammetry/
│
├── README.md
│
├── src/
│   ├── batch_photogrammetry.py
│   └── blender_script.py
│
├── scripts/
│   └── ...
│
├── assets/
│   ├── blender/
│   │   └── turntable_scene.blend
│   └── fonts/
│       └── DejaVuSans.ttf
│
├── config/
│   └── config.example.json
│
├── docs/
│   └── methodology.md
│
├── examples/
│   └── ...
│
├── requirements.txt
└── .gitignore
```

### `src/`

Contains the primary Python source code responsible for the photogrammetry and Blender processing.

### `scripts/`

Contains supporting scripts and utilities that are not part of the primary application logic.

### `assets/`

Contains static project assets required by the workflow, such as Blender scene files and fonts.

### `config/`

Contains example configuration files.

### `docs/`

Contains additional documentation describing the methodology and technical implementation.


---

## Reproducibility

The automated portion of the workflow uses explicitly defined RealityScan and Blender parameters to reduce variation between processing runs.

The manual control-point placement remains the primary user-dependent stage. Once the control points have been placed and constrained, the subsequent processing uses those measurements and predefined reconstruction parameters.

The use of a fixed 1 cm control-point separation and predefined reconstruction-region dimensions provides a consistent reference between photographic loops.

---

## Documentation

Additional documentation is available in:

* [`docs/methodology.md`](docs/methodology.md) — detailed description of the photogrammetry and measurement methodology.

---

## AI Assistance

Generative AI tools were used during the development of this project to assist with code development, debugging, technical explanations, and documentation. AI-assisted suggestions were reviewed, modified, and tested by the author, who remains responsible for the implementation, methodology, and contents of this repository.

## License

This project is licensed under the MIT License. See the LICENSE file for the full license text.

## Author

Leonardo Lin

This project was developed as part of research into automated photogrammetric reconstruction and geometric analysis of nodules.