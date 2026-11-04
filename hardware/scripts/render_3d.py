"""Render KiCad's exported GLB using Blender (no invented component geometry).

blender --background --factory-startup --python hardware/scripts/render_3d.py \
    -- hardware/build/desk-node.glb hardware/images
"""
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


src, out = sys.argv[sys.argv.index("--") + 1:]
out = Path(out)
out.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(Path(src).resolve()))
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
points = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
center = (lo + hi) / 2
span = max(hi - lo)
print("Imported board bounds:", tuple(lo), tuple(hi))
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 32
scene.cycles.use_denoising = True
scene.render.threads_mode = "FIXED"
scene.render.threads = 2
scene.render.resolution_x = 1400
scene.render.resolution_y = 1400
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.world.color = (0.65, 0.65, 0.65)
scene.view_settings.view_transform = "AgX"
scene.render.film_transparent = True


def light(name, offset, energy):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy * span * span
    data.shape = "DISK"
    data.size = span * 2
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = center + Vector(offset) * span
    obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()


light("top softbox", (-1, -1, 2.5), 150)
light("fill", (1, 1, 1.5), 80)
light("bottom softbox", (0, -1, -2.5), 150)
camera = bpy.data.cameras.new("Board camera")
camera.type = "ORTHO"
camera.ortho_scale = span * 1.35
obj = bpy.data.objects.new("Board camera", camera)
scene.collection.objects.link(obj)
scene.camera = obj
for name, offset in [("top", (0.65, -0.85, 1.8)), ("bottom", (-0.65, -0.85, -1.8))]:
    obj.location = center + Vector(offset) * span
    obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str((out / f"desk-node-{name}.png").resolve())
    bpy.ops.render.render(write_still=True)
