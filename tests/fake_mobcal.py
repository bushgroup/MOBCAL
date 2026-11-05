"""A stand-in for the 2012 binary, for testing the driver's plumbing in milliseconds.

Run as ``python fake_mobcal.py GAS`` in a directory holding ``mobcal.in``, exactly as the driver
runs the real binary: it reads the records, opens the input file named there, and writes the
output file named there. Like the program, it refuses, exit 1, a generator word on the seed
record that is not ``ranlux`` or ``philox``, a word on the split record that is not ``static``
or ``claim``, and ``claim`` on the combining run, and it refuses when ``parameters.tab`` is
missing or rendered for the other gas; at ``philox`` it prints the program's Philox line in
place of the RANLUX ones; it reads ``settings.tab`` when there is one (the 2012 values
otherwise), deals ``itn * inp`` blocks per set and writes the settings into each block file,
and prints the temperature in its SUMMARY. What it writes is chosen by the input file's first
line, its label:

    ok           a complete output ending in a SUMMARY block; the cross sections are a function
                 of the seed and the generator, so a result can be traced to its job
                 (``TM = 50 + seed % 7``, half an Å² more at ``philox``, and ``PA``/``EHS`` in
                 helium only, as the real program reports them)
    sets N       the same, with the multi-set SUMMARY the program writes for N coordinate sets
    refuse       the program's refusal of an undefined element: the header lines, then
                 ``type not defined for atom number      1``, exit 1, no SUMMARY
    crash        a partial output, then exit 3
    silent       no output file at all, exit 0
    sleep S      wait S seconds, then as ``ok`` (the concurrency test)
    lazy         as ``ok``, but in a split run the last worker leaves its last block unwritten
                 (under the static dealing) or claims its first block and never writes it
                 (under the claimed dealing)
    short K      as ``ok``, but a claiming worker stops after K claims, so with W * K below the
                 block count some blocks are never claimed
    greedy       as ``ok``, but a claiming worker ignores the claims and writes every block, so
                 every block is written by every worker

With a fourth record ``W w`` the stand-in does what the program does in a split run: worker
``w`` writes a block file for each of its blocks (``temp1`` a function of the seed, the set and
the block, no failures) and an output whose SUMMARY is a partial sum; the combining run
(``w = 0``) reads every block back, stops with ``combining run: no file ...`` and no SUMMARY if
one is missing, and otherwise writes the ``ok`` output (or ``sets N``) with the program's
``blocks of imp trajectories`` line. With ``W w claim`` the worker claims blocks as the program
does, creating ``../claim-<set>-<k>`` exclusively before each block and integrating the block
only when the create succeeds, in stream order (``ranlux``) or point-major order (``philox``),
and prints the program's ``blocks claimed as reached`` line.

The output mimics the real file's shape where the driver reads it (the SUMMARY labels, the
``a30`` padding of the echoed input name, the ``E`` exponents, the multi-set tables) and is a
sketch elsewhere.
"""

import os
import sys
import time
from pathlib import Path

from mobcal.io.block import Block, block_name, claim_name, owned
from mobcal.settings import DEFAULTS, RENDERED, SettingsError, read_rendered


