#!/usr/bin/env python3
"""
Write i2s-amp-shim.kicad_sch from scratch.

Plain python3 is enough (no pcbnew). Symbols are copied verbatim from the
stock KiCad libraries into lib_symbols. Nets come from local labels on short
wire stubs, so they come out as /NAME, which is what build_pcb.py expects.

Symbol UUIDs are fixed so re-running this does not break the footprint
links build_pcb.py makes with SetPath().

  J1  Feather side, right-angle socket: 3V, GND, A0, A1, A2
  J2  #3006 MAX98357 breakout, right-angle socket (amp stands vertical):
      Vin, GND, SD, GAIN, DIN, BCLK, LRC
"""

import os
import uuid

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SCRIPT_DIR, "i2s-amp-shim.kicad_sch")
SYM_DIR = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"

ROOT_UUID = "7b1d2c30-5a8e-4f61-9c3e-2a0f6d1e4b01"
UUIDS = {
    "J1": "7b1d2c30-5a8e-4f61-9c3e-2a0f6d1e4b11",
    "J2": "7b1d2c30-5a8e-4f61-9c3e-2a0f6d1e4b12",
}


def u():
    return str(uuid.uuid4())


def lib_block(lib, name):
    s = open(os.path.join(SYM_DIR, lib + ".kicad_sym")).read()
    i = s.index(f'(symbol "{name}"')
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0:
                blk = s[i:j + 1]
                # Only the top-level name gets the library prefix; the
                # _0_1 / _1_1 sub-symbols keep their bare names.
                return blk.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)
    raise ValueError(name)


def prop(name, value, x, y, hide=False):
    h = " (hide yes)" if hide else ""
    return (f'\t\t(property "{name}" "{value}" (at {x} {y} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)){h})\n\t\t)\n')


def symbol(lib_id, ref, value, fp, x, y, pins, rot=0):
    out = (f'\t(symbol (lib_id "{lib_id}") (at {x} {y} {rot}) (unit 1)\n'
           f'\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
           f'\t\t(uuid "{UUIDS[ref]}")\n')
    out += prop("Reference", ref, x + 2.54, y - 10.16)
    out += prop("Value", value, x + 2.54, y + 10.16)
    out += prop("Footprint", fp, x, y, hide=True)
    out += prop("Datasheet", "~", x, y, hide=True)
    for p in pins:
        out += f'\t\t(pin "{p}" (uuid "{u()}"))\n'
    out += (f'\t\t(instances (project "i2s-amp-shim"\n'
            f'\t\t\t(path "/{ROOT_UUID}" (reference "{ref}") (unit 1))))\n\t)\n')
    return out


def wire(x1, y1, x2, y2):
    return (f'\t(wire (pts (xy {x1} {y1}) (xy {x2} {y2}))\n'
            f'\t\t(stroke (width 0) (type default)) (uuid "{u()}"))\n')


def label(name, x, y, rot=0):
    just = "right bottom" if rot == 180 else "left bottom"
    return (f'\t(label "{name}" (at {x} {y} {rot}) (fields_autoplaced yes)\n'
            f'\t\t(effects (font (size 1.27 1.27)) (justify {just}))\n'
            f'\t\t(uuid "{u()}"))\n')


def no_connect(x, y):
    return f'\t(no_connect (at {x} {y}) (uuid "{u()}"))\n'


def text(t, x, y):
    return (f'\t(text "{t}" (exclude_from_sim no) (at {x} {y} 0)\n'
            f'\t\t(effects (font (size 1.27 1.27)) (justify left bottom))\n'
            f'\t\t(uuid "{u()}"))\n')


def main():
    body = ""

    # Conn_01x0N_Socket pins sit at local (-5.08, +2.54*k), pin 1 on top.
    # Schematic Y is down, so pin n is at y0 - local_y.
    def conn_pin(x0, y0, n, count):
        top = 2.54 * (count - 1) / 2
        return (x0 - 5.08, y0 - (top - 2.54 * (n - 1)))

    # J1: Feather 3V, GND, A0, A1, A2
    j1x, j1y = 88.9, 76.2
    body += symbol("Connector:Conn_01x05_Socket", "J1", "Feather 3V-A2",
                   "i2s-amp-shim:Feather_RtAngle_Socket_SMD_1x05",
                   j1x, j1y, [str(n) for n in range(1, 6)])
    j1_nets = {1: "3V3", 2: "GND", 3: "BCLK", 4: "LRC", 5: "DIN"}
    for n, net in j1_nets.items():
        px, py = conn_pin(j1x, j1y, n, 5)
        body += wire(px - 5.08, py, px, py)
        body += label(net, px - 5.08, py, 180)

    # J2: MAX98357 breakout (#3006) JP1, verified against Adafruit's EAGLE
    # source: 1=Vin 2=GND 3=SD 4=GAIN 5=DIN 6=BCLK 7=LRC
    j2x, j2y = 152.4, 76.2
    body += symbol("Connector:Conn_01x07_Socket", "J2", "MAX98357 #3006",
                   "i2s-amp-shim:Amp_RtAngle_Socket_SMD_1x07",
                   j2x, j2y, [str(n) for n in range(1, 8)])
    j2_nets = {1: "3V3", 2: "GND", 5: "DIN", 6: "BCLK", 7: "LRC"}
    for n in range(1, 8):
        px, py = conn_pin(j2x, j2y, n, 7)
        if n in j2_nets:
            body += wire(px - 5.08, py, px, py)
            body += label(j2_nets[n], px - 5.08, py, 180)
        else:
            body += no_connect(px, py)

    body += text("J2 SD and GAIN left open: amp defaults to 9 dB gain, (L+R)/2 mono.",
                 101.6, 105.41)

    libs = "".join("\t\t" + lib_block(lib, n).replace("\n", "\n\t\t") + "\n"
                   for lib, n in [("Connector", "Conn_01x05_Socket"),
                                  ("Connector", "Conn_01x07_Socket")])

    sch = (f'(kicad_sch\n\t(version 20231120)\n\t(generator "eeschema")\n'
           f'\t(generator_version "8.0")\n\t(uuid "{ROOT_UUID}")\n\t(paper "A4")\n'
           f'\t(title_block (title "Feather I2S Amp Shim") (company "mikeysklar"))\n'
           f'\t(lib_symbols\n{libs}\t)\n'
           f'{body}'
           f'\t(sheet_instances (path "/" (page "1")))\n)\n')
    with open(OUT, "w") as f:
        f.write(sch)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
