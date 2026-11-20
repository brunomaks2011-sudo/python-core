"""
rbxlib - Blender -> Roblox modelling pipeline for BLUE vs RED.

Models are built in Blender (metres, Z up, the model's FRONT faces +Y) out of
primitives that map 1:1 onto native Roblox parts:

    block  -> Part (Block)          wedge -> WedgePart
    cyl    -> Part (Cylinder)       ball  -> Part (Ball)

Each model is saved as an editable .blend file and exported as:
    * <name>.model.json  - Rojo JSON model of native Roblox parts (no upload needed)
    * <name>.fbx         - mesh version for optional import with Studio's 3D Importer
    * previews/<name>.png - Cycles preview render

Coordinate mapping (Blender metres -> Roblox studs, 3 studs = 1 m):
    roblox = P * blender * S, P maps (x, y, z) -> (x, z, -y)
so Blender +Y (model front) becomes Roblox -Z (LookVector) and Blender +Z is up.

Groups ("Turret", "Turret/Gun", "WheelL1", ...) become nested Roblox Models with
an invisible "Pivot" part at the group origin. At runtime every part is welded to
its group's Pivot and groups are joined to their parent with Motor6Ds, so
turrets, guns, wheels, rotors and doors can be animated.
"""
import json
import math
import os

import bpy  # noqa: I001  (bpy must be imported before bmesh/mathutils when used as a module)
import bmesh
from mathutils import Euler, Matrix, Vector

S = 3.0  # studs per metre
P = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))  # blender vector -> roblox vector

# Roblox material -> (roughness, metallic, extra) for Blender previews / FBX
MATERIALS = {
    "Plastic": (0.55, 0.0), "SmoothPlastic": (0.35, 0.0), "Metal": (0.42, 0.55), "DiamondPlate": (0.38, 0.75),
    "CorrodedMetal": (0.8, 0.45), "Foil": (0.25, 0.9), "Rubber": (0.92, 0.0), "Fabric": (0.95, 0.0), "Leather": (0.7, 0.0),
    "Glass": (0.04, 0.0), "Neon": (0.5, 0.0), "Wood": (0.7, 0.0), "WoodPlanks": (0.75, 0.0), "Concrete": (0.9, 0.0),
    "Brick": (0.85, 0.0), "Plaster": (0.92, 0.0), "ClayRoofTiles": (0.75, 0.0), "RoofShingles": (0.85, 0.0),
    "Slate": (0.8, 0.0), "Cobblestone": (0.85, 0.0), "Granite": (0.7, 0.0), "Marble": (0.3, 0.0), "Pebble": (0.85, 0.0),
    "Sand": (0.95, 0.0), "Grass": (0.95, 0.0), "LeafyGrass": (0.95, 0.0), "Ground": (0.95, 0.0), "Rock": (0.9, 0.0),
    "Asphalt": (0.9, 0.0), "Pavement": (0.9, 0.0), "Cardboard": (0.9, 0.0), "CeramicTiles": (0.3, 0.0), "Ice": (0.1, 0.0),
    "Salt": (0.8, 0.0), "Basalt": (0.85, 0.0), "Limestone": (0.85, 0.0), "Sandstone": (0.85, 0.0), "Mud": (0.9, 0.0),
}

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BLEND_DIR = os.path.join(ROOT, "BlenderProjects")
ASSET_DIR = os.path.join(ROOT, "Assets", "Models")
MESH_DIR = os.path.join(ROOT, "Assets", "Meshes")


def rgb(r, g, b):
    """0-255 sRGB -> 0-1 floats"""
    return (r / 255.0, g / 255.0, b / 255.0)


def srgb_to_linear(c):
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


