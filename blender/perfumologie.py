"""perfumologie taste demo: builds the 400ml bottle and renders the scroll scenes.

Run headless (0 credits, local GPU):
  blender.exe -b --factory-startup -P perfumologie.py -- --mode hi --out render/hi
  blender.exe -b --factory-startup -P perfumologie.py -- --mode hi --scenes 1 --frames 0,40,95 --out render/test

--mode hi  1280x720 landscape frames
--mode pt  576x1024 portrait frames (phones), same animation, reframed camera
Every scene is N=96 frames. Scene 5 is a seamless loop (its first and last
states are identical) because the scroll engine loops the last scene, and the
last frame of each scene equals the first frame of the next.

Geometry is measured from Daniel's 400ml packshot (sampled at 600px): body
r=0.865, shoulder to 3.45, collar r=0.345 to 4.11, actuator r=0.28 to 4.35,
spout to x=-0.785 at 4.36-4.47. 1 unit = 100px of that sample.
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default

MODE = arg('--mode', 'hi')
SCENES = [int(s) for s in arg('--scenes', '1,2,3,4,5').split(',')]
FRAMES = arg('--frames')
SAMPLES = int(arg('--samples', '96'))
N = 96
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = arg('--out', 'render/' + MODE)
OUT = OUT if os.path.isabs(OUT) else os.path.normpath(os.path.join(HERE, '..', OUT))

# ---------------------------------------------------------------- colours
FAMILY = {
    'green': '#4f6a53',      # Green Gardena, Pantone 5615 C
    'tangerine': '#a4502e',  # Timeless Tangerine, 1685 C
    'blue': '#2f6f84',       # Blue Bayberry, 2182 C
    'brown': '#6f625c',      # Brown Bergamot, 411 C
}
BG = {
    'dark': '#0b0a09', 'sand': '#d8c9b6', 'green': '#d3cdbf', 'tangerine': '#e4cab6',
    'blue': '#c6cfd1', 'brown': '#d3c6bd', 'row': '#d9cfc3',
}
LINE = (1.0, 0.78, 0.52)      # warm champagne light

def hex_srgb(h):
    h = h.lstrip('#'); return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
def to_lin(c):
    return [u / 12.92 if u <= 0.04045 else ((u + 0.055) / 1.055) ** 2.4 for u in c]
def mix(a, b, t):
    return [x + (y - x) * t for x, y in zip(a, b)]
def mix_hex(a, b, t):
    return '#%02x%02x%02x' % tuple(int(round(255 * u)) for u in mix(hex_srgb(a), hex_srgb(b), t))
def lin_hex(h): return to_lin(hex_srgb(h))
def rgba(c): return (c[0], c[1], c[2], 1.0)
def powc(c, p): return [max(1e-4, u) ** p for u in c]

# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def span(f, f0, f1): return clamp((f - f0) / (f1 - f0))
def ease(t): return t * t * t * (t * (t * 6 - 15) + 10)      # smootherstep
def lerp(a, b, t): return a + (b - a) * t
def ramp(f, f0, f1, a, b): return lerp(a, b, ease(span(f, f0, f1)))

# ---------------------------------------------------------------- scene helpers
bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene

def link(obj, parent=None):
    scn.collection.objects.link(obj)
    if parent: obj.parent = parent
    return obj

def empty(name, parent=None):
    return link(bpy.data.objects.new(name, None), parent)

def mesh_obj(name, bm, parent=None, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    if smooth:
        for p in me.polygons: p.use_smooth = True
    return link(bpy.data.objects.new(name, me), parent)

def lathe(profile, steps=128):
    """Revolve a list of (r, z) around Z."""
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0, z)) for r, z in profile]
    edges = [bm.edges.new((vs[i], vs[i + 1])) for i in range(len(vs) - 1)]
    bmesh.ops.spin(bm, geom=vs + edges, cent=(0, 0, 0), axis=(0, 0, 1),
                   angle=2 * math.pi, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm

def catmull(pts, n=6):
    """Smooth a polyline of (r, z) control points."""
    out = []
    P = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t
                       + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t * t
                       + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t ** 3) for j in (0, 1)))
    out.append(pts[-1])
    return out

def on_wall(a_deg, z, radius):
    """Outward normal and position on the cylinder at angle a (0 = front, toward the camera)."""
    a = math.radians(a_deg)
    n = Vector((math.sin(a), -math.cos(a), 0))
    return n, Vector((0, 0, z)) + n * radius

R = 0.865
SHOULDER = [(R, 3.00), (0.855, 3.09), (0.835, 3.15), (0.805, 3.21), (0.755, 3.27),
            (0.675, 3.33), (0.56, 3.39), (0.445, 3.45), (0.31, 3.47)]
BODY = ([(0.0, 0.0), (0.70, 0.0)]
        + catmull([(0.70, 0.0), (0.80, 0.012), (0.85, 0.06), (R, 0.16)], 4)[1:]
        + catmull([(R, 0.16), (R, 1.5), (R, 3.0)] + SHOULDER[1:], 5)[1:]
        + [(0.30, 3.49), (0.30, 3.64)])
PIV = 3.9                     # pump pivot height
ABSORB = 1.0                  # liquid: transmittance through the full diameter = colour ** ABSORB

# ---------------------------------------------------------------- materials
def principled_tree(idblock):
    try: idblock.use_nodes = True
    except Exception: pass
    nt = idblock.node_tree
    p = nt.nodes.get('Principled BSDF')
    if p is None:
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        p = nt.nodes.new('ShaderNodeBsdfPrincipled')
        nt.links.new(p.outputs[0], out.inputs['Surface'])
    return nt, p

class Mat:
    """Principled material whose colour can be re-driven every frame."""
    NAMES = {'base': 'Base Color', 'rough': 'Roughness', 'trans': 'Transmission Weight',
             'ior': 'IOR', 'coat': 'Coat Weight', 'spec': 'Specular IOR Level'}
    def __init__(self, name):
        self.m = bpy.data.materials.new(name)
        self.nt, self.p = principled_tree(self.m)
        self.hooks = []          # (socket, fn(family_lin) -> rgba)
    def set(self, **kw):
        for k, v in kw.items():
            self.p.inputs[self.NAMES[k]].default_value = v
        return self
    def hook(self, socket, fn):
        self.hooks.append((socket, fn)); return self
    def recolor(self, fam):
        for sock, fn in self.hooks: sock.default_value = fn(fam)

def bottle_materials(tag):
    shell = Mat('shell_' + tag)
    nt, p = shell.nt, shell.p
    shell.set(rough=0.035, trans=1.0, ior=1.5)
    shell.hook(p.inputs['Base Color'], lambda c: rgba(powc(c, 0.15)))
    # label band: matte knurled sleeve on the front, diagonal bottom edge
    lab = nt.nodes.new('ShaderNodeBsdfPrincipled')
    lab.inputs['Roughness'].default_value = 0.62
    shell.hook(lab.inputs['Base Color'], lambda c: rgba([u * 0.42 for u in c]))
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['Object'], sep.inputs[0])
    def op(kind, a, b):
        n = nt.nodes.new('ShaderNodeMath'); n.operation = kind
        for i, v in enumerate((a, b)):
            if isinstance(v, (int, float)): n.inputs[i].default_value = v
            else: nt.links.new(v, n.inputs[i])
        return n.outputs[0]
    ang = op('ARCTAN2', sep.outputs['X'], op('MULTIPLY', sep.outputs['Y'], -1))
    a0, a1, zb0, zb1, ztop = math.radians(-35), math.radians(30), 0.72, 1.61, 3.43
    edge = op('ADD', op('MULTIPLY', op('SUBTRACT', ang, a0), (zb1 - zb0) / (a1 - a0)), zb0)
    mask = op('MULTIPLY',
              op('MULTIPLY', op('GREATER_THAN', ang, a0), op('LESS_THAN', ang, a1)),
              op('MULTIPLY', op('LESS_THAN', sep.outputs['Z'], ztop), op('GREATER_THAN', sep.outputs['Z'], edge)))
    # diamond knurl in unrolled cylinder coordinates (arc length, height), crossing at 45 degrees
    arc = op('MULTIPLY', ang, R)
    waves = []
    for kind in ('ADD', 'SUBTRACT'):
        cv = nt.nodes.new('ShaderNodeCombineXYZ'); nt.links.new(op(kind, arc, sep.outputs['Z']), cv.inputs[0])
        w = nt.nodes.new('ShaderNodeTexWave'); w.wave_type = 'BANDS'; w.bands_direction = 'X'
        w.inputs['Scale'].default_value = 9; w.inputs['Distortion'].default_value = 0
        nt.links.new(cv.outputs[0], w.inputs['Vector']); waves.append(w.outputs['Fac'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.5; bump.inputs['Distance'].default_value = 0.004
    nt.links.new(op('MULTIPLY', *waves), bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], lab.inputs['Normal'])
    mixs = nt.nodes.new('ShaderNodeMixShader')
    out = next(n for n in nt.nodes if n.bl_idname == 'ShaderNodeOutputMaterial')
    nt.links.new(mask, mixs.inputs['Fac'])
    nt.links.new(p.outputs[0], mixs.inputs[1]); nt.links.new(lab.outputs[0], mixs.inputs[2])
    nt.links.new(mixs.outputs[0], out.inputs['Surface'])

    # liquid: clear surface + coloured absorption, so the centre reads deep and the edges glow
    liquid = Mat('liquid_' + tag).set(rough=0.04, trans=1.0, ior=1.34)
    liquid.hook(liquid.p.inputs['Base Color'], lambda c: rgba(powc(c, 0.08)))
    absn = liquid.nt.nodes.new('ShaderNodeVolumeAbsorption')
    lout = next(n for n in liquid.nt.nodes if n.bl_idname == 'ShaderNodeOutputMaterial')
    liquid.nt.links.new(absn.outputs[0], lout.inputs['Volume'])
    def absorb(c):
        k = [-math.log(max(u, 1e-3)) * ABSORB / 1.65 for u in c]
        d = max(k) * 1.25
        return [1 - x / d for x in k], d
    liquid.hook(absn.inputs['Color'], lambda c: rgba(absorb(c)[0]))
    liquid.hook(absn.inputs['Density'], lambda c: absorb(c)[1])
    mark = Mat('mark_' + tag).set(rough=0.3, coat=0.3)
    mark.hook(mark.p.inputs['Base Color'], lambda c: rgba([u * 0.6 for u in c]))
    pump = Mat('pump_' + tag).set(rough=0.4, coat=0.2)
    pump.hook(pump.p.inputs['Base Color'], lambda c: rgba([u * 0.32 for u in c]))
    return [shell, liquid, mark, pump]

def emissive(name, color, strength, halo=False):
    m = bpy.data.materials.new(name)
    try: m.use_nodes = True
    except Exception: pass
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission'); em.inputs['Color'].default_value = (*color, 1)
    em.inputs['Strength'].default_value = strength
    if halo:
        tr = nt.nodes.new('ShaderNodeBsdfTransparent')
        mx = nt.nodes.new('ShaderNodeMixShader'); mx.inputs['Fac'].default_value = 0.35
        nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(em.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], out.inputs['Surface'])
    else:
        nt.links.new(em.outputs[0], out.inputs['Surface'])
    return m, em

# ---------------------------------------------------------------- the bottle
FONT_PATHS = ['C:/Windows/Fonts/GOTHICB.TTF',
              'C:/Users/liav/Desktop/עסק/פונטים/פונטים באנגלית/ClashGrotesk_Complete/Fonts/OTF/ClashGrotesk-Regular.otf']
FONT = next((bpy.data.fonts.load(p) for p in FONT_PATHS if os.path.exists(p)), None)
print('[font]', FONT.filepath if FONT else 'default')

def flat_text(name, body, length):
    """Text as a flat, finely subdivided mesh in XY: reads along +X, letters up +Y, centred on Y."""
    cu = bpy.data.curves.new(name + '_c', 'FONT'); cu.body = body
    if FONT: cu.font = FONT
    cu.size = 1.0; cu.resolution_u = 6
    tmp = link(bpy.data.objects.new(name + '_tmp', cu))
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(tmp); bpy.data.curves.remove(cu)
    bm = bmesh.new(); bm.from_mesh(me); bpy.data.meshes.remove(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    xs = [v.co.x for v in bm.verts]; ys = [v.co.y for v in bm.verts]
    s = length / (max(xs) - min(xs)); x0 = min(xs); yc = (max(ys) + min(ys)) / 2
    for v in bm.verts:
        v.co = Vector(((v.co.x - x0) * s, (v.co.y - yc) * s, 0))
    for _ in range(2):
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=2, use_grid_fill=True)
    return bm

def place_on_wall(ob, root, a_deg, z0, radius, along=Vector((0, 0, 1))):
    """Local X runs along `along`, local Z points out of the wall."""
    n, pos = on_wall(a_deg, z0, radius)
    X = along.normalized(); Z = n; Y = Z.cross(X)
    ob.matrix_world = Matrix.Translation(pos) @ Matrix((X, Y, Z)).transposed().to_4x4()
    ob.parent = root; ob.matrix_parent_inverse = root.matrix_world.inverted()

def emboss(ob, shell, mat, th):
    ob.data.materials.append(mat)
    sw = ob.modifiers.new('wrap', 'SHRINKWRAP'); sw.target = shell
    sw.wrap_method = 'NEAREST_SURFACEPOINT'; sw.wrap_mode = 'OUTSIDE_SURFACE'; sw.offset = 0.001
    so = ob.modifiers.new('thick', 'SOLIDIFY'); so.thickness = th; so.offset = 1

def make_bottle(tag, parent):
    mats = bottle_materials(tag)
    shell_m, liquid_m, mark_m, pump_m = [m.m for m in mats]
    root = empty('spin_' + tag, parent)
    shell = mesh_obj('shell_' + tag, lathe(BODY), root)
    shell.data.materials.append(shell_m)
    sol = shell.modifiers.new('wall', 'SOLIDIFY'); sol.thickness = 0.028; sol.offset = -1
    # filled up into the shoulder, so the whole bottle reads coloured like the packshot
    inner = [(r - 0.04, z) for r, z in BODY if 0.12 < z < 3.36]
    liq = mesh_obj('liquid_' + tag, lathe([(0, 0.05), (0.66, 0.05)] + inner + [(0, inner[-1][1])]), root)
    liq.data.materials.append(liquid_m)

    # wordmark reads bottom to top on the left of the front, "p" logo ring bottom right
    wm = mesh_obj('word_' + tag, flat_text('word_' + tag, 'perfumologie', 2.24), None, smooth=False)
    place_on_wall(wm, root, -54, 0.36, R + 0.03)
    emboss(wm, shell, mark_m, 0.02)
    a = math.radians(30)
    across = Vector((math.cos(a), math.sin(a), 0))
    lg = mesh_obj('logo_' + tag, flat_text('logo_' + tag, 'p', 0.085), None, smooth=False)
    place_on_wall(lg, root, 30, 0.45, R + 0.03, along=across)
    emboss(lg, shell, mark_m, 0.012)
    bm = bmesh.new()
    o = [bm.verts.new((0.125 * math.cos(2 * math.pi * i / 48), 0.125 * math.sin(2 * math.pi * i / 48), 0)) for i in range(48)]
    n = [bm.verts.new((0.107 * math.cos(2 * math.pi * i / 48), 0.107 * math.sin(2 * math.pi * i / 48), 0)) for i in range(48)]
    for i in range(48):
        j = (i + 1) % 48; bm.faces.new((o[i], o[j], n[j], n[i]))
    ring = mesh_obj('logoring_' + tag, bm, None, smooth=False)
    place_on_wall(ring, root, 30, 0.45, R + 0.03, along=across)
    emboss(ring, shell, mark_m, 0.012)

    # pump: collar, actuator, top cap, spout, dip tube. Lifts and twists as one around PIV.
    pump = empty('pump_' + tag, root); pump.location.z = PIV
    def part(name, bm, smooth=True):
        ob = mesh_obj(name, bm, pump, smooth); ob.location.z = -PIV; return ob
    for name, prof in (('collar', [(0, 3.46), (0.33, 3.46), (0.345, 3.475), (0.345, 4.095), (0.33, 4.11), (0, 4.11)]),
                       ('stem', [(0, 4.11), (0.27, 4.11), (0.28, 4.12), (0.28, 4.35), (0, 4.35)]),
                       ('cap', [(0, 4.35), (0.28, 4.35), (0.28, 4.46), (0.27, 4.47), (0, 4.47)])):
        part(name + '_' + tag, lathe(prof, 96)).data.materials.append(pump_m)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts: v.co = Vector((v.co.x * 0.56 - 0.505, v.co.y * 0.15, v.co.z * 0.11 + 4.415))
    sp = part('spout_' + tag, bm, smooth=False); sp.data.materials.append(pump_m)
    bev = sp.modifiers.new('bev', 'BEVEL'); bev.width = 0.012; bev.segments = 2
    tube_m = Mat('tube_' + tag).set(base=(0.8, 0.8, 0.78, 1), rough=0.35, trans=0.3).m
    part('tube_' + tag, lathe([(0, 0.22), (0.035, 0.22), (0.035, 3.46), (0, 3.46)], 24)).data.materials.append(tube_m)
    return root, pump, mats

# ---------------------------------------------------------------- stage
tilt_main = empty('tilt_main')
spin_main, pump_main, mats_main = make_bottle('main', tilt_main)
others = {}
for fam in ('green', 'tangerine', 'blue'):
    holder = empty('hold_' + fam)
    sp, pu, ms = make_bottle(fam, holder)
    for m in ms: m.recolor(lin_hex(FAMILY[fam]))
    others[fam] = (holder, sp)

# contour light: two polylines start at the front of the base rim, run round to
# the sides, up the silhouette (spout on the left) and meet at the top. Child
# of the tilt (camera-facing plane), not of the spin.
contour = empty('contour', tilt_main)
def contour_points(side):
    Rr = R + 0.03
    pts = [(side * Rr * math.sin(math.radians(90 * i / 16)), -Rr * math.cos(math.radians(90 * i / 16)), 0.07)
           for i in range(17)]
    pts += [(side * (r + 0.03), 0, z) for r, z in catmull([(R, 0.16), (R, 3.0)] + SHOULDER[1:-1], 5)]
    pts += [(side * 0.375, 0, 3.47), (side * 0.375, 0, 4.10), (side * 0.31, 0, 4.12), (side * 0.31, 0, 4.35)]
    pts += [(-0.815, 0, 4.345), (-0.815, 0, 4.50)] if side < 0 else [(0.31, 0, 4.50)]
    pts.append((0, 0, 4.50))
    return pts

line_core_m, line_core_em = emissive('line_core', LINE, 14)
line_halo_m, line_halo_em = emissive('line_halo', LINE, 1.2, halo=True)
LINES = []
for side in (1, -1):
    for kind, depth, mat in (('core', 0.011, line_core_m), ('halo', 0.045, line_halo_m)):
        cu = bpy.data.curves.new(f'line_{kind}_{side}', 'CURVE'); cu.dimensions = '3D'
        spl = cu.splines.new('POLY'); pts = contour_points(side)
        spl.points.add(len(pts) - 1)
        for p, c in zip(spl.points, pts): p.co = (*c, 1)
        cu.bevel_depth = depth; cu.bevel_resolution = 4; cu.use_fill_caps = True
        cu.bevel_factor_mapping_end = 'SPLINE'
        ob = link(bpy.data.objects.new(f'line_{kind}_{side}', cu), contour)
        ob.data.materials.append(mat)
        LINES.append(ob)

spark_m, spark_em = emissive('spark', LINE, 60)
bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.035)
spark = mesh_obj('spark', bm, tilt_main); spark.data.materials.append(spark_m)
sparkh_m, sparkh_em = emissive('spark_halo', LINE, 3, halo=True)
bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.14)
spark_h = mesh_obj('spark_halo', bm, spark); spark_h.data.materials.append(sparkh_m)

# light rings that rise off the neck (scene 3): closed curves, radius set per frame
RINGS = []
for i in range(3):
    cu = bpy.data.curves.new(f'ring_{i}', 'CURVE'); cu.dimensions = '3D'
    spl = cu.splines.new('POLY'); spl.points.add(95); spl.use_cyclic_u = True
    cu.bevel_depth = 0.008; cu.bevel_resolution = 3
    ob = link(bpy.data.objects.new(f'ring_{i}', cu), tilt_main)
    m, em = emissive(f'ring_{i}', LINE, 20)
    ob.data.materials.append(m)
    RINGS.append((ob, spl, em))

# cyclorama: floor that curves up into a back wall
bm = bmesh.new()
prof = [(-40, 0)] + [(8 + 7 * math.sin(math.radians(a)), 7 - 7 * math.cos(math.radians(a))) for a in range(0, 91, 6)] + [(15, 40)]
cols = [[bm.verts.new((x, y, z)) for y, z in prof] for x in (-60, 60)]
for i in range(len(prof) - 1):
    bm.faces.new((cols[0][i], cols[1][i], cols[1][i + 1], cols[0][i + 1]))
cyc = mesh_obj('cyc', bm, None)
cyc_mat = Mat('cyc').set(rough=0.9)
cyc.data.materials.append(cyc_mat.m)

world = bpy.data.worlds.new('world'); scn.world = world
try: world.use_nodes = True
except Exception: pass
wbg = next(n for n in world.node_tree.nodes if n.bl_idname == 'ShaderNodeBackground')

# lights aim at a fixed point so the row in scene 5 is lit evenly
aim = empty('aim'); aim.location = (0, 0, 2.0)
def area(name, loc, size, energy, size_y=None):
    ld = bpy.data.lights.new(name, 'AREA'); ld.shape = 'RECTANGLE'; ld.size = size
    ld.size_y = size_y or size; ld.energy = energy
    ob = link(bpy.data.objects.new(name, ld)); ob.location = loc
    c = ob.constraints.new('TRACK_TO'); c.target = aim; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'
    return ob
LIGHTS = [(area(n, loc, s, e, sy), e) for n, loc, s, e, sy in (
    ('key', (-7, -7, 6.5), 4.5, 520, None),
    ('strip_l', (-6.5, 1.5, 3), 0.7, 750, 7),
    ('strip_r', (6.5, 2.5, 3), 0.7, 600, 7),
    ('top', (0, -1, 10), 5, 200, None),
    ('fill', (6, -8, 2.5), 6, 140, None))]
SWEEP = area('sweep', (-14, -9, 3), 1.2, 0, size_y=9)

cam_d = bpy.data.cameras.new('cam'); cam_d.lens = 70; cam_d.sensor_fit = 'AUTO'; cam_d.clip_end = 300
cam = link(bpy.data.objects.new('cam', cam_d)); scn.camera = cam

# ---------------------------------------------------------------- render setup
r = scn.render
r.resolution_x, r.resolution_y = (576, 1024) if MODE == 'pt' else (1280, 720)
r.resolution_percentage = 100
r.engine = 'CYCLES'
r.use_persistent_data = True
r.image_settings.file_format = 'JPEG'; r.image_settings.quality = 94
cy = scn.cycles
cy.samples = SAMPLES; cy.use_adaptive_sampling = True; cy.adaptive_threshold = 0.02
cy.use_denoising = True
cy.max_bounces = 16; cy.transmission_bounces = 14; cy.glossy_bounces = 6; cy.diffuse_bounces = 3
cy.transparent_max_bounces = 8
cy.caustics_reflective = False; cy.caustics_refractive = False
cy.blur_glossy = 1.0
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'; prefs.get_devices()
    for d in prefs.devices: d.use = (d.type != 'CPU')
    cy.device = 'GPU'
    print('[gpu]', [d.name for d in prefs.devices if d.use])
except Exception as e:
    print('[gpu] setup failed, CPU render:', e)
scn.view_settings.view_transform = 'AgX'
for look in ('AgX - Medium High Contrast', 'Medium High Contrast'):
    try: scn.view_settings.look = look; break
    except Exception: pass

# ---------------------------------------------------------------- per-frame state
H_FULL = 6.3                 # vertical content for a full-bottle shot
ROW_X = [-3.36, -1.12, 1.12, 3.36]
# row framing. Landscape: bottles in the lower half, the upper half free for the headline.
# Portrait (width-bound): bottles in the upper middle, the copy sits below them.
ROW_T, ROW_H = (0.85, 10.4) if MODE == 'pt' else (4.47, 10.4)
# Phones are narrower than the 9:16 frame (390x844 is ~0.46), so the page crops about 9% off
# each side; the portrait row is framed wider to keep the outer bottles whole.
ROW_W = 11.8 if MODE == 'pt' else 9.4
S3_T, S3_H = 3.85, 4.7           # scene 3 end framing: neck to floating pump
ROW = ['green', 'tangerine', 'blue']   # main (brown by then) takes the last slot

def family_at(f):
    """Colour and backdrop of the main bottle along scene 4's morph."""
    stops = [(22, 'green'), (36, 'tangerine'), (52, 'blue'), (68, 'brown')]
    if f <= stops[0][0]: return lin_hex(FAMILY['green']), BG['green']
    for (fa, a), (fb, b) in zip(stops, stops[1:]):
        if f <= fb:
            t = ease(span(f, fa + 4, fb))
            return mix(lin_hex(FAMILY[a]), lin_hex(FAMILY[b]), t), mix_hex(BG[a], BG[b], t)
    return lin_hex(FAMILY['brown']), BG['brown']

