"""
BK47 — single source of truth for every mechanical dimension (mm).

Coordinate system (shared by CAD, drawings and the PCB generator):
  origin = front-left corner of the key field, X → right, Y → back (away from user),
  Z → up, Z=0 is the underside of the case floor (feet not included).
"""
U = 19.05
COLS, ROWS = 12, 4
FIELD_W, FIELD_H = COLS * U, ROWS * U          # 228.6 x 76.2
KNOB_CELLS = [(0, 3), (11, 3)]                 # (col,row) cells replaced by the two haptic knobs; row 0 = front row


def cell_center(c, r):
    return (U * (c + 0.5), U * (r + 0.5))


KEYS = [(c, r) for r in range(ROWS) for c in range(COLS) if (c, r) not in KNOB_CELLS]   # 46 keys
KNOBS = [cell_center(*k) for k in KNOB_CELLS]  # (9.525, 66.675) and (219.075, 66.675)
KNOB_XY = KNOBS[0]
# rows whose switch is rotated 180° (pins toward the front). Creates free PCB strips at the
# front edge, back edge and in the middle (between row 1 and row 2) for all electronics.
ROT_ROWS = (1, 3)

# ---------------- case envelope ----------------
M_OUT = 4.3            # key-field edge -> outer case face
WALL = 2.0             # tub wall thickness
CASE_R = 4.0           # outer vertical corner radius
X0, Y0 = -M_OUT, -M_OUT
X1, Y1 = FIELD_W + M_OUT, FIELD_H + M_OUT      # outer: 237.2 x 84.8
CAV_X0, CAV_Y0 = X0 + WALL, Y0 + WALL          # cavity (inner wall faces)
CAV_X1, CAV_Y1 = X1 - WALL, Y1 - WALL

# ---------------- Z stack ----------------
FLOOR_T = 1.6
CAVITY_H = 5.6                                  # floor top -> PCB underside
PCB_T = 1.6
PCB_Z0 = FLOOR_T + CAVITY_H                     # 7.2
PCB_Z1 = PCB_Z0 + PCB_T                         # 8.8
PLATE_T = 1.5
PLATE_Z0 = PCB_Z1 + 3.5                         # 12.3  (MX: PCB top -> plate underside = 3.5)
PLATE_Z1 = PLATE_Z0 + PLATE_T                   # 13.8
GASKET_T = 1.2                                  # compressed gasket height (1.5 mm Poron, ~20 % squeeze)
LEDGE_Z = PLATE_Z0 - GASKET_T                   # 11.1  top of the tub gasket seats
SPLIT_Z = PLATE_Z1 + GASKET_T                   # 15.0  tub top / bezel underside
BEZEL_TOP = 19.8
SHIPLAP = 1.0                                   # bezel skirt overlap (width and height)
SHIPLAP_GAP = 0.15

# ---------------- plate ----------------
PLATE_OVER = 1.8                                # plate edge beyond the key field
PLATE_R = 1.5
CUTOUT = 14.0
CUTOUT_R = 0.3
KNOB_PLATE_R = 10.2                             # clearance radius around the motor
SEAT_D = 1.8                                    # gasket seat depth (from inner wall face)
GASKET_W = 1.5                                  # gasket strip width
STANDOFF_HOLE = 2.3
# PCB<->plate M2x3.5 standoffs (x in units of U, y in mm)
STANDOFFS = [(2 * U, 4.2), (5 * U, 4.2), (8 * U, 4.2), (11 * U, 4.2),
             (1 * U, 44.4), (3 * U, 44.4), (8 * U, 44.4), (11 * U, 44.4),
             (6 * U, 72.0), (8 * U, 72.0)]

# ---------------- PCB outline ----------------
PCB_X0, PCB_Y0 = 0.3, 0.3
PCB_X1, PCB_Y1 = FIELD_W - 0.3, FIELD_H - 0.3
PCB_KNOB_NOTCH = (20.6, 55.3)                   # PCB removed for x < 20.6 (and x > W-20.6) and y > 55.3
PCB_KNOB_NOTCH_R = 19.6                          # right-hand notch is 1 mm narrower (socket pad of key 10,3)
PCB_SCREW_NOTCH_W, PCB_SCREW_NOTCH_D = 9.0, 0.6
USB_X = 3 * U                                   # 57.15, USB-C centre on the back edge
USB_TAB_W, USB_TAB_Y = 10.4, 78.2               # PCB tab that carries the connector

# ---------------- bezel / tub screws ----------------
SCREW_X = [8.0, 4 * U, 8 * U, FIELD_W - 8.0]
SCREW_Y = [-2.0, FIELD_H + 2.0]
SCREWS = [(x, y) for y in SCREW_Y for x in SCREW_X]     # 8 x M2x18 countersunk, from below
SCREW_CLEAR = 2.2
SCREW_PILOT = 1.7                               # thread-forming / tap drill in the bezel
SCREW_PILOT_TOP = 18.8
CSK_D, CSK_H = 4.0, 1.2
SCREW_PIL_W, SCREW_PIL_D = 7.0, 2.3             # screw pilaster footprint
PLATE_SCREW_NOTCH_R = 1.6

# gasket seats: (centre along the wall, length)
SEATS_FRONT = [(24.0, 20), (58.0, 20), (88.5, 9), (140.0, 9), (170.6, 20), (204.6, 20)]
SEATS_BACK = [(34.0, 16), (96.0, 20), (133.0, 20), (172.0, 16), (194.6, 16)]
SEATS_LEFT = [(14.0, 16), (40.0, 20)]
SEATS_RIGHT = [(14.0, 16), (40.0, 20)]

