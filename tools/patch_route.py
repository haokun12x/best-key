"""Finish the last unrouted connections of a board (rip-up and reroute).

usage: tools/kpy.sh tools/patch_route.py in.kicad_pcb out.kicad_pcb [NET,NET,...]
env:   DUMP=x0,y0,x1,y1[,net]  -> write occupancy PNG (4 layers side by side) to $DUMPFILE and exit

Every pad / via / track / rule area is put into 0.1 mm occupancy grids on all four copper layers
(pcb/router.py).  Copper islands of a net come from KiCad's own connectivity.  An island is joined
to the rest of its net by A* in which tracks of ordinary signal nets are *soft* obstacles: crossing
one costs a penalty, and the tracks that the final path really hits are ripped out and their nets
are queued for re-routing.  Pads, vias, rule areas, tracks of plane nets (GND, VLED) and every track
added by this script are hard obstacles.  GND pours on F/B and the In1 GND plane are not obstacles
(they are refilled; In1 is expensive).  A VLED island is finished when it has a via into the In2
VLED plane.  Coordinates are KiCad's (y down).
"""
import heapq
import os
import struct
import sys
import zlib

os.environ.setdefault('ROUTER_CLR', '0.065')   # router INFL = CLR + 0.12 = 0.185 = 0.10 rule + 0.075 half track + 0.01
os.environ.setdefault('ROUTER_VIA', '0.45,0.2')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pcb'))
import numpy as np
import pcbnew
import router as R

SRC, DST = sys.argv[1], sys.argv[2]
TARGETS = sys.argv[3].split(',') if len(sys.argv) > 3 else ['+3V3', 'LED_EN', 'CHG', 'VLED']
PLANE_NETS = {'GND', 'VLED'}
WIDTH = {'VSYS': 0.5, 'VBUS': 0.5, 'VBAT': 0.5, 'K3V3': 0.4, 'VSENSE': 0.3}   # power nets keep their width when re-routed


def width(net):
    return WIDTH.get(net, TW)
           # never ripped
HIST = {}                       # net -> times ripped (ripping it again gets dearer)
b = pcbnew.LoadBoard(SRC)
mm, FM = pcbnew.ToMM, pcbnew.FromMM
LAY = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
LI = {l: i for i, l in enumerate(LAY)}
TW = 0.15                      # new tracks are 0.15 mm: they fit between the 0.8 mm-pitch module pads
LC = (1.0, 8.0, 5.0, 1.0)      # F, In1 (GND plane), In2 (VLED plane + key bus), B
PEN = float(os.environ.get('PEN', '150'))                      # cost per cell of crossing a rippable track
VIA_COST = 12.0

bb = b.GetBoardEdgesBoundingBox()
BOX = (float(np.floor(mm(bb.GetLeft()))) - 1, float(np.floor(mm(bb.GetTop()))) - 1, mm(bb.GetRight()) + 1, mm(bb.GetBottom()) + 1)   # grid on whole 0.1 mm

outl = pcbnew.SHAPE_POLY_SET()
b.GetBoardPolygonOutlines(outl, False)
ol = outl.Outline(0)
OUTLINE = [(mm(ol.CPoint(i).x), mm(ol.CPoint(i).y)) for i in range(ol.PointCount())]

NET = {}
LOCKED = set()                  # uuids of tracks this script added


def nid(name):
    return NET.setdefault(name, len(NET) + 1) if name else -1


def uid(it):
    return it.m_Uuid.AsString()


def soft_track(t):
    return t.GetNetname() not in PLANE_NETS and uid(t) not in LOCKED


