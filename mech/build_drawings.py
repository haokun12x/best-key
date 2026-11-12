"""2D fabrication drawings (DXF, mm, same origin as params.py) + a dimensioned stack-up section (SVG).
run: .venv/bin/python mech/build_drawings.py"""
import os, sys
import ezdxf
import cadquery as cq
sys.path.insert(0, os.path.dirname(__file__))
from params import *
import build_case as bc
OUT = os.path.join(os.path.dirname(__file__), 'out', 'drawings')
os.makedirs(OUT, exist_ok=True)


def section_dxf(solid, z, name):
    w = cq.Workplane('XY').workplane(offset=z).add(solid).section()
    cq.exporters.exportDXF(w, os.path.join(OUT, name))


section_dxf(bc.make_plate(), (PLATE_Z0 + PLATE_Z1) / 2, '01_plate_1.5mm.dxf')
section_dxf(bc.make_bezel(), SPLIT_Z + 2.0, '02_bezel_top_view.dxf')
tub = bc.make_tub()
section_dxf(tub, FLOOR_T + 3.0, '03_tub_section_z4.6.dxf')
section_dxf(tub, 0.3, '04_tub_floor_holes.dxf')


def new():
    d = ezdxf.new('R2010'); d.units = ezdxf.units.MM
    return d, d.modelspace()


def rect(m, x0, y0, x1, y1, layer='0'):
    m.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={'layer': layer})


# gasket strips: Poron 1.5 mm thick, 1.5 mm wide, stuck on BOTH faces of the plate flange at these places
d, m = new()
rect(m, -PLATE_OVER, -PLATE_OVER, FIELD_W + PLATE_OVER, FIELD_H + PLATE_OVER, 'plate_outline_ref')
n = 0
for cx, L in SEATS_FRONT:
    rect(m, cx - L / 2, -PLATE_OVER, cx + L / 2, -PLATE_OVER + GASKET_W, 'gasket'); n += 1
for cx, L in SEATS_BACK:
    rect(m, cx - L / 2, FIELD_H + PLATE_OVER - GASKET_W, cx + L / 2, FIELD_H + PLATE_OVER, 'gasket'); n += 1
for cy, L in SEATS_LEFT:
    rect(m, -PLATE_OVER, cy - L / 2, -PLATE_OVER + GASKET_W, cy + L / 2, 'gasket'); n += 1
for cy, L in SEATS_RIGHT:
    rect(m, FIELD_W + PLATE_OVER - GASKET_W, cy - L / 2, FIELD_W + PLATE_OVER, cy + L / 2, 'gasket'); n += 1
d.saveas(os.path.join(OUT, '05_gasket_positions_x2.dxf'))

# plate foam (between plate and PCB, 3.0-3.5 mm Poron/EVA): switch openings 14.5 mm
d, m = new()
rect(m, 0.8, 0.8, FIELD_W - 0.8, FIELD_H - 0.8, 'outline')
for c, r in KEYS:
    cx, cy = cell_center(c, r)
    rect(m, cx - 7.25, cy - 7.25, cx + 7.25, cy + 7.25, 'cut')
for kx, ky in KNOBS:
    m.add_circle((kx, ky), KNOB_PLATE_R + 0.5, dxfattribs={'layer': 'cut'})
for sx, sy in STANDOFFS:
    m.add_circle((sx, sy), 2.2, dxfattribs={'layer': 'cut'})
d.saveas(os.path.join(OUT, '06_plate_foam_3mm.dxf'))

# floor layout: where battery, Qi coil, display and knob boards sit (reference for assembly, also a 1 mm case-foam template)
d, m = new()
rect(m, CAV_X0, CAV_Y0, CAV_X1, CAV_Y1, 'cavity')
for nm, q in (('battery', BATT), ('qi_coil', QI)):
    rect(m, q['x'] - q['w'] / 2, q['y'] - q['d'] / 2, q['x'] + q['w'] / 2, q['y'] + q['d'] / 2, nm)
    m.add_text(nm, dxfattribs={'height': 3, 'layer': nm}).set_placement((q['x'] - q['w'] / 2 + 2, q['y']))
