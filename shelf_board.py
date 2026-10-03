# ===== メタルラック用 棚板 (Blender用スクリプト) =====
# 使い方: Blender上部の「Scripting」タブ → 「開く」でこのファイルを選択 → ▶(スクリプト実行)
# 単位: メートル(Blenderの標準)。数値を変えるとサイズを調整できます。

import bpy
import bmesh
import math
import mathutils

W   = 0.90    # 横幅 90cm
D   = 0.45    # 奥行き(縦) 45cm ※曲げ部分を含む外寸
H   = 0.04    # 手前・奥の曲げ高さ 4cm(下方向)
T   = 0.003   # 板厚 3mm
R   = 0.003   # 曲げの内側の丸み 3mm(0にすると角が直角)
SEG = 8       # 曲げの丸みの分割数

# --- パンチング(平らな天板部分だけ) ---
HOLE_D   = 0.010   # 穴の直径 10mm
HOLE_P   = 0.020   # 穴のピッチ 20mm(千鳥配置)
MARGIN   = 0.030   # 外周・曲げ部から穴までの余白 30mm(ここは穴なし=強度確保)
HOLE_SEG = 16      # 穴の分割数

# --- 強度確認(等分布荷重) ---
LOAD_KG  = 50.0    # 耐荷重 50kg
SPAN     = W       # 支点間距離(左右の支柱間)
E_STEEL  = 200e9   # ヤング率 鋼 [Pa]
YIELD    = 235e6   # 降伏応力 SS400相当 [Pa]
SAFETY   = 1.5     # 安全率

OBJ_NAME = "Shelf_Board"


def make_profile():
    """手前→天板→奥の断面形状(Y-Z平面)を、外周を一周する点列で作る"""
    Ro = R + T  # 曲げの外側の半径
    pts = []

    def arc(cy, cz, rad, a0, a1):
        if rad <= 0:
            pts.append((cy, cz))
            return
        for i in range(SEG + 1):
            a = math.radians(a0 + (a1 - a0) * i / SEG)
            pts.append((cy + rad * math.cos(a), cz + rad * math.sin(a)))

    # 外側
    pts.append((0.0, 0.0))                     # 手前の曲げの下端(外側)
    arc(Ro, H - Ro, Ro, 180, 90)               # 手前の角(外側)
    arc(D - Ro, H - Ro, Ro, 90, 0)             # 奥の角(外側)
    pts.append((D, 0.0))                       # 奥の曲げの下端(外側)
    # 内側
    pts.append((D - T, 0.0))                   # 奥の曲げの下端(内側)
    arc(D - Ro, H - Ro, R, 0, 90)              # 奥の角(内側)
    arc(Ro, H - Ro, R, 90, 180)                # 手前の角(内側)
    pts.append((T, 0.0))                       # 手前の曲げの下端(内側)
    return pts


# 再実行したときのために、前回作った棚板を削除
old = bpy.data.objects.get(OBJ_NAME)
if old:
    bpy.data.objects.remove(old, do_unlink=True)

def make_punch_cutter():
    """天板の平らな部分だけに開ける穴(千鳥配置)の切り抜き用オブジェクトを作る"""
    y_min = -D / 2 + H + MARGIN        # 曲げ部(高さH)+余白の内側だけに穴を開ける
    y_max = D / 2 - H - MARGIN
    x_min = -W / 2 + MARGIN
    x_max = W / 2 - MARGIN
    r = HOLE_D / 2
    bm_c = bmesh.new()
    count = 0
    row = 0
    y = y_min + r
    while y <= y_max - r:
        x = x_min + r + (HOLE_P / 2 if row % 2 else 0.0)
        while x <= x_max - r:
            bmesh.ops.create_cone(
                bm_c, cap_ends=True, segments=HOLE_SEG,
                radius1=r, radius2=r, depth=T * 4,
                matrix=mathutils.Matrix.Translation((x, y, H - T / 2)))
            count += 1
            x += HOLE_P
        y += HOLE_P * math.sqrt(3) / 2   # 千鳥の行間
        row += 1
    me = bpy.data.meshes.new("Punch_Cutter")
    bm_c.to_mesh(me)
    bm_c.free()
    cutter = bpy.data.objects.new("Punch_Cutter", me)
    bpy.context.collection.objects.link(cutter)
    return cutter, count


