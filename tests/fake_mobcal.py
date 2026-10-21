"""A stand-in for the 2012 binary, for testing the driver's plumbing in milliseconds.

Run as ``python fake_mobcal.py GAS`` in a directory holding ``mobcal.in``, exactly as the driver
runs the real binary: it reads the three records, opens the input file named there, and writes
the output file named there. What it writes is chosen by the input file's first line, its label:

    ok           a complete output ending in a SUMMARY block; the cross sections are a function
                 of the seed, so a result can be traced to its job (``TM = 50 + seed % 7``,
                 and ``PA``/``EHS`` in helium only, as the real program reports them)
    sets N       the same, with the multi-set SUMMARY the program writes for N coordinate sets
    refuse       the program's refusal of an undefined element: the header lines, then
                 ``type not defined for atom number  1``, exit 0, no SUMMARY
    crash        a partial output, then exit 3
    silent       no output file at all, exit 0
    sleep S      wait S seconds, then as ``ok`` (the concurrency test)

The output mimics the real file's shape where the driver reads it (the SUMMARY labels, the
``a30`` padding of the echoed input name, the ``E`` exponents, the multi-set tables) and is a
sketch elsewhere.
"""

import sys
import time
from pathlib import Path


def main() -> int:
    gas = sys.argv[1] if len(sys.argv) > 1 else "he"
    records = Path("mobcal.in").read_text(encoding="latin-1").splitlines()
    inp, out, seed = records[0].strip(), records[1].strip(), int(records[2])
    label = Path(inp).read_text(encoding="latin-1").splitlines()[0].strip()
    words = label.split()
    mode, arg = words[0], (words[1] if len(words) > 1 else None)

    if mode == "silent":
        return 0
    if mode == "sleep":
        time.sleep(float(arg))
        mode = "ok"

    lines = [f" input file name = {inp:<30}", f" input file label = {label:<30}",
             " number of coordinate sets =    1", " number of atoms =  21",
             " coordinates in angstroms", " using a calculated (non-uniform) charge distribution"]
    if mode == "refuse":
        lines.append(" type not defined for atom number  1")
        return write(out, lines, 0)
    lines += [" mass of ion = 1.0417D+02", " RANLUX INITIALIZED BY RLUXGO FROM SEEDS"
              f" {seed} 0 0", f" using RANLUX with seed integer ={seed:8d}"]
    if mode == "crash":
        return write(out, lines, 3)

    tm = 50 + seed % 7
    pa, ehs = tm + 5.5, tm + 8
    lines += ["", "", "", " SUMMARY", "", " program version = junkn.f",
              f" input file name = {inp:<30}", f" input file label = {label:<30}",
              " temperature = 3.0100E+02", f" using RANLUX with seed integer ={seed:8d}"]
    if mode == "ok":
        if gas == "he":
            lines += ["", " mobility calculation by MOBIL4 (HS scattering)",
                      f" average PA cross section = {pa:.4E}",
                      f" average EHS cross section = {ehs:.4E}"]
        lines += ["", " mobility calculation by MOBIL2 (trajectory method)",
                  f" average TM cross section = {tm:.4E}",
                  " standard deviation (percent) = 9.2000E-01",
                  " number of failed trajectories =   3"]
    else:  # sets N
        n = int(arg)
        if gas == "he":
            lines += ["", "    set     PA CS       PA MOB^-1      EHSS CS      EHSS MOB^-1"
                          "    ASYMP"]
            lines += [f" {i:5d}   {pa + i:11.4E}   {1.0:11.4E}   {ehs + i:11.4E}   {1.0:11.4E}"
                      f"   {1.0:8.4f}" for i in range(1, n + 1)]
            lines += ["", f"   AVGE  {pa + (n + 1) / 2:11.4E}   {1.0:11.4E}   "
                          f"{ehs + (n + 1) / 2:11.4E}   {1.0:11.4E}   {1.0:8.4f}"]
        lines += ["", "    set     TM CS       TM MOB^-1"]
        lines += [f" {i:5d}   {tm + i:11.4E}   {1.0:11.4E}" for i in range(1, n + 1)]
        lines += ["", f"   AVGE  {tm + (n + 1) / 2:11.4E}   {1.0:11.4E}"]
    return write(out, lines, 0)


def write(out: str, lines: list[str], rc: int) -> int:
    Path(out).write_text("\n".join(lines) + "\n", encoding="latin-1")
    return rc


if __name__ == "__main__":
    sys.exit(main())
