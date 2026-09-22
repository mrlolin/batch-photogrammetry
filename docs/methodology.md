
The Python script primarily functions as a wrapper for the automation of the photogrammetry workflow. It assists with the creation of 3D models from photographic datasets and the subsequent calculation of measurements from the resulting models. The majority of the photogrammetry processing is performed using RealityScan, while Blender is used for the final geometric calculations.

The script assumes a predefined file structure and, optionally, the existence of an output CSV file containing information associated with the collected nodule data. The CSV file is not required for the photogrammetry process itself, but can be used to associate the calculated measurements with other information relating to the nodule.

At a minimum, the photographic dataset is expected to follow a directory structure similar to the following:

```text
base directory
NOD501
├── NOD501
├── NOD501_loop_00
│   ├── NOD501_loop_00_9Y5A4936.tif
│   ├── ...
├── NOD501_loop_...
....
```

### 1. Initial RealityScan Project Creation

Before the manual processing can begin, an automated process is used to create the initial RealityScan project. This process imports the photographic datasets from the relevant directories and saves a RealityScan project file that can subsequently be manually prepared.

_`batch_photogrammetry.py`_  
_line 777_

```python
cmd = [
	 self.rs_exe,                                    ## Variable to call Reality Scan executable
	 "-headless",                                    ## Hides user interface
	 "-reset", "cfg",                                ## Reset the user settings, (cfg - reset application settings)
	 "-stdConsole",                                  ## Enables console redirection to the application standard output
	 "-silent", "c:\\CrashReportFolder",             ## Suppress warning dialogs and uploading of the crash reports, stores report in the specified location
	 "-newScene",                                    ## Create a new empty scene.
	 "-set", "appIncSubdirs=true",                   ## Add all images to the specified folder, including sub-directories
	 "-set", "appProcessActionTime=0",               ## Minimal process duration
	 "-set", "sfmFeatureDetectionQuality=High",      ## Feature detection quality
	 "-set", "sfmImageDownscaleFactor=2",            ## Image downscale factor. Lower for more accurate results.
	 *add_folder_args,                               ## Each loop directory
	 "-save", proj_file,                             ## Save the current project to specified location, under NODxxx
	 "-quit"                                         ## Quit the application.
] 

```

The resulting project file provides the starting point for the manual preparation of the dataset.


### 2. Manual Placement of Control Points

For each photographic loop, two control points are manually placed at corresponding locations within the images. The two control points are assigned a known separation of **1 cm**. This distance is used as a consistent reference when positioning the reconstruction region during the subsequent automated processing.

The choice of 1 cm is a fixed reference used throughout the project rather than a measurement of the nodule itself. Maintaining the same reference distance across all loops ensures that the reconstructed datasets have a consistent scale relative to the predefined reconstruction region.

Each control point must have a unique name across the entire project. For example, for `loop_01`, `point 0` may correspond to the 5 cm reference position and `point 1` to the 6 cm reference position. For `loop_02`, `point 2` and `point 3` may correspond to the same physical reference positions. These positions are examples only; the important requirement is that the two selected points for each loop have a known and consistent separation of 1 cm.

Once the two control points have been selected for a particular loop, their positions should remain consistent throughout that loop's image sequence.

The specific images used to place the control points depend on the visibility and readability of the reference lines within the photographic dataset. In some cases, the required reference line may only be sufficiently visible in the upper or lower portion of the image. In these situations, the control point names are given an additional suffix of either `top` or `bot`, corresponding to the upper or lower reference line respectively. Control points without either suffix are treated as being positioned at the middle reference line.

This naming convention is used by the subsequent automated processing to determine the appropriate reconstruction-region offset for that loop.

After all control points have been placed, the distance between each corresponding pair must be defined as 1 cm. This can be performed in the RealityScan console using the following command:

```
-defineDistance "point 0" "point 1" 0.01 -defineDistance "point 2" "point 3" 0.01 ...
```

The value `0.01` defines the distance between each pair of control points as 0.01 m, or 1 cm.

### 3. Requirements for Automated Processing

Once the manual preparation has been completed, the remaining processing steps are automated. To ensure that the automated process can operate correctly, the following conditions must be satisfied:

-   The RealityScan project file must contain links to the required photographic datasets.
    
-   All manually placed control points must have appropriate and unique names.
    
-   Each pair of control points must represent a known distance of 1 cm.
    
-   The corresponding distance constraints must be defined within the RealityScan project.
    