def claim(name: str, me: int) -> bool:
    """Create the claim file exclusively, as the program's ``open(status='new')`` does."""
    try:
        fd = os.open(Path("..") / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as f:
        f.write(f"{me:5d}\n")
    return True


def main() -> int:
    gas = sys.argv[1] if len(sys.argv) > 1 else "he"
    records = Path("mobcal.in").read_text(encoding="latin-1").splitlines()
    inp, out = records[0].strip(), records[1].strip()
    seed_record = records[2].split()
    seed = int(seed_record[0])
    generator = seed_record[1] if len(seed_record) > 1 else "ranlux"
    split_record = records[3].split() if len(records) > 3 else []
    split = tuple(int(x) for x in split_record[:2]) if split_record else None
    deal = split_record[2] if len(split_record) > 2 else "static"
    table = Path("parameters.tab")
    head = table.read_text(encoding="ascii").split()[:3] if table.is_file() else []
    if generator not in ("ranlux", "philox"):
        return write(out, [f" random number generator {generator} in mobcal.in is not ranlux or "
                           "philox"], 1)
    if deal not in ("static", "claim"):
        return write(out, [f" dealing word {deal[:6]:<6} in the split record of mobcal.in is "
                           "not static or claim"], 1)
    claiming = deal == "claim"
    if claiming and split[1] == 0:
        return write(out, [" the combining run (w = 0) does not claim blocks"], 1)
    # The settings, as the program reads them: the 2012 values without the file.
    settings = DEFAULTS
    if Path(RENDERED).is_file():
        try:
            settings = read_rendered(Path(RENDERED))
        except SettingsError as e:
            return write(out, [f" {RENDERED} cannot be read as a MOBCAL-SETTINGS 1 file ({e})"],
                         1)
    blocks_per_set = settings.blocks_per_set
    if head != ["MOBCAL-LJ", "1", {"he": "He", "n2": "N2"}[gas]]:
        return write(out, [" no parameters.tab for this gas in the run directory"], 1)
    label = Path(inp).read_text(encoding="latin-1").splitlines()[0].strip()
    words = label.split()
    mode, arg = words[0], (words[1] if len(words) > 1 else None)

    if mode == "silent":
        return 0
    if mode == "sleep":
        time.sleep(float(arg))
        mode = "ok"
    lazy, greedy, short = mode == "lazy", mode == "greedy", None
    if mode == "short":
        short = int(arg)
    if mode in ("lazy", "greedy", "short"):
        mode = "ok"

    lines = [f" input file name = {inp:<30}", f" input file label = {label:<30}",
             " number of coordinate sets =    1", " number of atoms =      21",
             " coordinates in angstroms", " using a calculated (non-uniform) charge distribution"]
    if mode == "refuse":
        lines.append(" type not defined for atom number      1")
        return write(out, lines, 1)
    if generator == "ranlux":
        banner = [" RANLUX INITIALIZED BY RLUXGO FROM SEEDS" f" {seed} 0 0"]
        seed_line = f" using RANLUX with seed integer ={seed:8d}"
    else:
        banner = []
        seed_line = f" using Philox4x32-10 with seed integer ={seed:8d}"
    lines += [" mass of ion = 1.0417E+02", *banner, seed_line]
    if mode == "crash":
        return write(out, lines, 3)

    sets = int(arg) if mode == "sets" else 1
    if split is not None:
        total, me = split
        done = read_blocks = empty = 0
        claims = 0
        for s in range(1, sets + 1):
            # the walk: stream order (cycle-major), or point-major for a claiming Philox worker
            ks = list(range(1, blocks_per_set + 1))
            if claiming and generator == "ranlux":
                ks.sort(key=lambda k: Block.cycle_point(k, settings.itn))
            for k in ks:
                if claiming:
                    if greedy:
                        mine = True
                    elif short is not None and claims >= short:
                        mine = False
                    else:
                        mine = claim(claim_name(s, k), me)
                        claims += mine
                else:
                    mine = owned(k, total, me)
                if mine:
                    if lazy and me == total and (
                            claiming and claims == 1 or not claiming and k == max(
                                kk for kk in range(1, blocks_per_set + 1)
                                if owned(kk, total, me))):
                        continue
                    Block(s, *Block.cycle_point(k, settings.itn), seed,
                          (seed % 1000 + s + k) / 1e3, 0.5, 0, generator,
                          settings).write(Path("."))
                    done += 1
                elif Path(block_name(s, k)).is_file():
                    read_blocks += 1
                elif me == 0:
                    lines.append(f" combining run: no file {block_name(s, k):<20} for this block")
                    return write(out, lines, 1)
                else:
                    empty += 1
        lines += ["", f" blocks of imp trajectories: integrated{done:5d}, read from files"
                      f"{read_blocks:5d}, empty{empty:5d} (worker{me:3d} of{total:3d})"]
        if claiming:
            walk = "point" if generator == "philox" else "cycle"
            lines.append(f" blocks claimed as reached, visited {walk}-major")

    tm = 50 + seed % 7 + (0.5 if generator == "philox" else 0)
    if split is not None and split[1] > 0:
        tm = tm / split[0]  # a worker's partial sum, which is not a result
    pa, ehs = tm + 5.5, tm + 8

    def e(x: float) -> str:  # the program's 1pe11.4
        return f"{x:11.4E}"

    def inv(cs: float) -> float:  # an inverse mobility that follows the cross section
        return 18.4 * cs

    def mean_inv(values: list[float]) -> float:  # the AVGE row's: 1 / (mean mobility)
        return len(values) / sum(1 / inv(v) for v in values)

    # Every SUMMARY line the program prints, in its formats (605-636 one set, 622-634 several),
    # in the order the program prints them, the charge-distribution lines excepted: the program
    # gates those on tmmob, which is zero where they would print.
    trajectory = ["", " mobility calculation by MOBIL2 (trajectory method)", "",
                  " trajectory parameters",
                  f" sw1 ={e(5e-5)}       sw2 ={e(5e-3)}",
                  f" dtsf1 ={e(0.5)}     dtsf2 ={e(0.1)}", "",
                  f" number of complete cycles (itn) ={settings.itn:6d}",
                  f" number of velocity points (inp) ={settings.inp:6d}",
                  f" number of random points (imp) ={settings.imp:6d}",
                  f" total number of points ={settings.itn * settings.inp * settings.imp:7d}"]
    lines += ["", "", "", " SUMMARY", "", " program version = junkn.f",
              f" input file name = {inp:<30}", f" input file label = {label:<30}",
              f" temperature ={e(settings.temperature)}", seed_line]
    if mode == "ok":
        lines.append(f" structural asymmetry parameter ={e(1.2982)}")
        if gas == "he":
            lines += ["", " mobility calculation by MOBIL4 (HS scattering)", "",
                      f" number of Monte Carlo trajectories ={settings.inum:7d}",
                      f" maximum number of reflections encountered ={4:3d}", "",
                      f" inverse average PA mobility ={e(inv(pa))}",
                      f" average PA cross section ={e(pa)}", "",
                      f" inverse average EHS mobility ={e(inv(ehs))}",
                      f" average EHS cross section ={e(ehs)}"]
        lines += trajectory + [
            "", f" inverse average (second order) TM mobility ={e(inv(tm))}",
            f" average TM cross section ={e(tm)}",
            f" standard deviation (percent) ={e(0.92)}",
            f" number of failed trajectories ={3:4d}"]
    else:  # sets N
        n = sets
        pas, ehss, tms = ([x + i for i in range(1, n + 1)] for x in (pa, ehs, tm))
        asym = [1.2982 + i / 1e4 for i in range(1, n + 1)]
        if gas == "he":
            lines += ["", " mobility calculation by MOBIL4 (HS scattering)", "",
                      f" number of Monte Carlo trajectories ={settings.inum:7d}", "",
                      f" minimum and maximum number of reflections ={3:3d}  {4:3d}", "", "",
                      "    set     PA CS       PA MOB^-1      EHSS CS      EHSS MOB^-1"
                      "    ASYMP"]
            lines += [f" {i:5d}   {p:11.4E}   {inv(p):11.4E}   {h:11.4E}   {inv(h):11.4E}"
                      f"   {a:8.4f}"
                      for i, p, h, a in zip(range(1, n + 1), pas, ehss, asym, strict=True)]
            lines += ["", f"   AVGE  {sum(pas) / n:11.4E}   {mean_inv(pas):11.4E}   "
                          f"{sum(ehss) / n:11.4E}   {mean_inv(ehss):11.4E}   "
                          f"{sum(asym) / n:8.4f}"]
        lines += trajectory + ["", f" total number of failed trajectories ={3:4d}", "", "",
                               "    set     TM CS       TM MOB^-1"]
        lines += [f" {i:5d}   {t:11.4E}   {inv(t):11.4E}" for i, t in enumerate(tms, 1)]
        lines += ["", f"   AVGE  {sum(tms) / n:11.4E}   {mean_inv(tms):11.4E}"]
    return write(out, lines, 0)


def write(out: str, lines: list[str], rc: int) -> int:
    Path(out).write_text("\n".join(lines) + "\n", encoding="latin-1")
    return rc


if __name__ == "__main__":
    sys.exit(main())
