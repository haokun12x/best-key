"""Magnetic field at the TMR sensor for an on-axis vs. 3.5 mm off-axis sensor position.
Model: axially magnetised cylinder (surface-charge model, numerically integrated).
Assumptions (typical centre-magnet HE switch, verify with your switch): magnet D2.9 x L3.5 mm, Br = 1.25 T,
magnet underside 0.6 mm above the PCB top when bottomed out, 3.5 mm travel, sensor die 2.1 mm below the PCB top
(1.6 mm PCB + 0.5 mm into the SOT-23).   run: python3 analysis/tmr_field.py"""
import numpy as np, os
Br, D, L = 1.25, 2.9, 3.5
GAP_PRESSED, TRAVEL, DIE = 0.6, 3.5, 2.1
OFFSET = 3.5

def field(r_obs, z_obs):
    """B (T) at (r_obs, 0, z_obs) from a cylinder whose bottom face is at z=0 and top at z=L (magnetised +z)."""
    n = 60
    rr = (np.arange(n) + 0.5) / n * D / 2
    th = (np.arange(2 * n) + 0.5) / (2 * n) * 2 * np.pi
    R, T = np.meshgrid(rr, th)
    dA = R * (D / 2 / n) * (2 * np.pi / (2 * n))
    xs, ys = R * np.cos(T), R * np.sin(T)
    B = np.zeros(3)
    for zf, sgn in ((L, 1.0), (0.0, -1.0)):          # +M on the top face, -M on the bottom face
        dx, dy, dz = r_obs - xs, -ys, z_obs - zf
        d3 = (dx * dx + dy * dy + dz * dz) ** 1.5
        k = sgn * Br / (4 * np.pi) * dA / d3
        B += np.array([(k * dx).sum(), (k * dy).sum(), (k * dz).sum()])
    return B

rows = []
for s in np.linspace(0, TRAVEL, 36):                 # s = key travel (0 = released)
    gap = GAP_PRESSED + (TRAVEL - s)                 # magnet underside above PCB top
    z = -(gap + DIE)                                 # sensor is below the magnet
    b0 = field(0.0, z); b1 = field(OFFSET, z)
    rows.append((s, abs(b0[2]) * 1e3, abs(b1[2]) * 1e3, abs(b1[0]) * 1e3))
rows = np.array(rows)
print('travel_mm  Bz_center_mT  Bz_offset_mT  Br_offset_mT')
for r in rows[::5]:
    print('  %4.2f      %7.2f       %7.2f       %7.2f' % tuple(r))
for name, col in (('Bz on-axis', 1), ('Bz @3.5mm', 2), ('Br(in-plane) @3.5mm', 3)):
    v = rows[:, col]; d = np.diff(v)
    mono = bool((d > 0).all() or (d < 0).all())
    print('%-22s span %.2f -> %.2f mT (x%.1f)  monotonic=%s  slope in last 0.5 mm: %.2f mT/mm' %
          (name, v[0], v[-1], v[-1] / v[0], mono, (v[-1] - v[-6]) / (rows[-1, 0] - rows[-6, 0])))
# SVG plot
W, H, m = 640, 360, 50
vmax = rows[:, 1:].max()
def px(s, v): return m + s / TRAVEL * (W - 2 * m), H - m - v / vmax * (H - 2 * m)
svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" font-family="sans-serif" font-size="12">' % (W, H),
       '<rect width="100%" height="100%" fill="white"/>',
       '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="black"/><line x1="%d" y1="%d" x2="%d" y2="%d" stroke="black"/>' % (m, H - m, W - m, H - m, m, m, m, H - m),
       '<text x="%d" y="%d" text-anchor="middle">key travel (mm, 0 = released)</text>' % (W / 2, H - 12),
       '<text x="14" y="%d" transform="rotate(-90 14 %d)" text-anchor="middle">|B| at sensor (mT)</text>' % (H / 2, H / 2)]
for i in range(5):
    v = vmax * i / 4; x, y = px(0, v)
    svg.append('<text x="%d" y="%.0f" text-anchor="end">%.0f</text>' % (m - 6, y + 4, v))
    s = TRAVEL * i / 4; x, y = px(s, 0)
    svg.append('<text x="%.0f" y="%d" text-anchor="middle">%.1f</text>' % (x, H - m + 16, s))
for (name, col, color) in (('Bz, sensor on axis (HE-only boards)', 1, '#888'), ('Bz, sensor 3.5 mm off axis (this board, TMR2617S)', 2, '#d33'), ('B in-plane, 3.5 mm off axis (alt. in-plane sensor)', 3, '#36c')):
    pts = ' '.join('%.1f,%.1f' % px(r[0], r[col]) for r in rows)
    svg.append('<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>' % (color, pts))
    svg.append('<text x="%d" y="%d" fill="%s">%s</text>' % (m + 12, m + 16 * col, color, name))
svg.append('</svg>')
open(os.path.join(os.path.dirname(__file__), 'tmr_field.svg'), 'w').write('\n'.join(svg))