class Grids:
    """hd: hard obstacles only; rt: everything (as the plain router sees it)"""

    def __init__(self):
        self.hd = R.Router(*BOX, nl=4)
        self.rt = R.Router(*BOX, nl=4)
        hd, rt = self.hd, self.rt
        XX, YY = np.meshgrid(rt.x0 + np.arange(rt.nx) * R.G, rt.y0 + np.arange(rt.ny) * R.G)
        inside = np.zeros(XX.shape, bool)
        for i in range(len(OUTLINE)):
            (xa, ya), (xb, yb) = OUTLINE[i], OUTLINE[(i + 1) % len(OUTLINE)]
            if ya != yb:
                inside ^= ((ya > YY) != (yb > YY)) & (XX < (xb - xa) * (YY - ya) / (yb - ya) + xa)
        out = ~R.erode(inside, 4)
        for l in range(4):
            rt.multi[l] |= out
            hd.multi[l] |= out
        self.cells = {}
        both = (hd, rt)
        for fp in b.GetFootprints():
            for p in fp.Pads():
                pb = p.GetBoundingBox()
                xa, ya, xb, yb = mm(pb.GetLeft()), mm(pb.GetTop()), mm(pb.GetRight()), mm(pb.GetBottom())
                tht = p.GetDrillSize().x > 0
                layers = [0, 1, 2, 3] if tht else [i for i, l in enumerate(LAY) if p.IsOnLayer(l)]
                if not layers:
                    continue
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    for g in both:
                        g.mark_disc(layers, (xa + xb) / 2, (ya + yb) / 2, (xb - xa) / 2, -1, R.INFL + 0.2)
                    continue
                n = nid(p.GetNetname())
                for g in both:
                    if tht and abs((xb - xa) - (yb - ya)) < 0.01:
                        g.mark_disc(layers, (xa + xb) / 2, (ya + yb) / 2, (xb - xa) / 2, n, R.INFL + 0.05)
                    else:
                        g.mark_rect(layers, xa, ya, xb, yb, n)
                    if n > 0:
                        c = g.add_conn_rect(layers, xa, ya, xb, yb, n)
                if n > 0:
                    self.cells[uid(p)] = c
        self.soft = []          # (uuid, layer, xa, ya, xb, yb, w, net)
        for t in b.GetTracks():
            n = nid(t.GetNetname())
            if t.Type() == pcbnew.PCB_VIA_T:
                x, y = mm(t.GetPosition().x), mm(t.GetPosition().y)
                for g in both:
                    g.mark_via(x, y, n, mm(t.GetWidth(pcbnew.F_Cu)))
                ix, iy = rt.ij(x, y)
                self.cells[uid(t)] = [(l, ix, iy) for l in range(4)]
            elif t.Type() == pcbnew.PCB_TRACE_T and t.GetLayer() in LI:
                l = LI[t.GetLayer()]
                seg = (mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y), mm(t.GetWidth()))
                before = set(rt.conn.get(n, ()))
                rt.mark_seg(l, *seg, n)
                self.cells[uid(t)] = [c for c in rt.conn[n] if c not in before and c[0] == l] or [(l,) + rt.ij(seg[0], seg[1])]
                if soft_track(t):
                    self.soft.append((uid(t), l) + seg + (t.GetNetname(),))
                else:
                    hd.mark_seg(l, *seg, n)
        self.vled = None
        for z in b.Zones():
            if z.GetIsRuleArea():
                zb = z.GetBoundingBox()
                for g in both:
                    g.mark_rect(range(4), mm(zb.GetLeft()), mm(zb.GetTop()), mm(zb.GetRight()), mm(zb.GetBottom()), -1)
            elif z.GetNetname() == 'VLED' and z.IsOnLayer(pcbnew.In2_Cu):
                f = z.GetFilledPolysList(pcbnew.In2_Cu)
                k = max(range(f.OutlineCount()), key=lambda i: f.Outline(i).Area())
                self.vled = pcbnew.SHAPE_POLY_SET()           # only the main fragment of the plane counts
                self.vled.AddOutline(f.Outline(k))
                for h in range(f.HoleCount(k)):
                    self.vled.AddHole(f.Hole(k, h))

    def in_vled(self, x, y, margin=0.4):
        if self.vled is None:
            return False
        return all(self.vled.Contains(pcbnew.VECTOR2I(FM(x + dx), FM(y + dy)))
                   for dx, dy in ((0, 0), (margin, 0), (-margin, 0), (0, margin), (0, -margin)))

    # ------------------------------------------------------------ A* with soft obstacles
    def route(self, net, starts, goals, margin, via_pred=None):
        hd, rt = self.hd, self.rt
        n = NET[net]
        pts = list(starts) + list(goals)
        mc = int(margin / R.G)
        ix0 = max(min(p[1] for p in pts) - mc, 0)
        ix1 = min(max(p[1] for p in pts) + mc, rt.nx - 1)
        iy0 = max(min(p[2] for p in pts) - mc, 0)
        iy1 = min(max(p[2] for p in pts) + mc, rt.ny - 1)
        W, H = ix1 - ix0 + 1, iy1 - iy0 + 1
        win = (ix0, iy0, ix1, iy1)
        hp = hd.passable(n, win)
        sp = rt.passable(n, win)
        fat = int(np.ceil((width(net) - TW) / 2 / R.G - 1e-6))
        if fat > 0:
            hp = [R.erode(a, fat) for a in hp]
            sp = [R.erode(a, fat) for a in sp]
        for g, arr in ((hd, hp), (rt, sp)):
            for (fl, fx, fy) in g.force.get(n, ()):
                if ix0 <= fx <= ix1 and iy0 <= fy <= iy1:
                    arr[fl][fy - iy0, fx - ix0] = True
        cost = []
        hist = np.ones(len(NET) + 2)
        for k_, v_ in HIST.items():
            hist[NET[k_]] += 2.0 * v_
        for l in range(4):
            own = np.clip(rt.owner[l][iy0:iy1 + 1, ix0:ix1 + 1], 0, None)
            c = np.where(sp[l], 1.0, 1.0 + PEN * hist[own]) * LC[l]
            c[~hp[l]] = np.inf
            cost.append(c.ravel())
        vh = R.erode(np.logical_and.reduce(hp), max(0, 2 - fat))
        vs = R.erode(np.logical_and.reduce(sp), max(0, 2 - fat))
        for (vx, vy) in rt.ownvia.get(n, ()):
            if ix0 <= vx <= ix1 and iy0 <= vy <= iy1:
                vh[vy - iy0, vx - ix0] = vs[vy - iy0, vx - ix0] = True
        vcost = np.where(vs, VIA_COST, VIA_COST + 4 * PEN)
        vcost[~vh] = np.inf
        vcost = vcost.ravel()
        via_goal = via_pred is not None
        goalset = set()
        if not via_goal:
            for (l, ix, iy) in goals:
                if ix0 <= ix <= ix1 and iy0 <= iy <= iy1:
                    goalset.add((l * H + iy - iy0) * W + ix - ix0)
            ga = np.array([(g % W, (g // W) % H) for g in goalset])
            gx0, gx1, gy0, gy1 = ga[:, 0].min(), ga[:, 0].max(), ga[:, 1].min(), ga[:, 1].max()

            def hf(x, y):
                dx = gx0 - x if x < gx0 else (x - gx1 if x > gx1 else 0)
                dy = gy0 - y if y < gy0 else (y - gy1 if y > gy1 else 0)
                return (dx + dy) - 0.5858 * min(dx, dy)
        else:
            def hf(x, y):
                return 0
        heap, gsc, prev = [], {}, {}
        for (l, ix, iy) in starts:
            if ix0 <= ix <= ix1 and iy0 <= iy <= iy1:
                k = (l * H + iy - iy0) * W + ix - ix0
                gsc[k] = 0.0
                prev[k] = -1
                heapq.heappush(heap, (hf(ix - ix0, iy - iy0), 0.0, k))
        moves = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                 (1, 1, R.SQ2), (1, -1, R.SQ2), (-1, 1, R.SQ2), (-1, -1, R.SQ2))
        found = -1
        while heap:
            f, g, k = heapq.heappop(heap)
            if g > gsc.get(k, 1e18):
                continue
            l, r = divmod(k, W * H)
            y, x = divmod(r, W)
            if via_goal:
                if g > 3 and vcost[r] < VIA_COST + 1 and via_pred(x + ix0, y + iy0):
                    found = k
                    break
            elif k in goalset:
                found = k
                break
            cl = cost[l]
            for dx, dy, c in moves:
                nx_, ny_ = x + dx, y + dy
                if nx_ < 0 or ny_ < 0 or nx_ >= W or ny_ >= H:
                    continue
                nr = ny_ * W + nx_
                cc = cl[nr]
                if cc == np.inf:
                    continue
                if dx and dy and (cl[y * W + nx_] == np.inf or cl[ny_ * W + x] == np.inf):
                    continue
                nk = l * W * H + nr
                ng = g + c * cc
                if ng < gsc.get(nk, 1e18):
                    gsc[nk] = ng
                    prev[nk] = k
                    heapq.heappush(heap, (ng + hf(nx_, ny_), ng, nk))
            vc = vcost[r]
            if vc < np.inf and not via_goal:
                for nl_ in range(4):
                    if nl_ != l:
                        nk = nl_ * W * H + r
                        ng = g + vc
                        if ng < gsc.get(nk, 1e18):
                            gsc[nk] = ng
                            prev[nk] = k
                            heapq.heappush(heap, (ng + hf(x, y), ng, nk))
        if found < 0:
            return None
        path = []
        k = found
        while k != -1:
            l, r = divmod(k, W * H)
            y, x = divmod(r, W)
            path.append((l, x + ix0, y + iy0))
            k = prev[k]
        return path[::-1]

    def hits(self, path, extra_via=None, w=TW):
        """uuids of soft tracks whose copper comes within clearance of the new path"""
        if not self.soft:
            return {}
        S = np.array([s[2:7] for s in self.soft])
        SL = np.array([s[1] for s in self.soft])
        segs, vias = R.Router.simplify(path)
        vias = list(vias) + ([extra_via] if extra_via else [])
        out = {}
        clr = R.CLR + 0.03

        def check(mask, ax, ay, bx, by, r):
            # distance between soft segments (mask) and segment a-b
            for t in np.linspace(0, 1, max(2, int(np.hypot(bx - ax, by - ay) / 0.05) + 1)):
                px, py = ax + (bx - ax) * t, ay + (by - ay) * t
                dx, dy = S[:, 2] - S[:, 0], S[:, 3] - S[:, 1]
                L2 = np.maximum(dx * dx + dy * dy, 1e-12)
                u = np.clip(((px - S[:, 0]) * dx + (py - S[:, 1]) * dy) / L2, 0, 1)
                d = np.hypot(S[:, 0] + u * dx - px, S[:, 1] + u * dy - py)
                for i in np.nonzero(mask & (d < S[:, 4] / 2 + r + clr))[0]:
                    out[self.soft[i][0]] = self.soft[i][7]

        for s in segs:
            l = s[0][0]
            for a, c in zip(s, s[1:]):
                xa, ya = self.rt.xy(a[1], a[2])
                xb, yb = self.rt.xy(c[1], c[2])
                check(SL == l, xa, ya, xb, yb, w / 2)
        for vx, vy in vias:
            x, y = self.rt.xy(vx, vy)
            check(np.ones(len(SL), bool), x, y, x, y, R.VIA_D / 2)
        return out


def islands(net, cells):
    code = b.FindNet(net).GetNetCode()
    items = [p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetCode() == code]
    items += [t for t in b.GetTracks() if t.GetNetCode() == code]
    left = {uid(i): i for i in items}
    out = []
    cn = b.GetConnectivity()
    while left:
        k, it = left.popitem()
        grp = {k}
        for o in cn.GetConnectedItems(it):
            grp.add(uid(o))
            left.pop(uid(o), None)
        out.append(grp)
    merged = []
    for g in out:
        for m in merged:
            if m & g:
                m |= g
                break
        else:
            merged.append(set(g))
    res = []
    for g in merged:
        s = set()
        for u in g:
            s.update(cells.get(u, ()))
        if s:
            res.append(s)
    return res


def outer_islands(G, net):
    """islands of a plane net built from F/B copper and vias only (zones ignored)"""
    n = NET[net]
    rt = G.rt
    vias = rt.ownvia.get(n, set())
    left = {c for c in rt.conn.get(n, ()) if c[0] in (0, 3)}
    out = []
    while left:
        s0 = left.pop()
        comp = {s0}
        st = [s0]
        while st:
            l, x, y = st.pop()
            nb = [(l, x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
            if (x, y) in vias:
                nb += [(k, x, y) for k in (0, 3)]
                comp.add((2, x, y))
            for c in nb:
                if c in left:
                    left.remove(c)
                    comp.add(c)
                    st.append(c)
        out.append(comp)
    return out


def add_via(net, x, y):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pcbnew.VECTOR2I(FM(x), FM(y)))
    v.SetWidth(FM(R.VIA_D))
    v.SetDrill(FM(R.VIA_DRILL))
    v.SetNet(b.FindNet(net))
    b.Add(v)


def commit(G, net, path, end_via=False):
    segs, vias = R.Router.simplify(path)
    for s in segs:
        l = s[0][0]
        for a, c in zip(s, s[1:]):
            xa, ya = G.rt.xy(a[1], a[2])
            xb, yb = G.rt.xy(c[1], c[2])
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(FM(xa), FM(ya)))
            t.SetEnd(pcbnew.VECTOR2I(FM(xb), FM(yb)))
            t.SetWidth(FM(width(net)))
            t.SetLayer(LAY[l])
            t.SetNet(b.FindNet(net))
            b.Add(t)
            if net in TARGETS:
                LOCKED.add(uid(t))
    for vx, vy in vias:
        add_via(net, *G.rt.xy(vx, vy))
    if end_via:
        add_via(net, *G.rt.xy(*path[-1][1:]))


def rip(uuids):
    for t in list(b.GetTracks()):
        if uid(t) in uuids:
            b.Remove(t)


if os.environ.get('DUMP'):
    G = Grids()
    a = os.environ['DUMP'].split(',')
    x0, y0, x1, y1 = [float(v) for v in a[:4]]
    rt = G.rt
    i0, j0 = rt.ij(x0, y0)
    i1, j1 = rt.ij(x1, y1)
    n = NET.get(a[4] if len(a) > 4 else None, -99)
    tiles = []
    for l in range(4):
        o = rt.owner[l][j0:j1, i0:i1]
        img = np.full(o.shape + (3,), 255, np.uint8)
        img[o != 0] = (175, 175, 175)
        img[o == n] = (150, 230, 150)
        img[rt.multi[l][j0:j1, i0:i1]] = (0, 0, 0)
        for (cl, cx, cy) in rt.conn.get(n, ()):
            if cl == l and i0 <= cx < i1 and j0 <= cy < j1:
                img[cy - j0, cx - i0] = (0, 110, 0)
        tiles += [img, np.tile(np.array([220, 0, 0], np.uint8), (o.shape[0], 2, 1))]
    im = np.ascontiguousarray(np.concatenate(tiles[:-1], axis=1).repeat(5, 0).repeat(5, 1))
    raw = b''.join(b'\x00' + im[r].tobytes() for r in range(im.shape[0]))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    open(os.environ.get('DUMPFILE', 'dump.png'), 'wb').write(
        b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', im.shape[1], im.shape[0], 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))
    sys.exit(0)

# ------------------------------------------------------------------ main loop
queue = list(TARGETS)
done_log, fails, ripped_log = [], [], []
it = 0
while queue and it < int(os.environ.get('ITERS', '160')):
    it += 1
    net = queue.pop(0)
    b.BuildConnectivity()
    G = Grids()
    if net == 'VLED':
        gs = outer_islands(G, net)
        todo = [s for s in gs if not any(l == 2 and G.in_vled(*G.rt.xy(x, y), 0.05) for l, x, y in s)]
        print('VLED islands', len(gs), 'off-plane', [G.rt.xy(*sorted(s)[0][1:]) for s in todo], flush=True)
        if not todo:
            continue
        s = todo[0]
        starts = [c for c in s if c[0] in (0, 3)]
        p = G.route(net, starts, [], 5.0, via_pred=lambda ix, iy: G.in_vled(*G.rt.xy(ix, iy)))
        where = G.rt.xy(*starts[0][1:])
        if p is None:
            fails.append((net, where))
            continue
        hit = G.hits(p, extra_via=p[-1][1:], w=width(net))
        rip(hit)
        commit(G, net, p, end_via=True)
    else:
        gs = islands(net, G.cells)
        if len(gs) < 2:
            continue
        gs.sort(key=len)
        s = gs[0]
        rest = set().union(*gs[1:])
        p = None
        for margin in (4.0, 12.0, 40.0):
            p = G.route(net, list(s), rest, margin)
            if p:
                break
        where = G.rt.xy(*next(iter(s))[1:])
        if p is None:
            fails.append((net, where))
            continue
        hit = G.hits(p, w=width(net))
        rip(hit)
        commit(G, net, p)
    done_log.append((net, where, len(p), sorted(set(c[0] for c in p)), len(hit)))
    for hn in set(hit.values()):
        HIST[hn] = HIST.get(hn, 0) + 1
    for u, hn in hit.items():
        ripped_log.append(hn)
        if hn not in queue:
            queue.append(hn)
    if net not in queue:
        queue.insert(0, net)        # re-check: the net may still have more islands

for d in done_log:
    print('routed', d)
print('ripped nets:', sorted(set(ripped_log)))
for f in fails:
    print('FAIL', f)
print('queue left:', queue)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard(DST, b)
print('saved', DST)
