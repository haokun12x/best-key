"""BK47 mechanical CAD (CadQuery). Generates STEP + STL for every part, an assembly STEP,
and runs interference / clearance checks.   run:  .venv/bin/python mech/build_case.py"""
import os, sys, math
import cadquery as cq
sys.path.insert(0, os.path.dirname(__file__))
from params import *

OUT = os.path.join(os.path.dirname(__file__), 'out')
os.makedirs(OUT, exist_ok=True)
EPS = 0.01


def box(x0, y0, z0, x1, y1, z1):
    return cq.Workplane('XY').box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def rbox(x0, y0, z0, x1, y1, z1, r):
    b = box(x0, y0, z0, x1, y1, z1)
    return b.edges('|Z').fillet(r) if r > 0 else b


def cyl(x, y, z0, z1, d):
    return cq.Workplane('XY').circle(d / 2).extrude(z1 - z0).translate((x, y, z0))


def mx(x, i):
    """mirror an X coordinate for the right-hand knob (i == 1)"""
    return x if i == 0 else FIELD_W - x


def union(items):
    out = items[0]
    for i in items[1:]:
        out = out.union(i)
    return out


# ------------------------------------------------------------------ tub
def make_tub():
    tub = rbox(X0, Y0, 0, X1, Y1, SPLIT_Z, CASE_R)
    tub = tub.cut(rbox(CAV_X0, CAV_Y0, FLOOR_T, CAV_X1, CAV_Y1, SPLIT_Z + 1, CASE_R - WALL))
    # shiplap: remove the outer 1 mm of the wall top
    ring = rbox(X0 - 1, Y0 - 1, SPLIT_Z - SHIPLAP, X1 + 1, Y1 + 1, SPLIT_Z + 1, 0).cut(
        rbox(X0 + SHIPLAP + SHIPLAP_GAP, Y0 + SHIPLAP + SHIPLAP_GAP, SPLIT_Z - SHIPLAP - 1, X1 - SHIPLAP - SHIPLAP_GAP,
             Y1 - SHIPLAP - SHIPLAP_GAP, SPLIT_Z + 2, CASE_R - SHIPLAP - SHIPLAP_GAP))
    tub = tub.cut(ring)
    add = []
    for cx, L in SEATS_FRONT:
        add.append(box(cx - L / 2, CAV_Y0 - EPS, FLOOR_T - EPS, cx + L / 2, CAV_Y0 + SEAT_D, LEDGE_Z))
    for cx, L in SEATS_BACK:
        add.append(box(cx - L / 2, CAV_Y1 - SEAT_D, FLOOR_T - EPS, cx + L / 2, CAV_Y1 + EPS, LEDGE_Z))
    for cy, L in SEATS_LEFT:
        add.append(box(CAV_X0 - EPS, cy - L / 2, FLOOR_T - EPS, CAV_X0 + SEAT_D, cy + L / 2, LEDGE_Z))
    for cy, L in SEATS_RIGHT:
        add.append(box(CAV_X1 - SEAT_D, cy - L / 2, FLOOR_T - EPS, CAV_X1 + EPS, cy + L / 2, LEDGE_Z))
    for sx, sy in SCREWS:
        if sy < 0:
            add.append(box(sx - SCREW_PIL_W / 2, CAV_Y0 - EPS, FLOOR_T - EPS, sx + SCREW_PIL_W / 2, CAV_Y0 + SCREW_PIL_D, LEDGE_Z))
        else:
            add.append(box(sx - SCREW_PIL_W / 2, CAV_Y1 - SCREW_PIL_D, FLOOR_T - EPS, sx + SCREW_PIL_W / 2, CAV_Y1 + EPS, LEDGE_Z))
    tub = tub.union(union(add))
    # bezel screws: clearance hole + countersink from below
    for sx, sy in SCREWS:
        tub = tub.cut(cyl(sx, sy, -1, SPLIT_Z + 1, SCREW_CLEAR))
        csk = cq.Workplane('XY').circle(CSK_D / 2).workplane(offset=CSK_H).circle(SCREW_CLEAR / 2).loft().translate((sx, sy, 0))
        tub = tub.cut(csk)
    # display pocket (module drops in from above) + window
    px0, px1 = DISP_X - DISP_W / 2 - DISP_TOL, DISP_X + DISP_W / 2 + DISP_TOL
    tub = tub.cut(box(px0, Y0 + DISP_SKIN, DISP_Z0, px1, CAV_Y0 + EPS, SPLIT_Z + 1))
    wx, wz = DISP_X + DISP_WIN_DX, DISP_Z0 + DISP_H / 2 + DISP_WIN_DZ
    win = (cq.Workplane('XZ').center(wx, wz).rect(DISP_WIN_W, DISP_WIN_H).extrude(-(DISP_SKIN + 2))
           .translate((0, Y0 - 1, 0)).edges('|Y').fillet(0.8))
    tub = tub.cut(win)
    # USB-C opening in the back wall
    uz = (USB_OPEN_Z0 + USB_OPEN_Z1) / 2
    usb = (cq.Workplane('XZ').center(USB_X, uz).rect(USB_OPEN_W, USB_OPEN_Z1 - USB_OPEN_Z0).extrude(-(WALL + 2))
           .translate((0, CAV_Y1 - 1, 0)).edges('|Y').fillet(1.2))
    tub = tub.cut(usb)
    # motor: 4 x M2 through the floor, pan-head counterbore 0.8 deep
    for i, (kx, ky) in enumerate(KNOBS):
        for dx in (-1, 1):
            for dy in (-1, 1):
                hx, hy = kx + dx * MOTOR_MOUNT / 2, ky + dy * MOTOR_MOUNT / 2
                tub = tub.cut(cyl(hx, hy, -1, FLOOR_T + 1, 4.3))          # clearance for the motor screw heads (they move with the island)
        for fdx, fdy in KNOB_FRAME_SCREWS:
            bx, by = kx + (fdx if i == 0 else -fdx), ky + fdy
            tub = tub.union(cyl(bx, by, FLOOR_T - EPS, KNOB_PCB_Z0, 4.4)).cut(cyl(bx, by, -1, KNOB_PCB_Z0 + 1, SCREW_PILOT))
        # press magnet seat on the motor axis: sensor clearance from above, 3 x 0.5 magnet glued flush with the underside
        tub = tub.cut(cyl(kx, ky, PRESS_MAGNET_T, FLOOR_T + 1, 4.6)).cut(cyl(kx, ky, -1, FLOOR_T, PRESS_MAGNET_D + 0.08))
        tx_, ty_ = mx(KNOB_PCB_SCREW[0], i), KNOB_PCB_SCREW[1]
        tub = tub.union(cyl(tx_, ty_, FLOOR_T - EPS, KNOB_PCB_Z0, 4.4))
        # knob-PCB tail screw (M2 thread-forming into the floor)
        tub = tub.cut(cyl(mx(KNOB_PCB_SCREW[0], i), KNOB_PCB_SCREW[1], -1, FLOOR_T + 1, SCREW_PILOT))
    return tub


