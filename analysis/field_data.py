"""Export field data for the homepage (site/field.json).  run: python3 analysis/field_data.py"""
import json, os, sys, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import importlib.util
spec = importlib.util.spec_from_file_location('tf', os.path.join(os.path.dirname(__file__), 'tmr_field.py'))
src = open(spec.origin).read().split('rows = []')[0]
ns = {}; exec(src, ns)
field, TRAVEL, GAP, DIE = ns['field'], ns['TRAVEL'], ns['GAP_PRESSED'], ns['DIE']
out = {'travel': [], 'center_z': [], 'off_z': [], 'off_r': []}
for s in np.linspace(0, TRAVEL, 36):
    z = -(GAP + (TRAVEL - s) + DIE)
    b0, b1 = field(0, z), field(3.5, z)
    out['travel'].append(round(float(s), 3)); out['center_z'].append(round(abs(b0[2]) * 1e3, 2))
    out['off_z'].append(round(abs(b1[2]) * 1e3, 2)); out['off_r'].append(round(abs(b1[0]) * 1e3, 2))
# slope (last 0.5 mm) vs radial offset
sl = []
for r in np.arange(0, 6.01, 0.25):
    zp, zq = -(GAP + DIE), -(GAP + 0.5 + DIE)
    a, b = field(r, zp), field(r, zq)
    sl.append([round(float(r), 2), round(abs(a[2] - b[2]) / 0.5 * 1e3, 2), round(abs(a[0] - b[0]) / 0.5 * 1e3, 2)])
out['slope_vs_offset'] = sl
# field vectors in the r-z plane, key bottomed out; magnet bottom at z=0, sensor plane at z=-(GAP+DIE)
g = []
for z in np.arange(-8, 5.01, 0.5):
    for r in np.arange(-7, 7.01, 0.5):
        if -1.45 <= r <= 1.45 and 0 <= z <= 3.5: continue
        B = field(r, z); g.append([round(float(r), 2), round(float(z), 2), round(B[0] * 1e3, 2), round(B[2] * 1e3, 2)])
out['grid'] = g; out['sensor_z'] = -(GAP + DIE); out['pcb'] = [-GAP - 1.6, -GAP]
json.dump(out, open(os.path.join(os.path.dirname(__file__), '..', 'site', 'field.json'), 'w'))
print(sl[::4])
