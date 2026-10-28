# Running the quantum chemistry for an import

To compute the cross section of an ion from a structure of your own, `mobcal import` needs an
output that holds one geometry of the ion and a partial charge on every atom
([Importing a structure and its charges](import.md)). This page gives ORCA and Gaussian inputs
that produce such an output, the level of theory and charge scheme that reproduce the charges of
the 2012 choline input, and how much the choice of charges moves the cross section of that ion in
helium and in nitrogen. The worked examples are the six ORCA 6.1.1 jobs and three Gaussian 16
Rev. B.01 jobs on the choline cation (C5H14NO+, 21 atoms, z = +1) in the source code's
`tests/data/qm/` ([their README](../tests/data/qm/README.md)), and every number on this page was
measured on them. The import reads both programs' outputs with cclib 1.9rc1.

## What the calculation provides

The 2012 model takes two things from a quantum chemistry calculation: the coordinates of every
atom and a partial charge on every atom. In helium, the trajectory calculation (TM) sums a
Lennard-Jones term over the ion's atoms and adds the ion-induced dipole potential, which the
partial charges set. In nitrogen, the partial charges also interact with the three point charges
that give the N2 molecule its quadrupole moment, so they enter two terms of the potential rather
than one. The projection approximation (PA) and the exact hard-sphere scattering method (EHS) use
the coordinates alone.