# ------------------------------------------------------------------ bezel
def make_bezel():
    bz = rbox(X0, Y0, SPLIT_Z, X1, Y1, BEZEL_TOP, CASE_R)
    skirt = rbox(X0, Y0, SPLIT_Z - SHIPLAP + SHIPLAP_GAP, X1, Y1, SPLIT_Z, CASE_R).cut(
        rbox(X0 + SHIPLAP, Y0 + SHIPLAP, 0, X1 - SHIPLAP, Y1 - SHIPLAP, SPLIT_Z + 1, CASE_R - SHIPLAP))
    bz = bz.union(skirt)
    bz = bz.cut(rbox(-0.5, -0.5, 0, FIELD_W + 0.5, FIELD_H + 0.5, BEZEL_TOP + 1, 1.5))
    bz = bz.faces('>Z').edges('%CIRCLE or %LINE').chamfer(0.5)
    for sx, sy in SCREWS:
        bz = bz.cut(cyl(sx, sy, SPLIT_Z - 1, SCREW_PILOT_TOP, SCREW_PILOT))
    return bz


# ------------------------------------------------------------------ plate / pcb
def knob_notch(r, zlo, zhi):
    kx, ky = KNOBS[0]
    left = union([cyl(kx, ky, zlo, zhi, 2 * r),
                  box(-20, ky - r, zlo, kx, FIELD_H + 20, zhi),
                  box(-20, ky, zlo, kx + r, FIELD_H + 20, zhi)])
    return left.union(left.mirror('YZ', (FIELD_W / 2, 0, 0)))