def check_strength():
    """50kg等分布荷重での曲げ応力・たわみを概算する(穴の分だけ天板を減らして計算)"""
    open_ratio = (math.pi * r_hole() ** 2) / (HOLE_P * HOLE_P * math.sqrt(3) / 2)
    flat_w = D - 2 * H                      # 平らな部分の幅
    perf_w = max(flat_w - 2 * MARGIN, 0)    # 穴あき範囲の幅
    eff_top = (D - perf_w * open_ratio)     # 天板の有効幅(穴を差し引く)
    # 断面: 天板(幅eff_top, 厚T, 上端z=H) + 手前/奥の曲げ(厚T, 高さH) ×2
    parts = [(eff_top * T, H - T / 2, eff_top * T ** 3 / 12),
             (2 * T * (H - T), (H - T) / 2, 2 * T * (H - T) ** 3 / 12)]
    A = sum(a for a, _, _ in parts)
    zc = sum(a * z for a, z, _ in parts) / A
    I = sum(i + a * (z - zc) ** 2 for a, z, i in parts)
    c = max(zc, H - zc)
    w = LOAD_KG * 9.80665 / SPAN            # N/m
    M = w * SPAN ** 2 / 8
    sigma = M * c / I
    delta = 5 * w * SPAN ** 4 / (384 * E_STEEL * I)
    ok = sigma <= YIELD / SAFETY
    print("--- 強度確認 (鋼, 等分布 {:.0f}kg, スパン{:.0f}cm) ---".format(LOAD_KG, SPAN * 100))
    print("開口率 {:.0f}%  曲げ応力 {:.1f} MPa (許容 {:.0f} MPa)  たわみ {:.2f} mm".format(
        open_ratio * 100, sigma / 1e6, YIELD / SAFETY / 1e6, delta * 1000))
    print("判定: " + ("OK (50kg に耐えられます)" if ok else "NG (板厚・曲げ高さ・開口率を見直してください)"))
    return ok


def r_hole():
    return HOLE_D / 2


# 断面を作って横方向(X)に押し出す
bm = bmesh.new()
verts = [bm.verts.new((-W / 2, y - D / 2, z)) for (y, z) in make_profile()]
face = bm.faces.new(verts)
res = bmesh.ops.extrude_face_region(bm, geom=[face])
new_verts = [e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)]
bmesh.ops.translate(bm, verts=new_verts, vec=(W, 0.0, 0.0))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

mesh = bpy.data.meshes.new(OBJ_NAME)
bm.to_mesh(mesh)
bm.free()

obj = bpy.data.objects.new(OBJ_NAME, mesh)
bpy.context.collection.objects.link(obj)

# 平らな部分をパンチング(穴あき)にする
cutter, n_holes = make_punch_cutter()
mod = obj.modifiers.new("Punching", 'BOOLEAN')
mod.operation = 'DIFFERENCE'
mod.object = cutter
mod.solver = 'EXACT'
bpy.context.view_layer.objects.active = obj
bpy.ops.object.modifier_apply(modifier=mod.name)
bpy.data.objects.remove(cutter, do_unlink=True)

# 金属っぽい質感
mat = bpy.data.materials.get("Shelf_Metal") or bpy.data.materials.new("Shelf_Metal")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.82, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.35
obj.data.materials.append(mat)

# 寸法をcmで表示する設定
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.length_unit = 'CENTIMETERS'

# 作った棚板を選択状態にする
for o in bpy.context.selected_objects:
    o.select_set(False)
obj.select_set(True)
bpy.context.view_layer.objects.active = obj

print("棚板を作成しました: 横{:.0f}cm × 奥行{:.0f}cm × 曲げ{:.0f}cm × 厚み{:.0f}mm × 穴{}個".format(
    W * 100, D * 100, H * 100, T * 1000, n_holes))
check_strength()
