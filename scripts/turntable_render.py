import sys
import os
import math
import re
import csv
import subprocess
from bpy import context
import bmesh, bpy, blf, gpu
from gpu_extras.batch import batch_for_shader
from PIL import Image, ImageDraw, ImageFont
import itertools
import platform
from mathutils import Matrix, Vector

script_dir = os.path.dirname(os.path.realpath(__file__))

def get_csv_info(csv_path, target_filename):
    """
    Reads a CSV with headers and returns the row dict for a given filename.
    Returns None if not found.
    """
    if not os.path.exists(csv_path):
        print(f"❌ CSV not found: {csv_path}")
        return None

    with open(csv_path, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Filename'] == target_filename:
                return row
    return None

# --- Parse CLI arguments ---
argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []
is_test = "--debug" in argv
is_anim = "--anim" in argv
is_first = "--first" in argv

for arg in argv:
    if arg.startswith("--sf="):
        start_frame = int(arg.split("=", 1)[1])
for arg in argv:
    if arg.startswith("--ef="):
        end_frame = int(arg.split("=", 1)[1])

# --- Setup variables ---
obj_path = next((a for a in argv if a.endswith(".obj")), None)
if not obj_path:
    print("❌ No OBJ file specified. Usage: blender scene.blend --background --python turntable_render.py -- my_model.obj [--debug]")
    sys.exit(1)


def wsl_to_win_path(path):
    m = re.match(r'^/mnt/([a-zA-Z])/(.*)', path)
    if m:
        drive = m.group(1).upper()
        rest = m.group(2).replace('/', '\\')
        return f"{drive}:\\{rest}"
    return path  # assume already Windows path if no match


obj_path_win = wsl_to_win_path(obj_path)
scene = bpy.context.scene
base_name = os.path.basename(obj_path_win)
node_name = os.path.basename(os.path.dirname(obj_path_win))

csv_path = next((a for a in argv if a.endswith(".csv")), None)

info = get_csv_info(csv_path, base_name)
volume_cm3 = float(info["Volume (cm3)"])

data_headers = list(info.keys())[1:15]
data_values =[info[h] for h in data_headers]

# data_headers.insert(0, "Nodule")
# data_values.insert(0, node_name)

blend_path = bpy.data.filepath
blend_dir = os.path.dirname(blend_path)

# Hard sync CWD to the .blend location
os.chdir(blend_dir)

# Ensure all texture paths resolve correctly
bpy.ops.file.make_paths_absolute()

# --- Import OBJ ---
is_import = 1

if is_import:
    bpy.ops.wm.obj_import(filepath=obj_path_win)

    output_path = os.path.join(os.path.dirname(obj_path_win), f"{node_name}_turntable.mp4")
    obj_name = os.path.splitext(os.path.split(obj_path_win)[-1])[0]
    bpy.context.scene.objects[obj_name].select_set(True)
obj = bpy.context.selected_objects[0]

def bbox_dims(obj, mat):
    corners = [mat @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return (
        max(xs) - min(xs),
        max(ys) - min(ys),
        max(zs) - min(zs),
    )

def orient_object(obj):
    # Clear transform randomness
    location = obj.location.copy()
    obj.matrix_world = Matrix.Identity(4)

    best_score = -1
    best_matrix = None

    axes = [
        Vector((1,0,0)),
        Vector((0,1,0)),
        Vector((0,0,1)),
    ]

    for perm in itertools.permutations(axes):
        for signs in itertools.product([-1,1], repeat=3):
            x_axis = perm[0] * signs[0]
            y_axis = perm[1] * signs[1]
            z_axis = perm[2] * signs[2]

            if abs(x_axis.dot(y_axis)) > 0.01:
                continue

            rot = Matrix((
                x_axis.to_4d(),
                y_axis.to_4d(),
                z_axis.to_4d(),
                Vector((0,0,0,1))
            )).transposed()

            dx, dy, dz = bbox_dims(obj, rot)

            # Face areas
            area_x = dy * dz
            area_y = dx * dz
            area_z = dx * dy

            # Largest face must face X
            if area_x < max(area_y, area_z):
                continue

            # Landscape: Z must NOT be the longest
            if dz >= max(dx, dy):
                continue

            score = area_x

            if score > best_score:
                best_score = score
                best_matrix = rot

    if best_matrix:
        obj.matrix_world = best_matrix
        obj.location = location
orient_object(obj)
bpy.context.scene.transform_orientation_slots[0].type = 'GLOBAL'
bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS', center='BOUNDS')
obj.location = (0, 0, 0.07)

# --- Center object and lift ---

obj_camera = bpy.data.objects["Camera"]
obj_camera.location = (-0.7,0,0.16)

volume_cm3 = float(info["Volume (cm3)"])

if ( volume_cm3 > 160 ):
    obj_camera.location = (-1,0,0.23)
    obj.location = (0, 0, 0.09)

if ( volume_cm3 < 15 ):
    obj_camera.location = (-0.33,0,0.115)

    bpy.data.objects["ruler_v1"].hide_render = True    
    bpy.data.objects["ruler_small_v1"].hide_render = False


# --- Setup animation ---
obj.rotation_mode = 'XYZ'
scene.frame_start = start_frame
scene.frame_end = end_frame

total_frames = 120

start_t = start_frame / total_frames
end_t   = end_frame / total_frames

rot_offset = math.degrees(obj.rotation_euler[2])

start_rot = 360.0 * start_t + rot_offset
end_rot   = 360.0 * end_t   + rot_offset

obj.rotation_euler[2] = math.radians(start_rot)
obj.keyframe_insert(data_path="rotation_euler", frame=scene.frame_start)
obj.rotation_euler[2] = math.radians(end_rot)
obj.keyframe_insert(data_path="rotation_euler", frame=scene.frame_end)

# Make rotation linear (no ease in/out)
if obj.animation_data and obj.animation_data.action:
    for fcurve in obj.animation_data.action.fcurves:
        for kp in fcurve.keyframe_points:
            kp.interpolation = 'LINEAR'

# --- Common render settings ---
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.eevee.use_gtao = True
scene.eevee.gtao_distance = 0.2
scene.eevee.use_fast_gi = True
scene.eevee.taa_render_samples=32
scene.eevee.use_raytracing = True

scene.render.fps=60
scene.render.resolution_x = 2560
scene.render.resolution_y = 1440
scene.render.resolution_percentage = 100

# --- Render logic ---
# Use still image output format
scene.render.image_settings.file_format = 'PNG'
frame_list = [1]
output_dir = os.path.dirname(obj_path_win)

def add_text_to_render(image_path, headers, values):
    margin=50
    line_spacing=10

    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)
    font_size = 20
    font = ImageFont.truetype("DejaVuSans.ttf", font_size)
    right_x = scene.render.resolution_x - 300
    left_x = right_x +10
    y = margin     

    for header, value in zip(headers, values):
        # Header: right-aligned
        text_width = font.getlength(header)
        draw.text(
            (right_x - text_width, y), 
            header, 
            fill=(255,255,255), 
            font=font, 
            stroke_width=1, 
            stroke_fill=(0,0,0)
        )

        # Value: left-aligned
        draw.text(
            (left_x, y), 
            value, 
            fill=(255,255,255), 
            font=font, 
            stroke_width=1, 
            stroke_fill=(0,0,0)
        )
        
        y += font_size + line_spacing
        
    img.save(image_path)


# print("CWD:", os.getcwd())
# print("BLEND:", bpy.data.filepath)


if is_test:

    # Range of numbers
    numbers = range(scene.frame_start, scene.frame_end)
    output_dir = os.path.join(os.path.dirname(obj_path_win), f"{node_name}_renders")
    os.makedirs(output_dir, exist_ok=True)

    # Get every nth number
    nth = 10
    frame_list = [n for n in numbers if n % nth == 0]
    print(f"🧪 Test mode: rendering every {nth} frames...")

if is_first:
    frame_name = f"{node_name}_render.png"
    scene.frame_set(1)
    frame_output = os.path.join(output_dir, frame_name)
    scene.render.filepath = frame_output
    bpy.ops.render.render(write_still=True)
    add_text_to_render(frame_output, data_headers, data_values)


if is_anim:
    output_dir = os.path.join(os.path.dirname(obj_path_win), f"{node_name}_renders")
    frame_path_list = []
    for f in range(scene.frame_start, scene.frame_end + 1):

        print(f"Frame: {f:04d}")
        scene.frame_set(f)
        frame_path = os.path.join(output_dir, f"{node_name}_beauty.{f:04d}.png")
        frame_path_list.append(frame_path)
        scene.render.filepath = frame_path
        bpy.ops.render.render(write_still=True)
    for frame_path in frame_path_list:
        add_text_to_render(frame_path, data_headers, data_values)

    # output_mp4 = os.path.join(os.path.dirname(obj_path_win), f"{node_name}_turntable.mp4")

    # print(f"🎥 Combining image sequence into {output_mp4}")


    # input_wsl = win_to_wsl_path(input_file)
    # output_wsl = win_to_wsl_path(output_file)

    # # Example ffmpeg command (H.265)
    # cmd = [
    #     "wsl",
    #     "ffmpeg",
    #     "-y",
    #     "-framerate", "60",
    #     "-i", os.path.join(output_dir, f"{node_name}.%%03d.png"),
    #     "-c:v", "libx265",
    #     "-preset", "medium",
    #     "-crf", "23",
    #     output_mp4
    # ]
    # print(cmd)
    # # Run ffmpeg (quietly, but you can remove -loglevel if you want details)
    # subprocess.run(cmd, check=True)

    # print("✅ Animation rendering complete!")
