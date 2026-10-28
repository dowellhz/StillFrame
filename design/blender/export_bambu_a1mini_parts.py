import bpy
import os
import math


ROOT = "/Volumes/ACASIS/e-ink/design"
OUT = os.path.join(ROOT, "bambu-a1mini-stl")
os.makedirs(OUT, exist_ok=True)

# Display drawing and enclosure envelope, millimetres.
SCREEN_W = 208.8
SCREEN_H = 284.7
FPC_EXTENSION = 29.75
FPC_TAIL_W = 29.50
FLANGE = 25.0
CAVITY_CLEARANCE = 0.8
SHELL_W = SCREEN_W + CAVITY_CLEARANCE + 2 * FLANGE
SHELL_H = SCREEN_H + FPC_EXTENSION + CAVITY_CLEARANCE + 2 * FLANGE
PANEL_W = SHELL_W / 2  # 129.8, fits 180 mm bed
PANEL_H = SHELL_H / 3  # 121.75, fits 180 mm bed
BACK_T = 1.2
RECESS_D = 1.4

# Full-thickness box-joint fingers make the six panels self-align before gluing.
JOINT_TAB_DEPTH = 8.0
JOINT_TAB_WIDTH = 18.0
JOINT_SOCKET_DEPTH = 8.3
JOINT_SOCKET_WIDTH = 18.5
VERTICAL_TAB_CENTRES = (-35.0, 0.0, 35.0)
HORIZONTAL_TAB_CENTRES = (-40.0, 0.0, 40.0)

# Global FPC slot position. It sits in the bottom-left quarter and lets the narrow
# tail pass from the display/FPC cavity to the folded controller board on the rear.
FPC_SLOT_W = 34.0
FPC_SLOT_H = 3.0
# The drawing locates the tail centre 40.24 mm from the 208.80 mm panel's left
# edge: -104.40 + 40.24 = -64.16 mm from panel centre.
FPC_SLOT_GLOBAL_X = -64.16
FPC_SLOT_GLOBAL_YS = (-138.0, -146.0, -154.0)

# Gravity supports for portrait hanging. These ribs sit immediately below the
# glass/white carrier bottom edge, keeping the panel weight off the FPC.
SCREEN_BOTTOM_Y = SHELL_H / 2 - FLANGE - CAVITY_CLEARANCE / 2 - SCREEN_H
SUPPORT_GAP = 0.4
SUPPORT_DEPTH = 4.0
SUPPORT_TOP_Y = SCREEN_BOTTOM_Y - SUPPORT_GAP
SUPPORT_CENTRE_Y = SUPPORT_TOP_Y - SUPPORT_DEPTH / 2
FPC_TAIL_LEFT_X = -SCREEN_W / 2 + 40.24 - FPC_TAIL_W / 2
LEFT_SUPPORT_MIN_X = -SCREEN_W / 2 + 1.0
LEFT_SUPPORT_MAX_X = FPC_TAIL_LEFT_X - 3.0
RIGHT_SUPPORT_MIN_X = SCREEN_W / 2 - 27.0
RIGHT_SUPPORT_MAX_X = SCREEN_W / 2 - 1.0

# Controller board, rotated 90 degrees in the installed position.
BOARD_X, BOARD_Y, BOARD_Z = 61.2, 90.1, 4.25
TRAY_MARGIN = 3.0
TRAY_X, TRAY_Y = BOARD_X + 2 * TRAY_MARGIN, BOARD_Y + 2 * TRAY_MARGIN
TRAY_BOTTOM, TRAY_WALL = 1.4, 1.7
STANDOFF_H = 2.2
TRAY_TOTAL_H = TRAY_BOTTOM + STANDOFF_H + BOARD_Z
HOLE_1 = (-BOARD_X / 2 + 4.5, -BOARD_Y / 2 + 4.3)
HOLE_2 = (BOARD_X / 2 - 4.5, BOARD_Y / 2 - 4.3)
PILOT_D, BOSS_D = 2.8, 9.0
USB_CENTRE_Y, USB_OPENING = 11.0, 16.0


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


