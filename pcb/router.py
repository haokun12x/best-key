"""Small grid router used by the BK47 board generators.

World coordinates in mm (x right, y up/north).  Routing layers are indexed 0..NL-1.
Occupancy is stored per layer as an "owner net" map already inflated by
(clearance + half track width), so a cell is usable by net N when nobody else claimed it.
"""
import heapq
import os
import numpy as np

G = 0.1            # grid pitch
CLR = float(os.environ.get('ROUTER_CLR', '0.2'))          # copper clearance the router keeps (set before import)
TW = 0.2           # default track width
VIA_D, VIA_DRILL = [float(v) for v in os.environ.get('ROUTER_VIA', '0.6,0.3').split(',')]
INFL = CLR + TW / 2 + 0.02
SQ2 = 1.41421356


def disc(r_cells):
    r = int(np.ceil(r_cells))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= r_cells * r_cells + 1e-6


def erode(a, r):
    """binary erosion with a square (2r+1) window"""
    if r <= 0:
        return a
    out = a.copy()
    for d in range(1, r + 1):
        out[:, d:] &= a[:, :-d]
        out[:, :-d] &= a[:, d:]
    b = out.copy()
    for d in range(1, r + 1):
        out[d:, :] &= b[:-d, :]
        out[:-d, :] &= b[d:, :]
    return out