def state(s, f):
    st = dict(target=2.24, yaw=0, pitch=4, H=H_FULL, W=0, float=0,
              tilt=0, spin=20, light=1, bg=BG['sand'], line=0, line_a=0, spark_z=None,
              spark_a=0, lift=0, twist=0, pump_tilt=0, rings=[0, 0, 0],
              fam=lin_hex(FAMILY['green']), main_x=0, others={k: None for k in ROW}, sweep=0)
    if s == 1:
        st.update(tilt=11, float=0.5, spin=ramp(f, 70, 95, 0, 15), light=ramp(f, 48, 82, 0, 1), bg=BG['dark'],
                  line=ramp(f, 10, 62, 0, 1), line_a=1 - ease(span(f, 68, 92)),
                  spark_z=ramp(f, 0, 14, -2.6, 0.07), spark_a=1 - ease(span(f, 14, 26)),
                  H=ramp(f, 0, 95, 6.9, 6.2), pitch=ramp(f, 0, 95, 7, 4), yaw=ramp(f, 70, 95, 0, -4))
    elif s == 2:
        st.update(tilt=ramp(f, 0, 60, 11, 0), float=ramp(f, 0, 60, 0.5, 0), spin=ramp(f, 0, 95, 15, 40),
                  bg=mix_hex(BG['dark'], BG['sand'], ease(span(f, 0, 34))),
                  target=ramp(f, 18, 95, 2.24, 2.55),
                  H=ramp(f, 18, 95, 6.2, 2.7), pitch=ramp(f, 0, 95, 4, 2), yaw=ramp(f, 0, 95, -4, -8))
    elif s == 3:
        # framing keeps the whole lifted pump (top at 4.47 + lift 1.04) in view
        st.update(spin=ramp(f, 0, 95, 40, 22), target=ramp(f, 0, 50, 2.55, S3_T),
                  H=ramp(f, 0, 50, 2.7, S3_H), pitch=ramp(f, 0, 50, 2, 11), yaw=ramp(f, 0, 95, -8, 7),
                  lift=ramp(f, 14, 60, 0, 0.92) + ramp(f, 60, 95, 0, 0.12),
                  twist=ramp(f, 14, 60, 0, 120), pump_tilt=ramp(f, 55, 95, 0, 7),
                  rings=[ease(span(f, 36 + 12 * i, 68 + 12 * i)) for i in range(3)])
    elif s == 4:
        fam, bg = family_at(f)
        st.update(lift=ramp(f, 0, 20, 1.04, 0), twist=ramp(f, 0, 20, 120, 0), pump_tilt=ramp(f, 0, 14, 7, 0),
                  rings=[1 - ease(span(f, 0, 14))] * 3,
                  target=ramp(f, 0, 30, S3_T, 2.24) + ramp(f, 66, 95, 0, ROW_T - 2.24),
                  H=ramp(f, 0, 30, S3_H, H_FULL) + ramp(f, 66, 95, 0, ROW_H - H_FULL),
                  pitch=ramp(f, 0, 30, 11, 5), yaw=ramp(f, 0, 30, 7, 0),
                  spin=ramp(f, 8, 70, 22, 380), fam=fam,
                  bg=mix_hex(bg, BG['row'], ease(span(f, 70, 95))),
                  main_x=ramp(f, 66, 95, 0, ROW_X[3]))
        if f > 66:
            st['W'] = ramp(f, 66, 95, 0, ROW_W)
            # slide in from the left; the bottle going furthest leads, so gaps never drop below 2.24
            st['others'] = {k: ROW_X[i] - 14 * (1 - ease(span(f, 66 + 4 * (2 - i), 90 + 2 * (2 - i))))
                            for i, k in enumerate(ROW)}
    elif s == 5:
        st.update(spin=380, fam=lin_hex(FAMILY['brown']), bg=BG['row'], main_x=ROW_X[3], W=ROW_W, pitch=5,
                  target=ROW_T, H=ROW_H,
                  others={k: ROW_X[i] for i, k in enumerate(ROW)},
                  sweep=math.sin(math.pi * f / N) ** 2)
    return st

