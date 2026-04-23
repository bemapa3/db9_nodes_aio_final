bl_info = {
    "name": "Poliigon Library Importer (i8 BBBviz)",
    "author": "BBBviz / i8 Studio",
    "version": (2, 0, 0),
    "blender": (3, 0, 0),
    "location": "File > Import > Poliigon Library",
    "description": "Import Poliigon-organized textures (PBR) from the Library folder.",
    "category": "Import-Export",
}

import bpy
import os
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper


MAP_KEYS = [
    ("COL", ["Base Color", "Color"]),
    ("DIFF", ["Base Color", "Color"]),
    ("ALBEDO", ["Base Color", "Color"]),
    ("NRM", ["Normal"]),
    ("NORMAL", ["Normal"]),
    ("ROUGH", ["Roughness"]),
    ("GLOSS", ["Roughness"]),
    ("METAL", ["Metallic"]),
    ("AO", ["Ambient Occlusion"]),
    ("DISP", ["Displacement"]),
    ("HEIGHT", ["Displacement"]),
    ("OPACITY", ["Alpha"]),
    ("SSS", ["Subsurface"]),
]


def find_maps(folder):
    found = {}
    for root, _dirs, files in os.walk(folder):
        for fname in files:
            lower = fname.lower()
            if not lower.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr")):
                continue
            for key, _sockets in MAP_KEYS:
                if key.lower() in lower and key not in found:
                    found[key] = os.path.join(root, fname)
    return found


def build_material(name, maps):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    y = 400
    for key, sockets in MAP_KEYS:
        if key not in maps:
            continue
        tex = nodes.new("ShaderNodeTexImage")
        tex.location = (-400, y)
        try:
            tex.image = bpy.data.images.load(maps[key], check_existing=True)
        except Exception:
            continue
        if key in ("NRM", "NORMAL"):
            nmap = nodes.new("ShaderNodeNormalMap")
            nmap.location = (-100, y)
            links.new(tex.outputs["Color"], nmap.inputs["Color"])
            links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
            try:
                tex.image.colorspace_settings.name = "Non-Color"
            except Exception:
                pass
        elif key == "DISP" or key == "HEIGHT":
            disp = nodes.new("ShaderNodeDisplacement")
            disp.location = (-100, y)
            links.new(tex.outputs["Color"], disp.inputs["Height"])
            links.new(disp.outputs["Displacement"], out.inputs["Displacement"])
            try:
                tex.image.colorspace_settings.name = "Non-Color"
            except Exception:
                pass
        else:
            target = sockets[0]
            if target in bsdf.inputs:
                links.new(tex.outputs["Color"], bsdf.inputs[target])
            if key not in ("COL", "DIFF", "ALBEDO"):
                try:
                    tex.image.colorspace_settings.name = "Non-Color"
                except Exception:
                    pass
        y -= 220
    return mat


class IMPORT_OT_poliigon_library(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.poliigon_library"
    bl_label = "Import Poliigon Asset Folder"
    directory: StringProperty(subtype="DIR_PATH")

    def execute(self, context):
        folder = self.directory or os.path.dirname(self.filepath)
        if not folder or not os.path.isdir(folder):
            self.report({"ERROR"}, "Folder not found")
            return {"CANCELLED"}
        maps = find_maps(folder)
        if not maps:
            self.report({"WARNING"}, "No texture maps detected")
            return {"CANCELLED"}
        name = os.path.basename(folder.rstrip(os.sep)) or "Poliigon_Material"
        build_material(name, maps)
        self.report({"INFO"}, f"Created material '{name}' from {len(maps)} maps")
        return {"FINISHED"}


def menu_func(self, context):
    self.layout.operator(IMPORT_OT_poliigon_library.bl_idname, text="Poliigon Library Folder")


def register():
    bpy.utils.register_class(IMPORT_OT_poliigon_library)
    bpy.types.TOPBAR_MT_file_import.append(menu_func)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func)
    bpy.utils.unregister_class(IMPORT_OT_poliigon_library)


if __name__ == "__main__":
    register()
