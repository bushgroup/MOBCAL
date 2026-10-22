"""A stand-in for the 2012 binary, for testing the driver's plumbing in milliseconds.

Run as ``python fake_mobcal.py GAS`` in a directory holding ``mobcal.in``, exactly as the driver
runs the real binary: it reads the records, opens the input file named there, and writes the
output file named there. What it writes is chosen by the input file's first line, its label:

    ok           a complete output ending in a SUMMARY block; the cross sections are a function
                 of the seed, so a result can be traced to its job (``TM = 50 + seed % 7``,
                 and ``PA``/``EHS`` in helium only, as the real program reports them)
    sets N       the same, with the multi-set SUMMARY the program writes for N coordinate sets
    refuse       the program's refusal of an undefined element: the header lines, then
                 ``type not defined for atom number   1``, exit 1, no SUMMARY
    crash        a partial output, then exit 3
    silent       no output file at all, exit 0
    sleep S      wait S seconds, then as ``ok`` (the concurrency test)
    lazy         as ``ok``, but in a split run the last worker leaves its last block unwritten

With a fourth record ``W w`` the stand-in does what the program does in a split run: worker
``w`` writes a block file for each of its blocks (``temp1`` a function of the seed, the set and
the block, no failures) and an output whose SUMMARY is a partial sum; the combining run
(``w = 0``) reads every block back, stops with ``combining run: no file ...`` and no SUMMARY if
one is missing, and otherwise writes the ``ok`` output (or ``sets N``) with the program's
``blocks of imp trajectories`` line.

The output mimics the real file's shape where the driver reads it (the SUMMARY labels, the
``a30`` padding of the echoed input name, the ``E`` exponents, the multi-set tables) and is a
sketch elsewhere.
"""

import sys
import time
from pathlib import Path

from mobcal.io.block import BLOCKS_PER_SET, Block, block_name, owned


def main() -> int:
    gas = sys.argv[1] if len(sys.argv) > 1 else "he"
    records = Path("mobcal.in").read_text(encoding="latin-1").splitlines()
    inp, out, seed = records[0].strip(), records[1].strip(), int(records[2])
    split = tuple(int(x) for x in records[3].split()[:2]) if len(records) > 3 else None
    label = Path(inp).read_text(encoding="latin-1").splitlines()[0].strip()
    words = label.split()
    mode, arg = words[0], (words[1] if len(words) > 1 else None)

    if mode == "silent":
        return 0
    if mode == "sleep":
        time.sleep(float(arg))
        mode = "ok"
    lazy = mode == "lazy"
    if lazy:
        mode = "ok"

    lines = [f" input file name = {inp:<30}", f" input file label = {label:<30}",
             " number of coordinate sets =    1", " number of atoms =  21",
             " coordinates in angstroms", " using a calculated (non-uniform) charge distribution"]
    if mode == "refuse":
        lines.append(" type not defined for atom number   1")
        return write(out, lines, 1)
    lines += [" mass of ion = 1.0417E+02", " RANLUX INITIALIZED BY RLUXGO FROM SEEDS"
              f" {seed} 0 0", f" using RANLUX with seed integer ={seed:8d}"]
    if mode == "crash":
        return write(out, lines, 3)

    sets = int(arg) if mode == "sets" else 1
    if split is not None:
        total, me = split
        done = read_blocks = empty = 0
        for s in range(1, sets + 1):
            for k in range(1, BLOCKS_PER_SET + 1):
                if owned(k, total, me):
                    if lazy and me == total and k == max(
                            kk for kk in range(1, BLOCKS_PER_SET + 1) if owned(kk, total, me)):
                        continue
                    Block(s, *Block.cycle_point(k), seed,
                          (seed % 1000 + s + k) / 1e3, 0.5, 0).write(Path("."))
                    done += 1
                elif Path(block_name(s, k)).is_file():
                    read_blocks += 1
                elif me == 0:
                    lines.append(f" combining run: no file {block_name(s, k):<20} for this block")
                    return write(out, lines, 1)
                else:
                    empty += 1
        lines += ["", f" blocks of imp trajectories: integrated{done:4d}, read from files"
                      f"{read_blocks:4d}, empty{empty:4d} (worker{me:3d} of{total:3d})"]

    tm = 50 + seed % 7
    if split is not None and split[1] > 0:
        tm = tm / split[0]  # a worker's partial sum, which is not a result
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
        n = sets
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