def apply(st, s, f):
    tilt_main.location = (st['main_x'], 0, st['float'])
    tilt_main.rotation_euler = (0, math.radians(st['tilt']), 0)
    spin_main.rotation_euler = (0, 0, math.radians(st['spin']))
    pump_main.location = (0, 0, PIV + st['lift'])
    pump_main.rotation_euler = (math.radians(st['pump_tilt']), 0, math.radians(st['twist']))
    for m in mats_main: m.recolor(st['fam'])
    for k, (holder, sp) in others.items():
        x = st['others'][k]
        for ob in [holder] + list(holder.children_recursive): ob.hide_render = x is None
        if x is not None:
            holder.location = (x, 0, 0)
            sp.rotation_euler = (0, 0, math.radians(20))
    for ob in LINES:
        ob.data.bevel_factor_end = max(0.0005, st['line'])
        ob.hide_render = st['line'] <= 0.001 or st['line_a'] <= 0.001
    line_core_em.inputs['Strength'].default_value = 14 * st['line_a']
    line_halo_em.inputs['Strength'].default_value = 1.2 * st['line_a']
    hide_spark = st['spark_z'] is None or st['spark_a'] <= 0.001
    spark.hide_render = spark_h.hide_render = hide_spark
    if not hide_spark:
        spark.location = (0, -(R + 0.03), st['spark_z'])
        spark_em.inputs['Strength'].default_value = 25 * st['spark_a']
        sparkh_em.inputs['Strength'].default_value = 3 * st['spark_a']
    for i, (ob, spl, em) in enumerate(RINGS):
        p = st['rings'][i]
        ob.hide_render = p <= 0.001
        rad = lerp(0.36, 0.62 + 0.15 * i, p); z = lerp(3.5, 3.62 + 0.24 * i, p)
        for k, pt in enumerate(spl.points):
            t = 2 * math.pi * k / len(spl.points)
            pt.co = (rad * math.cos(t), rad * math.sin(t), z, 1)
        em.inputs['Strength'].default_value = 3 * min(1, p * 1.5)
    for ob, e in LIGHTS: ob.data.energy = e * st['light']
    SWEEP.data.energy = 1400 * st['sweep']
    SWEEP.location = (lerp(-14, 14, f / N) if s == 5 else -14, -9, 3)
    cyc.hide_render = s == 1          # the dark opening floats in black, no floor
    bg = lin_hex(st['bg'])
    cyc_mat.p.inputs['Base Color'].default_value = rgba(bg)
    wbg.inputs['Color'].default_value = rgba(bg)
    wbg.inputs['Strength'].default_value = 0.7
    # camera: fit H (vertical) and W (horizontal) content around the target
    if MODE == 'pt':
        d = max(st['H'], st['W'] / (576 / 1024)) * cam_d.lens / 36
    else:
        d = max(st['H'] * 1280 / 720, st['W']) * cam_d.lens / 36
    tgt = (Matrix.Translation((0, 0, st['float'])) @ Matrix.Rotation(math.radians(st['tilt']), 4, 'Y')
           @ Vector((0, 0, st['target'])))
    yaw, pitch = math.radians(st['yaw']), math.radians(st['pitch'])
    cam.location = tgt + Vector((math.sin(yaw) * math.cos(pitch), -math.cos(yaw) * math.cos(pitch), math.sin(pitch))) * d
    cam.rotation_euler = (tgt - cam.location).to_track_quat('-Z', 'Y').to_euler()

# ---------------------------------------------------------------- render loop
frames = [int(x) for x in FRAMES.split(',')] if FRAMES else list(range(N))
for s in SCENES:
    os.makedirs(os.path.join(OUT, str(s)), exist_ok=True)
    for f in frames:
        path = os.path.join(OUT, str(s), '%03d.jpg' % (f + 1))
        if os.path.exists(path) and not FRAMES: continue
        apply(state(s, f), s, f)
        bpy.context.view_layer.update()
        r.filepath = path
        bpy.ops.render.render(write_still=True)
        print(f'[render] scene {s} frame {f + 1}/{N}', flush=True)
print('[done]')
