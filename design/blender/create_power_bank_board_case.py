import bpy
import math
import os


ROOT = "/Volumes/ACASIS/e-ink/design"
BLEND_PATH = os.path.join(ROOT, "blender", "stillframe-power-bank-board-case.blend")
STL_PATH = os.path.join(ROOT, "bambu-x2d-stl", "06-power-bank-board-case.stl")
PREVIEW_PATH = os.path.join(ROOT, "previews", "power-bank-board-case.png")
LOG_PATH = os.path.join(ROOT, "power-bank-board-case.log")
os.makedirs(os.path.dirname(STL_PATH), exist_ok=True)
os.makedirs(os.path.dirname(PREVIEW_PATH), exist_ok=True)

# Verified device envelopes, millimetres.
POWER_W, POWER_H, POWER_T = 105.0, 70.0, 15.9
BOARD_W, BOARD_H, BOARD_T = 90.1, 61.2, 4.25

# Housing dimensions. The two U-shaped cradles face a completely open cable bay.
OUTER_W, OUTER_H = 146.0, 170.0
BASE_T = 1.6
SIDE_T = 3.0
POWER_CLEAR_X, POWER_CLEAR_Y, POWER_CLEAR_Z = 1.0, 1.0, 1.1
POWER_CAVITY_W = POWER_W + POWER_CLEAR_X
POWER_CAVITY_H = POWER_H + POWER_CLEAR_Y
POWER_CAVITY_T = POWER_T + POWER_CLEAR_Z
POWER_Y0, POWER_Y1 = 12.0, 12.0 + POWER_CAVITY_H
POWER_CENTRE_Y = (POWER_Y0 + POWER_Y1) / 2
BOARD_CENTRE_Y = -51.4
DEVICE_X = 17.0
BOARD_Y0 = BOARD_CENTRE_Y - BOARD_H / 2
BOARD_Y1 = BOARD_CENTRE_Y + BOARD_H / 2
CABLE_BAY = POWER_Y0 - BOARD_Y1
FULL_WALL_H = BASE_T + POWER_CAVITY_T + 1.5
LOW_WALL_H = BASE_T + 4.0
OVERLAP = 0.08
FPC_NOTCH_X0 = DEVICE_X + BOARD_W / 2 - 10.0
FPC_NOTCH_Y0 = BOARD_CENTRE_Y - 25.0
FPC_NOTCH_Y1 = BOARD_CENTRE_Y + 25.0


def reset():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.name != "Collection":
            bpy.data.collections.remove(collection)
    bpy.context.scene.collection.children.unlink(bpy.data.collections["Collection"])
    bpy.data.collections.remove(bpy.data.collections["Collection"])


def collection(name):
    result = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(result)
    return result


def material(name, rgba, metallic=0.0, roughness=0.45):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def move_to(obj, target):
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    target.objects.link(obj)


def rounded_box(name, size, location, radius, target, mat=None):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if radius > 0:
        bevel = obj.modifiers.new("Soft rounded edges", "BEVEL")
        bevel.width = radius
        bevel.segments = 5
        bevel.limit_method = "ANGLE"
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=bevel.name)
    if mat:
        obj.data.materials.append(mat)
    move_to(obj, target)
    return obj


def annular_boss(name, x, y, target, mat):
    outer_r, inner_r = 4.5, 1.5
    z0, z1 = BASE_T - OVERLAP, BASE_T + 2.2
    segments = 48
    verts, faces = [], []
    for z in (z0, z1):
        for radius in (outer_r, inner_r):
            for index in range(segments):
                angle = 2 * math.pi * index / segments
                verts.append((x + radius * math.cos(angle), y + radius * math.sin(angle), z))
    ob, ib, ot, it = 0, segments, 2 * segments, 3 * segments
    for i in range(segments):
        j = (i + 1) % segments
        faces += [
            (ob+i, ob+j, ot+j, ot+i),
            (ib+j, ib+i, it+i, it+j),
            (ot+i, ot+j, it+j, it+i),
            (ob+j, ob+i, ib+i, ib+j),
        ]
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    target.objects.link(obj)
    obj.data.materials.append(mat)
    return obj


