import bpy
import os
import math
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

def image_material(name, image_path):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = bpy.data.images.load(image_path, check_existing=True)
    texture.interpolation = "Linear"
    shader.inputs["Roughness"].default_value = 0.48
    mat.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    mat.node_tree.links.new(texture.outputs["Alpha"], shader.inputs["Alpha"])
    mat.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return mat

def box(name, size, location, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new("Soft edge", "BEVEL")
        mod.width = bevel
        mod.segments = 3
    obj.data.materials.append(mat)
    return obj

def cylinder(name, radius, depth, location, mat, vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj

def image_plane(name, size, location, mat):
    bpy.ops.mesh.primitive_plane_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = (*size, 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return obj

def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()

clear_scene()

# Manufacturer dimensions, millimetres.
SCREEN_W, SCREEN_H, SCREEN_T = 208.8, 284.7, 1.20
# Drawing: FPC projects 29.75 +/- 0.30 mm from the panel; its fan-out is
# 40.24 +/- 0.30 mm wide. The 60-pin insertion end is 29.50 +/- 0.05 mm wide.
FANOUT_H = 29.75
FANOUT_W = 40.24
FPC_TAIL_W = 29.50
# User-supplied physical board size, replacing the earlier drawing estimate.
# Physical board envelope. It is rotated 90 degrees in the installation so the
# EPD socket faces the screen FPC and USB-C exits through the left side.
BOARD_LONG, BOARD_SHORT, BOARD_T = 90.1, 61.2, 4.25
BOARD_W, BOARD_H = BOARD_SHORT, BOARD_LONG

# Two photographs were scaled to the stated 90.1 x 61.2 mm envelope. The two large
# diagonal mounting holes are approximately 4.3/4.5 mm from their adjacent edges.
# Their estimated centre spacing is therefore about 81.5 x 52.2 mm. Slots remain
# mandatory until these centres are checked with calipers.
HOLE_EDGE_X, HOLE_EDGE_Y = 4.5, 4.3
HOLE_DIAMETER_EST = 4.1
HOLE_A = (-BOARD_W / 2 + HOLE_EDGE_X, -BOARD_H / 2 + HOLE_EDGE_Y)
HOLE_B = (BOARD_W / 2 - HOLE_EDGE_X, BOARD_H / 2 - HOLE_EDGE_Y)

SCREEN_CY = 23.0
SCREEN_BOTTOM = SCREEN_CY - SCREEN_H / 2
SCREEN_TOP = SCREEN_CY + SCREEN_H / 2
FLANGE = 12.0
SHELL_W = SCREEN_W + 2 * FLANGE
SHELL_BOTTOM = SCREEN_BOTTOM - FANOUT_H - FLANGE
SHELL_TOP = SCREEN_TOP + FLANGE
SHELL_H = SHELL_TOP - SHELL_BOTTOM
SHELL_CY = (SHELL_TOP + SHELL_BOTTOM) / 2

# Board folded 180 degrees at the narrow FPC neck and placed behind the display.
BOARD_CX, BOARD_CY, BOARD_Z = -45.0, SCREEN_BOTTOM + 42.0, 4.2

mat_white = material("Warm white mat", (0.91, 0.90, 0.86), roughness=0.82)
shell_white = material("Printed warm-white PETG", (0.77, 0.79, 0.75), roughness=0.64)
shell_edge = material("Shell edge", (0.66, 0.69, 0.65), roughness=0.67)
board_black = material("PCB", (0.014, 0.022, 0.019), roughness=0.34)
orange = material("Flexible PCB", (0.80, 0.25, 0.018), metallic=0.03, roughness=0.38)
gold = material("Gold", (0.72, 0.39, 0.06), metallic=0.72, roughness=0.24)
silver = material("Metal", (0.50, 0.53, 0.54), metallic=0.82, roughness=0.23)
dark = material("Components", (0.025, 0.032, 0.029), roughness=0.31)
blue = material("USB cable", (0.12, 0.55, 0.78), roughness=0.42)
wood = material("Light oak", (0.47, 0.25, 0.09), roughness=0.45)
board_front_photo = image_material("Mapped board front photo", os.path.join(ROOT, "assets", "esp32-board-front-crop.png"))
board_back_photo = image_material("Mapped board back photo", os.path.join(ROOT, "assets", "esp32-board-back-crop.png"))

# Mat and frame context, seen from the rear.
MAT_W, MAT_H, FRAME_RAIL = 300.0, 450.0, 18.0
box("Mat backing", (MAT_W, MAT_H, 1.8), (0, 0, -1.0), mat_white, bevel=0.5)
box("Frame left", (FRAME_RAIL, MAT_H, 13), (-MAT_W / 2 - FRAME_RAIL / 2, 0, 0), wood, bevel=1.0)
box("Frame right", (FRAME_RAIL, MAT_H, 13), (MAT_W / 2 + FRAME_RAIL / 2, 0, 0), wood, bevel=1.0)
box("Frame top", (MAT_W + 2 * FRAME_RAIL, FRAME_RAIL, 13), (0, MAT_H / 2 + FRAME_RAIL / 2, 0), wood, bevel=1.0)
box("Frame bottom", (MAT_W + 2 * FRAME_RAIL, FRAME_RAIL, 13), (0, -MAT_H / 2 - FRAME_RAIL / 2, 0), wood, bevel=1.0)

# Closed 1.2 mm back: screen and complete broad fan-out share this shallow container.
box("Main shallow closed back", (SHELL_W, SHELL_H, 1.2), (0, SHELL_CY, 0.5), shell_white, bevel=2.0)

# 1.9 mm shallow perimeter lip; the 12 mm outer flange bonds to the rear of the mat.
lip_t, lip_h = 1.4, 1.9
box("Tray lip left", (lip_t, SHELL_H, lip_h), (-SHELL_W / 2 + lip_t / 2, SHELL_CY, 1.55), shell_edge, bevel=0.6)
box("Tray lip right", (lip_t, SHELL_H, lip_h), (SHELL_W / 2 - lip_t / 2, SHELL_CY, 1.55), shell_edge, bevel=0.6)
box("Tray lip top", (SHELL_W, lip_t, lip_h), (0, SHELL_TOP - lip_t / 2, 1.55), shell_edge, bevel=0.6)
box("Tray lip bottom", (SHELL_W, lip_t, lip_h), (0, SHELL_BOTTOM + lip_t / 2, 1.55), shell_edge, bevel=0.6)

# Fine seams show an optional four-piece print which the user can glue together.
box("Vertical glue seam", (0.45, SHELL_H - 4, 0.10), (0, SHELL_CY, 1.13), shell_edge)
box("Horizontal glue seam", (SHELL_W - 4, 0.45, 0.10), (0, SHELL_CY, 1.13), shell_edge)

# Only the narrow neck comes through and folds back to the board connector.
connector_y = BOARD_CY - BOARD_H / 2 + 3.5
box("Folded narrow FPC neck", (FPC_TAIL_W, 18.0, 0.40), (BOARD_CX + 8.0, connector_y - 5.0, 2.25), orange, bevel=0.8)

# Separate PCB tray, printed independently and glued onto the main back.
tray_margin = 3.0
tray_w, tray_h = BOARD_W + 2 * tray_margin, BOARD_H + 2 * tray_margin
box("Separate PCB tray bottom", (tray_w, tray_h, 1.4), (BOARD_CX, BOARD_CY, 1.85), shell_white, bevel=2.0)

# Retaining walls; the left wall is interrupted for the USB-C plug.
wall_t, wall_h = 1.7, 5.0
box("PCB tray right wall", (wall_t, tray_h, wall_h), (BOARD_CX + tray_w / 2 - wall_t / 2, BOARD_CY, 4.1), shell_white, bevel=0.6)
box("PCB tray top wall", (tray_w, wall_t, wall_h), (BOARD_CX, BOARD_CY + tray_h / 2 - wall_t / 2, 4.1), shell_white, bevel=0.6)
USB_Y = BOARD_CY + 11.0
opening_h = 17.0
left_x = BOARD_CX - tray_w / 2 + wall_t / 2
lower_len = USB_Y - opening_h / 2 - (BOARD_CY - tray_h / 2)
upper_len = (BOARD_CY + tray_h / 2) - (USB_Y + opening_h / 2)
box("PCB tray left wall lower", (wall_t, lower_len, wall_h), (left_x, BOARD_CY - tray_h / 2 + lower_len / 2, 4.1), shell_white, bevel=0.6)
box("PCB tray left wall upper", (wall_t, upper_len, wall_h), (left_x, USB_Y + opening_h / 2 + upper_len / 2, 4.1), shell_white, bevel=0.6)

# Board remains exposed and serviceable.
board_center_z = BOARD_Z + (BOARD_T - 1.6) / 2
board_top_z = board_center_z + BOARD_T / 2
box("ESP32-133C02-IL PCB", (BOARD_W, BOARD_H, BOARD_T), (BOARD_CX, BOARD_CY, board_center_z), board_black, bevel=1.0)
# The board is folded over the connector, so its logo/back side faces outward.
back_surface = image_plane("Dimensionally mapped PCB back", (BOARD_LONG, BOARD_SHORT), (BOARD_CX, BOARD_CY, board_top_z + 0.04), board_back_photo)
back_surface.rotation_euler[2] = math.pi / 2
# Front/component texture is also embedded on the inward face of the 3D board.
front_surface = image_plane("Dimensionally mapped PCB front", (BOARD_LONG, BOARD_SHORT), (BOARD_CX, BOARD_CY, board_center_z - BOARD_T / 2 - 0.04), board_front_photo)
front_surface.rotation_euler[0] = math.pi
front_surface.rotation_euler[2] = -math.pi / 2

# USB-C, plug and cable all pass through the left wall opening.
usb_x = BOARD_CX - BOARD_W / 2 + 2.0
box("USB-C plug", (15.0, 12.0, 6.0), (BOARD_CX - BOARD_W / 2 - 6.5, USB_Y, board_top_z + 0.8), mat_white, bevel=2.0)
box("USB cable", (28.0, 5.0, 5.0), (BOARD_CX - BOARD_W / 2 - 27.5, USB_Y, board_top_z + 0.8), blue, bevel=2.2)

# Two diagonal screw bosses and M3 screw heads. Slots tolerate undocumented hole offsets.
for index, (hx, hy) in enumerate((HOLE_A, HOLE_B), start=1):
    wx, wy = BOARD_CX + hx, BOARD_CY + hy
    cylinder(f"Mounting boss {index}", 4.7, 2.5, (wx, wy, 3.0), shell_white)
    box(f"Adjustment slot {index}", (8.0, 5.0, 0.7), (wx, wy, board_top_z + 0.18), shell_edge, bevel=2.4)
    cylinder(f"M3 screw head {index}", 3.3, 1.7, (wx, wy, board_top_z + 1.0), silver)
    cylinder(f"M3 screw centre {index}", 1.25, 1.9, (wx, wy, board_top_z + 1.85), dark)

# Studio setup.
world = bpy.context.scene.world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.16, 0.17, 0.16, 1.0)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.75
box("Studio floor", (900, 900, 5), (0, 0, -18), material("Floor", (0.10, 0.11, 0.105), roughness=0.78), bevel=2)
for name, loc, energy, size in [("Key", (-250, 280, 430), 1500, 230), ("Fill", (320, 120, 300), 950, 190), ("Rim", (0, -350, 260), 800, 170)]:
    bpy.ops.object.light_add(type="AREA", location=loc)
    light = bpy.context.object
    light.name = name
    light.data.energy = energy
    light.data.shape = "DISK"
    light.data.size = size
    look_at(light, (0, 0, 0))

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.view_settings.look = "AgX - Medium High Contrast"

bpy.ops.object.camera_add(location=(310, -410, 520))
camera = bpy.context.object
look_at(camera, (-5, 0, 1.5))
camera.data.lens = 58
scene.camera = camera
scene.render.resolution_x, scene.render.resolution_y = 1200, 1500
scene.render.resolution_percentage = 100
scene.render.filepath = os.path.join(RENDER_DIR, "stillframe-protector-rear-v2.png")
bpy.ops.render.render(write_still=True)

camera.location = (165, -250, 170)
look_at(camera, (BOARD_CX - 5, BOARD_CY, 4.0))
camera.data.lens = 66
scene.render.resolution_x, scene.render.resolution_y = 1500, 1000
scene.render.filepath = os.path.join(RENDER_DIR, "stillframe-board-usb-detail.png")
bpy.ops.render.render(write_still=True)

camera.location = (280, -350, 85)
look_at(camera, (-10, -20, 2.0))
camera.data.lens = 62
scene.render.resolution_x, scene.render.resolution_y = 1500, 900
scene.render.filepath = os.path.join(RENDER_DIR, "stillframe-protector-thickness-v2.png")
bpy.ops.render.render(write_still=True)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "stillframe-protector-v2.blend"))
