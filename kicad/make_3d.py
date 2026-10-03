#!/usr/bin/env python3
"""
Make flat-SMT right-angle socket models for J1 and J2.

KiCad only ships the 2.54mm right-angle socket as through-hole. This takes
that model, keeps the body, cuts the legs off at the board surface, and adds
a flat foot from each leg out along its pad, which is how the SMT part sits.

Run with FreeCAD's command-line interpreter:
  /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd make_3d.py

Output is VRML, not STEP: a STEP written from freecadcmd carries no colours,
and VRML lets the body be black and the pins gold. Each model is written
already placed in its footprint's frame, so the footprint uses it with zero
offset and rotation.
"""

import os

import FreeCAD
import Part

V = FreeCAD.Vector

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd()
SRC = os.path.join(HERE, "3dmodels", "Connector_PinSocket_2.54mm.3dshapes")
OUT = os.path.join(HERE, "3dmodels", "i2s-amp-shim.3dshapes")

PITCH = 2.54
# Stock horizontal socket, in its own frame: pin 1 at the origin, pins run
# -Y, legs come out the back at x~0 and drop through the board, body from
# x=-10.03 to -1.52.
BODY_BACK = -1.52
PIN = 0.64            # square pin section
FOOT_H = 0.3          # foot thickness on the pad
LEG_X = 0.1 - PIN     # leg's near face (bbox max x is 0.1)
FOOT_END = 7.6 - 5.43 # foot runs to near the pad's far end (pad 5.445..7.955 in J1's frame)

BLACK = (0.10, 0.10, 0.10)
GOLD = (0.86, 0.74, 0.40)


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def flat_socket(src, pins):
    """Body and pins as two shapes, in the stock model's frame."""
    s = Part.read(src)
    bb = s.BoundBox
    body = s.common(box(bb.XMin - 1, BODY_BACK, bb.YMin - 1, bb.YMax + 1, 0, bb.ZMax + 1))
    legs = s.cut(box(bb.XMin - 1, BODY_BACK, bb.YMin - 1, bb.YMax + 1, bb.ZMin - 1, bb.ZMax + 1))
    # Drop everything below the board surface: the SMT part does not go through.
    legs = legs.common(box(bb.XMin - 1, bb.XMax + 1, bb.YMin - 1, bb.YMax + 1, 0, bb.ZMax + 1))
    feet = []
    for k in range(pins):
        y = -k * PITCH
        feet.append(box(LEG_X, FOOT_END, y - PIN / 2, y + PIN / 2, 0, FOOT_H))
    pins_shape = legs.fuse(feet).removeSplitter()
    return body, pins_shape


def place(shape, mirror_x, dx, dy):
    s = shape.copy()
    if mirror_x:
        s = s.mirror(V(0, 0, 0), V(1, 0, 0))
    s.translate(V(dx, dy, 0))
    return s


def write_wrl(path, parts):
    """parts: [(shape, rgb)]. KiCad reads VRML in units of 0.1in."""
    k = 1 / 2.54
    out = ["#VRML V2.0 utf8\n"]
    for shape, rgb in parts:
        pts, tris = shape.tessellate(0.02)
        out.append("Shape {\n appearance Appearance { material Material { "
                   f"diffuseColor {rgb[0]} {rgb[1]} {rgb[2]} specularColor 0.2 0.2 0.2 shininess 0.3 }} }}\n"
                   " geometry IndexedFaceSet {\n  solid FALSE\n  coord Coordinate { point [\n")
        out.append(",\n".join(f"   {p.x * k:.5f} {p.y * k:.5f} {p.z * k:.5f}" for p in pts))
        out.append("\n  ] }\n  coordIndex [\n")
        out.append(",\n".join(f"   {a},{b},{c},-1" for a, b, c in tris))
        out.append("\n  ]\n }\n}\n")
    with open(path, "w") as f:
        f.write("".join(out))
    print(f"wrote {path}")


# J1: same transform the footprint used on the stock model, offset (5.43, 5.08).
body, pins = flat_socket(os.path.join(SRC, "PinSocket_1x05_P2.54mm_Horizontal.step"), 5)
write_wrl(os.path.join(OUT, "Feather_RtAngle_Socket_SMD_1x05.wrl"),
          [(place(body, False, 5.43, 2 * PITCH), BLACK),
           (place(pins, False, 5.43, 2 * PITCH), GOLD)])

# J2: mirrored in X so the opening faces +X, then offset (-5.33, 7.62).
body, pins = flat_socket(os.path.join(SRC, "PinSocket_1x07_P2.54mm_Horizontal.step"), 7)
write_wrl(os.path.join(OUT, "Amp_RtAngle_Socket_SMD_1x07.wrl"),
          [(place(body, True, -5.33, 3 * PITCH), BLACK),
           (place(pins, True, -5.33, 3 * PITCH), GOLD)])