def capsule_x(name, width, height, depth, x=0, y=0, z=None, segments=16):
    """Closed horizontal capsule prism used as a cable-safe rounded cutter."""
    if z is None:
        z = depth / 2
    radius = height / 2
    straight = width / 2 - radius
    points = []
    for i in range(segments + 1):
        angle = -math.pi / 2 + math.pi * i / segments
        points.append((x + straight + radius * math.cos(angle), y + radius * math.sin(angle)))
    for i in range(segments + 1):
        angle = math.pi / 2 + math.pi * i / segments
        points.append((x - straight + radius * math.cos(angle), y + radius * math.sin(angle)))
    n = len(points)
    bottom_z, top_z = z - depth / 2, z + depth / 2
    verts = [(px, py, bottom_z) for px, py in points] + [(px, py, top_z) for px, py in points]
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    mesh = bpy.data.meshes.new(name + " mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
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
    mod = target.modifiers.new("Cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
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


def make_panel(name, col, row, add_fpc_slot=False):
    base = box(name + " back", PANEL_W, PANEL_H, BACK_T)
    if add_fpc_slot:
        # Convert global enclosure coordinates to this panel's local coordinates.
        centre_x = -PANEL_W / 2 if col == 0 else PANEL_W / 2
        centre_y = SHELL_H / 2 - PANEL_H / 2 - row * PANEL_H
        local_x = FPC_SLOT_GLOBAL_X - centre_x
        for slot_index, global_y in enumerate(FPC_SLOT_GLOBAL_YS, start=1):
            local_y = global_y - centre_y
            cutter = capsule_x(f"FPC pass-through cutter {slot_index}", FPC_SLOT_W, FPC_SLOT_H,
                               BACK_T + 1.0, x=local_x, y=local_y, z=BACK_T / 2)
            difference(base, cutter)

    # Left-column panels carry three tabs on their right edge. Right-column
    # panels have matching, slightly oversized sockets on their left edge.
    joint_parts = []
    if col == 0:
        for index, tab_y in enumerate(VERTICAL_TAB_CENTRES, start=1):
            joint_parts.append(box(
                f"{name} right joint tab {index}",
                JOINT_TAB_DEPTH,
                JOINT_TAB_WIDTH,
                BACK_T,
                x=PANEL_W / 2 + JOINT_TAB_DEPTH / 2,
                y=tab_y,
            ))
    else:
        for index, socket_y in enumerate(VERTICAL_TAB_CENTRES, start=1):
            cutter = box(
                f"{name} left joint socket {index}",
                JOINT_SOCKET_DEPTH,
                JOINT_SOCKET_WIDTH,
                BACK_T + 1.0,
                x=-PANEL_W / 2 + JOINT_SOCKET_DEPTH / 2,
                y=socket_y,
                z=BACK_T / 2,
            )
            difference(base, cutter)

    # Each upper row carries tabs on its bottom edge; the next row receives them
    # in matching sockets along its top edge.
    if row < 2:
        for index, tab_x in enumerate(HORIZONTAL_TAB_CENTRES, start=1):
            joint_parts.append(box(
                f"{name} bottom joint tab {index}",
                JOINT_TAB_WIDTH,
                JOINT_TAB_DEPTH,
                BACK_T,
                x=tab_x,
                y=-PANEL_H / 2 - JOINT_TAB_DEPTH / 2,
            ))
    if row > 0:
        for index, socket_x in enumerate(HORIZONTAL_TAB_CENTRES, start=1):
            cutter = box(
                f"{name} top joint socket {index}",
                JOINT_SOCKET_WIDTH,
                JOINT_SOCKET_DEPTH,
                BACK_T + 1.0,
                x=socket_x,
                y=PANEL_H / 2 - JOINT_SOCKET_DEPTH / 2,
                z=BACK_T / 2,
            )
            difference(base, cutter)

    parts = [base] + joint_parts
    # A full 25 mm-wide raised flange contacts the rear of the mat. The display and
    # broad FPC sit in the central 1.4 mm recessed area. Split edges stay unraised.
    if col == 0:
        parts.append(box(name + " left bonding flange", FLANGE, PANEL_H, RECESS_D,
                         x=-PANEL_W / 2 + FLANGE / 2, z=BACK_T + RECESS_D / 2))
    else:
        parts.append(box(name + " right bonding flange", FLANGE, PANEL_H, RECESS_D,
                         x=PANEL_W / 2 - FLANGE / 2, z=BACK_T + RECESS_D / 2))
    if row == 0:
        parts.append(box(name + " top bonding flange", PANEL_W, FLANGE, RECESS_D,
                         y=PANEL_H / 2 - FLANGE / 2, z=BACK_T + RECESS_D / 2))
    if row == 2:
        parts.append(box(name + " bottom bonding flange", PANEL_W, FLANGE, RECESS_D,
                         y=-PANEL_H / 2 + FLANGE / 2, z=BACK_T + RECESS_D / 2))
        panel_centre_x = -PANEL_W / 2 if col == 0 else PANEL_W / 2
        panel_centre_y = SHELL_H / 2 - PANEL_H / 2 - row * PANEL_H
        if col == 0:
            support_min_x, support_max_x = LEFT_SUPPORT_MIN_X, LEFT_SUPPORT_MAX_X
            support_name = name + " left gravity support"
        else:
            support_min_x, support_max_x = RIGHT_SUPPORT_MIN_X, RIGHT_SUPPORT_MAX_X
            support_name = name + " right gravity support"
        parts.append(box(
            support_name,
            support_max_x - support_min_x,
            SUPPORT_DEPTH,
            RECESS_D,
            x=(support_min_x + support_max_x) / 2 - panel_centre_x,
            y=SUPPORT_CENTRE_Y - panel_centre_y,
            z=BACK_T + RECESS_D / 2,
        ))
    return join(parts, name)


panel_specs = [
    ("01-shell-top-left.stl", "Shell top left", 0, 0, False),
    ("02-shell-top-right.stl", "Shell top right", 1, 0, False),
    ("03-shell-middle-left.stl", "Shell middle left", 0, 1, False),
    ("04-shell-middle-right.stl", "Shell middle right", 1, 1, False),
    ("05-shell-bottom-left-fpc-slot.stl", "Shell bottom left with FPC slot", 0, 2, True),
    ("06-shell-bottom-right.stl", "Shell bottom right", 1, 2, False),
]

for filename, name, col, row, slot in panel_specs:
    clear_scene()
    part = make_panel(name, col, row, slot)
    export_object(part, filename)

clear_scene()

# Separate PCB tray. Bottom side is open for the folded FPC; left wall is split for USB-C.
tray_parts = [box("PCB tray bottom", TRAY_X, TRAY_Y, TRAY_BOTTOM)]
tray_parts.append(box("PCB tray right wall", TRAY_WALL, TRAY_Y, TRAY_TOTAL_H,
                      x=TRAY_X / 2 - TRAY_WALL / 2))
tray_parts.append(box("PCB tray top wall", TRAY_X, TRAY_WALL, TRAY_TOTAL_H,
                      y=TRAY_Y / 2 - TRAY_WALL / 2))
left_x = -TRAY_X / 2 + TRAY_WALL / 2
opening_low = USB_CENTRE_Y - USB_OPENING / 2
opening_high = USB_CENTRE_Y + USB_OPENING / 2
lower_len = opening_low + TRAY_Y / 2
upper_len = TRAY_Y / 2 - opening_high
tray_parts.append(box("PCB tray left lower wall", TRAY_WALL, lower_len, TRAY_TOTAL_H,
                      x=left_x, y=-TRAY_Y / 2 + lower_len / 2))
tray_parts.append(box("PCB tray left upper wall", TRAY_WALL, upper_len, TRAY_TOTAL_H,
                      x=left_x, y=opening_high + upper_len / 2))

for index, (hx, hy) in enumerate((HOLE_1, HOLE_2), start=1):
    boss = cylinder(f"Boss {index}", BOSS_D, STANDOFF_H, hx, hy,
                    z=TRAY_BOTTOM + STANDOFF_H / 2)
    cutter = cylinder(f"M3 pilot {index}", PILOT_D, TRAY_BOTTOM + STANDOFF_H + 1,
                      hx, hy, z=(TRAY_BOTTOM + STANDOFF_H) / 2)
    difference(boss, cutter)
    tray_parts.append(boss)

tray = join(tray_parts, "Stillframe PCB tray")
export_object(tray, "07-controller-board-tray.stl")

clear_scene()

# Six identical rear seam strips, arranged compactly for the accessories plate.
joiners = []
for row in range(3):
    for col in range(2):
        joiners.append(box(f"Seam joiner {row}-{col}", 70.0, 12.0, 1.2,
                           x=-38.0 + col * 76.0, y=-18.0 + row * 18.0))
joiner_group = join(joiners, "Six seam joiners")
export_object(joiner_group, "08-seam-joiners-six.stl")

clear_scene()
patch = box("Centre seam patch", 36.0, 36.0, 1.2)
export_object(patch, "09-centre-seam-patch.stl")

print("Exported A1-mini-compatible STL parts to", OUT)
for filename in sorted(os.listdir(OUT)):
    if filename.endswith(".stl"):
        print(filename, os.path.getsize(os.path.join(OUT, filename)), "bytes")