def add_text(body, location, size, target, mat):
    curve = bpy.data.curves.new(body + " curve", "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.size = size
    curve.extrude = 0.03
    obj = bpy.data.objects.new(body, curve)
    obj.location = location
    obj.data.materials.append(mat)
    target.objects.link(obj)
    return obj


reset()
print_parts = collection("PRINT - housing")
guides = collection("REFERENCE - devices and cable")

shell_mat = material("Warm white PETG", (0.88, 0.87, 0.82, 1.0), roughness=0.38)
bank_mat = material("Power bank", (0.94, 0.94, 0.91, 1.0), roughness=0.28)
pcb_mat = material("Controller PCB", (0.018, 0.025, 0.022, 1.0), roughness=0.32)
gold_mat = material("PCB metal", (0.70, 0.47, 0.13, 1.0), metallic=0.65, roughness=0.28)
cable_mat = material("USB cable guide", (0.25, 0.48, 0.90, 1.0), metallic=0.0, roughness=0.4)
label_mat = material("Dimension labels", (0.08, 0.16, 0.13, 1.0), roughness=0.45)

# Rounded base split around a right-edge opening for the reverse-folded FPC.
outer_x1 = OUTER_W / 2
main_x1 = FPC_NOTCH_X0 + 1.0
rounded_box("Rounded housing main base", (main_x1 + OUTER_W/2, OUTER_H, BASE_T),
            ((main_x1 - OUTER_W/2)/2, 0, BASE_T/2), 3.0, print_parts, shell_mat)
for index, (y0, y1) in enumerate(((-OUTER_H/2, FPC_NOTCH_Y0),
                                  (FPC_NOTCH_Y1, OUTER_H/2)), start=1):
    rounded_box(f"FPC notch base return {index}",
                (outer_x1-FPC_NOTCH_X0+1.0, y1-y0, BASE_T),
                ((outer_x1+FPC_NOTCH_X0-1.0)/2, (y0+y1)/2, BASE_T/2),
                2.0, print_parts, shell_mat)

# Power-bank U cradle: bottom is open into the cable bay.
side_x = POWER_CAVITY_W / 2 + SIDE_T / 2
rounded_box("Power bank right wall", (SIDE_T, POWER_CAVITY_H + 2.0, FULL_WALL_H),
            (DEVICE_X+side_x, POWER_CENTRE_Y+1.0, FULL_WALL_H/2), 1.25, print_parts, shell_mat)
rounded_box("Power bank low cable-side guide", (SIDE_T, POWER_CAVITY_H + 2.0, LOW_WALL_H),
            (DEVICE_X-side_x, POWER_CENTRE_Y+1.0, LOW_WALL_H/2), 1.25, print_parts, shell_mat)
rounded_box("Power bank top wall", (POWER_CAVITY_W + 2 * SIDE_T, SIDE_T, FULL_WALL_H),
            (DEVICE_X, POWER_Y1 + SIDE_T / 2, FULL_WALL_H / 2), 1.25, print_parts, shell_mat)

# Two low lower stops retain the bank but leave a 58 mm cable mouth in the middle.
stop_w = (POWER_CAVITY_W - 58.0) / 2
for side, x in (("left", DEVICE_X-(58.0 + stop_w) / 2),
                ("right", DEVICE_X+(58.0 + stop_w) / 2)):
    rounded_box(f"Power bank lower stop {side}", (stop_w, 4.0, LOW_WALL_H),
                (x, POWER_Y0, LOW_WALL_H / 2), 1.2, print_parts, shell_mat)

# Board U cradle is deliberately low, keeping components, buttons and ports exposed.
board_clear_w = BOARD_W + 1.0
board_side_x = board_clear_w / 2 + SIDE_T / 2
rounded_box("Controller left guide", (SIDE_T, BOARD_H + 1.0, LOW_WALL_H),
            (DEVICE_X-board_side_x, BOARD_CENTRE_Y, LOW_WALL_H/2), 1.0, print_parts, shell_mat)
rounded_box("Controller bottom guide", (board_clear_w + 2 * SIDE_T, SIDE_T, LOW_WALL_H),
            (DEVICE_X, BOARD_Y0 - SIDE_T / 2, LOW_WALL_H / 2), 1.0, print_parts, shell_mat)

# Two diagonal mounting holes follow the photographed ESP32-133C02-IL board.
for index, (dx, dy) in enumerate(((-40.75, -26.10), (40.75, 26.10)), start=1):
    annular_boss(f"Controller screw boss {index}", DEVICE_X + dx, BOARD_CENTRE_Y + dy,
                 print_parts, shell_mat)

# Non-printing fit references.
rounded_box("POWER BANK 105 x 70 x 15.9", (POWER_W, POWER_H, POWER_T),
            (DEVICE_X, POWER_CENTRE_Y, BASE_T + 2.2 + POWER_T / 2), 5.0, guides, bank_mat)
rounded_box("CONTROLLER 90.1 x 61.2 x 4.25", (BOARD_W, BOARD_H, BOARD_T),
            (DEVICE_X, BOARD_CENTRE_Y, BASE_T + 2.2 + BOARD_T / 2), 1.2, guides, pcb_mat)
rounded_box("ESP32 module", (18.0, 25.0, 2.8),
            (DEVICE_X, BOARD_CENTRE_Y - 6.0, BASE_T + 2.2 + BOARD_T + 1.4), 0.8, guides, gold_mat)

# Right-angle USB plug proxy at the real board edge; cable curve shows usable slack.
usb_x, usb_y = DEVICE_X + 12.0, BOARD_Y1 + 2.5
rounded_box("Right-angle USB plug clearance", (18.0, 12.0, 7.0),
            (usb_x, usb_y, BASE_T + 5.5), 2.0, guides, cable_mat)
curve_data = bpy.data.curves.new("USB cable clearance curve", "CURVE")
curve_data.dimensions = "3D"
curve_data.bevel_depth = 2.4
curve_data.bevel_resolution = 5
spline = curve_data.splines.new("BEZIER")
spline.bezier_points.add(3)
points = [
    (DEVICE_X-POWER_CAVITY_W/2-4.0, POWER_CENTRE_Y, BASE_T + 8.0),
    (-54.0, 4.0, BASE_T + 7.0),
    (DEVICE_X-8.0, -5.0, BASE_T + 7.0),
    (usb_x, usb_y, BASE_T + 7.0),
]
for point, coordinate in zip(spline.bezier_points, points):
    point.co = coordinate
    point.handle_left_type = "AUTO"
    point.handle_right_type = "AUTO"
cable = bpy.data.objects.new("USB cable path - reference only", curve_data)
cable.data.materials.append(cable_mat)
guides.objects.link(cable)

add_text(f"OPEN CABLE BAY  {CABLE_BAY:.1f} mm", (0, -5.5, BASE_T + 0.2), 4.0, guides, label_mat)
add_text("OPEN FPC REVERSE-FOLD NOTCH", (DEVICE_X+14.0, BOARD_CENTRE_Y, BASE_T+0.2),
         2.8, guides, label_mat)

# Export only printable housing objects.
bpy.ops.object.select_all(action="DESELECT")
for obj in print_parts.objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = print_parts.objects[0]
bpy.ops.wm.stl_export(filepath=STL_PATH, export_selected_objects=True,
                      apply_modifiers=True, ascii_format=False, global_scale=1.0)

# Save the editable Blender scene before rendering.
bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)

