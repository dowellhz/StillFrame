#!/usr/bin/env python3
"""Update validated X2D 3MF templates with the final STL meshes."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET
import json
import re
import struct


ROOT = Path("/Volumes/ACASIS/e-ink")
STL = ROOT / "design/bambu-x2d-stl"
OUT = ROOT / "design/bambu-x2d-3mf"
TEMPLATES = Path("/private/tmp/stillframe-x2d-3mf-old.i0aAiJ")


def stl_mesh(path, offset):
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    vertices, indices, triangles = [], {}, []
    for triangle_index in range(count):
        raw = struct.unpack_from("<9f", data, 84 + triangle_index * 50 + 12)
        triangle = []
        for start in range(0, 9, 3):
            vertex = tuple(raw[start + axis] + offset[axis] for axis in range(3))
            key = tuple(round(value, 6) for value in vertex)
            if key not in indices:
                indices[key] = len(vertices)
                vertices.append(vertex)
            triangle.append(indices[key])
        triangles.append(tuple(triangle))
    vertex_xml = "\n".join(
        f'     <vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>'
        for x, y, z in vertices
    )
    triangle_xml = "\n".join(
        f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>'
        for a, b, c in triangles
    )
    return vertex_xml, triangle_xml, len(triangles)


def replace_mesh(xml, vertex_xml, triangle_xml):
    xml = re.sub(r"(?s)(<vertices>).*?(</vertices>)", rf"\1\n{vertex_xml}\n    \2", xml)
    return re.sub(r"(?s)(<triangles>).*?(</triangles>)", rf"\1\n{triangle_xml}\n    \2", xml)


def rewrite_single(template_name, output_name, stl_name, offset, display_name,
                   component_transform=None, settings_y=0.0, settings_z=0.0):
    template = TEMPLATES / template_name
    vertex_xml, triangle_xml, face_count = stl_mesh(STL / stl_name, offset)
    replacements = {}
    with ZipFile(template) as source:
        object_xml = source.read("3D/Objects/object_1.model").decode()
        replacements["3D/Objects/object_1.model"] = replace_mesh(
            object_xml, vertex_xml, triangle_xml
        ).encode()

        settings = source.read("Metadata/model_settings.config").decode()
        old_name = re.search(r'<metadata key="name" value="([^"]+)"/>', settings).group(1)
        settings = settings.replace(old_name, display_name)
        settings = re.sub(r'face_count="\d+"', f'face_count="{face_count}"', settings)
        settings = re.sub(r'<mesh_stat face_count="\d+"', f'<mesh_stat face_count="{face_count}"', settings)
        settings = re.sub(r'<metadata key="source_file" value="[^"]+"/>',
                          f'<metadata key="source_file" value="{display_name}"/>', settings)
        if component_transform:
            settings = re.sub(
                r'<metadata key="matrix" value="[^"]+"/>',
                f'<metadata key="matrix" value="1 0 0 0 0 1 0 {settings_y:g} 0 0 1 {settings_z:g} 0 0 0 1"/>',
                settings,
            )
            settings = re.sub(r'(<metadata key="source_offset_y" value=")[^"]+("/>)', r'\g<1>0\2', settings)
            settings = re.sub(
                r'(<metadata key="source_offset_z" value=")[^"]+("/>)',
                rf'\g<1>{settings_z:g}\2', settings
            )
        replacements["Metadata/model_settings.config"] = settings.encode()

        project = json.loads(source.read("Metadata/project_settings.config"))
        project["wall_loops"] = "3"
        project["bottom_shell_layers"] = "6"
        replacements["Metadata/project_settings.config"] = json.dumps(
            project, ensure_ascii=False, separators=(",", ":")
        ).encode()

        if component_transform:
            main = source.read("3D/3dmodel.model").decode()
            main = re.sub(r'(<component [^>]* transform=")[^"]+("/>)',
                          rf'\g<1>{component_transform}\2', main, count=1)
            replacements["3D/3dmodel.model"] = main.encode()

        with ZipFile(OUT / output_name, "w", ZIP_DEFLATED) as target:
            for item in source.infolist():
                target.writestr(item, replacements.get(item.filename, source.read(item.filename)))


rewrite_single(
    "plate-01-shell-top.3mf", "plate-01-shell-top.3mf", "01-shell-top.stl",
    (0.0, 4.0, -1.3), "01-shell-top.stl",
    "1 0 0 0 1 0 0 0 1 0 -4 1.3", settings_y=-4.0, settings_z=1.3
)
rewrite_single(
    "plate-02-shell-bottom-fpc-slots.3mf", "plate-02-shell-bottom-fpc-slots.3mf",
    "02-shell-bottom-fpc-slots.stl", (0.0, 0.0, -1.3),
    "02-shell-bottom-fpc-slots.stl"
)
rewrite_single(
    "plate-01-shell-top.3mf", "plate-03-controller-case-and-lid.3mf",
    "08-controller-case-and-lid.stl", (0.0, 0.0, -4.675),
    "08-controller-case-and-lid.stl",
    "1 0 0 0 1 0 0 0 1 0 0 4.675", settings_z=4.675
)
print("Updated three X2D 3MF plates; plate 3 contains only controller case and snap lid")
