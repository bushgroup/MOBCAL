# tests/reference/

What the regression gate compares with: choline in helium and in nitrogen as the current
programs print it, at the 2012 reference's seed (5013489), generator (RANLUX, no word on the seed
record) and staged input name (`Choline_pop.mfj`), serial, with end-of-line CR stripped.

They are the 2012 outputs under `fortran/sample-output/` and two changes of print format, made
in one commit of the Fortran (2026-10-23, `fortran/README.md`): the atom count printed `i7`
where 2012 printed `i4`, and the q1st column divided by the number of cycles where 2012 divided
by the number of velocity points, four times the 2012 values. Each file differs from its
original in exactly those 41 lines. `tests/test_reference.py` holds that, line by line, on every
test run, and checks that the corrected column sums to the printed mean collision integral.
The originals are never edited.

Produced 2026-10-23 on Windows 11 with MSYS2 gfortran 16.2.0 and the recorded flags, by binaries
built from the sources of the commit that made the two changes. The sources are named by their
SHA-256 because the binaries are not: two builds of the same source on this toolchain differ in
their bytes, if not in what they compute.

| File | Source and its SHA-256 | Binary wall |
|---|---|---|
| `Choline_He.out` | `mobcal_He.f` `21c2e957ce4dda6077f4ec6b7088ee32e692e273a9c4a877adc121a6601c8a67` | 189 s |
| `Choline_N2.out` | `mobcal_N2.f` `41deed0efb32d667a9ae24395f198f88e1c7793a7f2844cce1c89997c13df163` | 4,413 s |

Both include `mobcal_ljread.inc`, `mobcal_rng.inc` and `mobcal_arrays.inc` as pinned in
`mobcal.fortran.SHA256` at that commit.

## `a10A1.out`, the 2000 example

What the shipped helium program prints for the example of the 2000 helium release,
`tests/data/mobcal-2000/a10A1.mfj` (50 coordinate sets), under the shipped method `2000-he` (the
2000 element table, 298 K, `imp` 25, RANLUX) at the seed of `mobcal.run` in the release, 5013486,
staged as `a10A1.mfj`, serial, end-of-line CR stripped. It differs from `a10A1.out.orig` of the
release in exactly 42 lines: the two changes above (1 + 40 lines) and the exponent
letter of the `mass of ion` line, `D` in the 2000 output and `E` since format 604 became
`1pe11.4`. `tests/test_reference.py` holds that line by line. The cross sections averaged over
the 50 sets are those of the 2000 output: PA 183.74, EHS 206.03, and TM 196.31 Å².

Produced 2026-11-14 on Windows 11 with MSYS2 gfortran 16.2.0 and the recorded flags, from
`mobcal_He.f` `ce9d056b60343514ff7891e3dbd195be3c0c29083d5f96e9ad22499833a3fd52` with the includes
as pinned at version 2.1.0.dev0; 1,170 s as one process, beside other work on a 36-core
workstation, not a timing. The output of the same calculation on Linux, macOS, and Windows in
continuous integration printed the same lines against the 2000 output on the same day.

A change to the Fortran that moves a line of these outputs replaces them in the same commit, says
why, and keeps a test that ties the new files to these or to the originals.
