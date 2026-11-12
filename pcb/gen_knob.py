"""BK46 knob driver board (2-layer, 0.6 mm FR4), left and right variants. Writes the UNROUTED boards; routing is done by
tools/freeroute.py (Freerouting).
The motor sits on a 13.4 mm island held by four 1.6 mm beams (press-force flexure).  run: tools/kpy.sh pcb/gen_knob.py"""
import os, sys, json, math
import numpy as np
import pcbnew
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'mech'))
from params import *
os.environ.setdefault('ROUTER_CLR', '0.15')        # 0.5 mm pitch parts need the tighter (still >= 5 mil) spacing
import router as R
FPLIB = os.path.expanduser('~/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
OUT = os.path.join(HERE, 'knob')
os.makedirs(OUT, exist_ok=True)
mm = pcbnew.FromMM
OX, OY = 30.0, 110.0
FFC_ORDER = ['VM', 'VM', 'VM', 'GND', 'GND', 'GND', 'K3V3', 'INU', 'INV', 'INW', 'PRESS', 'CSN', 'CLK', 'DO']
LAY = {0: pcbnew.F_Cu, 1: pcbnew.B_Cu}


def build(side):
    mir = side == 'R'
    X = (lambda x: FIELD_W - x) if mir else (lambda x: x)
    P = lambda x, y: pcbnew.VECTOR2I(mm(OX + X(x)), mm(OY - y))          # x given in LEFT-board coordinates
    W = lambda v: (pcbnew.ToMM(v.x) - OX, OY - pcbnew.ToMM(v.y))          # actual board coordinates
    b = pcbnew.CreateEmptyBoard()
    b.SetCopperLayerCount(2)
    b.GetDesignSettings().SetBoardThickness(mm(KNOB_PCB_T))
    nets, nid = {}, {}

    def net(n):
        if n not in nets:
            nets[n] = pcbnew.NETINFO_ITEM(b, n); b.Add(nets[n]); nid[n] = len(nid) + 1
        return nets[n]

    comps = []

    def place(lib, name, ref, val, x, y, rot, nm, bottom=False):
        fp = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + '.pretty'), name)
        fp.SetReference(ref); fp.SetValue(val); fp.SetPosition(P(x, y)); b.Add(fp)
        if bottom:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(rot)
        for p in fp.Pads():
            if nm.get(p.GetNumber()):
                p.SetNet(net(nm[p.GetNumber()]))
        comps.append(dict(ref=ref, value=val, footprint=lib + ':' + name, side='B' if bottom else 'F'))
        return fp

    def hole(ref, x, y, d, pad=0, n=None):
        fp = pcbnew.FOOTPRINT(b); fp.SetReference(ref); fp.SetValue('hole %.1f' % d)
        fp.Reference().SetVisible(False); fp.Value().SetVisible(False)
        p = pcbnew.PAD(fp); p.SetNumber('1' if pad else '')
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if pad else pcbnew.PAD_ATTRIB_NPTH)
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE); p.SetSize(pcbnew.VECTOR2I(mm(pad or d), mm(pad or d)))
        p.SetDrillSize(pcbnew.VECTOR2I(mm(d), mm(d)))
        p.SetLayerSet(pcbnew.PAD.PTHMask() if pad else pcbnew.PAD.UnplatedHoleMask()); fp.Add(p)
        fp.SetPosition(P(x, y)); b.Add(fp)
        if n:
            p.SetNet(net(n))

    def edge(pts):
        for a, c in zip(pts, pts[1:] + pts[:1]):
            s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetStart(P(*a)); s.SetEnd(P(*c))
            s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(mm(0.1)); b.Add(s)

    nud = float(os.environ.get('KNOB_NUDGE', '0.5')) if mir else 0.0
    kx, ky = KNOBS[0]
    outline = [(kx + dx, ky + dy) for dx, dy in knob_pcb_outline()]
    slots = [[(kx + dx, ky + dy) for dx, dy in sl] for sl in knob_pcb_slots()]
    edge(outline)
    for sl in slots:
        edge(sl)
    for dx in (-1, 1):
        for dy in (-1, 1):
            hole('H', kx + dx * MOTOR_MOUNT / 2, ky + dy * MOTOR_MOUNT / 2, 2.2)
    for fdx, fdy in KNOB_FRAME_SCREWS:
        hole('H', kx + fdx, ky + fdy, 2.2)
    hole('H9', KNOB_PCB_SCREW[0], KNOB_PCB_SCREW[1], 2.2, 3.0, 'GND')
    # --- island: encoder on top (on the motor axis), press sensor underneath (same axis)
    place('Package_DFN_QFN', 'QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm', 'U1', 'MT6701QT', kx, ky, 0,
          {'6': 'DO', '7': 'CLK', '8': 'CSN', '13': 'K3V3', '14': 'GND', '16': 'GND', '17': 'GND'})
    place('Capacitor_SMD', 'C_0402_1005Metric', 'C1', '100n', kx - 3.6, ky, 90, {'1': 'K3V3', '2': 'GND'})
    place('Package_TO_SOT_SMD', 'SOT-23', 'U3', 'Z-axis linear Hall/TMR (DRV5056A4 / TMR2617S)', kx, ky, 0,
          {'1': 'K3V3', '2': 'PRESS', '3': 'GND'}, bottom=True)
    # --- tail: driver, bulk capacitor, motor pads, FFC
    place('Package_DFN_QFN', 'VQFN-16-1EP_3x3mm_P0.5mm_EP1.8x1.8mm', 'U2', 'STSPIN233', 28.4 + nud, 66.5, 0,
          {'1': 'INU', '2': 'K3V3', '3': 'OUTU', '4': 'GND', '5': 'VM', '6': 'GND', '7': 'OUTV', '8': 'GND', '9': 'GND', '10': 'OUTW',
           '11': 'INW', '12': 'K3V3', '13': 'EN', '14': 'K3V3', '15': 'INV', '16': 'K3V3', '17': 'GND'})
    place('Capacitor_SMD', 'C_0603_1608Metric', 'C2', '22u 6.3V', 32.8 + nud, 66.5, 90, {'1': 'VM', '2': 'GND'})
    place('Capacitor_SMD', 'C_0402_1005Metric', 'C4', '100n', 28.4 + nud, 63.6, 0, {'1': 'VM', '2': 'GND'})
    place('Resistor_SMD', 'R_0402_1005Metric', 'R1', '10k', 28.4 + nud, 69.6, 0, {'1': 'EN', '2': 'K3V3'})
    for i, n in enumerate(('OUTU', 'OUTV', 'OUTW')):
        fp = pcbnew.FOOTPRINT(b); fp.SetReference('M%d' % (i + 1)); fp.SetValue('motor ' + n)
        fp.Reference().SetVisible(False); fp.Value().SetVisible(False)
        p = pcbnew.PAD(fp); p.SetNumber('1'); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
        p.SetSize(pcbnew.VECTOR2I(mm(1.3), mm(2.0)))
        ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.F_Mask); p.SetLayerSet(ls); fp.Add(p)
        fp.SetPosition(P(21.6, 63.6 + 2.6 * i)); b.Add(fp); p.SetNet(net(n))
    j = place('Connector_FFC-FPC', 'Hirose_FH12-14S-0.5SH_1x14-1MP_P0.50mm_Horizontal', 'J1', 'FFC 14P 0.5mm', 2 * U + 0.025, 73.675, 180, {'MP': 'GND'})
    sig = sorted([p for p in j.Pads() if p.GetNumber() != 'MP'], key=lambda p: p.GetPosition().x)
    order = FFC_ORDER[::-1] if mir else FFC_ORDER
    pinmap = {}
    for p, n in zip(sig, order):
        p.SetNet(net(n)); pinmap[p.GetNumber()] = n
    mp = [p for p in j.Pads() if p.GetNumber() == 'MP'][0]
    assert mp.GetPosition().y < sig[0].GetPosition().y, 'FFC cable side must face the back wall'

    # ---------------- routing
    ax = [X(x) for x, _ in outline]
    # align the routing grid with the QFN pad lattice (pads of U1 sit at axis +-0.25/0.75)
    phx, phy = (X(kx) + 0.25) % R.G, (ky + 0.25) % R.G
    gx0 = math.floor((min(ax) - 1) / R.G) * R.G + phx - R.G
    gy0 = math.floor((ky - KNOB_TAB - 1) / R.G) * R.G + phy - R.G
    rt = R.Router(gx0, gy0, max(ax) + 1, ky + KNOB_TAB + 1, nl=2)
    xs = rt.x0 + np.arange(rt.nx) * R.G
    ys = rt.y0 + np.arange(rt.ny) * R.G
    XX, YY = np.meshgrid(xs, ys)

    def inside_poly(pts):
        ins = np.zeros(XX.shape, bool)
        q = [(X(x), y) for x, y in pts]
        for (xa, ya), (xb, yb) in zip(q, q[1:] + q[:1]):
            if ya == yb:
                continue
            ins ^= ((ya > YY) != (yb > YY)) & (XX < (xb - xa) * (YY - ya) / (yb - ya) + xa)
        return ins
    ok = inside_poly(outline)
    for sl in slots:
        ok &= ~inside_poly(sl)
    blocked = ~R.erode(ok, 4)
    for l in range(2):
        rt.multi[l] |= blocked
    # keep bottom copper away from the motor screw heads
    for dx in (-1, 1):
        for dy in (-1, 1):
            rt.mark_disc([1], X(kx + dx * MOTOR_MOUNT / 2), ky + dy * MOTOR_MOUNT / 2, 2.1, -1, 0.1)
    pads_by_net = {}
    for fp in b.GetFootprints():
        fx, fy = W(fp.GetPosition())
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            xa, xb = pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetRight()) - OX
            ya, yb = OY - pcbnew.ToMM(bb.GetBottom()), OY - pcbnew.ToMM(bb.GetTop())
            tht = p.GetDrillSize().x > 0
            layers = [0, 1] if tht else ([0] if p.IsOnLayer(pcbnew.F_Cu) else ([1] if p.IsOnLayer(pcbnew.B_Cu) else None))
            if layers is None:
                continue
            n = p.GetNetname()
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                rt.mark_disc(layers, (xa + xb) / 2, (ya + yb) / 2, (xb - xa) / 2, -1, R.INFL + 0.1)
                continue
            i_ = nid.get(n, -1)
            rt.mark_rect(layers, xa, ya, xb, yb, i_)
            if i_ > 0:
                fine = len(fp.Pads()) >= 8 and not tht
                cells = rt.add_conn_rect(layers, xa, ya, xb, yb, i_, away_from=(fx, fy) if fine else None)
                pads_by_net.setdefault(n, []).append(dict(cells=cells, x=(xa + xb) / 2, y=(ya + yb) / 2, ref=fp.GetReference(), num=p.GetNumber()))
    # no bottom copper under the motor screw heads (they sit against the board)
    for dx in (-1, 1):
        for dy in (-1, 1):
            ko = pcbnew.ZONE(b); ko.SetIsRuleArea(True); ko.SetLayer(pcbnew.B_Cu)
            ko.SetDoNotAllowTracks(True); ko.SetDoNotAllowVias(True); ko.SetDoNotAllowZoneFills(True); ko.SetDoNotAllowPads(False); ko.SetDoNotAllowFootprints(False)
            ol = ko.Outline(); ol.NewOutline()
            for k_ in range(16):
                a_ = 2 * math.pi * k_ / 16
                pt = P(kx + dx * MOTOR_MOUNT / 2 + 2.1 * math.cos(a_), ky + dy * MOTOR_MOUNT / 2 + 2.1 * math.sin(a_))
                ol.Append(pt.x, pt.y)
            b.Add(ko)
    d0 = os.path.join(OUT, side)
    os.makedirs(d0, exist_ok=True)
    pcbnew.SaveBoard(os.path.join(d0, 'bk46_knob_%s_unrouted.kicad_pcb' % side), b)     # input for Freerouting
    json.dump(comps, open(os.path.join(d0, 'components.json'), 'w'), indent=1)
    if not os.environ.get('KNOB_OWN_ROUTER'):
        return pinmap          # routing is done by tools/freeroute.py (see README)
    failed = []

    def stubs():
        """short escape stubs out of the fine-pitch pads so that later routes cannot wall them in"""
        for fp in b.GetFootprints():
            pads = list(fp.Pads())
            if len(pads) < 8:
                continue
            ref = fp.GetReference()
            fx, fy = W(fp.GetPosition())
            for p in pads:
                n = p.GetNetname()
                bb = p.GetBoundingBox()
                xa, xb = pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetRight()) - OX
                ya, yb = OY - pcbnew.ToMM(bb.GetBottom()), OY - pcbnew.ToMM(bb.GetTop())
                w_, h_ = xb - xa, yb - ya
                if not n or min(w_, h_) > 0.45 or max(w_, h_) > 2.0:
                    continue
                cx, cy = (xa + xb) / 2, (ya + yb) / 2
                if w_ <= h_:
                    dx, dy, half = 0.0, (1.0 if cy >= fy else -1.0), h_ / 2
                else:
                    dx, dy, half = (1.0 if cx >= fx else -1.0), 0.0, w_ / 2
                odd = pads.index(p) % 2
                L = half + ((0.45 if odd else 0.95) if ref == 'J1' else (0.6 if odd else 1.1))
                l = 0 if p.IsOnLayer(pcbnew.F_Cu) else 1
                t = pcbnew.PCB_TRACK(b)
                t.SetStart(pcbnew.VECTOR2I(mm(OX + cx), mm(OY - cy))); t.SetEnd(pcbnew.VECTOR2I(mm(OX + cx + dx * L), mm(OY - cy - dy * L)))
                t.SetWidth(mm(0.2)); t.SetLayer(LAY[l]); t.SetNet(net(n)); b.Add(t)
                before = set(rt.conn.get(nid[n], set()))
                rt.mark_seg(l, cx, cy, cx + dx * L, cy + dy * L, 0.2, nid[n])
                rt.force.setdefault(nid[n], set()).update(set(rt.conn[nid[n]]) - before)
                if ref in ('J1', 'U2'):
                    ex, ey = cx + dx * L, cy + dy * L
                    if rt.via_legal(nid[n], ex, ey, 0.45):
                        v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(mm(OX + ex), mm(OY - ey))); v.SetDrill(mm(0.2)); v.SetWidth(pcbnew.F_Cu, mm(0.45))
                        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(net(n)); b.Add(v)
                        rt.mark_via(ex, ey, nid[n], 0.45)
    stubs()
    # fixed lanes across the flexure: island -> north bridge -> north beam -> tab -> tail (3 per layer)
    LANE = {}
    for l, names in ((0, ('CSN', 'CLK', 'DO')), (1, ('K3V3', 'PRESS', 'GND'))):
        for k, n in enumerate(names):
            net(n)
            lx, ly, tx = -0.6 + 0.6 * k, 9.0 - 0.4 * k, 11.9 - 0.6 * k
            pts = [(kx + lx, ky + 6.1), (kx + lx, ky + ly), (kx + tx, ky + ly), (kx + tx, ky + 6.3)]
            before = set(rt.conn.get(nid[n], set()))
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                t = pcbnew.PCB_TRACK(b); t.SetStart(P(xa, ya)); t.SetEnd(P(xb, yb)); t.SetWidth(mm(0.2)); t.SetLayer(LAY[l]); t.SetNet(net(n)); b.Add(t)
                rt.mark_seg(l, X(xa), ya, X(xb), yb, 0.2, nid[n])
            LANE[n] = set(rt.conn[nid[n]]) - before
            rt.force.setdefault(nid[n], set()).update(LANE[n])
    if os.environ.get('DBG') and side == 'L':
        for l in range(2):
            pas = rt.passable(9999, (0, 0, rt.nx - 1, rt.ny - 1))[l]
            im = np.kron((pas[::-1] * 255).astype(np.uint8), np.ones((3, 3), np.uint8))
            with open('/tmp/knob_%d.pgm' % l, 'wb') as f:
                f.write(b'P5 %d %d 255\n' % (im.shape[1], im.shape[0])); f.write(im.tobytes())

    def commit(path, n, w):
        segs, vias = R.Router.simplify(path)
        for pts in segs:
            for a, c in zip(pts, pts[1:]):
                (xa, ya), (xb, yb) = rt.xy(a[1], a[2]), rt.xy(c[1], c[2])
                t = pcbnew.PCB_TRACK(b)
                t.SetStart(pcbnew.VECTOR2I(mm(OX + xa), mm(OY - ya))); t.SetEnd(pcbnew.VECTOR2I(mm(OX + xb), mm(OY - yb)))
                t.SetWidth(mm(w)); t.SetLayer(LAY[pts[0][0]]); t.SetNet(net(n)); b.Add(t)
                rt.mark_seg(pts[0][0], xa, ya, xb, yb, w, nid[n])
        for ix, iy in vias:
            x, y = rt.xy(ix, iy)
            v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I(mm(OX + x), mm(OY - y))); v.SetDrill(mm(0.3)); v.SetWidth(pcbnew.F_Cu, mm(0.6))
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(net(n)); b.Add(v)
            rt.mark_via(x, y, nid[n])

    def route_net(n, w=0.2, fat=0):
        groups = {}
        for p in pads_by_net.get(n, []):
            groups.setdefault((p['ref'], p['num']), []).append(p)
        gl = list(groups.values())
        if n in LANE:
            tree, done, todo = set(LANE[n]), [[dict(x=X(kx), y=ky + 8.6)]], gl
        elif len(gl) < 2:
            return
        else:
            tree = {c for p in gl[0] for c in p['cells']}
            done, todo = [gl[0]], gl[1:]
        while todo:
            todo.sort(key=lambda g: min(math.hypot(a['x'] - c['x'], a['y'] - c['y']) for a in g for d in done for c in d))
            g = todo.pop(0)
            starts = [c for p in g for c in p['cells']]
            before = set(rt.conn.get(nid[n], set()))
            path, ww = rt.route(nid[n], starts, tree, layers=(0, 1), fat=fat, margin=30.0, layer_cost=(1.0, 1.0)), w
            if path is None and fat:
                path, ww = rt.route(nid[n], starts, tree, layers=(0, 1), fat=0, margin=30.0, layer_cost=(1.0, 1.0)), 0.2
            if path is None:
                failed.append((n, g[0]['ref'], g[0]['num']))
                if os.environ.get('DBG') and n in os.environ['DBG']:
                    print('  fail', n, g[0]['ref'], g[0]['num'], round(g[0]['x'], 2), round(g[0]['y'], 2), getattr(rt, 'last_fail', None))
            else:
                commit(path, n, ww)
                tree |= set(rt.conn[nid[n]]) - before
            tree |= set(starts)
            done.append(g)

    for n in ('CSN', 'CLK', 'DO', 'PRESS', 'K3V3', 'INU', 'INV', 'INW', 'EN'):
        route_net(n)
    for n in ('OUTU', 'OUTV', 'OUTW', 'VM'):
        route_net(n, 0.4, 1)
    route_net('GND')
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(b); z.SetLayer(layer); z.SetNet(net('GND'))
        ol = z.Outline(); ol.NewOutline()
        for x, y in ((rt.x0, rt.y0), (rt.x0 + rt.nx * R.G, rt.y0), (rt.x0 + rt.nx * R.G, rt.y0 + rt.ny * R.G), (rt.x0, rt.y0 + rt.ny * R.G)):
            ol.Append(mm(OX + x), mm(OY - y))
        z.SetLocalClearance(mm(0.25)); z.SetMinThickness(mm(0.2)); z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS); b.Add(z)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    d = os.path.join(OUT, side)
    os.makedirs(d, exist_ok=True)
    pcbnew.SaveBoard(os.path.join(d, 'bk46_knob_%s.kicad_pcb' % side), b)
    json.dump(comps, open(os.path.join(d, 'components.json'), 'w'), indent=1)
    print(side, 'failed:', failed)
    return pinmap


out = {s: build(s) for s in ('L', 'R')}
json.dump(out, open(os.path.join(OUT, 'ffc_pinmap.json'), 'w'), indent=1)
