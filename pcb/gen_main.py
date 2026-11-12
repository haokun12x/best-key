"""BK46 main board generator (KiCad pcbnew API).
run:  tools/kpy.sh pcb/gen_main.py
Creates pcb/main/bk46_main.kicad_pcb (+ .kicad_pro), pcb/main/netlist.json, pcb/main/keymap.json
"""
import os, sys, json, math, time
import numpy as np
import pcbnew
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'mech'))
from params import *
os.environ.setdefault('ROUTER_CLR', '0.15')     # router keeps 0.15 mm (DRC rule is 0.10 mm)
os.environ.setdefault('ROUTER_VIA', '0.45,0.2')  # 0.45 / 0.20 mm vias
import router as R

FPLIB = os.path.expanduser('~/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
OUT = os.path.join(HERE, os.environ.get('OUTDIR', 'main'))
os.makedirs(OUT, exist_ok=True)
OX, OY = 30.0, 110.0
LAY = {0: pcbnew.F_Cu, 1: pcbnew.In2_Cu, 2: pcbnew.B_Cu}
YB = 2 * U                       # centre line of the free middle band
mm = pcbnew.FromMM


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY - y))


def Wxy(v):
    return (pcbnew.ToMM(v.x) - OX, OY - pcbnew.ToMM(v.y))


board = pcbnew.CreateEmptyBoard() if hasattr(pcbnew, 'CreateEmptyBoard') else pcbnew.BOARD()
board.SetCopperLayerCount(4)
board.GetDesignSettings().SetBoardThickness(mm(PCB_T))

# ------------------------------------------------------------------ nets
NETS, NETID = {}, {}


def net(name):
    if name not in NETS:
        n = pcbnew.NETINFO_ITEM(board, name)
        board.Add(n)
        NETS[name] = n
        NETID[name] = len(NETID) + 1
    return NETS[name]


COMPONENTS = []          # for BOM / netlist


def place(lib, name, ref, value, x, y, rot=0, side='B', nets=None, pred=None, lcsc=''):
    fp = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + '.pretty'), name)
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetPosition(P(x, y))
    board.Add(fp)
    if side == 'B':
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    rots = [rot] if pred is None else [rot, (rot + 180) % 360, (rot + 90) % 360, (rot + 270) % 360]
    for r in rots:
        fp.SetOrientationDegrees(r)
        if pred is None or pred(fp):
            break
    else:
        raise RuntimeError('no orientation satisfies predicate for ' + ref)
    if nets:
        setnets(fp, nets)
    COMPONENTS.append(dict(ref=ref, value=value, footprint=lib + ':' + name, side=side, x=round(x, 3), y=round(y, 3), lcsc=lcsc))
    return fp


def setnets(fp, nets):
    for p in fp.Pads():
        n = nets.get(p.GetNumber())
        if n:
            p.SetNet(net(n))


def padxy(fp, num):
    pts = [Wxy(p.GetPosition()) for p in fp.Pads() if p.GetNumber() == num]
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def mean_xy(fp, nums):
    pts = [Wxy(p.GetPosition()) for p in fp.Pads() if p.GetNumber() in nums]
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def lset(*layers):
    ls = pcbnew.LSET()
    for l in layers:
        ls.AddLayer(l)
    return ls


def add_pad(fp, num, x, y, kind, size, drill=0, shape=pcbnew.PAD_SHAPE_CIRCLE, layers=None):
    """x,y in footprint-local KiCad coordinates (y down) before the footprint is moved"""
    p = pcbnew.PAD(fp)
    p.SetNumber(num)
    p.SetAttribute(kind)
    p.SetShape(shape)
    p.SetSize(pcbnew.VECTOR2I(mm(size[0]), mm(size[1])))
    if shape == pcbnew.PAD_SHAPE_ROUNDRECT:
        p.SetRoundRectRadiusRatio(0.2)
    if drill:
        p.SetDrillSize(pcbnew.VECTOR2I(mm(drill), mm(drill)))
    if layers is None:
        layers = pcbnew.PAD.UnplatedHoleMask() if kind == pcbnew.PAD_ATTRIB_NPTH else pcbnew.PAD.PTHMask()
    p.SetLayerSet(layers)
    p.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    fp.Add(p)
    return p


def text(fp, s, x, y, layer, size=0.8):
    t = pcbnew.PCB_TEXT(fp)
    t.SetText(s)
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(0.12))
    t.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    if layer in (pcbnew.B_SilkS, pcbnew.B_Fab):
        t.SetMirrored(True)
    fp.Add(t)


BSMD = lset(pcbnew.B_Cu, pcbnew.B_Mask, pcbnew.B_Paste)