# Camera and lighting for a clear assembly preview.
bpy.ops.object.camera_add(location=(150, -205, 205))
camera = bpy.context.object
camera.name = "Preview camera"
camera.data.lens = 58
bpy.context.scene.camera = camera

def point_camera(obj, target=(0, 0, 3)):
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

import mathutils
point_camera(camera)
bpy.ops.object.light_add(type="AREA", location=(-80, -60, 210))
bpy.context.object.data.energy = 1150
bpy.context.object.data.shape = "DISK"
bpy.context.object.data.size = 120
bpy.ops.object.light_add(type="AREA", location=(120, 90, 120))
bpy.context.object.data.energy = 850
bpy.context.object.data.size = 100
point_camera(bpy.context.object, (0, 15, 0))

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 900
scene.render.resolution_y = 1100
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = PREVIEW_PATH
scene.world.color = (0.035, 0.035, 0.035)
bpy.ops.render.render(write_still=True)

with open(LOG_PATH, "w", encoding="utf-8") as log:
    log.write("OK\n")
    log.write(f"outer={OUTER_W}x{OUTER_H} mm\n")
    log.write(f"power_cavity={POWER_CAVITY_W}x{POWER_CAVITY_H}x{POWER_CAVITY_T} mm\n")
    log.write(f"board={BOARD_W}x{BOARD_H}x{BOARD_T} mm\n")
    log.write(f"cable_bay={CABLE_BAY:.2f} mm\n")
    log.write(BLEND_PATH + "\n" + STL_PATH + "\n" + PREVIEW_PATH + "\n")

print("STILLFRAME_POWER_BOARD_CASE_DONE")
