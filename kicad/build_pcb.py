#!/usr/bin/env python3
"""
Build script for the Feather I2S amp shim (Feather 3V/GND/A0/A1/A2 ->
Adafruit MAX98357 #3006 breakout).

Run with KiCad's own bundled Python:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 build_pcb.py

Idempotent: resets the .kicad_pcb to a stub, loads it (LoadBoard, not
CreateEmptyBoard), regenerates everything, saves, patches fonts, and
re-exports the etch PDFs.

Process: Bantam cuts the outline, xTool F1 Ultra fiber laser ablates the
copper. Single layer F.Cu, SMT only, no vias. Every net, GND included, is
a routed trace; the rest of the board is an unconnected copper fill, there
only so the laser has less copper to remove.

Layout (no mounting holes, like sdio-shim):
  - J1 west: right-angle SMD socket, opening on the west edge, 75% of its
    body overhanging. The Feather plugs in edge-on. Pin 1 (3V) north.
  - J2 east: the same socket mirrored, 7 pins, 75% overhanging the east
    edge. The amp plugs in standing vertical with its parts facing away
    from the Feather, which puts its Vin at the north end.
  - J1 sits three rows lower than J2 so A0->BCLK and A1->LRC are straight.
    3V and GND each rise on their own lane to J2 pins 1 and 2. A2->DIN runs
    straight east under J2's south end, north under J2's body, and enters
    pin 5 from behind. No crossings, no jumpers.
  - Front silk: a label just past each end of each socket's pin row, where
    the socket legs do not cover it. Back silk (burned with the laser):
    board name, a Feather pin -> I2S table, and the date.
"""

import math
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCH_PATH = os.path.join(SCRIPT_DIR, "i2s-amp-shim.kicad_sch")
OUT_PCB = os.path.join(SCRIPT_DIR, "i2s-amp-shim.kicad_pcb")
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
LOCAL_LIB = os.path.join(SCRIPT_DIR, "footprints", "i2s-amp-shim.pretty")

STUB = (
    '(kicad_pcb\n'
    '\t(version 20260206)\n'
    '\t(generator "pcbnew")\n'
    '\t(generator_version "10.0")\n'
    ')\n'
)

DATE_STAMP = "20261003"

# ----------------------------------------------------------------------
# Geometry. Everything below derives from these.
# ----------------------------------------------------------------------
PITCH = 2.54

# Right-angle socket footprints: pads 2.51 x 1.0mm at local x=+/-6.7, body
# from the pads' side at local 3.8 out to the opening at 8.4mm away.
PAD_X = 6.7
PAD_LEN = 2.51
BODY_NEAR = 3.8      # body edge nearest the pads
BODY_LEN = 8.4
# 75% of the body hangs off the board, which puts the edge 2.1mm from the
# body's near edge. Leaves the pads plus the label strip on the board.
OVERHANG = 0.75
EDGE_FROM_BODY = BODY_LEN * (1 - OVERHANG)

# Traces as wide as the pads they land on (1.0mm short side). The user
# asked for as thick as possible; nothing on this board forces a neck.
TRACE_WIDTH = 1.0
# Gap between parallel traces and from trace to unrelated pad. Generous on
# purpose: laser-ablated, no mask.
GAP = 0.6
LANE = TRACE_WIDTH + GAP

CHAMFER = 0.4

R_CORNER = 3.0

# Unconnected fill: isolation gap around every trace and pad (this is what
# the laser actually ablates), and its thinnest allowed neck.
FILL_GAP = 0.5
FILL_MIN = 0.5
# Copper held back from the milled outline.
EDGE_GAP = 0.5

# Rows: J2 pin k is on row k. J1 pin k is on row k+3, so J1.3 (A0) faces
# J2.6 (BCLK) and J1.4 (A1) faces J2.7 (LRC). J1.5 (A2) lands on row 8,
# one row below J2's last pin, which is DIN's path under J2.
# Room above J2 pin 1 for its end label.
Y_ROW1 = 3.7


def row(k):
    return Y_ROW1 + (k - 1) * PITCH