def key_footprint(ref, cx, cy, rotated):
    """MX 3/5-pin + Kailh hot-swap socket (bottom side) footprint, switch on the top side."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetValue('MX_HS_TMR')
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    add_pad(fp, '', 0, 0, pcbnew.PAD_ATTRIB_NPTH, (4.0, 4.0), 4.0)
    add_pad(fp, '', -5.08, 0, pcbnew.PAD_ATTRIB_NPTH, (1.75, 1.75), 1.75)
    add_pad(fp, '', 5.08, 0, pcbnew.PAD_ATTRIB_NPTH, (1.75, 1.75), 1.75)
    add_pad(fp, '1', -3.81, -2.54, pcbnew.PAD_ATTRIB_PTH, (3.3, 3.3), 3.0)
    add_pad(fp, '2', 2.54, -5.08, pcbnew.PAD_ATTRIB_PTH, (3.3, 3.3), 3.0)
    add_pad(fp, '1', -7.36, -2.54, pcbnew.PAD_ATTRIB_SMD, (2.55, 2.5), 0, pcbnew.PAD_SHAPE_ROUNDRECT, BSMD)
    add_pad(fp, '1', -5.635, -2.54, pcbnew.PAD_ATTRIB_SMD, (1.65, 2.5), 0, pcbnew.PAD_SHAPE_RECT, lset(pcbnew.B_Cu, pcbnew.B_Mask))
    add_pad(fp, '2', 6.09, -5.08, pcbnew.PAD_ATTRIB_SMD, (2.55, 2.5), 0, pcbnew.PAD_SHAPE_ROUNDRECT, BSMD)
    add_pad(fp, '2', 4.34, -5.08, pcbnew.PAD_ATTRIB_SMD, (1.65, 2.5), 0, pcbnew.PAD_SHAPE_RECT, lset(pcbnew.B_Cu, pcbnew.B_Mask))
    text(fp, ref, 0, 7.6, pcbnew.B_SilkS, 0.9)
    fp.SetPosition(P(cx, cy))
    fp.SetOrientationDegrees(180 if rotated else 0)
    board.Add(fp)
    return fp


def mount_hole(ref, x, y):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetValue('M2 standoff 3.5mm')
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    add_pad(fp, '1', 0, 0, pcbnew.PAD_ATTRIB_PTH, (3.6, 3.6), 2.2)
    fp.SetPosition(P(x, y))
    board.Add(fp)
    setnets(fp, {'1': 'GND'})
    return fp


def tp(ref, x, y, netname, size=1.5, side='B'):
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetValue(netname)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    L = lset(pcbnew.B_Cu, pcbnew.B_Mask) if side == 'B' else lset(pcbnew.F_Cu, pcbnew.F_Mask)
    add_pad(fp, '1', 0, 0, pcbnew.PAD_ATTRIB_SMD, (size, size), 0, pcbnew.PAD_SHAPE_ROUNDRECT, L)
    text(fp, netname.replace('+', ''), 0, -size / 2 - 0.7, pcbnew.B_SilkS if side == 'B' else pcbnew.F_SilkS, 0.7)
    fp.SetPosition(P(x, y))
    board.Add(fp)
    setnets(fp, {'1': netname})
    COMPONENTS.append(dict(ref=ref, value='pad ' + netname, footprint='solder pad %.1fmm' % size, side=side, x=x, y=y, lcsc='-'))
    return fp


# ================================================================== placement
ROWY = [U * (r + 0.5) for r in range(ROWS)]
KEYINFO = {}
key_index = {k: i for i, k in enumerate(KEYS)}
C0402, R0402, C0603, C0805 = ('Capacitor_SMD', 'C_0402_1005Metric'), ('Resistor_SMD', 'R_0402_1005Metric'), ('Capacitor_SMD', 'C_0603_1608Metric'), ('Capacitor_SMD', 'C_0805_2012Metric')
SOT23 = ('Package_TO_SOT_SMD', 'SOT-23')

for (c, r) in KEYS:
    i = key_index[(c, r)]
    cx, cy = cell_center(c, r)
    rot = r in ROT_ROWS
    chan = 'W' if c == 3 else 'E'
    s = 1 if ((chan == 'E') != rot) else -1          # local side of the KEY pin / resistor
    keypin = '2' if s > 0 else '1'
    kn, son = 'KEY_%d_%d' % (c, r), 'SO_%d_%d' % (c, r)
    sw = key_footprint('SW%d' % (i + 1), cx, cy, rot)
    setnets(sw, {keypin: kn, ('1' if keypin == '2' else '2'): 'GND'})

    def w(lx, ly):
        return (cx - lx, cy - ly) if rot else (cx + lx, cy + ly)
    ux, uy = w(0, -3.5)
    u = place(*SOT23, 'U%d' % (100 + i), 'TMR2617S', ux, uy, 0, 'B', {'1': 'VSENSE', '2': son, '3': 'GND'}, lcsc='TMR2617S (MDT)')
    def nudge(q):          # keep clear of the module's antenna keep-out
        if 28.0 < q[1] < 34.5 and abs(q[0] - 4 * U) < 6.7:
            return (q[0] + (0.4 if q[0] > 4 * U else -0.4), q[1])
        return q
    rx, ry = nudge(w(s * 3.1, -2.3))
    rr = place(*R0402, 'R%d' % (100 + i), '10k', rx, ry, 90, 'B', lcsc='C25744')
    # resistor pad nearer to the socket pin gets KEY
    pk = padxy(sw, keypin)
    pads = sorted(rr.Pads(), key=lambda p: abs(Wxy(p.GetPosition())[1] - pk[1]))
    pads[0].SetNet(net(kn))
    pads[1].SetNet(net(son))
    qx, qy = nudge(w(-s * 3.1, -2.3))
    place(*C0402, 'C%d' % (100 + i), '22n', qx, qy, 90, 'B', {'1': 'VSENSE', '2': 'GND'}, lcsc='C1532')
    lx, ly = w(0, -4.7)
    led = place('LED_SMD', 'LED_WS2812B-2020_PLCC4_2.0x2.0mm', 'D%d' % (100 + i), 'WS2812B-2020', lx, ly, 0, 'F', lcsc='C965555')
    def cap_ok(q):
        if any(math.hypot(q[0] - sx, q[1] - sy) < 3.4 for sx, sy in STANDOFFS):
            return False
        if abs(q[0] - 4 * U) < 7.0 and 28.5 < q[1] < 48.0:           # under the MCU module / antenna
            return False
        if q[1] > PCB_KNOB_NOTCH[1] - 1 and (q[0] < PCB_KNOB_NOTCH[0] + 1.2 or q[0] > FIELD_W - PCB_KNOB_NOTCH_R - 1.2):
            return False
        return PCB_X0 + 0.8 < q[0] < PCB_X1 - 0.8
    for cand in (w(8.2, -4.7), w(-8.2, -4.7)):
        if cap_ok(cand):
            place(*C0402, 'C%d' % (200 + i), '100n', cand[0], cand[1], 90, 'F', {'1': 'VLED', '2': 'GND'}, lcsc='C1525')
            break
    KEYINFO[(c, r)] = dict(sw=sw, u=u, r=rr, led=led, keypin=keypin, chan=chan, kn=kn, son=son, cx=cx, cy=cy)

# LED chain (Hamiltonian path starting next to the MCU)
chain = [(c, 1) for c in range(4, -1, -1)] + [(c, 0) for c in range(12)] + [(c, 1) for c in range(11, 4, -1)] + \
        [(c, 2) for c in range(5, 12)] + [(c, 3) for c in range(10, 0, -1)] + [(c, 2) for c in range(0, 5)]
assert sorted(chain) == sorted(KEYS), 'LED chain must visit every key once'
for n, k in enumerate(chain):
    din = 'LED_DIN' if n == 0 else 'LD%d' % n
    dout = 'LD%d' % (n + 1) if n < len(chain) - 1 else None
    setnets(KEYINFO[k]['led'], {'4': 'VLED', '2': 'GND', '3': din, **({'1': dout} if dout else {})})
    KEYINFO[k]['led_index'] = n

for n, (sx, sy) in enumerate(STANDOFFS):
    mount_hole('H%d' % (n + 1), sx, sy)

# ---- analog muxes
MUX = []
for g in range(3):
    xm = (4 * g + 2) * U
    fp = place('Package_SO', 'SSOP-24_5.3x8.2mm_P0.65mm', 'U%d' % (10 + g), 'CD74HC4067SM96', xm + 2.7, YB, 0, 'B', lcsc='C98457')
    inp = [p for p in fp.Pads() if p.GetNumber() in [str(n) for n in list(range(2, 10)) + list(range(16, 24))]]
    my = sum(Wxy(p.GetPosition())[1] for p in inp) / len(inp)
    fp.SetPosition(P(xm + 2.7, YB + (YB - my)))
    setnets(fp, {'1': 'MUX' + 'ABC'[g], '10': 'S0', '11': 'S1', '14': 'S2', '13': 'S3', '12': 'GND', '15': 'GND', '24': '+3V3'})
    place(*C0402, 'C%d' % (10 + g), '100n', xm + 2.7, YB + 5.6, 0, 'B', {'1': '+3V3', '2': 'GND'}, lcsc='C1525')
    MUX.append(dict(fp=fp, xm=xm, xc=xm + 2.7))

# ---- MCU module (antenna towards the front)
MODX, MODY = 4 * U, 38.05
U1 = place('RF_Module', 'Raytac_MDBT50Q', 'U1', 'MDBT50Q-1MV2', MODX, MODY, 0, 'B',
           pred=lambda f: mean_xy(f, [str(n) for n in range(15, 34)])[1] > Wxy(f.GetPosition())[1] + 3, lcsc='C5118826')
MOD_NETS = {'1': 'GND', '2': 'GND', '15': 'GND', '33': 'GND', '55': 'GND', '28': '+3V3', '30': '+3V3', '32': 'VBUS',
            '34': 'USB_DM', '35': 'USB_DP', '51': 'SWDIO', '53': 'SWCLK', '40': 'RESET',
            '10': 'MUXA', '12': 'MUXB', '14': 'MUXC', '20': 'VBAT_SNS',
            '16': 'S0', '22': 'S1', '24': 'S2', '26': 'S3',
            # left knob on the west side of the module, right knob on the east side
            '3': 'K1U', '4': 'K1V', '6': 'K1W', '8': 'ENC_CSN1',
            '37': 'K2U', '39': 'K2V', '41': 'K2W', '44': 'ENC_CSN2', '46': 'ENC_CLK', '48': 'ENC_DO',
            '36': 'SDA', '38': 'SCL', '42': 'KNOB_PWR_EN', '45': 'LED_DIN',
            '5': 'SENSE_EN', '7': 'LED_EN', '9': 'CHG', '11': 'FL_CS', '13': 'FL_CLK', '19': 'FL_MOSI', '21': 'FL_MISO'}
setnets(U1, MOD_NETS)
MOD_GPIO = {'3': 'P1.10', '4': 'P1.11', '5': 'P1.12', '6': 'P1.13', '7': 'P1.14', '8': 'P1.15', '9': 'P0.03', '10': 'P0.29', '12': 'P0.31',
            '14': 'P0.30', '16': 'P0.27', '20': 'P0.04', '22': 'P0.06', '24': 'P0.08', '26': 'P1.09', '36': 'P0.14', '37': 'P0.13',
            '38': 'P0.16', '39': 'P0.15', '40': 'P0.18', '41': 'P0.17', '42': 'P0.19', '43': 'P0.21', '44': 'P0.20', '45': 'P0.23',
            '46': 'P0.22', '48': 'P0.24', '11': 'P0.02', '13': 'P0.28', '19': 'P0.26', '21': 'P0.05'}
place(*C0402, 'C1', '100n', MODX - 8.4, MODY + 2.3, 90, 'B', {'1': '+3V3', '2': 'GND'}, lcsc='C1525')
place(*C0603, 'C2', '4u7', MODX - 8.4, MODY, 90, 'B', {'1': '+3V3', '2': 'GND'}, lcsc='C19666')
place(*C0603, 'C3', '4u7', 63.3, 71.4, 0, 'B', {'1': 'VBUS', '2': 'GND'}, lcsc='C19666')
place('Package_SO', 'SOIC-8_3.9x4.9mm_P1.27mm', 'U6', 'W25Q32JVSSIQ (optional)', 97.6, YB, 90, 'B',
      {'1': 'FL_CS', '2': 'FL_MISO', '3': '+3V3', '4': 'GND', '5': 'FL_MOSI', '6': 'FL_CLK', '7': '+3V3', '8': '+3V3'}, lcsc='C179171')

# ---- USB-C, ESD
J1 = place('Connector_USB', 'USB_C_Receptacle_HRO_TYPE-C-31-M-12', 'J1', 'USB-C 16P', USB_X, Y1 - 0.7 - 3.65, 0, 'B',
           {'A1': 'GND', 'B1': 'GND', 'A12': 'GND', 'B12': 'GND', 'A4': 'VBUS', 'B4': 'VBUS', 'A9': 'VBUS', 'B9': 'VBUS',
            'A5': 'CC1', 'B5': 'CC2', 'A6': 'USB_DP', 'B6': 'USB_DP', 'A7': 'USB_DM', 'B7': 'USB_DM', 'SH': 'GND'},
           pred=lambda f: padxy(f, 'A6')[1] < Wxy(f.GetPosition())[1] - 2, lcsc='C165948')
place('Package_TO_SOT_SMD', 'SOT-23-6', 'U3', 'USBLC6-2SC6', USB_X, 67.7, 0, 'B',
      {'1': 'USB_DP', '6': 'USB_DP', '3': 'USB_DM', '4': 'USB_DM', '2': 'GND', '5': 'VBUS'}, lcsc='C7519')
place(*R0402, 'R1', '5k1', USB_X - 5.0, 69.6, 90, 'B', {'1': 'CC1', '2': 'GND'}, lcsc='C25905')
place(*R0402, 'R2', '5k1', USB_X + 5.0, 69.6, 90, 'B', {'1': 'CC2', '2': 'GND'}, lcsc='C25905')

# ---- charger / power path (back strip, bay 4U..5U)
SOD = ('Diode_SMD', 'D_SOD-123')
place(*SOD, 'D1', 'B5819W', 66.2, 74.0, 0, 'B', {'1': 'VIN', '2': 'VBUS'}, lcsc='C8598')
U4 = place('Package_DFN_QFN', 'VQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm', 'U4', 'BQ24075RGT', 76.25, 71.75, 0, 'B',
           {'1': 'TS', '2': 'VBAT', '3': 'VBAT', '4': 'GND', '5': 'GND', '6': 'EN1', '8': 'GND', '9': 'CHG', '10': 'VSYS', '11': 'VSYS',
            '12': 'ILIM', '13': 'VIN', '15': 'GND', '16': 'ISET', '17': 'GND', '': 'GND'}, lcsc='C15220')
place(*C0603, 'C4', '1u', 78.3, 68.8, 0, 'B', {'1': 'VIN', '2': 'GND'}, lcsc='C15849')
place(*C0603, 'C5', '4u7', 71.6, 72.4, 0, 'B', {'1': 'VBAT', '2': 'GND'}, lcsc='C19666')
place(*C0603, 'C6', '4u7', 80.7, 72.4, 0, 'B', {'1': 'VSYS', '2': 'GND'}, lcsc='C19666')
place(*R0402, 'R3', '2k2', 73.9, 68.8, 0, 'B', {'1': 'ISET', '2': 'GND'}, lcsc='C25879')
place(*R0402, 'R4', '1k5', 80.3, 70.6, 0, 'B', {'1': 'ILIM', '2': 'GND'}, lcsc='C25867')
place(*R0402, 'R5', '10k', 72.0, 70.6, 0, 'B', {'1': 'TS', '2': 'GND'}, lcsc='C25744')
place(*R0402, 'R6', '10k', 74.4, 74.6, 0, 'B', {'1': 'EN1', '2': 'VIN'}, lcsc='C25744')
place(*SOT23, 'U5', 'XC6206P332MR', 89.6, 73.8, 0, 'B', {'1': 'GND', '2': '+3V3', '3': 'VSYS'}, lcsc='C5446')
place(*C0603, 'C7', '1u', 93.4, 74.7, 0, 'B', {'1': '+3V3', '2': 'GND'}, lcsc='C15849')
place(*SOD, 'D2', 'B5819W', 95.25, 70.9, 0, 'B', {'1': 'VIN', '2': 'QI5V'}, lcsc='C8598')
tp('TP1', 97.6, 74.2, 'QI5V')
tp('TP2', 100.0, 74.2, 'GND')
# sensor rail switch
place(*SOT23, 'Q1', 'AO3401A', 110.4, 73.7, 0, 'B', {'1': 'SENSE_EN', '2': '+3V3', '3': 'VSENSE'}, lcsc='C15127')
place(*R0402, 'R7', '100k', 110.4, 70.6, 0, 'B', {'1': '+3V3', '2': 'SENSE_EN'}, lcsc='C25741')
place(*C0603, 'C8', '1u', 111.4, 68.6, 0, 'B', {'1': 'VSENSE', '2': 'GND'}, lcsc='C15849')
# LED rail switch (P-FET + N-FET level shifter)
place(*SOT23, 'Q3', 'AO3401A', 169.0, 73.7, 0, 'B', {'1': 'LED_G', '2': 'VSYS', '3': 'VLED'}, lcsc='C15127')
place(*SOT23, 'Q4', '2N7002', 174.0, 73.7, 0, 'B', {'1': 'LED_EN', '2': 'GND', '3': 'LED_G'}, lcsc='C8545')
place(*R0402, 'R9', '100k', 171.5, 70.6, 0, 'B', {'1': 'VSYS', '2': 'LED_G'}, lcsc='C25741')
place(*R0402, 'R12', '100k', 175.6, 70.6, 0, 'B', {'1': 'LED_EN', '2': 'GND'}, lcsc='C25741')
place(*C0805, 'C9', '10u', 171.5, 68.6, 0, 'B', {'1': 'VLED', '2': 'GND'}, lcsc='C15850')
# battery
J4 = place('Connector_JST', 'JST_SH_SM02B-SRSS-TB_1x02-1MP_P1.00mm_Horizontal', 'J4', 'BAT (JST-SH 2P)', 7 * U, 72.6, 90, 'B',
           {'MP': 'GND'}, pred=lambda f: mean_xy(f, ['MP'])[0] > mean_xy(f, ['1', '2'])[0], lcsc='C160402')
bp = sorted([p for p in J4.Pads() if p.GetNumber() in ('1', '2')], key=lambda p: Wxy(p.GetPosition())[1])
bp[1].SetNet(net('VBAT'))       # northern pin = BAT+
bp[0].SetNet(net('GND'))
place(*R0402, 'R10', '1M', 128.4, 73.6, 0, 'B', {'1': 'VBAT', '2': 'VBAT_SNS'}, lcsc='C26083')
place(*R0402, 'R11', '1M', 128.4, 72.2, 0, 'B', {'1': 'VBAT_SNS', '2': 'GND'}, lcsc='C26083')
place(*C0402, 'C12', '100n', 128.4, 70.8, 0, 'B', {'1': 'VBAT_SNS', '2': 'GND'}, lcsc='C1525')
# knob 3V3 switch
place(*SOT23, 'Q2', 'AO3401A', 148.4, 73.7, 0, 'B', {'1': 'KNOB_PWR_EN', '2': '+3V3', '3': 'K3V3'}, lcsc='C15127')
place(*R0402, 'R8', '100k', 148.4, 70.6, 0, 'B', {'1': '+3V3', '2': 'KNOB_PWR_EN'}, lcsc='C25741')
# knob FFC connectors (cable leaves towards the back wall, U-turns down to the knob board)
FFC_ORDER = ['VSYS', 'VSYS', 'VSYS', 'GND', 'GND', 'GND', 'K3V3', 'U', 'V', 'W', 'PRESS', 'CSN', 'ENC_CLK', 'ENC_DO']
FFCS = []
for k, fx in enumerate((2 * U + 0.05, 10 * U + 0.05)):
    j = place('Connector_FFC-FPC', 'Hirose_FH12-14S-0.5SH_1x14-1MP_P0.50mm_Horizontal', 'J%d' % (2 + k), 'FFC 14P 0.5mm', fx, 72.3, 0, 'B',
              {'MP': 'GND'}, pred=lambda f: mean_xy(f, ['MP'])[1] > padxy(f, '1')[1] + 1, lcsc='C11084')
    sig = sorted([p for p in j.Pads() if p.GetNumber() != 'MP'], key=lambda p: Wxy(p.GetPosition())[0])
    order = FFC_ORDER if k == 0 else FFC_ORDER[::-1]        # mirrored board for the right knob
    pinmap = {}
    for p, nm in zip(sig, order):
        nm2 = {'U': 'K%dU' % (k + 1), 'V': 'K%dV' % (k + 1), 'W': 'K%dW' % (k + 1), 'CSN': 'ENC_CSN%d' % (k + 1), 'PRESS': 'PRESS%d' % (k + 1)}.get(nm, nm)
        p.SetNet(net(nm2))
        pinmap[p.GetNumber()] = nm2
    place(*C0805, 'C%d' % (20 + k), '22u', fx + (-9.3 if k == 0 else 9.3), 74.4, 0, 'B', {'1': 'VSYS', '2': 'GND'}, lcsc='C45783')
    FFCS.append(pinmap)
# display + debug pads
for n, (nm, dx) in enumerate((('GND', -3.0), ('+3V3', -1.0), ('SCL', 1.0), ('SDA', 3.0))):
    tp('TP%d' % (10 + n), DISP_X + dx * 1.1, 3.0, nm, 1.6)
for n, nm in enumerate(('SWDIO', 'SWCLK', 'RESET', 'GND', '+3V3')):
    tp('TP%d' % (20 + n), 91.0 + 2.4 * n, YB + 5.3, nm, 1.3)

# ================================================================== outline
def outline_pts():
    a, b = PCB_X0, PCB_X1
    pts = [(a, PCB_Y0)]
    yn = PCB_Y0 + PCB_SCREW_NOTCH_D
    feats = [(sx - PCB_SCREW_NOTCH_W / 2, sx + PCB_SCREW_NOTCH_W / 2, yn) for sx in SCREW_X]
    feats.append((DISP_X - DISP_W / 2 - 1.0, DISP_X + DISP_W / 2 + 1.0, DISP_PCB_NOTCH_Y))
    for x0, x1, y in sorted(feats):
        pts += [(x0, PCB_Y0), (x0, y), (x1, y), (x1, PCB_Y0)]
    kx, ky = PCB_KNOB_NOTCH
    pts += [(b, PCB_Y0), (b, ky), (FIELD_W - PCB_KNOB_NOTCH_R, ky), (FIELD_W - PCB_KNOB_NOTCH_R, PCB_Y1)]
    yb = PCB_Y1 - PCB_SCREW_NOTCH_D
    back = [(SCREW_X[2] + PCB_SCREW_NOTCH_W / 2, SCREW_X[2] - PCB_SCREW_NOTCH_W / 2, yb, 'n'),
            (SCREW_X[1] + PCB_SCREW_NOTCH_W / 2, SCREW_X[1] - PCB_SCREW_NOTCH_W / 2, yb, 'n')]
    for x1, x0, y, _ in back:
        pts += [(x1, PCB_Y1), (x1, y), (x0, y), (x0, PCB_Y1)]
    t = USB_TAB_W / 2
    pts += [(USB_X + t, PCB_Y1), (USB_X + t, USB_TAB_Y), (USB_X + 4.6, USB_TAB_Y), (USB_X + 4.6, Y1 - 1.2),
            (USB_X - 4.6, Y1 - 1.2), (USB_X - 4.6, USB_TAB_Y), (USB_X - t, USB_TAB_Y), (USB_X - t, PCB_Y1)]
    pts += [(kx, PCB_Y1), (kx, ky), (a, ky)]
    return pts


OUTLINE = outline_pts()
for (xa, ya), (xb, yb_) in zip(OUTLINE, OUTLINE[1:] + OUTLINE[:1]):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(xa, ya))
    s.SetEnd(P(xb, yb_))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.1))
    board.Add(s)

# ================================================================== router setup
rt = R.Router(-1.0, -1.0, FIELD_W + 1.0, Y1 + 0.5)
xs = rt.x0 + np.arange(rt.nx) * R.G
ys = rt.y0 + np.arange(rt.ny) * R.G
XX, YY = np.meshgrid(xs, ys)
inside = np.zeros(XX.shape, bool)
n = len(OUTLINE)
for i in range(n):
    (xa, ya), (xb, yb_) = OUTLINE[i], OUTLINE[(i + 1) % n]
    if ya == yb_:
        continue
    cond = ((ya > YY) != (yb_ > YY)) & (XX < (xb - xa) * (YY - ya) / (yb_ - ya) + xa)
    inside ^= cond
edge_block = ~R.erode(inside, 4)
for l in range(3):
    rt.multi[l] |= edge_block

PADCELLS = {}        # (ref, padnumber, idx) -> cells
PADS_BY_NET = {}


def register_pads():
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for idx, p in enumerate(fp.Pads()):
            bb = p.GetBoundingBox()
            xa, xb = pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetRight()) - OX
            ya, yb_ = OY - pcbnew.ToMM(bb.GetBottom()), OY - pcbnew.ToMM(bb.GetTop())
            tht = p.GetDrillSize().x > 0
            if tht:
                layers = [0, 1, 2]
            elif p.IsOnLayer(pcbnew.F_Cu):
                layers = [0]
            elif p.IsOnLayer(pcbnew.B_Cu):
                layers = [2]
            else:
                continue
            nm = p.GetNetname()
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                cx, cy = (xa + xb) / 2, (ya + yb_) / 2
                rt.mark_disc(layers, cx, cy, (xb - xa) / 2, -1, R.INFL + 0.08)
                continue
            nid = NETID.get(nm, -1)
            if tht and abs((xb - xa) - (yb_ - ya)) < 0.01:
                rt.mark_disc(layers, (xa + xb) / 2, (ya + yb_) / 2, (xb - xa) / 2, nid, R.INFL + 0.12)
            else:
                rt.mark_rect(layers, xa, ya, xb, yb_, nid)
            if nid > 0 and tht:
                cx_, cy_ = (xa + xb) / 2, (ya + yb_) / 2
                q_ = min(xb - xa, yb_ - ya) / 2 * 0.6
                cells = rt.add_conn_rect(layers, cx_ - q_, cy_ - q_, cx_ + q_, cy_ + q_, nid)
                THT_CELLS.setdefault(nid, set()).update(cells)
                PADS_BY_NET.setdefault(nm, []).append(dict(ref=ref, num=p.GetNumber(), cells=cells, layers=layers, tht=tht,
                                                           x=cx_, y=cy_, w=xb - xa, h=yb_ - ya))
            elif nid > 0:
                fine = len(fp.Pads()) >= 8 and not tht
                cells = rt.add_conn_rect(layers, xa, ya, xb, yb_, nid)
                PADCELLS[(ref, p.GetNumber(), idx)] = cells
                PADONLY.setdefault(nid, set()).update(cells)
                PADS_BY_NET.setdefault(nm, []).append(dict(ref=ref, num=p.GetNumber(), cells=cells, layers=layers, tht=tht,
                                                           x=(xa + xb) / 2, y=(ya + yb_) / 2, w=xb - xa, h=yb_ - ya))


ANT = (MODX - 5.4, MODY - 8.5, MODX + 5.4, MODY - 4.2)
for z_ in U1.Zones():
    bb_ = z_.GetBoundingBox()
    ANT = (pcbnew.ToMM(bb_.GetLeft()) - OX - 0.1, OY - pcbnew.ToMM(bb_.GetBottom()) - 0.1, pcbnew.ToMM(bb_.GetRight()) - OX + 0.1, OY - pcbnew.ToMM(bb_.GetTop()) + 0.1)
print('antenna keep-out', [round(v, 2) for v in ANT])

NTRACK = NVIA = 0
PADONLY = {}          # net id -> cells that are only SMD pad interiors (not proof of a plane connection)
VIA_CELLS = set()
THT_CELLS = {}


def add_track(netname, l, xa, ya, xb, yb_, w=R.TW):
    global NTRACK
    if abs(xa - xb) < 1e-6 and abs(ya - yb_) < 1e-6:
        return
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(P(xa, ya))
    t.SetEnd(P(xb, yb_))
    t.SetWidth(mm(w))
    t.SetLayer(LAY[l])
    t.SetNet(net(netname))
    board.Add(t)
    rt.mark_seg(l, xa, ya, xb, yb_, w, NETID[netname])
    NTRACK += 1


VIA_POS = set()


def add_via(netname, x, y, d=R.VIA_D, drill=R.VIA_DRILL):
    global NVIA
    key_ = (round(x, 2), round(y, 2))
    if key_ in VIA_POS:
        return
    VIA_POS.add(key_)
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(x, y))
    v.SetDrill(mm(drill))
    v.SetWidth(pcbnew.F_Cu, mm(d))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(net(netname))
    board.Add(v)
    rt.mark_via(x, y, NETID[netname], d)
    ix_, iy_ = rt.ij(x, y)
    for l_ in range(3):
        VIA_CELLS.add((l_, ix_, iy_))
    NVIA += 1


def commit(path, netname, w=R.TW):
    segs, vias = R.Router.simplify(path)
    for pts in segs:
        l = pts[0][0]
        for a, b in zip(pts, pts[1:]):
            xa, ya = rt.xy(a[1], a[2])
            xb, yb_ = rt.xy(b[1], b[2])
            add_track(netname, l, xa, ya, xb, yb_, w)
    for ix, iy in vias:
        add_via(netname, *rt.xy(ix, iy))


# ================================================================== deterministic key routing
KEYMAP = []
OFF = {('near', 'inner'): 0.325, ('near', 'outer'): 0.975, ('far', 'inner'): 1.625, ('far', 'outer'): 2.275}
XE = {('W', 'near', 'inner'): -5.85, ('W', 'near', 'outer'): -5.15, ('W', 'far', 'inner'): -6.55, ('W', 'far', 'outer'): -7.25,
      ('E', 'near', 'inner'): 5.15, ('E', 'near', 'outer'): 5.85, ('E', 'far', 'inner'): 6.55, ('E', 'far', 'outer'): 7.25}
MUX_IN = {}
for nn in range(8):
    MUX_IN[str(9 - nn)] = nn          # pins 9..2 -> I0..I7
    MUX_IN[str(23 - nn)] = 8 + nn     # pins 23..16 -> I8..I15

for (c, r) in KEYS:
    ki = KEYINFO[(c, r)]
    g, i = c // 4, c % 4
    m = MUX[g]
    side = 'W' if i < 2 else 'E'
    nf = 'near' if i in (1, 2) else 'far'
    io = 'inner' if r in (1, 2) else 'outer'
    yl = YB + (OFF[(nf, io)] if r >= 2 else -OFF[(nf, io)])
    d = 3.15 if io == 'inner' else 2.45
    xch = (c + 1) * U - d if ki['chan'] == 'E' else c * U + d
    xe = m['xc'] + XE[(side, nf, io)]
    px, py = [Wxy(p_.GetPosition()) for p_ in ki['sw'].Pads() if p_.GetNumber() == ki['keypin'] and p_.GetDrillSize().x > 0][0]
    kn = ki['kn']
    add_track(kn, 1, px, py, xch, py)
    add_track(kn, 1, xch, py, xch, yl)
    add_via(kn, xch, yl, 0.45, 0.2)
    if abs(xch - xe) > 0.01:
        add_track(kn, 0, xch, yl, xe, yl)
        add_via(kn, xe, yl, 0.45, 0.2)
    # mux input pad on that side at that y
    cand = [p for p in m['fp'].Pads() if p.GetNumber() in MUX_IN and abs(Wxy(p.GetPosition())[1] - yl) < 0.05
            and ((Wxy(p.GetPosition())[0] < m['xc']) == (side == 'W'))]
    assert len(cand) == 1, (c, r, yl, len(cand))
    pad = cand[0]
    pad.SetNet(net(kn))
    pxm, pym = Wxy(pad.GetPosition())
    add_track(kn, 2, xe, yl, pxm, yl)
    KEYMAP.append(dict(key='%d,%d' % (c, r), col=c, row=r, mux='ABC'[g], channel=MUX_IN[pad.GetNumber()], led=ki['led_index'],
                       rotated=r in ROT_ROWS, net=kn))

for g_, nm_ in ((0, 'PRESS1'), (2, 'PRESS2')):
    spare = [p_ for p_ in MUX[g_]['fp'].Pads() if p_.GetNumber() in MUX_IN and not p_.GetNetname()]
    assert len(spare) == 1, len(spare)
    spare[0].SetNet(net(nm_))
    KEYMAP.append(dict(key='knob%d_press' % (1 if g_ == 0 else 2), mux='ABC'[g_], channel=MUX_IN[spare[0].GetNumber()], net=nm_))
register_pads()
# antenna keep-out: no copper on any layer under the module antenna
rt.mark_rect([0, 1, 2], *ANT, -1, 0.1)


FAN_VIA = set()


def hits2(cx, cy, sx, sy, L, p, boxes, mg):
    ex, ey = cx + sx * L, cy + sy * L
    return any(q is not p and xa2 - mg < ex < xb2 + mg and ya2 - mg < ey < yb2 + mg for xa2, ya2, xb2, yb2, q in boxes)


def fanout():
    """pre-route a short escape stub out of every fine-pitch pad so that later routes cannot wall it in"""
    n_ = 0
    for fp in board.GetFootprints():
        pads = list(fp.Pads())
        if len(pads) < 8:
            continue
        fx, fy = Wxy(fp.GetPosition())
        ref_ = fp.GetReference()
        boxes = []
        cnt = 0
        for p in pads:
            bb = p.GetBoundingBox()
            boxes.append((pcbnew.ToMM(bb.GetLeft()) - OX, OY - pcbnew.ToMM(bb.GetBottom()), pcbnew.ToMM(bb.GetRight()) - OX, OY - pcbnew.ToMM(bb.GetTop()), p))
        for xa, ya, xb, yb_, p in boxes:
            nm = p.GetNetname()
            if not nm or nm.startswith('KEY_') or p.GetDrillSize().x > 0:
                continue
            w_, h_ = xb - xa, yb_ - ya
            if min(w_, h_) > (0.65 if ref_ == 'J1' else 0.45) or max(w_, h_) > 2.0:
                continue
            cx, cy = (xa + xb) / 2, (ya + yb_) / 2
            if w_ <= h_:
                dx, dy = 0.0, (1.0 if cy >= fy else -1.0)
                half = h_ / 2
            else:
                dx, dy = (1.0 if cx >= fx else -1.0), 0.0
                half = w_ / 2
            L = half + 0.7
            dogbone = ref_ in ('U1', 'J2', 'J3') or (ref_ == 'J1' and p.GetNumber() in ('B6', 'B7'))
            if dogbone:
                cnt += 1
                if ref_ == 'U1':
                    L += 0.4 + (0.8 if cnt % 2 else 0.0)
                elif ref_ == 'J1':
                    L += 1.3
                else:
                    L += 0.9 if cnt % 2 else 0.0

            mg = 0.45 if ref_ == 'U1' else 0.15

            def hits(sx, sy):
                for t_ in (half + 0.3, half + 0.7, half + 1.1, L):
                    ex, ey = cx + sx * t_, cy + sy * t_
                    if any(q is not p and xa2 - mg < ex < xb2 + mg and ya2 - mg < ey < yb2 + mg for xa2, ya2, xb2, yb2, q in boxes):
                        return True
                return False
            if hits(dx, dy):
                dx, dy = -dx, -dy
                if hits(dx, dy):
                    continue
            l = 0 if p.IsOnLayer(pcbnew.F_Cu) else 2
            ex, ey = round((cx + dx * L) * 10) / 10 if dx else cx, round((cy + dy * L) * 10) / 10 if dy else cy
            nid_ = NETID[nm]

            def free_(L_):
                for t_ in np.arange(half + 0.35, L_ + 0.01, 0.1):
                    ix_, iy_ = rt.ij(cx + dx * t_, cy + dy * t_)
                    if rt.multi[l][iy_, ix_] or rt.owner[l][iy_, ix_] not in (0, nid_):
                        return False
                return True
            while L > half + 0.5 and not free_(L):
                L -= 0.2
            ex, ey = round((cx + dx * L) * 10) / 10 if dx else cx, round((cy + dy * L) * 10) / 10 if dy else cy
            small = ref_ in ('J2', 'J3')
            vd, vdr = (0.45, 0.2) if small else (R.VIA_D, R.VIA_DRILL)
            if dogbone:
                ok_ = False
                for dL in (0.0, 0.4, -0.4, 0.8):
                    ex2 = round((cx + dx * (L + dL)) * 10) / 10 if dx else cx
                    ey2 = round((cy + dy * (L + dL)) * 10) / 10 if dy else cy
                    if not hits2(cx, cy, dx, dy, L + dL, p, boxes, mg) and free_(L + dL) and rt.via_legal(nid_, ex2, ey2, vd):
                        ex, ey, ok_ = ex2, ey2, True
                        break
            before_ = set(rt.conn.get(nid_, set()))
            add_track(nm, l, cx, cy, ex, ey)
            rt.force.setdefault(nid_, set()).update(set(rt.conn[nid_]) - before_)
            if dogbone and ok_:
                add_via(nm, ex, ey, vd, vdr)
                FAN_VIA.add((ref_, p.GetNumber()))
            n_ += 1
    # exposed pad of the charger: via-in-pad before anything is routed over it
    for q_ in PADS_BY_NET.get('GND', []):
        if q_['ref'] == 'U4' and q_['num'] == '17' and min(q_['w'], q_['h']) > 1.4:
            add_via('GND', round(q_['x'], 1), round(q_['y'], 1))
            FAN_VIA.add(('U4', '17'))
    return n_


STAGE_A = os.environ.get('STAGE') == 'A'      # only the regular key-array wiring; Freerouting does the rest
print('fan-out stubs:', 0 if STAGE_A else fanout())
if not STAGE_A:
    fpad = {q_['num']: q_ for q_ in PADS_BY_NET['+3V3'] if q_['ref'] == 'U6'}
    p3, p7, p8 = fpad['3'], fpad['7'], fpad['8']
    add_track('+3V3', 2, p7['x'], p7['y'], p8['x'], p8['y'], 0.25)
    midy = (p3['y'] + p7['y']) / 2
    add_track('+3V3', 2, p3['x'], p3['y'], p3['x'], midy, 0.25)
    add_track('+3V3', 2, p3['x'], midy, p7['x'], midy, 0.25)
    add_track('+3V3', 2, p7['x'], midy, p7['x'], p7['y'], 0.25)
    BRIDGED = {('U6', '3'), ('U6', '7')}

FAILED = []


def cells_of(netname, ref=None, num=None):
    out = []
    for p in PADS_BY_NET.get(netname, []):
        if (ref is None or p['ref'] == ref) and (num is None or p['num'] == num):
            out.append(p)
    return out


def dbg(netname, x, y, r=7.0, tag='dbg'):
    """dump passability maps (white = usable by `netname`) around a point, one PGM per routing layer"""
    nid = NETID[netname]
    i0, j0 = rt.ij(x - r, y - r)
    i1, j1 = rt.ij(x + r, y + r)
    pas = rt.passable(nid, (i0, j0, i1, j1))
    for l in range(3):
        a = (pas[l][::-1] * 200).astype(np.uint8)
        own = (rt.owner[l][j0:j1 + 1, i0:i1 + 1][::-1] == nid)
        a[own & (a > 0)] = 255
        a = np.kron(a, np.ones((6, 6), np.uint8))
        with open('/tmp/%s_%d.pgm' % (tag, l), 'wb') as f:
            f.write(b'P5 %d %d 255\n' % (a.shape[1], a.shape[0]))
            f.write(a.tobytes())


def route_pair(netname, start_cells, goal_cells, w=R.TW, fat=0, **kw):
    path = rt.route(NETID[netname], start_cells, goal_cells, fat=fat, **kw)
    if path is None:
        return False
    commit(path, netname, w)
    return True


def route_net(netname, w=R.TW, fat=0, **kw):
    """connect all pads of a net (Prim-like: nearest unconnected pad to the growing tree)"""
    pads = PADS_BY_NET.get(netname, [])
    if len(pads) < 2:
        return
    nid = NETID[netname]
    # group pads that share a footprint+number (same physical pin drawn as several pads)
    groups = {}
    for p in pads:
        groups.setdefault((p['ref'], p['num']), []).append(p)
    glist = list(groups.values())
    tree = set()
    for p in glist[0]:
        tree |= set(p['cells'])
    done = [glist[0]]
    todo = glist[1:]
    while todo:
        def dist(gp):
            return min(math.hypot(a['x'] - b['x'], a['y'] - b['y']) for a in gp for d_ in done for b in d_)
        todo.sort(key=dist)
        gp = todo.pop(0)
        if (gp[0]['ref'], gp[0]['num']) in globals().get('BRIDGED', ()) and any(q['ref'] == 'U6' and q['num'] == '8' for d_ in done + todo for q in d_):
            done.append(gp)       # already tied to pin 8 under the package
            continue
        starts = [c for p in gp for c in p['cells']]
        before = set(rt.conn.get(nid, set()))
        path = rt.route(nid, starts, tree, fat=fat, **kw)
        ww = w
        if path is None and fat:
            path = rt.route(nid, starts, tree, fat=0, **kw)
            ww = R.TW
        if path is None:
            kw2 = dict(kw); kw2['margin'] = 25.0
            path = rt.route(nid, starts, tree, fat=0, **kw2)
            ww = R.TW
        if path is None:
            # neighbouring pin of the same part on the same net (e.g. BQ24075 OUT 10/11): bridge the two pads directly
            near = [q for d_ in done for q in d_ if q['ref'] == gp[0]['ref'] and q['layers'] == gp[0]['layers'] and not q['tht']
                    and 0 < math.hypot(q['x'] - gp[0]['x'], q['y'] - gp[0]['y']) < 0.7]
            if near:
                add_track(netname, gp[0]['layers'][0], gp[0]['x'], gp[0]['y'], near[0]['x'], near[0]['y'], 0.2)
                tree |= set(starts)
                done.append(gp)
                continue
        if path is None:
            FAILED.append((netname, gp[0]['ref'], gp[0]['num']))
            if os.environ.get('DBGFAIL') == netname:
                dbg(netname, gp[0]['x'], gp[0]['y'], 5.0, 'fs')
                tx = min(done[0], key=lambda q: 0)
                dbg(netname, done[0][0]['x'], done[0][0]['y'], 5.0, 'fg')
                print('DBGFAIL stats', getattr(rt, 'last_fail', None))
                for (l_, ix_, iy_) in sorted(tree)[:14]:
                    o_ = rt.owner[l_][iy_ - 2:iy_ + 3, ix_ - 6:ix_ + 3]
                    m_ = rt.multi[l_][iy_ - 2:iy_ + 3, ix_ - 6:ix_ + 3]
                    print('DBGFAIL goal', l_, rt.xy(ix_, iy_), 'nid', nid, 'forced', (l_, ix_, iy_) in rt.force.get(nid, ()))
                    print(np.where(m_, -1, o_))
                    break
                print('DBGFAIL start', gp[0]['ref'], gp[0]['num'], gp[0]['x'], gp[0]['y'], 'goal', done[0][0]['ref'], done[0][0]['num'], done[0][0]['x'], done[0][0]['y'], len(tree))
        else:
            commit(path, netname, ww)
            tree |= set(rt.conn[nid]) - before
            for l, ix, iy in path:
                tree.add((l, ix, iy))
        tree |= set(starts)
        done.append(gp)
    for f in [f for f in FAILED if f[0] == netname and len(f) == 3]:
        me = [q for g_ in glist for q in g_ if q['ref'] == f[1] and q['num'] == f[2]]
        ok_refs = {(x[1], x[2]) for x in FAILED if x[0] == netname}
        near = [q for g_ in glist for q in g_ if me and q['ref'] == f[1] and (q['ref'], q['num']) not in ok_refs and not q['tht']
                and q['layers'] == me[0]['layers'] and math.hypot(q['x'] - me[0]['x'], q['y'] - me[0]['y']) < 0.7]
        if near:
            add_track(netname, me[0]['layers'][0], me[0]['x'], me[0]['y'], near[0]['x'], near[0]['y'], 0.2)
            FAILED.remove(f)


def to_plane(netname, pad, w=R.TW):
    """drop a via next to an SMD pad of a plane net"""
    nid = NETID[netname]
    def open_plane(ix, iy, k=9):
        o = rt.owner[1][iy - k:iy + k + 1, ix - k:ix + k + 1]
        m = rt.multi[1][iy - k:iy + k + 1, ix - k:ix + k + 1]
        return not m.any() and not ((o != 0) & (o != nid)).any()
    path = rt.route(nid, pad['cells'], [], via_goal=True, layers=(pad['layers'][0],), margin=5.0, max_len=12.0,
                    via_pred=open_plane if netname == 'VLED' else None)
    if path is None:
        # fall back: join any copper already on this net (other via, THT pin)
        sx_, sy_ = rt.ij(pad['x'], pad['y'])
        goals = {g_ for g_ in set(rt.conn.get(nid, ())) - set(pad['cells']) if abs(g_[1] - sx_) < 150 and abs(g_[2] - sy_) < 150
                 and g_ not in PADONLY.get(nid, ())}
        path = rt.route(nid, pad['cells'], goals, margin=4.0) if goals else None
        if path is None:
            FAILED.append((netname, pad['ref'], pad['num'], 'plane'))
        else:
            commit(path, netname, w)
        return
    commit(path, netname, w)
    add_via(netname, *rt.xy(path[-1][1], path[-1][2]))


t0 = time.time()
# ---- 1. per-key local hook-ups
for (c, r) in KEYS:
    ki = KEYINFO[(c, r)]
    route_net(ki['son'])
    # KEY: resistor pad -> anything already on the net (socket pin / bus)
    rp = [p for p in PADS_BY_NET[ki['kn']] if p['ref'] == ki['r'].GetReference()]
    nid = NETID[ki['kn']]
    sx_, sy_ = rt.ij(rp[0]['x'], rp[0]['y'])
    goals = {g_ for g_ in set(rt.conn[nid]) - set(rp[0]['cells']) if abs(g_[1] - sx_) < 120 and abs(g_[2] - sy_) < 120}
    if not route_pair(ki['kn'], rp[0]['cells'], goals):
        FAILED.append((ki['kn'], 'R-hookup'))
print('key hookups done', round(time.time() - t0, 1), 's  failed:', len(FAILED))

# ---- 1b. per-key plane hook-ups while the cells are still empty
KEYREFS = set()
for ki in KEYINFO.values():
    KEYREFS |= {ki['u'].GetReference(), ki['led'].GetReference()}
KEYREFS |= {'C%d' % (100 + i) for i in range(len(KEYS))} | {'C%d' % (200 + i) for i in range(len(KEYS))}
DONE_PLANE = set()


def planes(only_keys):
    for nm in ('GND', 'VLED'):
        for p in PADS_BY_NET.get(nm, []):
            key = (p['ref'], p['num'], p['x'], p['y'])
            if p['tht'] or key in DONE_PLANE or ((p['ref'] in KEYREFS) != only_keys) or (p['ref'], p['num']) in FAN_VIA:
                continue
            DONE_PLANE.add(key)
            to_plane(nm, p)


for n_ in range(1, len(chain)):
    route_net('LD%d' % n_, margin=6.0)
planes(True)
route_net('VSENSE', margin=6.0)
print('key planes done', round(time.time() - t0, 1), 's  failed:', len(FAILED))

# ---- 2. everything that touches the MCU module first (it is the bottleneck), then the rest
PLANE_NETS = {'GND', 'VLED'}
POWER = {'VBUS': (0.4, 1), 'VIN': (0.4, 1), 'VBAT': (0.4, 1), 'QI5V': (0.4, 1), 'VSYS': (0.5, 2), '+3V3': (0.25, 0), 'K3V3': (0.25, 0)}
mod_nets = []
for p_ in U1.Pads():
    nm_ = p_.GetNetname()
    if nm_ and nm_ not in PLANE_NETS and nm_ not in mod_nets:
        mod_nets.append(nm_)


def far_(nm_):          # route the shortest module nets first
    ps = PADS_BY_NET.get(nm_, [])
    return max(math.hypot(a_["x"] - MODX, a_["y"] - MODY) for a_ in ps)


mod_nets.sort(key=far_)
SEED = int(os.environ.get('SEED', '3'))        # routing order that gave the best result
if SEED:
    import random
    random.Random(SEED).shuffle(mod_nets)
    if SEED % 2:
        mod_nets.sort(key=lambda n_: n_ in POWER)        # odd seeds: power nets last
PRIO = [n_ for n_ in os.environ.get('PRIORITY', '').split(',') if n_]
mod_nets = [n_ for n_ in PRIO if n_ in mod_nets] + [n_ for n_ in mod_nets if n_ not in PRIO]
ROUTED = set()
for nm in ([] if STAGE_A else mod_nets):
    w_, fat_ = POWER.get(nm, (R.TW, 0))
    route_net(nm, w_, fat_, margin=10.0)
    ROUTED.add(nm)
print('module nets done', round(time.time() - t0, 1), 's  failed:', len(FAILED))
for nm in ([] if STAGE_A else ['CC1', 'CC2', 'ISET', 'ILIM', 'TS', 'EN1', 'LED_G', 'PRESS1', 'PRESS2']):
    route_net(nm, margin=6.0)
for nm, (w_, fat_) in POWER.items():
    if nm not in ROUTED and not STAGE_A:
        route_net(nm, w_, fat_, margin=8.0)
if not STAGE_A:
    planes(False)
print('all routing done', round(time.time() - t0, 1), 's  failed:', len(FAILED))

# ================================================================== zones
def zone(netname, layer, prio=0, pts=None, clearance=0.25):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    if netname:
        z.SetNet(net(netname))
    pts = pts or [(-2, -2), (FIELD_W + 2, -2), (FIELD_W + 2, Y1 + 1), (-2, Y1 + 1)]
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(OX + x), mm(OY - y))
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(mm(clearance))
    z.SetMinThickness(mm(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetThermalReliefGap(mm(0.25))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


zone('GND', pcbnew.In1_Cu)
zone('VLED', pcbnew.In2_Cu)
zone('GND', pcbnew.F_Cu)
zone('GND', pcbnew.B_Cu)
ko = pcbnew.ZONE(board)
ko.SetIsRuleArea(True)
ko.SetLayerSet(pcbnew.LSET.AllCuMask())
ko.SetDoNotAllowZoneFills(True)
ko.SetDoNotAllowTracks(True)
ko.SetDoNotAllowVias(True)
ko.SetDoNotAllowPads(False)
ko.SetDoNotAllowFootprints(False)
ol = ko.Outline()
ol.NewOutline()
for x, y in ((ANT[0], ANT[1]), (ANT[2], ANT[1]), (ANT[2], ANT[3]), (ANT[0], ANT[3])):
    ol.Append(mm(OX + x), mm(OY - y))
board.Add(ko)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())

pcbnew.SaveBoard(os.path.join(OUT, 'bk46_main_unrouted.kicad_pcb' if STAGE_A else 'bk46_main.kicad_pcb'), board)
json.dump(dict(keys=KEYMAP, mcu_pins={MOD_GPIO[k]: v for k, v in MOD_NETS.items() if k in MOD_GPIO}, ffc=FFCS),
          open(os.path.join(OUT, 'keymap.json'), 'w'), indent=1)
json.dump(COMPONENTS, open(os.path.join(OUT, 'components.json'), 'w'), indent=1)
nl = {}
for fp in board.GetFootprints():
    for p in fp.Pads():
        if p.GetNetname():
            nl.setdefault(p.GetNetname(), set()).add(fp.GetReference() + '.' + p.GetNumber())
json.dump({k: sorted(v) for k, v in sorted(nl.items())}, open(os.path.join(OUT, 'netlist.json'), 'w'), indent=1)
print('tracks', NTRACK, 'vias', NVIA, 'footprints', len(board.GetFootprints()), 'nets', len(NETS))
json.dump([list(map(str, f)) for f in FAILED], open(os.path.join(OUT, 'unrouted.json'), 'w'), indent=1)
print('FAILED (%d):' % len(FAILED))
for f in FAILED:
    print('   ', f)


if os.environ.get('DBG'):
    for spec in os.environ['DBG'].split(';'):
        nm, x, y, tag = spec.split(',')
        dbg(nm, float(x), float(y), tag=tag)