class Model:
    def __init__(self, name, category, kind="", attributes=None):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.name = name
        self.category = category  # e.g. "Vehicles/Tanks"
        self.kind = kind
        self.attributes = dict(attributes or {})
        self.parts = []
        self.groups = {"": None}
        self.group_origin = {"": Vector((0, 0, 0))}
        self.group_parent = {}
        self.attachments = []
        self.lights = []
        self._mats = {}
        self._counter = 0
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
        self.coll = coll

    # ------------------------------------------------------------------ groups
    def group(self, path, origin=(0, 0, 0)):
        if path in self.groups:
            return self.groups[path]
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent not in self.groups:
            raise ValueError(f"parent group {parent!r} must be created before {path!r}")
        empty = bpy.data.objects.new("G_" + path.replace("/", "_"), None)
        empty.empty_display_type = "ARROWS"
        empty.empty_display_size = 0.5
        empty.location = Vector(origin)
        self.coll.objects.link(empty)
        self.groups[path] = empty
        self.group_origin[path] = Vector(origin)
        self.group_parent[path] = parent
        return empty

    # --------------------------------------------------------------- materials
    def _material(self, rbx_mat, color):
        key = (rbx_mat, tuple(round(c, 3) for c in color))
        if key in self._mats:
            return self._mats[key]
        mat = bpy.data.materials.new(f"{rbx_mat}_{len(self._mats)}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        rough, metal = MATERIALS.get(rbx_mat, (0.6, 0.0))
        lin = srgb_to_linear(color)
        bsdf.inputs["Base Color"].default_value = (*lin, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        if rbx_mat == "Neon":
            bsdf.inputs["Emission Color"].default_value = (*lin, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 6.0
        if rbx_mat == "Glass":
            bsdf.inputs["Transmission Weight"].default_value = 0.85
            bsdf.inputs["Roughness"].default_value = 0.05
        mat["roblox_material"] = rbx_mat
        self._mats[key] = mat
        return mat

    # -------------------------------------------------------------- primitives
    def _new_obj(self, name, bm):
        self._counter += 1
        mesh = bpy.data.meshes.new(f"{name}_{self._counter}")
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(name, mesh)
        self.coll.objects.link(obj)
        return obj

    def _place(self, obj, at, rot, group):
        obj.location = Vector(at)
        obj.rotation_mode = "XYZ"
        obj.rotation_euler = Euler(tuple(math.radians(a) for a in rot), "XYZ")
        if group not in self.groups:
            raise ValueError(f"unknown group {group!r} in {self.name}")

    def _record(self, obj, cls, shape, size_bl, mat, color, group, transparency=0.0, reflectance=0.0, extra=None):
        obj.data.materials.append(self._material(mat, color))
        if transparency >= 0.99:
            obj.hide_render = True
        elif transparency > 0:
            obj.color = (1, 1, 1, 1 - transparency)
        rec = {
            "obj": obj, "class": cls, "shape": shape, "size_bl": Vector(size_bl), "material": mat, "color": color,
            "group": group, "transparency": transparency, "reflectance": reflectance, "extra": extra or {},
        }
        self.parts.append(rec)
        return rec

    def block(self, name, size, at, rot=(0, 0, 0), mat="Metal", color=(0.5, 0.5, 0.5), group="", transparency=0.0, **extra):
        sx, sy, sz = size
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=Vector((sx, sy, sz)), verts=bm.verts)
        obj = self._new_obj(name, bm)
        self._place(obj, at, rot, group)
        return self._record(obj, "Part", "Block", (sx, sy, sz), mat, color, group, transparency, extra=extra)

    def wedge(self, name, size, at, rot=(0, 0, 0), mat="Metal", color=(0.5, 0.5, 0.5), group="", transparency=0.0, **extra):
        """Roblox WedgePart. size=(x width, y depth, z height) in Blender local axes.
        The vertical face is at local -Y and the slope descends toward local +Y
        (Roblox: back face +Z vertical, slope faces the front -Z)."""
        sx, sy, sz = size
        hx, hy, hz = sx / 2, sy / 2, sz / 2
        bm = bmesh.new()
        v = [bm.verts.new(p) for p in [
            (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),  # bottom
            (-hx, -hy, hz), (hx, -hy, hz),  # top back edge
        ]]
        bm.faces.new((v[0], v[3], v[2], v[1]))  # bottom
        bm.faces.new((v[0], v[1], v[5], v[4]))  # back (vertical)
        bm.faces.new((v[3], v[4], v[5], v[2]))  # slope
        bm.faces.new((v[0], v[4], v[3]))  # left
        bm.faces.new((v[1], v[2], v[5]))  # right
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        obj = self._new_obj(name, bm)
        self._place(obj, at, rot, group)
        return self._record(obj, "WedgePart", "Wedge", (sx, sy, sz), mat, color, group, transparency, extra=extra)

    def cyl(self, name, length, diameter, at, rot=(0, 0, 0), mat="Metal", color=(0.5, 0.5, 0.5), group="", segments=20, transparency=0.0, **extra):
        """Roblox cylinder part: axis along local X (Blender local X as well)."""
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=diameter / 2, radius2=diameter / 2, depth=length)
        # create_cone builds along Z; rotate so the axis is X
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(90), 3, "Y"))
        obj = self._new_obj(name, bm)
        self._place(obj, at, rot, group)
        for f in obj.data.polygons:
            f.use_smooth = True
        return self._record(obj, "Part", "Cylinder", (length, diameter, diameter), mat, color, group, transparency, extra=extra)

    def ball(self, name, diameter, at, mat="Metal", color=(0.5, 0.5, 0.5), group="", transparency=0.0, **extra):
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=diameter / 2)
        obj = self._new_obj(name, bm)
        self._place(obj, at, (0, 0, 0), group)
        for f in obj.data.polygons:
            f.use_smooth = True
        return self._record(obj, "Part", "Ball", (diameter, diameter, diameter), mat, color, group, transparency, extra=extra)

    def seat(self, name, at, rot=(0, 0, 0), group=""):
        """Invisible Roblox Seat (the character faces the model front)."""
        rec = self.block(name, (0.6, 0.6, 0.25), at, rot, "SmoothPlastic", (0.2, 0.2, 0.2), group, transparency=1.0)
        rec["class"] = "Seat"
        rec["obj"].display_type = "WIRE"
        return rec

    def hitbox(self, name, size, at, rot=(0, 0, 0), group=""):
        """Invisible collision box used for physics (visual parts do not collide)."""
        rec = self.block(name, size, at, rot, "SmoothPlastic", (1, 0, 1), group, transparency=1.0)
        rec["extra"]["hitbox"] = True
        rec["obj"].display_type = "WIRE"
        return rec

    def attach(self, name, at, rot=(0, 0, 0), group=""):
        empty = bpy.data.objects.new("A_" + name, None)
        empty.empty_display_type = "SINGLE_ARROW"
        empty.empty_display_size = 0.3
        empty.location = Vector(at)
        empty.rotation_euler = Euler(tuple(math.radians(a) for a in rot), "XYZ")
        self.coll.objects.link(empty)
        self.attachments.append({"name": name, "obj": empty, "group": group})
        return empty

    def light(self, name, at, rot=(0, 0, 0), group="", kind="SpotLight", color=(1, 0.95, 0.85), brightness=2, range_=60, angle=50):
        """Exported as an Attachment + light (disabled until the vehicle turns lights on)."""
        emp = self.attach(name, at, rot, group)
        self.attachments[-1]["light"] = {"kind": kind, "color": color, "brightness": brightness, "range": range_, "angle": angle}
        return emp

    # ------------------------------------------------------------- mirroring
    def sym(self, fn, name, *args, at, **kw):
        """Create a primitive on +X and its mirror on -X. Names get L/R suffix."""
        x, y, z = at
        rot = kw.pop("rot", (0, 0, 0))
        a = fn(name + "R", *args, at=(abs(x), y, z), rot=rot, **kw)
        b = fn(name + "L", *args, at=(-abs(x), y, z), rot=(rot[0], -rot[1], -rot[2]), **kw)
        return a, b

    # ------------------------------------------------------------------ export
    @staticmethod
    def _rbx_cframe(world_matrix):
        loc = world_matrix.to_translation()
        rot = world_matrix.to_3x3().normalized()
        r = P @ rot @ P.transposed()
        pos = P @ loc * S
        return pos, r

    @staticmethod
    def _cf_json(pos, r):
        return {"CFrame": {"position": [round(pos.x, 4), round(pos.y, 4), round(pos.z, 4)],
                           "orientation": [[round(r[i][j], 6) for j in range(3)] for i in range(3)]}}

    def _part_json(self, rec):
        obj = rec["obj"]
        pos, r = self._rbx_cframe(obj.matrix_world)
        sx, sy, sz = rec["size_bl"]
        if rec["shape"] == "Ball":
            size = [sx * S] * 3
        else:
            size = [sx * S, sz * S, sy * S]
        size = [round(max(0.05, v), 4) for v in size]
        props = {
            "Size": size,
            "CFrame": self._cf_json(pos, r),
            "Color": [round(c, 4) for c in rec["color"]],
            "Material": rec["material"],
            "Anchored": False,
            "CanCollide": bool(rec["extra"].get("hitbox", False) or rec["extra"].get("collide", False)),
            "CanTouch": False,
            "Massless": not rec["extra"].get("hitbox", False),
            "TopSurface": "Smooth",
            "BottomSurface": "Smooth",
            "CastShadow": rec["transparency"] < 0.9 and not rec["extra"].get("noshadow", False),
        }
        if rec["transparency"]:
            props["Transparency"] = rec["transparency"]
        if rec["class"] == "Part":
            props["Shape"] = rec["shape"]
        if rec["class"] == "Seat":
            props["Disabled"] = True
            props["Anchored"] = False
            props["CanCollide"] = False
            props["Massless"] = True
            props["CastShadow"] = False
        attrs = {}
        for k, v in rec["extra"].items():
            if k in ("collide", "noshadow"):
                continue
            if isinstance(v, bool):
                attrs[k] = {"Bool": v}
            elif isinstance(v, (int, float)):
                attrs[k] = {"Float64": float(v)}
            elif isinstance(v, str):
                attrs[k] = {"String": v}
        if attrs:
            props["Attributes"] = {"Attributes": attrs}
        return {"Name": obj.name.split(".")[0], "ClassName": rec["class"], "Properties": props}

    def _pivot_json(self, path):
        o = self.group_origin[path]
        pos = P @ o * S
        return {
            "Name": "Pivot", "ClassName": "Part",
            "Properties": {
                "Size": [0.4, 0.4, 0.4], "CFrame": self._cf_json(pos, Matrix.Identity(3)), "Transparency": 1.0,
                "Anchored": False, "CanCollide": False, "CanTouch": False, "CanQuery": False, "Massless": True,
                "CastShadow": False, "TopSurface": "Smooth", "BottomSurface": "Smooth",
            },
            "Children": [],
        }

    def _attachment_json(self, a, pivot_pos):
        pos, r = self._rbx_cframe(a["obj"].matrix_world)
        rel = pos - pivot_pos
        node = {"Name": a["name"], "ClassName": "Attachment", "Properties": {"CFrame": self._cf_json(rel, r)}}
        if "light" in a:
            L = a["light"]
            lp = {"Enabled": False, "Brightness": L["brightness"], "Range": L["range"], "Color": list(L["color"]), "Shadows": False}
            if L["kind"] == "SpotLight":
                lp["Angle"] = L["angle"]
                lp["Face"] = "Front"
            node["Children"] = [{"Name": "Light", "ClassName": L["kind"], "Properties": lp}]
        return node

    def to_json(self):
        bpy.context.view_layer.update()
        # build group tree
        nodes = {}
        for path in self.groups:
            name = self.name if path == "" else path.rsplit("/", 1)[-1]
            node = {"Name": name, "ClassName": "Model", "Children": []}
            pivot = self._pivot_json(path)
            node["Children"].append(pivot)
            nodes[path] = (node, pivot)
        for rec in self.parts:
            nodes[rec["group"]][0]["Children"].append(self._part_json(rec))
        for a in self.attachments:
            node, pivot = nodes[a["group"]]
            pivot_pos = P @ self.group_origin[a["group"]] * S
            pivot["Children"].append(self._attachment_json(a, pivot_pos))
        for path in self.groups:
            if path == "":
                continue
            parent = self.group_parent[path]
            nodes[parent][0]["Children"].append(nodes[path][0])
        root = nodes[""][0]
        attrs = {"Category": {"String": self.category}, "Kind": {"String": self.kind}, "PartCount": {"Float64": float(len(self.parts))}}
        for k, v in self.attributes.items():
            if isinstance(v, bool):
                attrs[k] = {"Bool": v}
            elif isinstance(v, (int, float)):
                attrs[k] = {"Float64": float(v)}
            else:
                attrs[k] = {"String": str(v)}
        root["Properties"] = {"Attributes": {"Attributes": attrs}}
        return root

    def bounds(self):
        bpy.context.view_layer.update()
        mn = Vector((1e9, 1e9, 1e9))
        mx = Vector((-1e9, -1e9, -1e9))
        for rec in self.parts:
            if rec["transparency"] >= 1.0:
                continue
            for c in rec["obj"].bound_box:
                w = rec["obj"].matrix_world @ Vector(c)
                mn = Vector(map(min, mn, w))
                mx = Vector(map(max, mx, w))
        return mn, mx

    def save(self, preview=False, fbx=True):
        cat_dir = self.category.split("/")[0]
        blend_dir = os.path.join(BLEND_DIR, cat_dir)
        os.makedirs(blend_dir, exist_ok=True)
        out_dir = os.path.join(ASSET_DIR, self.category)
        os.makedirs(out_dir, exist_ok=True)
        data = self.to_json()
        with open(os.path.join(out_dir, self.name + ".model.json"), "w") as f:
            json.dump(data, f, separators=(",", ":"))
        if fbx:
            mesh_dir = os.path.join(MESH_DIR, self.category)
            os.makedirs(mesh_dir, exist_ok=True)
            self._export_fbx(os.path.join(mesh_dir, self.name + ".fbx"))
        if preview:
            self.render_preview(os.path.join(blend_dir, "previews", self.name + ".png"))
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(blend_dir, self.name + ".blend"), compress=True)
        return len(self.parts)

    def _export_fbx(self, path):
        for o in bpy.context.scene.objects:
            o.select_set(o.type == "MESH" and not o.display_type == "WIRE")
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True, apply_unit_scale=True, bake_space_transform=False,
                                 object_types={"MESH", "EMPTY"}, use_mesh_modifiers=True, mesh_smooth_type="FACE",
                                 axis_forward="Y", axis_up="Z", add_leaf_bones=False)

    # --------------------------------------------------------------- previews
    def render_preview(self, path, res=(640, 400), samples=20, view=(1.0, 1.25, 0.65)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        scene = bpy.context.scene
        mn, mx = self.bounds()
        center = (mn + mx) / 2
        radius = max((mx - mn).length / 2, 0.5)
        # ground
        bpy.ops.mesh.primitive_plane_add(size=radius * 12, location=(center.x, center.y, mn.z - 0.001))
        ground = bpy.context.active_object
        gm = bpy.data.materials.new("PreviewGround")
        gm.use_nodes = True
        gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.32, 0.33, 0.30, 1)
        gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.95
        ground.data.materials.append(gm)
        # camera
        cam_data = bpy.data.cameras.new("PreviewCam")
        cam_data.lens = 50
        cam = bpy.data.objects.new("PreviewCam", cam_data)
        scene.collection.objects.link(cam)
        d = Vector(view).normalized() * radius * 3.6
        cam.location = center + d
        direction = center - cam.location
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        scene.camera = cam
        # lights
        sun_data = bpy.data.lights.new("Sun", "SUN")
        sun_data.energy = 3.2
        sun_data.angle = math.radians(4)
        sun = bpy.data.objects.new("Sun", sun_data)
        sun.rotation_euler = Euler((math.radians(50), math.radians(10), math.radians(40)), "XYZ")
        scene.collection.objects.link(sun)
        world = bpy.data.worlds.new("PreviewWorld")
        world.use_nodes = True
        world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.62, 0.72, 1)
        world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
        scene.world = world
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = samples
        try:
            scene.cycles.use_denoising = True
        except Exception:
            pass
        scene.render.resolution_x, scene.render.resolution_y = res
        scene.render.film_transparent = False
        scene.view_settings.view_transform = "AgX" if "AgX" in [v.identifier for v in type(scene.view_settings).bl_rna.properties["view_transform"].enum_items] else "Filmic"
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        # clean preview helpers so they don't end up in the .blend
        for o in (ground, cam, sun):
            bpy.data.objects.remove(o, do_unlink=True)


# ---------------------------------------------------------------------------
# Common detail helpers
# ---------------------------------------------------------------------------
def bolt_row(m, name, start, end, count, size=0.04, mat="Metal", color=(0.3, 0.3, 0.3), group="", axis_rot=(0, 0, 0)):
    s, e = Vector(start), Vector(end)
    for i in range(count):
        t = i / max(1, count - 1)
        m.cyl(f"{name}{i}", size * 0.6, size, s.lerp(e, t), axis_rot, mat, color, group, segments=8)


def box_grid(m, name, origin, size, nx, ny, gap, mat, color, group="", rot=(0, 0, 0)):
    """Grid of small boxes (e.g. ERA blocks, louvres) along local X/Y of origin."""
    ox, oy, oz = origin
    sx, sy, sz = size
    for i in range(nx):
        for j in range(ny):
            m.block(f"{name}{i}_{j}", size, (ox + i * (sx + gap), oy + j * (sy + gap), oz), rot, mat, color, group)