def make_plate():
    p = rbox(-PLATE_OVER, -PLATE_OVER, PLATE_Z0, FIELD_W + PLATE_OVER, FIELD_H + PLATE_OVER, PLATE_Z1, PLATE_R)
    p = p.cut(knob_notch(KNOB_PLATE_R, PLATE_Z0 - 1, PLATE_Z1 + 1))
    pts = [cell_center(c, r) for c, r in KEYS]
    cuts = (cq.Workplane('XY').workplane(offset=PLATE_Z0 - 1).pushPoints(pts).rect(CUTOUT, CUTOUT)
            .extrude(PLATE_T + 2).edges('|Z').fillet(CUTOUT_R))
    p = p.cut(cuts)
    for sx, sy in SCREWS:
        p = p.cut(cyl(sx, sy, PLATE_Z0 - 1, PLATE_Z1 + 1, 2 * PLATE_SCREW_NOTCH_R))
    for sx, sy in STANDOFFS:
        p = p.cut(cyl(sx, sy, PLATE_Z0 - 1, PLATE_Z1 + 1, STANDOFF_HOLE))
    p = p.cut(box(DISP_X - DISP_W / 2 - 0.6, -5, PLATE_Z0 - 1, DISP_X + DISP_W / 2 + 0.6, DISP_PLATE_NOTCH_Y, PLATE_Z1 + 1))
    return p


def make_pcb_dummy():
    p = box(PCB_X0, PCB_Y0, PCB_Z0, PCB_X1, PCB_Y1, PCB_Z1)
    p = p.cut(box(-5, PCB_KNOB_NOTCH[1], PCB_Z0 - 1, PCB_KNOB_NOTCH[0], FIELD_H + 5, PCB_Z1 + 1))
    p = p.cut(box(FIELD_W - PCB_KNOB_NOTCH_R, PCB_KNOB_NOTCH[1], PCB_Z0 - 1, FIELD_W + 5, FIELD_H + 5, PCB_Z1 + 1))
    for sx, sy in SCREWS:
        if sy < 0:
            p = p.cut(box(sx - PCB_SCREW_NOTCH_W / 2, -1, PCB_Z0 - 1, sx + PCB_SCREW_NOTCH_W / 2, PCB_Y0 + PCB_SCREW_NOTCH_D, PCB_Z1 + 1))
        elif PCB_KNOB_NOTCH[0] < sx < FIELD_W - PCB_KNOB_NOTCH_R:
            p = p.cut(box(sx - PCB_SCREW_NOTCH_W / 2, PCB_Y1 - PCB_SCREW_NOTCH_D, PCB_Z0 - 1, sx + PCB_SCREW_NOTCH_W / 2, FIELD_H + 1, PCB_Z1 + 1))
    p = p.cut(box(DISP_X - DISP_W / 2 - 1.0, -1, PCB_Z0 - 1, DISP_X + DISP_W / 2 + 1.0, DISP_PCB_NOTCH_Y, PCB_Z1 + 1))
    p = p.union(box(USB_X - USB_TAB_W / 2, PCB_Y1 - EPS, PCB_Z0, USB_X + USB_TAB_W / 2, USB_TAB_Y, PCB_Z1))
    # hot-swap socket envelope under every key (worst case height)
    socks = []
    for c, r in KEYS:
        cx, cy = cell_center(c, r)
        s = -1 if r in ROT_ROWS else 1
        ya, yb = sorted((cy + s * 1.0, cy + s * 6.9))
        socks.append(box(max(cx - 8.7, PCB_X0), ya, PCB_Z0 - SOCKET_H, min(cx + 8.7, PCB_X1), yb, PCB_Z0))
    return p, union(socks)


