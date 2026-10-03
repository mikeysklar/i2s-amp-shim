#!/usr/bin/env python3
"""
Write the two render-only footprints: a Feather RP2350 plugged into J1 and
the MAX98357 breakout plugged into J2, both standing at 90 degrees to the
shim.

They have no pads and are board-only, excluded from the BOM and position
files, so they show up in the 3D viewer and nowhere else. build_pcb.py
places each one at the same origin as the socket it sits in, so the
transforms below are in that socket footprint's frame (3D axes: X east,
Y north, Z up from the board's top surface).

Plain python3 is enough.

Board models are Adafruit's (github.com/adafruit/Adafruit_CAD_Parts, MIT).
They are bare boards, so male headers from KiCad's library are added.
"""

import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "footprints", "i2s-amp-shim.pretty")
M3D = "${KIPRJMOD}/3dmodels"

PITCH = 2.54
# Both sockets: opening 4.6mm from the footprint origin, pin axis 1.27mm
# above the board (stock right-angle socket is 2.54mm tall).
OPENING = 4.6
AXIS_Z = 1.27
# A male header's plastic sits between the plugged board and the socket.
HEADER_PLASTIC = 2.54


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def matvec(a, v):
    return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]


def cols(x, y, z):
    """Rotation whose columns are the images of the source X, Y, Z axes."""
    return [[x[i], y[i], z[i]] for i in range(3)]


def kicad_rotate(r):
    """KiCad applies p' = Rz(-rz) Ry(-ry) Rx(-rx) p. Decompose r as
    Rz(a) Ry(b) Rx(c) and return (rx, ry, rz) = (-c, -b, -a)."""
    if abs(r[2][0]) > 1 - 1e-9:
        # Gimbal lock (b = +/-90): only a +/- c is defined, so take a = 0.
        a = 0.0
        if r[2][0] < 0:
            b = math.pi / 2
            c = math.atan2(r[0][1], r[0][2])
        else:
            b = -math.pi / 2
            c = math.atan2(-r[0][1], -r[0][2])
    else:
        b = -math.asin(r[2][0])
        a = math.atan2(r[1][0], r[0][0])
        c = math.atan2(r[2][1], r[2][2])
    return tuple(round(-math.degrees(v), 4) + 0.0 for v in (c, b, a))


def model(path, r, t):
    rx, ry, rz = kicad_rotate(r)
    return (f'\t(model "{path}"\n'
            f'\t\t(offset (xyz {t[0]:.4f} {t[1]:.4f} {t[2]:.4f}))\n'
            f'\t\t(scale (xyz 1 1 1))\n'
            f'\t\t(rotate (xyz {rx} {ry} {rz}))\n\t)\n')


# A KiCad vertical male header, mounted on the underside of the board it
# belongs to: header Z points away from that board (-z of the board), and
# its pins, which run -Y from pin 1, run +x along the board's header row.
HEADER_ON_UNDERSIDE = cols((0, -1, 0), (-1, 0, 0), (0, 0, -1))


def footprint(name, descr, models):
    return f'''(footprint "{name}"
	(version 20260206)
	(generator "pcbnew")
	(generator_version "10.0")
	(layer "F.Cu")
	(descr "{descr}")
	(tags "render-only 3D")
	(property "Reference" "REF**"
		(at 0 0 0)
		(layer "F.Fab")
		(hide yes)
		(effects (font (size 1 1) (thickness 0.15)))
	)
	(property "Value" "{name}"
		(at 0 0 0)
		(layer "F.Fab")
		(hide yes)
		(effects (font (size 1 1) (thickness 0.15)))
	)
	(attr board_only exclude_from_pos_files exclude_from_bom)
{"".join(models)})
'''


def assembly(board_path, board_r, board_t, headers):
    """headers: [(path, origin_in_board_frame)]"""
    out = [model(board_path, board_r, board_t)]
    for path, origin in headers:
        r = matmul(board_r, HEADER_ON_UNDERSIDE)
        t = [a + b for a, b in zip(matvec(board_r, origin), board_t)]
        out.append(model(path, r, t))
    return out


# ----------------------------------------------------------------------
# Feather RP2350 in J1's frame.
# Adafruit model: x along the board (USB end at x=0), y across, z up, top
# copper at z=1.57. 16-pin row JP1 at y=1.27, pads x = 44.45 - (n-1)*2.54:
# n=14 3.3V at 11.43, 13 GND, 12 A0, 11 A1, n=10 A2 at 21.59 (from the
# Feather RP2350 EAGLE .brd). 12-pin row JP3 at y=21.6535, x 16.51..44.45.
#
# Pins point into J1 (+X), so the Feather's -z is +X and its parts face
# west. Its 16-pin row is the bottom edge, the board rising above the shim
# (+y -> +Z). That leaves x -> -Y: USB end north, which puts 3.3V north of
# A2, matching J1 pin 1 north.
# ----------------------------------------------------------------------
f_r = cols((0, -1, 0), (0, 0, 1), (-1, 0, 0))
# J1 pin 1 (3V) is at Y=+2*PITCH and must meet x=11.43.
f_t = (-(OPENING + HEADER_PLASTIC), 2 * PITCH + 11.43, AXIS_Z - 1.27)
feather = assembly(f"{M3D}/Adafruit.3dshapes/Adafruit_Feather_RP2350_6000.step", f_r, f_t, [
    (f"{M3D}/Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x16_P2.54mm_Vertical.step", (6.35, 1.27, 0)),
    (f"{M3D}/Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x12_P2.54mm_Vertical.step", (16.51, 21.6535, 0)),
])

# ----------------------------------------------------------------------
# MAX98357 (#3006) in J2's frame.
# Adafruit model: 17.78 x 19.05, header row JP1 at y=2.54, pads
# x = 16.51 - (n-1)*2.54: n=1 Vin at 16.51 ... n=7 LRC at 1.27.
#
# Pins point into J2 (-X), so the amp's +z (parts) faces east. Header row
# is the bottom edge, board rising above the shim (+y -> +Z), which leaves
# x -> +Y: Vin north, matching J2 pin 1 north.
# ----------------------------------------------------------------------
a_r = cols((0, 1, 0), (0, 0, 1), (1, 0, 0))
# J2 pin 1 (Vin) is at Y=+3*PITCH and must meet x=16.51.
a_t = (OPENING + HEADER_PLASTIC, 3 * PITCH - 16.51, AXIS_Z - 2.54)
amp = assembly(f"{M3D}/Adafruit.3dshapes/Adafruit_MAX98357_3006.step", a_r, a_t, [
    (f"{M3D}/Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x07_P2.54mm_Vertical.step", (1.27, 2.54, 0)),
])

for name, descr, models in [
    ("Render_Feather_RP2350_on_J1",
     "Render only, no copper: Adafruit Feather RP2350 (#6000) with male headers, plugged into J1.",
     feather),
    ("Render_MAX98357_on_J2",
     "Render only, no copper: Adafruit MAX98357 I2S amp (#3006) with male header, plugged into J2.",
     amp),
]:
    path = os.path.join(OUT, name + ".kicad_mod")
    with open(path, "w") as f:
        f.write(footprint(name, descr, models))
    print(f"wrote {path}")