### 4. Exporting Control Point Measurements

The first automated processing stage exports the manually defined control point measurements to a CSV file.

_`batch_photogrammetry.py`_  
_line 839_

```python
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

```

The exported CSV contains the measured locations of the control points and is subsequently used by the automated processing stages.

It is important to note that this and the subsequent automated processes do **not modify the manually prepared RealityScan project**. Instead, the required data is extracted from the prepared project and used as input for new processing operations. This prevents the manually prepared project from being overwritten.


### 5. Reconstruction Region and Mask Generation

After the control point measurements have been exported, the next stage is to generate the masks used during model reconstruction.

The purpose of the reconstruction region is to restrict the reconstructed geometry to the relevant portion of the photographic dataset. The photographs contain additional objects, including the measurement apparatus and supporting stand, which are not part of the nodule itself. The reconstruction region therefore limits the geometry used to construct the final model and reduces unwanted background geometry and noise.

Within RealityScan, a reconstruction region must first be established before a preview model can be generated. The automated process therefore initially determines a reconstruction region based on the density of the sparse point cloud and generates a preview model. The preview model is not used as the final reconstruction; instead, this step provides the spatial information required to subsequently replace the automatically generated region with a predefined reconstruction region.

For each photographic loop, a new RealityScan scene is created. The images are aligned, the previously exported control point measurements are imported, and the corresponding pair of control points is assigned a 1 cm distance constraint.

The two control points are also assigned the RealityScan **Ground Point** type (`gpType=1`). This places the control points on the ground plane, corresponding to `Z = 0`. This establishes a consistent reference plane from which the reconstruction region can subsequently be positioned.

`_batch_photogrammetry.py_`  
_line 1094_

```python
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
	 "-addFolder", folder,                                               ## Add the images from one loop.
	 "-align",                                                           ## Align images using the current settings.
	 "-importControlPointsMeasurements", LOOP_CSV,                       ## Import measurements of control points (CPs) using the current settings.
	 "-defineDistance", f'{controlPt_1}', f'{controlPt_2}', '0.01',      ## Define a 1 cm distance constraint between the two control points.
	 "-selectControlPoint", f'{controlPt_1}',                            ## Select a control point by its name.
	 "-editControlPointSelection", "gpType=1",                           ## Set the selected CP as a Ground Point, placing it on the ground plane (Z = 0).
	 "-selectControlPoint", f'{controlPt_2}',                            ## Select the second control point by its name.
	 "-editControlPointSelection", "gpType=1",                           ## Set the selected CP as a Ground Point, placing it on the ground plane (Z = 0).
	 "-setReconstructionRegionByDensity",                                ## Set the reconstruction region to the highest-density part of the sparse point cloud.
	 "-calculatePreviewModel",                                           ## Generate a preview mesh; this is required to establish the reconstruction region.
	 "-update",                                                          ## Update scene components and models to satisfy the control-point constraints.
	 "-setReconstructionRegion", MASK_FILE,                              ## Import the predefined 20 x 20 x 20 cm reconstruction region.
	 "-moveReconstructionRegion", "0", "0", f'{mask_offset}',            ## Move the reconstruction region along its local axis according to the control-point position: top, middle, or bot.
	 "-selectTrianglesOutsideReconReg",                                  ## Select triangles outside the reconstruction region.
	 "-removeSelectedTriangles",                                         ## Remove the selected triangles from the model.
	 "-exportDepthAndMask", folder, EXPORT_FILE,                         ## Export depth maps and masks using the defined settings.
	 "-quit"
]
```

Following the generation of the preview model, the automatically positioned reconstruction region is replaced with a predefined reconstruction-region file. This region is a 20 × 20 × 20 cm box and provides a consistent volume from which the relevant portion of each loop can be extracted.

The predefined region is translated along its local axis according to the position of the control points within the photographic dataset. Control points located on the upper reference line use the `top` offset, control points located on the middle reference line use the default offset, and control points located on the lower reference line use the `bot` offset. In the current implementation, these offsets correspond to 2.5 cm, 2.0 cm, and 1.7 cm respectively.

The 1 cm control-point constraint is important at this stage because it provides a consistent scale for the preview reconstruction. Without a consistent constraint, the reconstructed scene could vary in scale between loops, which would prevent the predefined reconstruction region from being positioned consistently.

After the reconstruction region has been positioned, triangles outside the region are selected and removed. The resulting depth maps and masks are then exported. This process is repeated independently for each photographic loop.
### 6. Final 3D Model Reconstruction