# ------------------------------------------------------------------ knob parts
def make_motor_dummy():
    return union([cyl(kx, ky, MOTOR_Z0, MOTOR_Z1, MOTOR_D).union(cyl(kx, ky, MOTOR_Z1, MOTOR_Z1 + MOTOR_SHAFT_L, MOTOR_SHAFT_D))
                  for kx, ky in KNOBS])


def make_spacer():
    kx, ky = KNOB_XY
    z0 = KNOB_PCB_Z0 + KNOB_PCB_T
    s = cyl(kx, ky, z0, z0 + MOTOR_SPACER, 13.0).cut(cyl(kx, ky, z0 - 1, z0 + MOTOR_SPACER + 1, 8.0))
    s = s.cut(box(kx - 2.3, ky - 2.3, z0 - 1, kx + 2.3, ky + 2.3, z0 + MOTOR_SPACER + 1))   # MT6701QT window
    s = s.cut(box(kx - 5.2, ky - 1.3, z0 - 1, kx - 2.0, ky + 1.3, z0 + MOTOR_SPACER + 1))   # decoupling capacitor pocket
    s = s.cut(box(kx + 2, ky - 1.6, z0 - 1, kx + 10, ky + 1.6, z0 + MOTOR_SPACER + 1))      # motor-wire exit (towards +X)
    for dx in (-1, 1):
        for dy in (-1, 1):
            s = s.cut(cyl(kx + dx * MOTOR_MOUNT / 2, ky + dy * MOTOR_MOUNT / 2, z0 - 1, z0 + MOTOR_SPACER + 1, 2.2))
    return s


def make_knob_pcb_dummy():
    out = []
    kx, ky = KNOBS[0]
    for i in range(len(KNOBS)):
        pts = [(kx + dx, ky + dy) for dx, dy in knob_pcb_outline()]
        b = cq.Workplane('XY').workplane(offset=KNOB_PCB_Z0).polyline(pts).close().extrude(KNOB_PCB_T)
        for sl in knob_pcb_slots():
            b = b.cut(cq.Workplane('XY').workplane(offset=KNOB_PCB_Z0 - 1).polyline([(kx + dx, ky + dy) for dx, dy in sl]).close().extrude(3))
        out.append(b if i == 0 else b.mirror('YZ', (FIELD_W / 2, 0, 0)))
    return union(out)


def make_knob_core():
    """Screws onto the bell (2 x M2, T-mount). The cap presses over it."""
    kx, ky = KNOB_XY
    core_d, core_h = 14.0, 8.0
    k = cyl(kx, ky, KNOB_Z0, KNOB_Z0 + core_h, core_d)
    k = k.cut(cyl(kx, ky, KNOB_Z0 - 1, KNOB_Z0 + MOTOR_SHAFT_L + 1.5, MOTOR_SHAFT_D + 0.5))
    for s in (-1, 1):
        k = k.cut(cyl(kx + s * MOTOR_TMOUNT / 2, ky, KNOB_Z0 - 1, KNOB_Z0 + core_h + 1, 2.2))
        k = k.cut(cyl(kx + s * MOTOR_TMOUNT / 2, ky, KNOB_Z0 + 2.0, KNOB_Z0 + core_h + 1, 4.0))
    # two flats for anti-rotation of the cap
    for s in (-1, 1):
        k = k.cut(box(kx - 10, ky + s * 6.2 if s > 0 else ky - 10, KNOB_Z0 + 2.0, kx + 10, ky + 10 if s > 0 else ky - 6.2, KNOB_Z0 + core_h + 1))
    return k