The charges belong to the geometry they were computed at. A calculation for an import therefore
ends with a charge block computed at the geometry the import will take, which is the last one the
output prints ([Which geometry](import.md#which-geometry)).

## The 2012 choline charges

The 2012 choline input, `fortran/Choline.mfj`, labels its charge column `Choline_631G++dp_pop`
and records nothing else about it. To find the calculation behind it, we ran single points at its
coordinates in both programs, at B3LYP/6-31++G(d,p), the basis set the label names. Gaussian's
Merz-Kollman fit at that level reproduces the 2012 column to within 0.005 e on every atom (root
mean square 0.002 e). Optimizing the 2012 coordinates at the same level in Gaussian moved no atom
by more than 0.003 Å (root mean square 0.001 Å), and the 2012 file gives its coordinates to
0.001 Å. The 2012 choline input is therefore a B3LYP/6-31++G(d,p) minimum carrying the
Merz-Kollman charges computed at it.

In Gaussian, that recipe is an optimization followed by a Merz-Kollman fit at the optimized
geometry. Two of the Gaussian jobs test its halves. `choline_optfreq` optimizes at this level and
carries an ESP fit into the frequency step, which prints it again after the optimized geometry:

```
# B3LYP/6-31++G(d,p) Opt Freq Pop=CHELPG
```

and `choline_2012_mk` fits Merz-Kollman charges at a fixed geometry, given as written with
`NoSymm`:

```
# B3LYP/6-31++G(d,p) SP NoSymm Pop=(MK,Hirshfeld)
```

`Pop=MK` in place of `Pop=CHELPG` in the first route does both in one job, a route none of the
jobs here runs as such, and `--charges mk` imports the frequency step's charges with the
optimized geometry.

Among the blocks the import reads from an ORCA output, the ESP fit is CHELPG. The ORCA job
`choline_2012_b3lyp` runs it at the 2012 coordinates, at the level of the 2012 column:

```
! B3LYP/G 6-31++G(d,p) CHELPG Hirshfeld
%pal nprocs 8 end
%maxcore 3000
* xyzfile 1 1 choline_2012.xyz
```

`B3LYP/G` is ORCA's name for B3LYP as Gaussian defines it (with the VWN III local correlation
functional), whereas ORCA's `B3LYP` uses VWN V. The CHELPG charges are within 0.034 e of the
2012 column on 20 of the 21 atoms, whereas the quaternary nitrogen is 0.17 e more positive (root
mean square over all atoms 0.039 e). ORCA uses spherical d functions, whereas Gaussian's default
for 6-31++G(d,p) is Cartesian d functions, so the two programs' runs differ in the basis as well
as in the fit.

The nitrogen's offset is a property of the fit rather than of the level of theory. Gaussian's own
CHELPG fit, at the same level and geometry as its Merz-Kollman fit, is 0.075 e from the 2012
column (root mean square), and its largest differences are on the three methyl carbons, 0.16 to
0.17 e more positive, with each methyl's hydrogens about 0.055 e less positive. Summed over each
methyl group, the differences cancel to within 0.008 e. ORCA's fit moves charge between the
nitrogen and the four groups bonded to it instead: +0.17 e on the nitrogen, −0.036 to −0.046 e on
each group. An ESP fit chooses charges that reproduce the electrostatic potential at points
outside the ion, and that potential sets the total charge of a group of atoms more closely than it
sets how the total is divided among them, least of all for an atom buried at the centre of the
ion, i.e., the quaternary nitrogen or a methyl carbon under its three hydrogens. Fits that place
their points differently, the Merz-Kollman shells (861 points here) and the CHELPG cubic grid
(12,034), each with its program's radii, therefore disagree most on those atoms. This is
consistent with the poor conditioning of buried-atom charges that Bayly, Cieplak, Cornell and
Kollman described for ESP fits (*J. Phys. Chem.* 1993, 97, 10269). The cross section is far less
sensitive to these redistributions than the per-atom charges are: all three ESP fits at this level
move choline's TM cross section by less than 0.1 % in either gas (below).

## Optimizing, then computing the charges

The jobs in `tests/data/qm/` show three ways to get the charges at an optimized geometry, and the
import reads each the same way, taking the last geometry and the blocks printed after it.

- **Two jobs.** The ORCA job `choline_opt` optimizes at r2SCAN-3c (`! r2SCAN-3c Opt`) and writes
  its final geometry to `choline_opt.xyz`. The job `choline_sp` reads that file and computes the
  charges at another level (`! B3LYP D3BJ def2-TZVP CHELPG Hirshfeld`). Only the second output is
  imported.
- **Two jobs in one file.** ORCA's `$new_job` runs a second job on the first one's final
  geometry, as `choline_two_jobs.inp` does:

  ```
  ! B3LYP D3BJ def2-SVP Opt
  %pal nprocs 8 end
  %maxcore 3000
  * xyzfile 1 1 choline_2012.xyz

  $new_job
  ! B3LYP D3BJ def2-TZVP CHELPG Hirshfeld
  %pal nprocs 8 end
  %maxcore 3000
  * xyzfile 1 1 choline_two_jobs.xyz
  ```

  The import takes the second job's geometry and charges.
- **Charges from the optimization itself.** An ORCA optimization prints the Mulliken and Löwdin
  charges, and with `CHELPG` on the route the CHELPG charges, at the stationary point
  (`choline_opt_chelpg`), and a Gaussian `Opt Freq` job prints the charges its `Pop=` option asks
  for in the frequency step (`choline_optfreq`). The charges are then at the level of the
  optimization.

The 2012 recipe is of the third kind, with the optimization and the charges at one level. Where
the geometry and the charges come from different levels, the two-job forms keep each step's level
on its own route line.

## The blocks each program prints

Each program prints some charge blocks by default and others only when the route asks for them.
`--charges` names the block ([Choosing the charges](import.md#choosing-the-charges)), and the
import offers only the blocks the file holds.

| Program | Printed by default | Printed when asked for |
|---|---|---|
| ORCA 6 | `mulliken`, `lowdin` | `chelpg` (`CHELPG`), `hirshfeld` (`Hirshfeld`) |
| Gaussian 16 | `mulliken` | `hirshfeld` and `cm5` (`Pop=Hirshfeld`), `mk` (`Pop=MK`), `chelpg` (`Pop=CHELPG`), `natural` (`Pop=NBO`) |

## How much the choice moves the cross section

To measure how much the charge scheme moves the cross section, we ran the choline cation at the
2012 coordinates with nine charge columns that differ only in the charges: the 2012 column and
eight others imported from the jobs in `tests/data/qm/`. Each column ran in helium under the
`2012-philox-he` method and in nitrogen under `2012-philox-n2`, at the same three seeds (5013489,
1234567 and 7654321), so that each difference from the 2012 column is taken between two runs that
share their random numbers. With the 2012 column, TM is 55.30 Å² in helium and 115.77 Å² in
nitrogen (mean of the three seeds), with a standard deviation over seeds of 0.12 and 0.20 Å², and
the paired differences below are tighter than either. The runs were made on one workstation
(Windows 11, MSYS2 gfortran 16.2.0, October 2026; lab record, tasks 29 and 30), the nitrogen runs
split across ten processes, which gives the serial result exactly.

| Charges | Σ\|q\| (e) | ΔTM, N2 (%) | ΔTM, He (%) |
|---|---|---|---|
| Gaussian, B3LYP/6-31++G(d,p), Merz-Kollman | 4.64 | −0.02 (−0.03 to −0.01) | −0.003 (−0.005 to −0.002) |
| Gaussian, B3LYP/6-31++G(d,p), CHELPG | 3.68 | −0.06 (−0.08 to −0.04) | +0.08 (+0.08 to +0.08) |
| ORCA, B3LYP/G 6-31++G(d,p), CHELPG | 4.72 | +0.04 (+0.03 to +0.07) | +0.07 (+0.06 to +0.07) |
| ORCA, B3LYP/G 6-31++G(d,p), Löwdin | 3.34 | −0.03 (−0.16 to +0.07) | +0.08 (+0.05 to +0.15) |
| ORCA, HF 6-31++G(d,p), CHELPG | 5.07 | +0.35 (+0.32 to +0.41) | +0.14 (+0.14 to +0.15) |
| ORCA, B3LYP/G 6-31++G(d,p), Mulliken | 4.78 | −0.64 (−0.66 to −0.63) | −0.37 (−0.39 to −0.36) |
| ORCA, B3LYP/G 6-31++G(d,p), Hirshfeld | 1.44 | −1.39 (−1.43 to −1.35) | −0.04 (−0.06 to 0.00) |
| `uniform`, 1/21 e on every atom | 1.00 | −2.85 (−2.99 to −2.71) | −0.27 (−0.28 to −0.27) |

ΔTM is the difference from the 2012 column (Σ|q| = 4.64 e), the mean over the three seeds with
their range in brackets. PA and EHS are the same for every column to the printed digits, as they
must be. In nitrogen the charges move TM from −2.85 to +0.35 %, whereas in helium they move it
from −0.37 to +0.14 %. Note that this is one singly charged ion of 21 atoms at one geometry, and
a larger or multiply charged ion has not been measured with this program. The three B3LYP ESP
fits and the Löwdin charges are within 0.1 % of the 2012 column in both gases (mean of the
seeds), and the Merz-Kollman fit is the 2012 column in Ω as it is in charge. In
nitrogen the columns fall roughly in order of Σ|q|, i.e., how strongly polarized the ion's charge
distribution is: Hirshfeld charges, the least polarized of the population analyses, lower TM by
1.4 %, and a uniform distribution lowers it by 2.9 %, about 16 times the standard deviation over
seeds of the 2012 column's own TM (0.17 %). The Mulliken charges are the exception, close to
the ESP fits in Σ|q| and 0.64 % low, and they put −0.75 e on the buried nitrogen, where every ESP
fit puts less than 0.2 e of either sign.

To repeat a row, import the column and run it at the three seeds in each gas, e.g., for the
Gaussian Merz-Kollman row:

```
mobcal import tests/data/qm/gaussian/choline_2012_mk/choline_2012_mk.log --charges mk
mobcal run choline_2012_mk_mk.mfj --seeds 5013489,1234567,7654321
mobcal run choline_2012_mk_mk.mfj --seeds 5013489,1234567,7654321 --method 2012-philox-n2 --split 10
```

The ORCA rows import `choline_2012_b3lyp.out` and `choline_2012_hf.out`, the `uniform` row
imports `choline_2012_b3lyp.out` with `--charges uniform`, and the 2012 column is
`fortran/Choline.mfj` as it stands. The import records the charges it wrote and the route that
computed them in the `.import.json` beside each input, so a cross section computed from an
imported input can be traced to its charge scheme.