class Router:
    def __init__(self, x0, y0, x1, y1, nl=3):
        self.x0, self.y0 = x0, y0
        self.nx = int(round((x1 - x0) / G)) + 1
        self.ny = int(round((y1 - y0) / G)) + 1
        self.nl = nl
        self.owner = [np.zeros((self.ny, self.nx), np.int32) for _ in range(nl)]
        self.multi = [np.zeros((self.ny, self.nx), bool) for _ in range(nl)]
        self.conn = {}          # net -> set of (l, ix, iy) cells that are copper centres of that net
        self.force = {}         # net -> set of cells always passable for that net (inside own pads)
        self.ownvia = {}        # net -> set of (ix, iy) where the net already has a through via

    # ---------------- coordinates
    def ij(self, x, y):
        return int(round((x - self.x0) / G)), int(round((y - self.y0) / G))

    def xy(self, ix, iy):
        return round(self.x0 + ix * G, 4), round(self.y0 + iy * G, 4)

    # ---------------- obstacle marking
    def _mark(self, l, iy0, ix0, mask, net):
        h, w = mask.shape
        ya, xa = max(iy0, 0), max(ix0, 0)
        yb, xb = min(iy0 + h, self.ny), min(ix0 + w, self.nx)
        if ya >= yb or xa >= xb:
            return
        m = mask[ya - iy0:yb - iy0, xa - ix0:xb - ix0]
        o = self.owner[l][ya:yb, xa:xb]
        mu = self.multi[l][ya:yb, xa:xb]
        if net < 0:
            mu |= m
        else:
            mu |= m & (o != 0) & (o != net)
            o[m & (o == 0)] = net

    def mark_rect(self, layers, xa, ya, xb, yb, net, infl=INFL):
        ix0 = int(np.ceil((min(xa, xb) - infl - self.x0) / G - 1e-6))
        iy0 = int(np.ceil((min(ya, yb) - infl - self.y0) / G - 1e-6))
        ix1 = int(np.floor((max(xa, xb) + infl - self.x0) / G + 1e-6))
        iy1 = int(np.floor((max(ya, yb) + infl - self.y0) / G + 1e-6))
        if ix1 < ix0 or iy1 < iy0:
            return
        mask = np.ones((iy1 - iy0 + 1, ix1 - ix0 + 1), bool)
        for l in layers:
            self._mark(l, iy0, ix0, mask, net)

    def mark_disc(self, layers, x, y, r, net, infl=INFL):
        d = disc((r + infl) / G)
        ix, iy = self.ij(x, y)
        k = d.shape[0] // 2
        for l in layers:
            self._mark(l, iy - k, ix - k, d, net)

    def mark_seg(self, l, xa, ya, xb, yb, w, net):
        n = max(1, int(np.hypot(xb - xa, yb - ya) / (G / 2)))
        d = disc((w / 2 + INFL) / G)
        k = d.shape[0] // 2
        cells = set()
        for i in range(n + 1):
            t = i / n
            cells.add(self.ij(xa + (xb - xa) * t, ya + (yb - ya) * t))
        for ix, iy in cells:
            self._mark(l, iy - k, ix - k, d, net)
            self.conn.setdefault(net, set()).add((l, ix, iy))

    def via_legal(self, net, x, y, d=VIA_D):
        ix, iy = self.ij(x, y)
        k = int(np.ceil((d / 2 - TW / 2) / G - 1e-6))
        for l in range(self.nl):
            o = self.owner[l][iy - k:iy + k + 1, ix - k:ix + k + 1]
            m = self.multi[l][iy - k:iy + k + 1, ix - k:ix + k + 1]
            if m.any() or ((o != 0) & (o != net)).any():
                return False
        return True

    def mark_via(self, x, y, net, d=VIA_D):
        self.mark_disc(range(self.nl), x, y, d / 2, net)
        ix, iy = self.ij(x, y)
        self.ownvia.setdefault(net, set()).add((ix, iy))
        for l in range(self.nl):
            self.conn.setdefault(net, set()).add((l, ix, iy))

    def add_conn_rect(self, layers, xa, ya, xb, yb, net, away_from=None):
        """register the interior of a pad as connectable copper of `net`"""
        xa, xb = min(xa, xb), max(xa, xb)
        ya, yb = min(ya, yb), max(ya, yb)
        w, h = xb - xa, yb - ya
        cx, cy = (xa + xb) / 2, (ya + yb) / 2
        m = 0.11
        if w <= 0.45:          # narrow pad: stay on its long axis
            xa2 = xb2 = cx
            ya2, yb2 = ya + m, yb - m
        elif h <= 0.45:
            ya2 = yb2 = cy
            xa2, xb2 = xa + m, xb - m
        else:
            xa2, xb2, ya2, yb2 = xa + m, xb - m, ya + m, yb - m
        if away_from is not None and (w <= 0.45 or h <= 0.45):
            # fine-pitch pad: allow the escape track to continue 0.5 mm straight out of the pad
            ext = 0.5
            if w <= 0.45:
                if cy >= away_from[1]:
                    yb2 += ext + m
                else:
                    ya2 -= ext + m
            else:
                if cx >= away_from[0]:
                    xb2 += ext + m
                else:
                    xa2 -= ext + m
        i0, j0 = self.ij(xa2, ya2)
        i1, j1 = self.ij(xb2, yb2)
        cells = [(ix, iy) for ix in range(min(i0, i1), max(i0, i1) + 1) for iy in range(min(j0, j1), max(j0, j1) + 1)]
        if not cells:
            cells = [self.ij(cx, cy)]
        for l in layers:
            for ix, iy in cells:
                self.conn.setdefault(net, set()).add((l, ix, iy))
                self.force.setdefault(net, set()).add((l, ix, iy))
        return [(l, ix, iy) for l in layers for ix, iy in cells]

    # ---------------- search
    def passable(self, net, win, fat=0):
        ix0, iy0, ix1, iy1 = win
        out = []
        for l in range(self.nl):
            o = self.owner[l][iy0:iy1 + 1, ix0:ix1 + 1]
            p = (~self.multi[l][iy0:iy1 + 1, ix0:ix1 + 1]) & ((o == 0) | (o == net))
            out.append(p)
        return out

    def route(self, net, starts, goals, layers=(0, 1, 2), fat=0, margin=4.0, via_cost=25,
              layer_cost=(1.0, 1.4, 1.0), via_goal=False, max_len=None, win=None, via_pred=None):
        """A* from any start cell to any goal cell (cells = (l, ix, iy)).
        via_goal=True: stop at the first cell where a via is legal (used for plane hook-ups).
        Returns list of (l, ix, iy) or None."""
        starts = list(starts)
        goals = set(goals)
        if not starts:
            return None
        pts = starts + list(goals)
        mc = int(margin / G)
        if win is None:
            ix0 = max(min(p[1] for p in pts) - mc, 0)
            ix1 = min(max(p[1] for p in pts) + mc, self.nx - 1)
            iy0 = max(min(p[2] for p in pts) - mc, 0)
            iy1 = min(max(p[2] for p in pts) + mc, self.ny - 1)
        else:
            a, b = self.ij(win[0], win[1])
            c, d = self.ij(win[2], win[3])
            ix0, iy0, ix1, iy1 = max(a, 0), max(b, 0), min(c, self.nx - 1), min(d, self.ny - 1)
        W, H = ix1 - ix0 + 1, iy1 - iy0 + 1
        pas = self.passable(net, (ix0, iy0, ix1, iy1))
        allp = pas[0] & pas[1] & pas[2] if self.nl == 3 else np.logical_and.reduce(pas)
        viaok = erode(allp, 2 + fat)
        if fat:
            pas = [erode(p, fat) for p in pas]
        forced = self.force.get(net, ())
        pb = []
        for l in range(self.nl):
            a = pas[l].copy()
            for (fl, fx, fy) in forced:
                if fl == l and ix0 <= fx <= ix1 and iy0 <= fy <= iy1:
                    a[fy - iy0, fx - ix0] = True
            pb.append(a.tobytes())
        for (vx, vy) in self.ownvia.get(net, ()):
            if ix0 <= vx <= ix1 and iy0 <= vy <= iy1:
                viaok[vy - iy0, vx - ix0] = True
        vb = viaok.tobytes()
        lay_ok = [l in layers for l in range(self.nl)]
        ownv = self.ownvia.get(net, set())
        goalset = set()
        gx = gy = None
        if not via_goal:
            for (l, ix, iy) in goals:
                if ix0 <= ix <= ix1 and iy0 <= iy <= iy1:
                    goalset.add((l * H + (iy - iy0)) * W + (ix - ix0))
            if not goalset:
                return None
            ga = np.array([(g % W, (g // W) % H) for g in goalset])
            gxmin, gxmax, gymin, gymax = ga[:, 0].min(), ga[:, 0].max(), ga[:, 1].min(), ga[:, 1].max()

            def hfun(x, y):
                dx = gxmin - x if x < gxmin else (x - gxmax if x > gxmax else 0)
                dy = gymin - y if y < gymin else (y - gymax if y > gymax else 0)
                return (dx + dy) - 0.5858 * (dx if dx < dy else dy)
        else:
            def hfun(x, y):
                return 0
        heap = []
        gsc = {}
        prev = {}
        for (l, ix, iy) in starts:
            if not (ix0 <= ix <= ix1 and iy0 <= iy <= iy1):
                continue
            k = (l * H + (iy - iy0)) * W + (ix - ix0)
            gsc[k] = 0.0
            prev[k] = -1
            heapq.heappush(heap, (hfun(ix - ix0, iy - iy0), 0.0, k))
        moves = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0), (1, 1, SQ2), (1, -1, SQ2), (-1, 1, SQ2), (-1, -1, SQ2))
        found = -1
        limit = (max_len / G) if max_len else None
        while heap:
            f, g, k = heapq.heappop(heap)
            if g > gsc.get(k, 1e18):
                continue
            l = k // (W * H)
            r = k - l * W * H
            y, x = divmod(r, W)
            if via_goal:
                if vb[r] and prev[k] != -1 and g > 3 and (via_pred is None or via_pred(x + ix0, y + iy0)):
                    found = k
                    break
            elif k in goalset:
                found = k
                break
            if limit and g > limit:
                continue
            p = pb[l]
            lc = layer_cost[l]
            for dx, dy, c in moves:
                nx_, ny_ = x + dx, y + dy
                if nx_ < 0 or ny_ < 0 or nx_ >= W or ny_ >= H:
                    continue
                nr = ny_ * W + nx_
                if not p[nr]:
                    continue
                if dx and dy and not (p[y * W + nx_] and p[ny_ * W + x]):
                    continue
                nk = l * W * H + nr
                ng = g + c * lc
                if ng < gsc.get(nk, 1e18):
                    gsc[nk] = ng
                    prev[nk] = k
                    heapq.heappush(heap, (ng + hfun(nx_, ny_), ng, nk))
            if vb[r] and not via_goal:
                for nl_ in range(self.nl):
                    if nl_ == l or not lay_ok[nl_]:
                        continue
                    nk = nl_ * W * H + r
                    ng = g + (1 if (x + ix0, y + iy0) in ownv else via_cost)
                    if ng < gsc.get(nk, 1e18):
                        gsc[nk] = ng
                        prev[nk] = k
                        heapq.heappush(heap, (ng + hfun(x, y), ng, nk))
        if found < 0:
            if gsc:
                ks = np.array(list(gsc.keys()))
                ls = ks // (W * H); rr = ks % (W * H)
                self.last_fail = dict(expanded=len(ks), layers=sorted(set(ls.tolist())), win=(self.xy(ix0, iy0), self.xy(ix1, iy1)),
                                      reach={int(l): (self.xy(int((rr[ls == l] % W).min()) + ix0, int((rr[ls == l] // W).min()) + iy0),
                                                      self.xy(int((rr[ls == l] % W).max()) + ix0, int((rr[ls == l] // W).max()) + iy0)) for l in set(ls.tolist())},
                                      ngoals=len(goalset) if not via_goal else -1, nstart=len(starts))
            return None
        path = []
        k = found
        while k != -1:
            l = k // (W * H)
            r = k - l * W * H
            y, x = divmod(r, W)
            path.append((l, x + ix0, y + iy0))
            k = prev[k]
        return path[::-1]

    @staticmethod
    def simplify(path):
        """split into per-layer polylines with collinear points removed; returns (segments, via_cells)"""
        segs, vias = [], []
        cur = [path[0]]
        for a, b in zip(path, path[1:]):
            if a[0] != b[0]:
                vias.append((a[1], a[2]))
                if len(cur) > 1:
                    segs.append(cur)
                cur = [b]
            else:
                cur.append(b)
        if len(cur) > 1:
            segs.append(cur)
        out = []
        for s in segs:
            pts = [s[0]]
            for i in range(1, len(s) - 1):
                d1 = (s[i][1] - s[i - 1][1], s[i][2] - s[i - 1][2])
                d2 = (s[i + 1][1] - s[i][1], s[i + 1][2] - s[i][2])
                if d1 != d2:
                    pts.append(s[i])
            pts.append(s[-1])
            out.append(pts)
        return out, vias
