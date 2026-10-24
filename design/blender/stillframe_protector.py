import bpy
import math
import os
from mathutils import Vector


ROOT = "/Volumes/ACASIS/e-ink/design"
RENDER_DIR = os.path.join(ROOT, "renders")
os.makedirs(RENDER_DIR, exist_ok=True)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def material(name, color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def box(name, size, location, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        mod = obj.modifiers.new("Soft printed edge", "BEVEL")
        mod.width = bevel
        mod.segments = 3
    obj.data.materials.append(mat)
    return obj


def polygon_plate(name, points, z, thickness, mat, bevel=0.0):
    verts = [(x, y, z - thickness / 2) for x, y in points]
    verts += [(x, y, z + thickness / 2) for x, y in points]
    n = len(points)
    faces = [tuple(range(n)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if bevel > 0:
        mod = obj.modifiers.new("Soft edge", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    obj.data.materials.append(mat)
    return obj


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


clear_scene()

# Verified manufacturer dimensions, millimetres.
SCREEN_W = 208.8
SCREEN_H = 284.7
ACTIVE_W = 202.8
ACTIVE_H = 270.4
SCREEN_T = 0.85
BOARD_W = 98.298
BOARD_H = 69.215

# Frame/mat dimensions discussed for the installation.
MAT_W = 300.0
MAT_H = 450.0
WINDOW_W = 200.0
WINDOW_H = 268.0
FRAME_RAIL = 18.0

# Actual photo layout: portrait display, broad FPC at the bottom, landscape PCB lower-left.
SCREEN_CY = 38.0
SCREEN_BOTTOM = SCREEN_CY - SCREEN_H / 2
BOARD_CX = -73.0
BOARD_CY = SCREEN_BOTTOM - 45.0

# Materials.
mat_white = material("Warm white mat", (0.92, 0.91, 0.87), roughness=0.78)
shell_white = material("Printed shell", (0.82, 0.84, 0.80), roughness=0.62)
screen_back = material("EPD rear film", (0.24, 0.26, 0.25), metallic=0.08, roughness=0.5)
board_black = material("PCB", (0.018, 0.026, 0.024), roughness=0.35)
orange = material("Flexible PCB", (0.82, 0.28, 0.025), metallic=0.05, roughness=0.38)
gold = material("Contacts", (0.75, 0.43, 0.08), metallic=0.72, roughness=0.25)
silver = material("Metal", (0.53, 0.56, 0.56), metallic=0.82, roughness=0.22)
dark = material("Components", (0.035, 0.04, 0.038), roughness=0.3)
wood = material("Light oak", (0.48, 0.24, 0.085), roughness=0.42)

# Mat board and wooden frame, viewed from the rear.
box("Mat board", (MAT_W, MAT_H, 1.8), (0, 0, -0.9), mat_white, bevel=0.6)
outer_w = MAT_W + 2 * FRAME_RAIL
outer_h = MAT_H + 2 * FRAME_RAIL
box("Frame top", (outer_w, FRAME_RAIL, 15), (0, MAT_H / 2 + FRAME_RAIL / 2, 0), wood, bevel=1.2)
box("Frame bottom", (outer_w, FRAME_RAIL, 15), (0, -MAT_H / 2 - FRAME_RAIL / 2, 0), wood, bevel=1.2)
box("Frame left", (FRAME_RAIL, MAT_H, 15), (-MAT_W / 2 - FRAME_RAIL / 2, 0, 0), wood, bevel=1.2)
box("Frame right", (FRAME_RAIL, MAT_H, 15), (MAT_W / 2 + FRAME_RAIL / 2, 0, 0), wood, bevel=1.2)

# Ultra-thin rear protector. The 12 mm flange lies against the mat; the screen area rises
# only 1.6 mm. This is intentionally stepped rather than one PCB-height slab.
flange = 12.0
box(
    "Wide contact flange",
    (SCREEN_W + 2 * flange, SCREEN_H + 2 * flange, 0.9),
    (0, SCREEN_CY, 0.5),
    shell_white,
    bevel=2.0,
)
box(
    "Ultra thin screen back",
    (SCREEN_W + 3.0, SCREEN_H + 3.0, 1.6),
    (0, SCREEN_CY, 1.45),
    shell_white,
    bevel=2.0,
)

# A hairline reveal communicates the real screen outline without creating a front bezel.
box(
    "Screen outline reveal",
    (SCREEN_W, SCREEN_H, SCREEN_T),
    (0, SCREEN_CY, 2.55),
    screen_back,
    bevel=0.7,
)

# Broad, asymmetric integrated FPC copied from the real photo: it leaves most of the
# lower screen edge, continues down on the right, and feeds the PCB at lower-left.
fpc_points = [
    (-102.0, SCREEN_BOTTOM + 1.5),
    (49.0, SCREEN_BOTTOM + 1.5),
    (49.0, SCREEN_BOTTOM - 44.0),
    (-25.0, SCREEN_BOTTOM - 44.0),
    (-25.0, SCREEN_BOTTOM - 14.0),
    (-102.0, SCREEN_BOTTOM - 14.0),
]
polygon_plate("Wide integrated display FPC", fpc_points, 3.15, 0.35, orange, bevel=0.8)

# Simple closed-bottom PCB tray, offset to the lower-left exactly as in the user's photo.
tray_margin = 3.2
box(
    "PCB closed bottom",
    (BOARD_W + 2 * tray_margin, BOARD_H + 2 * tray_margin, 1.4),
    (BOARD_CX, BOARD_CY, 1.3),
    shell_white,
    bevel=2.0,
)

# Low tray walls; their tops remain below the tallest board components.
wall_t = 1.7
wall_h = 6.0
box("PCB wall left", (wall_t, BOARD_H + 2 * tray_margin, wall_h),
    (BOARD_CX - BOARD_W / 2 - tray_margin + wall_t / 2, BOARD_CY, 4.0), shell_white, bevel=0.7)
box("PCB wall right", (wall_t, BOARD_H + 2 * tray_margin, wall_h),
    (BOARD_CX + BOARD_W / 2 + tray_margin - wall_t / 2, BOARD_CY, 4.0), shell_white, bevel=0.7)
box("PCB wall bottom", (BOARD_W + 2 * tray_margin, wall_t, wall_h),
    (BOARD_CX, BOARD_CY - BOARD_H / 2 - tray_margin + wall_t / 2, 4.0), shell_white, bevel=0.7)

# Controller PCB, landscape and lower-left, as the real photo shows it.
box("ESP32-133C02-IL PCB", (BOARD_W, BOARD_H, 1.6), (BOARD_CX, BOARD_CY, 3.0), board_black, bevel=1.0)

# Correct EPD socket location: along the PCB top edge, offset toward its left side.
connector_x = BOARD_CX - 19.0
connector_y = BOARD_CY + BOARD_H / 2 - 3.2
box("60-pin EPD socket", (55.0, 6.0, 4.2), (connector_x, connector_y, 5.6), mat_white, bevel=0.8)
box("EPD contact bar", (49.0, 1.2, 1.0), (connector_x, connector_y + 0.8, 7.8), gold, bevel=0.2)

# USB-C is on the actual board edge; leave it accessible rather than moving it.
usb_x = BOARD_CX - BOARD_W / 2 + 10.0
usb_y = BOARD_CY - 2.0
box("USB-C", (13.0, 10.0, 5.0), (usb_x, usb_y, 5.6), silver, bevel=1.4)

# Major board components, kept schematic but dimensionally subordinate to the real PCB.
box("ESP32 module", (25.0, 19.0, 3.2), (BOARD_CX + 13.0, BOARD_CY - 12.0, 5.4), silver, bevel=1.0)
box("SD slot", (28.0, 25.0, 3.2), (BOARD_CX + 2.0, BOARD_CY + 10.0, 5.3), silver, bevel=0.8)
box("Power stage", (19.0, 15.0, 3.5), (BOARD_CX - 31.0, BOARD_CY - 15.0, 5.5), dark, bevel=0.7)
for ix in range(5):
    for iy in range(3):
        x = BOARD_CX + 27.0 + ix * 4.2
        y = BOARD_CY + 20.0 - iy * 7.0
        box(f"Small component {ix}-{iy}", (2.4, 4.0, 1.5), (x, y, 4.8), gold if (ix + iy) % 3 == 0 else dark, bevel=0.25)

# Four visible mounting holes.
for sx in (-1, 1):
    for sy in (-1, 1):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=48,
            radius=3.1,
            depth=1.9,
            location=(BOARD_CX + sx * (BOARD_W / 2 - 6.5), BOARD_CY + sy * (BOARD_H / 2 - 6.5), 3.6),
        )
        bpy.context.object.data.materials.append(gold)

# Lighting and neutral studio background.
world = bpy.context.scene.world
world.color = (0.025, 0.027, 0.026)
box("Studio floor", (900, 900, 5), (0, 0, -18), material("Floor", (0.11, 0.12, 0.115), roughness=0.75), bevel=2)

for name, loc, energy, size in [
    ("Key", (-260, 260, 430), 1450, 240),
    ("Fill", (300, 100, 300), 900, 180),
    ("Rim", (0, -350, 250), 800, 160),
]:
    bpy.ops.object.light_add(type="AREA", location=loc)
    light = bpy.context.object
    light.name = name
    light.data.energy = energy
    light.data.shape = "DISK"
    light.data.size = size
    look_at(light, (0, 0, 0))

# Camera and render setup.
bpy.ops.object.camera_add(location=(330, -430, 560))
camera = bpy.context.object
look_at(camera, (-8, -5, 0))
camera.data.lens = 58
bpy.context.scene.camera = camera

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 1200
scene.render.resolution_y = 1500
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.look = "AgX - Medium High Contrast"

scene.render.filepath = os.path.join(RENDER_DIR, "stillframe-protector-rear.png")
bpy.ops.render.render(write_still=True)

# Low side angle to demonstrate that only the PCB tray has meaningful height.
camera.location = (360, -380, 125)
look_at(camera, (-15, -40, 2.0))
camera.data.lens = 62
scene.render.resolution_x = 1500
scene.render.resolution_y = 900
scene.render.filepath = os.path.join(RENDER_DIR, "stillframe-protector-thickness.png")
bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "stillframe-protector.blend"))