for i, (kx, ky) in enumerate(KNOBS):
    m.add_circle((kx, ky), MOTOR_D / 2, dxfattribs={'layer': 'motor'})
    x0, x1, y0, y1 = KNOB_PCB_TAIL
    xa, xb = sorted((bc.mx(x0, i), bc.mx(x1, i)))
    rect(m, xa, y0, xb, y1, 'knob_pcb')
rect(m, DISP_X - DISP_W / 2, Y0 + DISP_SKIN, DISP_X + DISP_W / 2, Y0 + DISP_SKIN + DISP_T, 'display')
rect(m, USB_X - 4.5, CAV_Y1 - 6, USB_X + 4.5, Y1, 'usb')
d.saveas(os.path.join(OUT, '07_floor_layout.dxf'))

# ---------------- stack-up section (through a key column, looking from the left) ----------------
S = 22
layers = [('tub floor', 0, FLOOR_T, '#59606b'), ('cavity: battery 3.2 / Qi coil 1.3 / sockets 1.85', FLOOR_T, PCB_Z0, '#eef2f6'),
          ('main PCB 1.6 (4-layer)', PCB_Z0, PCB_Z1, '#2e7d4f'), ('switch lower housing / plate foam 3.5', PCB_Z1, PLATE_Z0, '#f4ecd6'),
          ('plate 1.5 (FR4 / PC / Al)', PLATE_Z0, PLATE_Z1, '#c9a84c'), ('bezel 15.0 - 19.8', SPLIT_Z, BEZEL_TOP, '#7a828e')]
Wd, Hd = 760, int((KNOB_Z1 + 6) * S)
yz = lambda z: Hd - 40 - z * S
sv = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" font-family="sans-serif" font-size="13">' % (Wd, Hd), '<rect width="100%" height="100%" fill="white"/>']
x0, wall, inner = 60, WALL * S, 150
sv.append('<rect x="%d" y="%.1f" width="%.1f" height="%.1f" fill="#59606b"/>' % (x0, yz(SPLIT_Z), wall, SPLIT_Z * S))       # tub wall
sv.append('<rect x="%d" y="%.1f" width="%.1f" height="%.1f" fill="#7a828e"/>' % (x0, yz(BEZEL_TOP), (M_OUT - 0.5) * S, (BEZEL_TOP - SPLIT_Z) * S))
sv.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#59606b"/>' % (x0 + wall, yz(LEDGE_Z), SEAT_D * S, (LEDGE_Z - FLOOR_T) * S))   # gasket seat
for z0, z1 in ((LEDGE_Z, PLATE_Z0), (PLATE_Z1, SPLIT_Z)):
    sv.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#e2574c"/>' % (x0 + (M_OUT - PLATE_OVER) * S, yz(z1), GASKET_W * S, (z1 - z0) * S))
for name, z0, z1, col in layers[:5]:
    xa = x0 if z0 == 0 else x0 + (M_OUT - (PLATE_OVER if 'plate 1.5' in name else -0.3 if 'PCB' in name else 0)) * S
    if 'cavity' in name or 'housing' in name:
        xa = x0 + (M_OUT + 0.3) * S
    sv.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" stroke="#333" stroke-width="0.5"/>' % (xa, yz(z1), x0 + 330 - xa, (z1 - z0) * S, col))
for name, z0, z1, col in layers:
    sv.append('<text x="%d" y="%.1f">%s</text>' % (x0 + 345, yz((z0 + z1) / 2) + 4, name))
for z in (0, FLOOR_T, PCB_Z0, PCB_Z1, LEDGE_Z, PLATE_Z0, PLATE_Z1, SPLIT_Z, BEZEL_TOP):
    sv.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#999" stroke-dasharray="3 3"/><text x="8" y="%.1f">%.1f</text>' % (40, yz(z), x0 + 335, yz(z), yz(z) + 4, z))
sv.append('<text x="%d" y="%.1f" fill="#e2574c">gasket 1.5 Poron, compressed to 1.2 (both faces)</text>' % (x0 + 345, yz(SPLIT_Z) + 18))
sv.append('<text x="%d" y="22" font-size="15">BK46 stack-up section at the front wall (Z in mm from the underside; keycap/knob top = %.1f)</text>' % (x0, KNOB_Z1))
sv.append('</svg>')
open(os.path.join(OUT, '00_stackup_section.svg'), 'w').write('\n'.join(sv))
print('drawings written:', sorted(os.listdir(OUT)), 'gasket strips per face:', n)