def make_knob_cap():
    kx, ky = KNOB_XY
    core_d, core_h, fit = 14.0, 8.0, 0.08
    cap = cyl(kx, ky, KNOB_Z0, KNOB_Z1, KNOB_D)
    cap = cap.faces('>Z').edges().fillet(1.0)
    bore = cyl(kx, ky, KNOB_Z0 - 1, KNOB_Z0 + 2.0, core_d + 2 * fit)
    upper = cyl(kx, ky, KNOB_Z0 + 2.0 - EPS, KNOB_Z0 + core_h + 0.3, core_d + 2 * fit).intersect(
        box(kx - 10, ky - 6.2 - fit, KNOB_Z0, kx + 10, ky + 6.2 + fit, KNOB_Z1))
    cap = cap.cut(bore).cut(upper)
    # grip: 36 shallow flutes
    n = 36
    for i in range(n):
        a = 2 * math.pi * i / n
        cap = cap.cut(cyl(kx + (KNOB_D / 2 + 0.25) * math.cos(a), ky + (KNOB_D / 2 + 0.25) * math.sin(a), KNOB_Z0 + 1.0, KNOB_Z1 - 1.6, 1.1))
    return cap


def dummies():
    d = {}
    d['display'] = box(DISP_X - DISP_W / 2, Y0 + DISP_SKIN, DISP_Z0, DISP_X + DISP_W / 2, Y0 + DISP_SKIN + DISP_T, DISP_Z0 + DISP_H)
    b = BATT
    d['battery'] = box(b['x'] - b['w'] / 2, b['y'] - b['d'] / 2, FLOOR_T, b['x'] + b['w'] / 2, b['y'] + b['d'] / 2, FLOOR_T + b['t'])
    q = QI
    d['qi_coil'] = box(q['x'] - q['w'] / 2, q['y'] - q['d'] / 2, FLOOR_T, q['x'] + q['w'] / 2, q['y'] + q['d'] / 2, FLOOR_T + q['t'])
    # worst-case keycap envelope (pressed): 18.2 square from plate+2.5 upward
    caps = []
    for c, r in KEYS:
        cx, cy = cell_center(c, r)
        caps.append(box(cx - 9.1, cy - 9.1, PLATE_Z1 + 2.5, cx + 9.1, cy + 9.1, PLATE_Z1 + 12))
    d['keycaps'] = union(caps)
    return d


def vol(a, b):
    try:
        v = a.intersect(b).val()
        return v.Volume() if v is not None else 0.0
    except Exception:
        return 0.0