# ---------------- display (0.91" 128x32 SSD1306 I2C module, 38 x 12 mm PCB) ----------------
DISP_X = 6 * U                                  # 114.3 centre of the front wall
DISP_W, DISP_H = 38.0, 12.0
DISP_TOL = 0.2
DISP_T = 3.6                                    # glass + PCB + rear parts
DISP_Z0 = 2.2
DISP_SKIN = 0.6                                 # wall left in front of the glass
DISP_WIN_W, DISP_WIN_H = 23.6, 7.4              # window (active area 22.4 x 5.6 + margin)
DISP_WIN_DX, DISP_WIN_DZ = -2.0, 0.4            # active-area offset vs module centre (measure your module!)
DISP_PLATE_NOTCH_Y = 0.2
DISP_PCB_NOTCH_Y = 1.0

# ---------------- USB opening ----------------
USB_OPEN_W, USB_OPEN_Z0, USB_OPEN_Z1 = 10.0, 3.4, 7.8

# ---------------- haptic knob (1404-class outrunner, T-mount bell) ----------------
MOTOR_D = 18.9                                  # bell diameter (max)
MOTOR_H = 13.5                                  # mounting face -> bell top
MOTOR_SHAFT_D, MOTOR_SHAFT_L = 1.5, 4.0         # shaft stub above the bell
MOTOR_MOUNT = 9.0                               # 4 x M2 on a 9 x 9 mm square
MOTOR_TMOUNT = 5.0                              # 2 x M2 on the bell, 5 mm apart
KNOB_PCB_T = 0.6
KNOB_PCB_LIFT = 0.4                             # knob board sits on 0.4 mm bosses (room for the press flexure to move)
KNOB_PCB_Z0 = FLOOR_T + KNOB_PCB_LIFT           # 2.0
MOTOR_SPACER = 1.2                              # printed spacer: sets magnet -> MT6701QT air gap
MOTOR_Z0 = KNOB_PCB_Z0 + KNOB_PCB_T + MOTOR_SPACER  # 4.0
MOTOR_Z1 = MOTOR_Z0 + MOTOR_H                   # 17.5
# press sensing: the motor sits on a 13.4 mm island held by four FR4 beams; a Z-axis hall/TMR sensor on the underside
# of the island (on the motor axis) watches a 3 x 0.5 mm magnet glued into the floor
KNOB_ISLAND = 13.0
KNOB_BEAM_IN = 7.4                              # beams are the strips between 7.4 and 9.4 mm from the axis (2.0 mm wide)
KNOB_BRIDGE = 3.0                               # width of the four island-to-beam bridges
KNOB_TAB = 11.0                                 # corner tabs reach 11 mm from the axis
KNOB_FRAME_SCREWS = [(-9.6, -9.6), (9.6, -9.6), (-9.6, 9.6), (14.2, 9.7)]   # axis-relative (left knob), M2 thread-forming
PRESS_MAGNET_D, PRESS_MAGNET_T = 3.0, 0.5
KNOB_D = 18.6
KNOB_Z0 = MOTOR_Z1 + 0.3
KNOB_Z1 = 31.0
KNOB_PCB_SQ = 18.8                              # square part under the motor
KNOB_PCB_TAIL = (18.0, 48.5, 62.0, 76.4)        # x0,x1,y0,y1 of the tail (driver + FFC); mirrored for the right knob
KNOB_PCB_SCREW = (46.4, 72.8)

# ---------------- battery / Qi (for clearance checks and drawings) ----------------
BATT = dict(x=176.0, y=38.1, w=60.0, d=40.0, t=3.2)       # 304060 LiPo, ~800 mAh
QI = dict(x=114.3, y=38.1, w=48.0, d=34.0, t=1.3)         # generic 5 W Qi receiver coil + ferrite

SOCKET_H = 1.85                                 # hot-swap socket below the PCB


def knob_pcb_outline():
    """outline of the LEFT knob board in axis-relative coordinates (dx to the right, dy to the back)"""
    a, b, c = KNOB_PCB_SQ / 2, KNOB_TAB, KNOB_BEAM_IN
    kx, ky = KNOBS[0]
    tx0, tx1 = KNOB_PCB_TAIL[0] + 1.7 - kx, KNOB_PCB_TAIL[1] - kx       # tail starts 0.8 mm clear of the east beam
    ty0, ty1 = KNOB_PCB_TAIL[2] - ky, KNOB_PCB_TAIL[3] - ky
    return [(-b, -b), (-c, -b), (-c, -a), (c, -a), (c, -b), (b, -b), (b, -c), (a, -c), (a, c), (tx0, c), (tx0, ty0), (tx1, ty0),
            (tx1, ty1), (16.0, ty1), (16.0, b), (c, b), (c, a), (-c, a), (-c, b), (-b, b), (-b, c), (-a, c), (-a, -c), (-b, -c)]


def knob_pcb_slots():
    i, c = KNOB_ISLAND / 2, KNOB_BEAM_IN
    h = KNOB_BRIDGE / 2
    base = [(h, i), (i, i), (i, h), (c, h), (c, c), (h, c)]
    return [[(sx * x, sy * y) for x, y in base] for sx in (-1, 1) for sy in (-1, 1)]
