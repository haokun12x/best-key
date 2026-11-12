"""Route the open connections of a board with Freerouting and import the result (own SES importer).
usage: tools/kpy.sh tools/freeroute.py in.kicad_pcb out.kicad_pcb [passes] [--zones NET:LAYER,NET:LAYER...]"""
import os, sys, subprocess, glob, re
import pcbnew
src, dst = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
passes = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else '50'
zones = [a.split('=', 1)[1] for a in sys.argv if a.startswith('--zones=')]
mm = pcbnew.FromMM
base = dst[:-len('.kicad_pcb')]
dsn, ses = base + '.dsn', base + '.ses'
pro = src[:-len('.kicad_pcb')] + '.kicad_pro'
assert os.path.exists(pro), 'design rules (.kicad_pro) must sit next to the input board'
b = pcbnew.LoadBoard(src)
assert pcbnew.ExportSpecctraDSN(b, dsn), 'DSN export failed'
here = os.path.dirname(os.path.abspath(__file__))
jar = sorted(glob.glob(os.path.join(here, 'freerouting', '*.jar')))[-1]
java = '/opt/homebrew/opt/openjdk/bin/java'
if os.path.exists(ses):
    os.remove(ses)
r = subprocess.run([java, '-jar', jar, '-de', dsn, '-do', ses, '-mp', passes, '--gui.enabled=false'], capture_output=True, text=True)
m_ = re.findall(r'\((\d+) unrouted', r.stdout)
print('UNROUTED', m_[-1] if m_ else '?')
for line in r.stdout.splitlines():
    if 'Auto-routing stage completed' in line or 'optimiz' in line.lower():
        print(line[-260:])
assert os.path.exists(ses), 'Freerouting produced no session file\n' + r.stdout[-2000:] + r.stderr[-2000:]

# ---- minimal Specctra session parser
tok = re.findall(r'"[^"]*"|\(|\)|[^\s()]+', open(ses).read())
pos = 0


def parse():
    global pos
    out = []
    while pos < len(tok):
        t = tok[pos]; pos += 1
        if t == '(':
            out.append(parse())
        elif t == ')':
            return out
        else:
            out.append(t.strip('"'))
    return out


tree = parse()[0]


def find(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


routes = find(tree, 'routes')[0]
res = find(routes, 'resolution')[0]
scale = {'um': 1e-3, 'mm': 1.0, 'mil': 0.0254, 'inch': 25.4}[res[1]] / float(res[2])       # -> mm
nt = nv = 0
r3 = lambda v: round(pcbnew.ToMM(v), 3)
have_t, have_v = set(), set()
for t in b.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        have_v.add((r3(t.GetPosition().x), r3(t.GetPosition().y)))
    else:
        a_, c_ = (r3(t.GetStart().x), r3(t.GetStart().y)), (r3(t.GetEnd().x), r3(t.GetEnd().y))
        have_t.add((t.GetLayer(), min(a_, c_), max(a_, c_)))
for netn in find(find(routes, 'network_out')[0], 'net'):
    net = b.FindNet(netn[1])
    assert net is not None, netn[1]
    for w in find(netn, 'wire'):
        for p in find(w, 'path'):
            layer, width, xy = b.GetLayerID(p[1]), float(p[2]) * scale, [float(v) * scale for v in p[3:]]
            pts = list(zip(xy[0::2], xy[1::2]))
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                a_, c_ = (round(xa, 3), round(-ya, 3)), (round(xb, 3), round(-yb, 3))
                if (layer, min(a_, c_), max(a_, c_)) in have_t:
                    continue
                t = pcbnew.PCB_TRACK(b)
                t.SetStart(pcbnew.VECTOR2I(mm(xa), mm(-ya))); t.SetEnd(pcbnew.VECTOR2I(mm(xb), mm(-yb)))
                t.SetWidth(mm(width)); t.SetLayer(layer); t.SetNet(net); b.Add(t); nt += 1
    for v in find(netn, 'via'):
        m = re.search(r'_(\d+):(\d+)_um', v[1])
        d, dr = (int(m.group(1)) / 1000, int(m.group(2)) / 1000) if m else (0.6, 0.3)
        if (round(float(v[2]) * scale, 3), round(-float(v[3]) * scale, 3)) in have_v:
            continue
        via = pcbnew.PCB_VIA(b)
        via.SetPosition(pcbnew.VECTOR2I(mm(float(v[2]) * scale), mm(-float(v[3]) * scale)))
        via.SetDrill(mm(dr)); via.SetWidth(pcbnew.F_Cu, mm(d)); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetNet(net); b.Add(via); nv += 1
for spec in zones:
    for item in spec.split(','):
        n, lay = item.split(':')
        z = pcbnew.ZONE(b); z.SetLayer(b.GetLayerID(lay)); z.SetNet(b.FindNet(n))
        bb = b.GetBoardEdgesBoundingBox()
        ol = z.Outline(); ol.NewOutline()
        for x, y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetTop()), (bb.GetRight(), bb.GetBottom()), (bb.GetLeft(), bb.GetBottom())):
            ol.Append(x, y)
        z.SetLocalClearance(mm(0.25)); z.SetMinThickness(mm(0.2)); z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS); b.Add(z)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
protxt = open(pro).read()
pcbnew.SaveBoard(dst, b)
open(base + '.kicad_pro', 'w').write(protxt.replace(os.path.basename(pro), os.path.basename(base) + '.kicad_pro'))
print('imported', nt, 'track segments,', nv, 'vias ->', dst)