# X: west edge at 0.
X_J1 = EDGE_FROM_BODY - BODY_NEAR          # footprint origin (off board)
X_J1_PAD = X_J1 + PAD_X
X_3V_UP = X_J1_PAD + PAD_LEN / 2 + GAP + TRACE_WIDTH / 2
X_GND_UP = X_3V_UP + LANE
X_J2_PAD = X_GND_UP + TRACE_WIDTH / 2 + GAP + PAD_LEN / 2
X_J2 = X_J2_PAD + PAD_X                    # footprint origin (off board)
# DIN's run north, under J2's body, clear of the label strip.
X_DIN_UP = X_J2 - BODY_NEAR + TRACE_WIDTH / 2 + 0.3
# East edge: far enough past DIN's run that the fill closes into a ring
# around the board (the laser software trips on open fill). J2 overhangs a
# bit less than 75% as a result.
FILL_RING = 1.0
W = X_DIN_UP + TRACE_WIDTH / 2 + FILL_GAP + FILL_RING + EDGE_GAP
# Room below J1 pin 5 for its end label.
H = row(8) + 3.4


def fail(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def read_schematic_uuids():
    with open(SCH_PATH) as f:
        text = f.read()
    pat = re.compile(r'\(uuid "([0-9a-fA-F-]{36})"\)\s*\(property "Reference" "(\w+)"')
    found = {ref: uid for uid, ref in pat.findall(text)}
    for ref in ("J1", "J2"):
        if ref not in found:
            fail(f"symbol {ref} not found in {SCH_PATH}; run gen_sch.py first")
    return found


def main():
    sch_uuids = read_schematic_uuids()

    with open(OUT_PCB, "w") as f:
        f.write(STUB)

    import pcbnew  # noqa: E402  (wxApp assert noise on import is expected)

    MM = pcbnew.FromMM

    board = pcbnew.LoadBoard(OUT_PCB)
    ds = board.GetDesignSettings()
    ds.m_MinClearance = MM(0.2)
    ds.m_TrackMinWidth = MM(0.2)
    ds.m_CopperEdgeClearance = MM(EDGE_GAP)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(MM(0.2))
    nc.SetTrackWidth(MM(TRACE_WIDTH))

    def make_net(name):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        return ni

    net_3v3 = make_net("/3V3")
    net_gnd = make_net("/GND")
    net_bclk = make_net("/BCLK")
    net_lrc = make_net("/LRC")
    net_din = make_net("/DIN")
    net_sd = make_net("unconnected-(J2-Pin_3-Pad3)")
    net_gain = make_net("unconnected-(J2-Pin_4-Pad4)")

    def place(name, ref, value, x, y, sym_ref):
        fp = pcbnew.FootprintLoad(LOCAL_LIB, name)
        if fp is None:
            fail(f"could not load {name} from {LOCAL_LIB}")
        # FootprintLoad leaves the library nickname empty; set it so the
        # board matches the schematic's Footprint field (parity check).
        fp.SetFPID(pcbnew.LIB_ID("i2s-amp-shim", name))
        fp.SetReference(ref)
        fp.SetValue(value)
        fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        fp.SetPath(pcbnew.KIID_PATH("/" + sch_uuids[sym_ref]))
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        board.Add(fp)
        return fp

    # J1 pin 3 on row 6: footprint centre (pin 3) on row 6.
    j1 = place("Feather_RtAngle_Socket_SMD_1x05", "J1", "Feather 3V-A2",
               X_J1, row(6), "J1")
    # J2 pin 4 is its centre; pin 1 north.
    j2 = place("Amp_RtAngle_Socket_SMD_1x07", "J2", "MAX98357 #3006",
               X_J2, row(4), "J2")

    # Render-only: the Feather and the amp plugged into J1 and J2. No pads,
    # board-only, out of the BOM and position files; they exist so the 3D
    # viewer shows the finished assembly. Same origins as their sockets,
    # which is the frame gen_render_fps.py built their transforms in.
    for name, ref, x, y in (("Render_Feather_RP2350_on_J1", "VIS1", X_J1, row(6)),
                            ("Render_MAX98357_on_J2", "VIS2", X_J2, row(4))):
        fp = pcbnew.FootprintLoad(LOCAL_LIB, name)
        if fp is None:
            fail(f"could not load {name} from {LOCAL_LIB}; run gen_render_fps.py")
        fp.SetFPID(pcbnew.LIB_ID("i2s-amp-shim", name))
        fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        board.Add(fp)

    # J1 = Feather 3V, GND, A0, A1, A2
    j1_nets = {"1": net_3v3, "2": net_gnd, "3": net_bclk, "4": net_lrc, "5": net_din}
    for pad in j1.Pads():
        pad.SetNet(j1_nets[pad.GetNumber()])

    # J2 = amp JP1, verified against Adafruit's EAGLE .brd:
    # 1=Vin 2=GND 3=SD 4=GAIN 5=DIN 6=BCLK 7=LRC
    j2_nets = {"1": net_3v3, "2": net_gnd, "3": net_sd, "4": net_gain,
               "5": net_din, "6": net_bclk, "7": net_lrc}
    for pad in j2.Pads():
        pad.SetNet(j2_nets[pad.GetNumber()])

    def pad_pos(fp, num):
        for pad in fp.Pads():
            if pad.GetNumber() == num:
                p = pad.GetPosition()
                return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))
        raise KeyError(num)

    j1p = {n: pad_pos(j1, n) for n in "12345"}
    j2p = {n: pad_pos(j2, n) for n in "1234567"}

    print(f"Board {W:.2f} x {H:.2f} mm, J2 overhang {(X_J2 + BODY_LEN - BODY_NEAR - W) / BODY_LEN:.0%}")
    print("Pad positions (mm):")
    for n in "12345":
        print(f"  J1.{n} {j1p[n]}")
    for n in "1234567":
        print(f"  J2.{n} {j2p[n]}")

    # ------------------------------------------------------------------
    # Outline: 4 lines + 4 arcs, mid point on the bisector.
    # ------------------------------------------------------------------
    def add_line(p1, p2):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.05))
        s.SetStart(pcbnew.VECTOR2I(MM(p1[0]), MM(p1[1])))
        s.SetEnd(pcbnew.VECTOR2I(MM(p2[0]), MM(p2[1])))
        board.Add(s)

    def add_arc(start, mid, end):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.05))
        s.SetArcGeometry(pcbnew.VECTOR2I(MM(start[0]), MM(start[1])),
                         pcbnew.VECTOR2I(MM(mid[0]), MM(mid[1])),
                         pcbnew.VECTOR2I(MM(end[0]), MM(end[1])))
        board.Add(s)

    def bisector_mid(c, a, b, r):
        vx = (a[0] - c[0]) + (b[0] - c[0])
        vy = (a[1] - c[1]) + (b[1] - c[1])
        L = math.hypot(vx, vy)
        return (c[0] + vx / L * r, c[1] + vy / L * r)

    R = R_CORNER
    corners = [
        ((R, R), (0, R), (R, 0)),
        ((W - R, R), (W - R, 0), (W, R)),
        ((W - R, H - R), (W, H - R), (W - R, H)),
        ((R, H - R), (R, H), (0, H - R)),
    ]
    for c, a, b in corners:
        add_arc(a, bisector_mid(c, a, b, R), b)
    add_line((R, 0), (W - R, 0))
    add_line((W, R), (W, H - R))
    add_line((W - R, H), (R, H))
    add_line((0, H - R), (0, R))

    # ------------------------------------------------------------------
    # Tracks
    # ------------------------------------------------------------------
    def miter_path(points, chamfer=CHAMFER):
        """Every interior vertex becomes two points, one backed off along
        each leg, so a 90-degree turn comes out as two 45-degree bends."""
        if len(points) < 3:
            return list(points)
        out = [points[0]]
        for i in range(1, len(points) - 1):
            a, c, b = points[i - 1], points[i], points[i + 1]

            def backoff(q):
                vx, vy = q[0] - c[0], q[1] - c[1]
                L = math.hypot(vx, vy)
                if L < 1e-9:
                    return c
                k = min(chamfer, L * 0.5)
                return (c[0] + vx / L * k, c[1] + vy / L * k)

            out.append(backoff(a))
            out.append(backoff(b))
        out.append(points[-1])
        return out

    def add_track(p1, p2, net, width=TRACE_WIDTH):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(MM(p1[0]), MM(p1[1])))
        t.SetEnd(pcbnew.VECTOR2I(MM(p2[0]), MM(p2[1])))
        t.SetWidth(MM(width))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(net)
        board.Add(t)

    def add_path(points, net, width=TRACE_WIDTH):
        pts = miter_path(points)
        for a, b in zip(pts, pts[1:]):
            add_track(a, b, net, width)

    # 3V: east off J1.1, north on its lane, east into J2.1.
    add_path([j1p["1"], (X_3V_UP, j1p["1"][1]), (X_3V_UP, j2p["1"][1]), j2p["1"]],
             net_3v3)
    # GND: same shape one lane east; its rise ends below 3V's row, so the
    # two never meet.
    add_path([j1p["2"], (X_GND_UP, j1p["2"][1]), (X_GND_UP, j2p["2"][1]), j2p["2"]],
             net_gnd)
    # A0 -> BCLK and A1 -> LRC: same rows, straight across.
    add_path([j1p["3"], j2p["6"]], net_bclk)
    add_path([j1p["4"], j2p["7"]], net_lrc)
    # A2 -> DIN: straight east under J2's south end, north under J2's body
    # to pin 5's row, then west into the outer end of pin 5's pad. Entering
    # on the row keeps the full 1.54mm inter-row gap to pins 4 and 6.
    add_path([j1p["5"], (X_DIN_UP, j1p["5"][1]), (X_DIN_UP, j2p["5"][1]), j2p["5"]],
             net_din)

    # ------------------------------------------------------------------
    # Front silkscreen: pin labels only, in the strip between each socket's
    # body and its pads, which stays visible once the socket is soldered.
    # ------------------------------------------------------------------
    def add_text(text, x, y, size=0.8, justify=None, layer=pcbnew.F_SilkS,
                 mirror=False, rot=0):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
        t.SetTextThickness(MM(size * 0.15))
        if justify == "right":
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
        elif justify == "left":
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        t.SetMirrored(mirror)
        t.SetTextAngle(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
        board.Add(t)
        return t

    def add_dot(x, y, d=0.6):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_CIRCLE)
        s.SetLayer(pcbnew.F_SilkS)
        s.SetFilled(True)
        s.SetWidth(MM(0.1))
        s.SetCenter(pcbnew.VECTOR2I(MM(x), MM(y)))
        s.SetEnd(pcbnew.VECTOR2I(MM(x + d / 2), MM(y)))
        board.Add(s)

    # End labels: past each end of each pin row, in line with the pads.
    # The strip between a socket body and its pads is covered by the
    # socket's legs once it is soldered, so nothing goes there.
    end_off = 1.6
    x1, x2 = j1p["1"][0], j2p["1"][0]
    add_text("3V", x1, j1p["1"][1] - end_off)
    add_text("A2", x1, j1p["5"][1] + end_off)
    add_text("Feather", (X_3V_UP - TRACE_WIDTH / 2) / 2, j1p["1"][1] - end_off - 1.3)
    add_dot(x1 - PAD_LEN / 2 - 0.6, j1p["1"][1] - 1.2)
    add_text("VIN", x2, j2p["1"][1] - end_off)
    # Below J2 pin 7 there is only the gap down to DIN's run under the
    # socket end, so this one sits midway between the two.
    add_text("LRC", x2, (j2p["7"][1] + j1p["5"][1]) / 2)
    add_dot(x2 + PAD_LEN / 2 + 0.6, j2p["1"][1] - 1.2)

    # ------------------------------------------------------------------
    # Back silkscreen: name and date only, filling the back. Mirrored so it
    # reads correctly from behind.
    # ------------------------------------------------------------------
    # Everything here is laid out in "view" X, as read from behind, then
    # mirrored into board X.
    def vx(x):
        return W - x

    def add_back_line(p1, p2):
        sh = pcbnew.PCB_SHAPE(board)
        sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
        sh.SetLayer(pcbnew.B_SilkS)
        sh.SetWidth(MM(0.2))
        sh.SetStart(pcbnew.VECTOR2I(MM(vx(p1[0])), MM(p1[1])))
        sh.SetEnd(pcbnew.VECTOR2I(MM(vx(p2[0])), MM(p2[1])))
        board.Add(sh)

    def back_text(text, x, y, size):
        add_text(text, vx(x), y, size=size, layer=pcbnew.B_SilkS, mirror=True)

    name = ["Feather", "I2S Amp", "Shim"]
    size_name, lead = 2.4, 1.35
    table = [("A0", "BCLK"), ("A1", "LRC"), ("A2", "DIN")]
    size_tab, row_h = 1.1, 1.8
    size_date = 1.4
    gap = 1.0
    name_h = (len(name) - 1) * size_name * lead + size_name
    tab_h = len(table) * row_h
    block = name_h + gap + tab_h + gap + size_date
    y = (H - block) / 2

    for i, line in enumerate(name):
        back_text(line, W / 2, y + size_name / 2 + i * size_name * lead, size_name)
    y += name_h + gap

    # Feather pin -> amp signal, two columns with a box and a divider.
    tab_l, tab_r, tab_div = W / 2 - 4.5, W / 2 + 4.5, W / 2 - 1.0
    for i in range(len(table) + 1):
        add_back_line((tab_l, y + i * row_h), (tab_r, y + i * row_h))
    add_back_line((tab_l, y), (tab_l, y + tab_h))
    add_back_line((tab_r, y), (tab_r, y + tab_h))
    add_back_line((tab_div, y), (tab_div, y + tab_h))
    for i, (pin, sig) in enumerate(table):
        yc = y + (i + 0.5) * row_h
        back_text(pin, (tab_l + tab_div) / 2, yc, size_tab)
        back_text(sig, (tab_div + tab_r) / 2, yc, size_tab)
    y += tab_h + gap

    back_text(DATE_STAMP, W / 2, y + size_date / 2, size_date)

    # ------------------------------------------------------------------
    # Unconnected copper fill over the whole board. No net, so every island
    # is kept; nothing relies on it electrically.
    # ------------------------------------------------------------------
    zone = pcbnew.ZONE(board)
    zone.SetLayer(pcbnew.F_Cu)
    zone.SetNetCode(0)
    zone.SetLocalClearance(MM(FILL_GAP))
    zone.SetMinThickness(MM(FILL_MIN))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_NONE)
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    # Outline inset EDGE_GAP from the board outline (same corner centres,
    # smaller radius). The filler does not apply the edge clearance from
    # the design settings here, so the inset is built into the zone itself.
    outline = zone.Outline()
    outline.NewOutline()
    r_in = R - EDGE_GAP
    for (c, a, b) in corners:
        a0 = math.atan2(a[1] - c[1], a[0] - c[0])
        a1 = math.atan2(b[1] - c[1], b[0] - c[0])
        if a1 < a0:
            a1 += 2 * math.pi
        for i in range(9):
            t = a0 + (a1 - a0) * i / 8
            outline.Append(MM(c[0] + r_in * math.cos(t)), MM(c[1] + r_in * math.sin(t)))
    board.Add(zone)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    board.Save(OUT_PCB)

    # Data 70 on every text element. The Python API cannot set a face.
    with open(OUT_PCB) as f:
        s = f.read()
    s, n_font = re.subn(r'\(font\n(\s*)\(size',
                        lambda m: f'(font\n{m.group(1)}(face "Data 70")\n{m.group(1)}(size', s)
    with open(OUT_PCB, "w") as f:
        f.write(s)
    print(f"Patched {n_font} text blocks with Data 70")

    etch = os.path.join(SCRIPT_DIR, "etch")
    os.makedirs(etch, exist_ok=True)
    common = [KICAD_CLI, "pcb", "export", "pdf", "--layers", "F.Cu,Edge.Cuts",
              "--black-and-white"]
    subprocess.run(common + ["--mirror", "-o",
                             os.path.join(etch, "etch-FCu-MIRRORED-1to1.pdf"), OUT_PCB],
                   check=True, capture_output=True)
    subprocess.run(common + ["-o", os.path.join(etch, "etch-FCu-reference.pdf"), OUT_PCB],
                   check=True, capture_output=True)
    print("Exported etch PDFs")


if __name__ == "__main__":
    main()
