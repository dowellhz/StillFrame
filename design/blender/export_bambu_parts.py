import bpy
import os


ROOT = "/Volumes/ACASIS/e-ink/design"
OUT = os.path.join(ROOT, "bambu-stl")
os.makedirs(OUT, exist_ok=True)

# All dimensions are millimetres. Blender exports with global_scale=1.0; Bambu Studio
# interprets STL coordinates as millimetres.
SCREEN_W = 208.8
SCREEN_H = 284.7
FPC_EXTENSION = 29.75
FLANGE = 12.0
SHELL_W = SCREEN_W + 2 * FLANGE          # 232.8
SHELL_H = SCREEN_H + FPC_EXTENSION + 2 * FLANGE  # 338.45
HALF_H = SHELL_H / 2

BACK_T = 1.2
LIP_T = 1.4
LIP_H = 1.9

# Board is rotated 90 degrees after folding behind the screen.
BOARD_X = 61.2
BOARD_Y = 90.1
BOARD_Z = 4.25
BOARD_CLEARANCE = 0.6
TRAY_MARGIN = 3.0
TRAY_X = BOARD_X + 2 * TRAY_MARGIN
TRAY_Y = BOARD_Y + 2 * TRAY_MARGIN
TRAY_BOTTOM = 1.4
TRAY_WALL = 1.7
STANDOFF_H = 2.2
TRAY_TOTAL_H = TRAY_BOTTOM + STANDOFF_H + BOARD_Z

# Estimated from the supplied front/back photos. Keep adjustable until measured.
HOLE_1 = (-BOARD_X / 2 + 4.5, -BOARD_Y / 2 + 4.3)
HOLE_2 = (BOARD_X / 2 - 4.5, BOARD_Y / 2 - 4.3)
PILOT_D = 2.8
BOSS_D = 9.0
USB_CENTRE_Y = 11.0
USB_OPENING = 16.0


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def box(name, sx, sy, sz, x=0, y=0, z=None):
    if z is None:
        z = sz / 2
    bpy.ops.mesh.primitive_cube_add(location=(x, y, z))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = (sx, sy, sz)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def cylinder(name, diameter, height, x, y, z=None, vertices=64):
    if z is None:
        z = height / 2
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=diameter / 2, depth=height, location=(x, y, z))
    obj = bpy.context.object
    obj.name = name
    return obj


def join(objects, name):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    objects[0].name = name
    return objects[0]


def difference(target, cutter):
    modifier = target.modifiers.new("Cut", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def export_object(obj, filename):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(
        filepath=os.path.join(OUT, filename),
        export_selected_objects=True,
        apply_modifiers=True,
        ascii_format=False,
        global_scale=1.0,
    )


def shell_half(name, top_half):
    # Flat closed back plus only the three external perimeter walls. The joining edge
    # remains wall-free so the two halves meet without trapping the display.
    parts = [box(name + " back", SHELL_W, HALF_H, BACK_T)]
    parts.append(box(name + " left lip", LIP_T, HALF_H, LIP_H,
                     x=-SHELL_W / 2 + LIP_T / 2, z=BACK_T + LIP_H / 2))
    parts.append(box(name + " right lip", LIP_T, HALF_H, LIP_H,
                     x=SHELL_W / 2 - LIP_T / 2, z=BACK_T + LIP_H / 2))
    outer_y = HALF_H / 2 - LIP_T / 2 if top_half else -HALF_H / 2 + LIP_T / 2
    parts.append(box(name + " outer lip", SHELL_W, LIP_T, LIP_H,
                     y=outer_y, z=BACK_T + LIP_H / 2))
    return join(parts, name)


clear_scene()

upper = shell_half("Stillframe upper shell", True)
export_object(upper, "01-main-shell-upper.stl")

clear_scene()
lower = shell_half("Stillframe lower shell", False)
export_object(lower, "02-main-shell-lower.stl")

clear_scene()

# Separate controller tray. Bottom edge stays open for the folded display FPC.
tray_parts = [box("PCB tray bottom", TRAY_X, TRAY_Y, TRAY_BOTTOM)]
tray_parts.append(box("PCB tray right wall", TRAY_WALL, TRAY_Y, TRAY_TOTAL_H,
                      x=TRAY_X / 2 - TRAY_WALL / 2))
tray_parts.append(box("PCB tray top wall", TRAY_X, TRAY_WALL, TRAY_TOTAL_H,
                      y=TRAY_Y / 2 - TRAY_WALL / 2))

# Left wall is split around the USB-C plug opening.
left_x = -TRAY_X / 2 + TRAY_WALL / 2
lower_edge = -TRAY_Y / 2
upper_edge = TRAY_Y / 2
opening_low = USB_CENTRE_Y - USB_OPENING / 2
opening_high = USB_CENTRE_Y + USB_OPENING / 2
lower_length = opening_low - lower_edge
upper_length = upper_edge - opening_high
tray_parts.append(box("PCB tray left lower wall", TRAY_WALL, lower_length, TRAY_TOTAL_H,
                      x=left_x, y=lower_edge + lower_length / 2))
tray_parts.append(box("PCB tray left upper wall", TRAY_WALL, upper_length, TRAY_TOTAL_H,
                      x=left_x, y=opening_high + upper_length / 2))

# Two screw bosses. Pilot holes are suitable for M3 self-tapping screws in PETG/PLA.
for index, (hx, hy) in enumerate((HOLE_1, HOLE_2), start=1):
    boss = cylinder(f"Boss {index}", BOSS_D, STANDOFF_H, hx, hy,
                    z=TRAY_BOTTOM + STANDOFF_H / 2)
    cutter = cylinder(f"M3 pilot {index}", PILOT_D, TRAY_BOTTOM + STANDOFF_H + 1.0,
                      hx, hy, z=(TRAY_BOTTOM + STANDOFF_H) / 2)
    difference(boss, cutter)
    tray_parts.append(boss)

tray = join(tray_parts, "Stillframe PCB tray")
export_object(tray, "03-controller-board-tray.stl")

clear_scene()

# Glue these across the rear seam after the display is seated. They avoid adding a
# thick interlocking joint around the fragile glass panel.
joiner_a = box("Seam joiner A", 70.0, 14.0, 1.2, x=-42.0)
joiner_b = box("Seam joiner B", 70.0, 14.0, 1.2, x=42.0)
joiners = join([joiner_a, joiner_b], "Stillframe seam joiners")
export_object(joiners, "04-seam-joiners-two.stl")

print("Exported Bambu-compatible STL parts to", OUT)
for filename in sorted(os.listdir(OUT)):
    if filename.endswith(".stl"):
        print(filename, os.path.getsize(os.path.join(OUT, filename)), "bytes")