Once the depth maps and masks have been generated for all loops, the final nodule reconstruction can be performed.

The original RealityScan project containing the photographic datasets is loaded, and the corresponding image and mask data from all loops are added. The existing components are removed to ensure that the model is reconstructed from a clean state.

The reconstruction is then performed using the specified multi-view stereo, normal-model, and texture settings. The resulting mesh is saved as a new RealityScan project and exported as an OBJ file.

_`batch_photogrammetry.py`_  
_line 1239_

```python
 cmd = [
	  self.rs_exe,
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
	  "-quit"
 ]

```
The control-point constraints and reconstruction-region processing ensure that the individual loop datasets have been reconstructed using a consistent spatial reference. The exported OBJ therefore provides a model with a consistent physical scale for subsequent geometric measurements.


### 7. Calculation of Surface Area and Volume

The final stage uses Blender to calculate the geometric properties of the reconstructed nodule. The exported OBJ file is imported into Blender and its transforms are applied before the mesh is analysed.

For each imported mesh, a BMesh representation is created. The number of faces, surface area, and volume are then calculated from the reconstructed geometry.

_blender_script.py_
_line 111_

```python
# --- Face count ---
face_count = f"{len(bm.faces):,d}"

# --- Calculate in meters ---
area_m2 = sum(f.calc_area() for f in bm.faces)
volume_m3 = bm.calc_volume(signed=False)

# --- Convert to cm² / cm³ ---
area_cm2 = round((area_m2 * 10000.0), 3)
volume_cm3 = round((volume_m3 * 1000000.0), 3)
```

The `calc_area()` and `calc_volume()` functions calculate the surface area and volume using the model's metre-scale dimensions. These values are converted to square centimetres and cubic centimetres respectively.

For surface area, the conversion is based on the fact that:

[  1,m = 100,cm  ]

Because surface area has two dimensions:

[  1,m^2 = 100,cm \times 100,cm = 10,000,cm^2  ]

Therefore, the calculated area in square metres is multiplied by 10,000 to obtain square centimetres.

Similarly, volume has three dimensions:

[  1,m^3 = 100,cm \times 100,cm \times 100,cm = 1,000,000,cm^3 ]

Therefore, the calculated volume in cubic metres is multiplied by 1,000,000 to obtain cubic centimetres.

#### Convex Hull Calculation

In addition to the measurements of the reconstructed mesh, a convex hull is generated from the same geometry. The convex hull is the smallest convex surface that completely encloses the original mesh. This provides a second set of area and volume measurements based on the convexified geometry.

_blender_script.py_
_line 121_

```python
# --- Replace mesh with convex hull ---
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.convex_hull(delete_unused=True)
bpy.ops.object.mode_set(mode='OBJECT')

# --- Recalculate BMesh for convex hull ---
bm_convex = bmesh.new()
bm_convex.from_mesh(obj.data)
hull_area_m2 = sum(f.calc_area() for f in bm_convex.faces)
hull_volume_m3 = bm_convex.calc_volume(signed=False)

hull_area_cm2 = round(hull_area_m2 * 10000.0, 3)
hull_volume_cm3 = round(hull_volume_m3 * 1000000.0, 3)
```

The mesh is converted to a convex hull using Blender's `convex_hull` operation. A new BMesh is then created from the resulting geometry, and its surface area and volume are calculated using the same method as the original reconstructed mesh.

This produces two sets of geometric measurements:

1.  **Original mesh:** surface area and volume calculated directly from the reconstructed nodule geometry.
2.  **Convex hull:** surface area and volume calculated from the convex hull of the reconstructed geometry.

The two measurements can therefore be compared to quantify the difference between the reconstructed surface and its convex approximation.

### 8. Summary of the Workflow

The complete workflow consists of a combination of manual preparation and automated processing. The initial photographic datasets are imported and a RealityScan project is generated automatically. Control points are then manually placed and constrained using known physical distances. These control points provide the scale and spatial reference required by the subsequent automated processing.

Once the manually prepared project is complete, the remaining processing is automated. Control point measurements are exported, reconstruction regions and masks are generated for each photographic loop, and the resulting data is combined to reconstruct the final 3D nodule model. The model is then exported and processed in Blender to calculate its surface area and volume.

This separation between manual preparation and automated processing ensures that the automated stages operate using explicitly defined control points, distances, and reconstruction parameters rather than relying on assumptions about the photographic dataset.