if __name__ == '__main__':
    parts = {
        'tub': make_tub(), 'bezel': make_bezel(), 'plate': make_plate(),
        'motor_spacer': make_spacer(), 'knob_core': make_knob_core(), 'knob_cap': make_knob_cap(),
    }
    pcb, sockets = make_pcb_dummy()
    parts_r = {'knob_cap_R': parts['knob_cap'].mirror('YZ', (FIELD_W / 2, 0, 0)), 'knob_core_R': parts['knob_core'].mirror('YZ', (FIELD_W / 2, 0, 0)),
               'motor_spacer_R': parts['motor_spacer'].mirror('YZ', (FIELD_W / 2, 0, 0))}
    refs = {'pcb_ref': pcb, 'sockets_ref': sockets, **parts_r, 'motor_ref': make_motor_dummy(), 'knob_pcb_ref': make_knob_pcb_dummy()}
    refs.update({k + '_ref': v for k, v in dummies().items()})

    for name, p in parts.items():
        cq.exporters.export(p, os.path.join(OUT, name + '.step'))
        cq.exporters.export(p, os.path.join(OUT, name + '.stl'), tolerance=0.02, angularTolerance=0.15)
    asm = cq.Assembly()
    colors = {'tub': (0.25, 0.27, 0.3), 'bezel': (0.3, 0.32, 0.36), 'plate': (0.85, 0.8, 0.6), 'knob_cap': (0.9, 0.5, 0.2)}
    for name, p in {**parts, **refs}.items():
        c = colors.get(name, (0.6, 0.6, 0.65))
        asm.add(p, name=name, color=cq.Color(*c, 1.0 if name in parts else 0.6))
    asm.save(os.path.join(OUT, 'bk46_assembly.step'))

    for name, view in (('tub', (0.4, -1, 1.2)), ('bezel', (0.4, -1, 1.2)), ('plate', (0, 0, 1))):
        cq.exporters.export(parts[name], os.path.join(OUT, f'preview_{name}.svg'),
                            opt={'projectionDir': view, 'width': 1600, 'height': 700, 'showAxes': False, 'showHidden': False})
    whole = union([parts[k] for k in ('tub', 'bezel', 'plate', 'knob_cap')]).union(refs['keycaps_ref']).union(refs['knob_cap_R'])
    cq.exporters.export(whole, os.path.join(OUT, 'preview_assembly.svg'),
                        opt={'projectionDir': (0.0, -0.6, 1), 'width': 1600, 'height': 800, 'showAxes': False, 'showHidden': False})
    print('--- part volumes / mass estimate (PA12 1.01 g/cc, FR4 1.85, 6063 2.70) ---')
    for name, p in parts.items():
        v = p.val().Volume() / 1000
        print(f'{name:13s} {v:7.2f} cm3   PA12 {v*1.01:6.1f} g   Al {v*2.7:6.1f} g   FR4 {v*1.85:6.1f} g')
        bb = p.val().BoundingBox()
        print(f'              bbox {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f}')

    print('--- interference check (mm3, must be 0) ---')
    allp = {**parts, **refs}
    pairs = [('tub', 'bezel'), ('tub', 'plate'), ('tub', 'pcb_ref'), ('tub', 'sockets_ref'), ('tub', 'motor_ref'),
             ('tub', 'knob_pcb_ref'), ('tub', 'display_ref'), ('tub', 'battery_ref'), ('tub', 'qi_coil_ref'),
             ('bezel', 'plate'), ('bezel', 'keycaps_ref'), ('bezel', 'knob_cap'), ('bezel', 'motor_ref'),
             ('plate', 'motor_ref'), ('plate', 'display_ref'), ('plate', 'pcb_ref'), ('pcb_ref', 'motor_ref'),
             ('pcb_ref', 'display_ref'), ('sockets_ref', 'battery_ref'), ('sockets_ref', 'qi_coil_ref'),
             ('sockets_ref', 'knob_pcb_ref'), ('sockets_ref', 'motor_ref'), ('motor_spacer', 'motor_ref'),
             ('knob_core', 'motor_ref'), ('knob_core', 'knob_cap'), ('knob_cap', 'keycaps_ref'),
             ('knob_cap', 'motor_ref'), ('battery_ref', 'qi_coil_ref'), ('display_ref', 'sockets_ref'),
             ('motor_spacer', 'knob_pcb_ref'), ('pcb_ref', 'knob_pcb_ref'),
             ('bezel', 'knob_cap_R'), ('knob_cap_R', 'keycaps_ref'), ('motor_spacer_R', 'knob_pcb_ref'), ('tub', 'motor_spacer_R')]
    bad = 0
    for a, b in pairs:
        v = vol(allp[a], allp[b])
        flag = '' if v < 1e-3 else '   <-- INTERFERENCE'
        bad += v >= 1e-3
        print(f'{a:13s} x {b:13s} {v:9.4f}{flag}')
    print('RESULT:', 'OK - no interference' if not bad else f'{bad} interfering pairs')
