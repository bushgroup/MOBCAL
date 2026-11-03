# Importing a structure and its charges

The 2012 programs read an ion from a `.mfj` file, which gives, for every atom, its x, y and z
coordinates, the integer key of its element, and a partial charge. The 2012 model needs nothing
else from a structure: no atom types, no bonds and no force-field labels. `mobcal import` writes
an ion file, `X.ion.json` ([The ion file](ion-file.md)), from an ORCA or Gaussian output or from
an `.xyz` file, with the charges you name, or from a `.mfj` with its own charges
([below](#a-mfj-as-the-source)), and the ion file carries the record of where every number came
from. From an output or an `.xyz`, the ion file has one conformer, coordinates in ångström,
each atom's element, and charges in `calc` mode, i.e., one explicit charge on every atom, which
is the form both 2012 programs read the same way. The `.mfj` the program reads is written from
the ion file.

This page describes what the import reads, how the charges are chosen, and what it refuses. It
does not choose a level of theory or a charge scheme for you;
[Running the quantum chemistry for an import](qm.md) gives inputs for both programs, the
calculation behind the 2012 choline charges, and how much the choice of charges moves the cross
section.

## The command

In the window, an ORCA or Gaussian output or an `.xyz` file added to the inputs is imported by
the rules on this page, and its row offers the charges the file holds
([The window](window.md#inputs)). From a terminal,

```
mobcal import choline_sp.out --charges chelpg
```

reads the ORCA output `choline_sp.out` and writes the ion file `choline_sp_chelpg.ion.json` in
the current directory:

```
wrote choline_sp_chelpg.ion.json: 21 atoms from choline_sp.out (ORCA 6.1.1), chelpg charges summing to +1.000000 (net charge +1), every element in the He and N2 tables
```

`-o NAME.ion.json` names the file instead. The import never replaces an existing file unless
given `--force`.

To run the imported ion, give the ion file to `mobcal run` like any other input, in helium
under the default method and in nitrogen under its nitrogen form:

```
mobcal run choline_sp_chelpg.ion.json
mobcal run choline_sp_chelpg.ion.json --method 2012-philox-n2
```

Each run writes the `.mfj` the program reads from the ion file and the run's element table, and
keeps it in the run directory as `choline_sp_chelpg.mfj`
([Writing the `.mfj`](ion-file.md#writing-the-mfj)). For a `.mfj` beside the ion file, e.g., to
read in another program, `mobcal export` writes one, with each element's key from the element
table of each gas (both by default, so the file runs in either):

```
mobcal export choline_sp_chelpg.ion.json
```

`mobcal export` takes `--gas he` or `n2` for one gas's table, `--parameters` for another table
([The element tables](parameters.md)), and `-o NAME.mfj` for another name, and it refuses an
element the table lacks. The `.mfj` it writes is a function of the ion file and the table alone,
so the same ion file gives the same bytes on every computer.

The installed program carries this ORCA output as `examples/choline_sp.out`, and a Gaussian 16
output on the same ion as `examples/choline_2012_mk.log`. They are two of six ORCA jobs and three
Gaussian jobs on the choline cation in the source code's `tests/data/qm/`, and
[their README](../tests/data/qm/README.md) gives each job's route and which charge blocks it
prints.

## Choosing the charges

There is no default. The charge distribution enters every trajectory through the ion-induced
dipole potential, so the choice belongs to the person running the calculation, and the import
refuses until one is named. Without `--charges` it lists what the file holds:

```
error: choose the charges: choline_opt_chelpg.out holds mulliken, lowdin, chelpg; or uniform (Q/N on every atom, from the net charge)
```

The names are the ones each program's blocks are read under:

| `--charges` | ORCA block | Gaussian block |
|---|---|---|
| `mulliken` | MULLIKEN ATOMIC CHARGES | Mulliken charges |
| `lowdin` | LOEWDIN ATOMIC CHARGES | |
| `hirshfeld` | HIRSHFELD ANALYSIS (`Hirshfeld` on the route) | the Q-H column of the Hirshfeld and CM5 block (`Pop=Hirshfeld`) |
| `cm5` | | the Q-CM5 column of the same block |
| `natural` | | Summary of Natural Population Analysis (`Pop=NBO`, Gaussian's own NBO 3.1) |
| `chelpg` | CHELPG Charges (`CHELPG` on the route) | ESP charges fitted with Breneman radii (`Pop=CHELPG`) |
| `mk` | | ESP charges fitted with Merz-Kollman radii (`Pop=MK`) |
| `column` | the fifth column of an `.xyz` file | |
| `uniform` | Q/N on every atom | Q/N on every atom |

Gaussian prints the hydrogen-summed form of each set as well, and atomic polar tensor charges
after a frequency calculation; the import offers neither, because neither is one charge per atom
of the kind the 2012 model takes. An ESP fit is named by the radii line Gaussian prints before it,
e.g., `Merz-Kollman atomic radii used.`, and the route's `Pop=` option must ask for the same fit.

The 2012 choline input carries a charge column labelled `Choline_631G++dp_pop` and nothing else
about where it came from. `--charges mk` on `choline_2012_mk.log`, a B3LYP/6-31++G(d,p) single
point at the 2012 coordinates, reproduces that column to within 0.005 e on every atom (root mean
square 0.002 e), whereas the CHELPG fit at the same geometry and level is 0.17 e away on one atom.
The 2012 column is therefore a Merz-Kollman fit
([The 2012 choline charges](qm.md#the-2012-choline-charges)).

The net charge Q is the charge the calculation was run at. `--net-charge Q` may be given as
well, and the import refuses when the two disagree. An `.xyz` file carries no net charge, so
`--net-charge` is required for one.

Named charges are written as the output prints them and are never rescaled. They must sum to Q
within 0.001 e, and the import refuses a block that does not, giving the sum. ORCA prints
Mulliken, Löwdin and CHELPG charges that sum to Q at the printed digits, whereas it integrates
Hirshfeld charges on a grid, and for the 21-atom choline cation they sum to +1.0002. Gaussian's
Hirshfeld and CM5 charges for the same ion sum to +1.00002.

`uniform` writes Q/N as an explicit charge on every atom, in `calc` mode. The file format has a
mode for this, `equal`, which the import never writes, because the two 2012 programs read it
differently: the helium program gives every atom 1/N whatever the ion's charge, whereas the
nitrogen program divides the sum of the file's charge column evenly. An explicit charge on every
line means the same thing to both.

## Which geometry

The import takes the last geometry the output prints and, for each kind of charge, the last
block of that kind, and pairs them only when the block is printed after that geometry. ORCA
prints a block after the coordinates it was computed at. In an optimization, ORCA 6 prints the
Mulliken and Löwdin charges twice, at the starting geometry and after the final energy
evaluation at the stationary point, and with `CHELPG` on the route it prints the CHELPG charges
after every cycle as well; the last block of each kind follows the stationary point. A file with
two jobs (`$new_job`) is read the same way, so the second job's geometry and charges are the ones
imported. A kind whose last block comes before the last geometry belongs to an earlier one, and
the import lists it as refused rather than pair it with the wrong coordinates.

Gaussian also prints each block after the coordinates it belongs to, in the standard orientation
unless `NoSymm` is on the route, in which case the coordinates are the input orientation, i.e.,
the coordinates as given. An `Opt Freq` job writes two job steps to one log, and the frequency
step prints its own coordinates and its own population analysis, with the `Pop=` options of the
route carried into it. The import takes the frequency step's geometry and blocks, and it checks
that this geometry is the optimization's last point to the printed digits, refusing the log if it
is not.

An output from a run that did not terminate normally is refused, and so is an optimization that
did not converge, because its last geometry is not a stationary point. A Gaussian log must end
every job step with a normal termination, so a two-step log whose second step stopped part way is
refused even though its first step finished.

## Program versions

The import is tested on ORCA 6 and Gaussian 16 outputs. An output of another version is
imported, the command prints a warning naming the tested version, and the record carries
`"untested_version": true`. In the window, the input's status reads "ready (untested version)".
Check the charges such an import writes against the output before running it.

An `.xyz` file holds one geometry: an atom count, a comment line, and one line per atom with the
element symbol, x, y and z in ångström, and optionally a charge in a fifth column. ORCA's
`<job>.chelpg.xyz` file has that form, so it imports with `--charges column --net-charge Q`. A
file with more than one frame is refused; conformers are separate inputs, which `mobcal run`
runs side by side.

## A `.mfj` as the source

A `.mfj` already holds an ion with its charges, so `mobcal import` takes one without a choice of
charges:

```
mobcal import Choline.mfj
```

writes `Choline.ion.json`, i.e., the source file's name with `.ion.json` in place of `.mfj`. The
import reads two layouts. The first is the one the 2012 programs read
([Reading a `.mfj` into an ion file](ion-file.md#reading-a-mfj-into-an-ion-file)): the label,
units, charge mode, correction factor, every coordinate set and the charge column are kept as
read, and each integer key is named as an element from the shipped element tables. The second is
the nine-column `.mfj` that MobCal-MPI reads, in which line 6 is the switch of MobCal-MPI's
empirical high-field correction and not a coordinate factor, line 7 is a run line
(`itn inp imp igas seed T_bath`, optionally followed by T_eff,max and the number of temperature
points), and each atom line holds x, y, z, a mass, a charge and the MMFF94 parameters α, N, A
and G of the atom's MMFF94 type. The import recognizes this layout by its run line and by nine
fields on the first atom line. Each atom's element is the one whose mass in the shipped tables
lies within 0.25 u of the mass the file gives, a window that holds both the average mass of
every element the tables hold and its monoisotopic mass, which MobCal-MPI's input generator
writes for C, N, O and S. A mass in no element's window, or in two, is refused. The masses and
the four MMFF94 parameters are kept as declared columns of the ion file, and line 6 and the run
line as written are kept in the record, so the ion file loses nothing the source holds. The
ion file's correction factor is 1, because MobCal-MPI applies no factor to the coordinates.
MobCal-MPI reads one coordinate set, and a nine-column file with more is refused. `mobcal run`
refuses a nine-column file given to it directly, before the program starts, since the 2012
program would read its run line as the first atom; the ion file imported from it runs instead.

In both layouts the charges are the file's charge column, the charge mode is the file's, and
the net charge is the integer every coordinate set's charges sum to within 0.001 e, or none
when they do not. `--charges` and `--net-charge` are refused. The 2012 programs weigh each atom
by the mass of its element in the run's element table, and a run from the ion file does so
too, so a mass column in the source moves no number a run computes. A MobCal-MPI input in
`equal` mode keeps that mode, which the 2012 helium program reads as 1/N on every atom and the
nitrogen program as the charge column's sum divided evenly
([Charges](ion-file.md#charges)).

## Elements

Each atom's key is its element's key in the element table of each gas
([The element tables](parameters.md)). By default the import checks both tables, so the file
runs in both gases. An element a table lacks is refused, naming the gas and what the table holds.
The helium table has no phosphorus, so an ion with phosphorus imports only with `--gas n2`. The
import adds no element to either table.

## What is refused

- an output of any program but ORCA or Gaussian;
- an output that did not terminate normally (for Gaussian, every job step), or an optimization
  that did not converge;
- a Gaussian log whose last geometry is not the optimization's last point;
- no `--charges`, or a block the file does not hold, or one printed only before the last
  geometry;
- a Gaussian ESP fit whose radii line and `Pop=` option disagree, a fit with radii read from the
  input (`Pop=ReadRadii`), a fit constrained to the dipole moment or fitting point dipoles, and
  the CHELP, Hu-Lu-Yang and MK-UFF fits, for which the import has no test output;
- natural charges from an NBO program other than Gaussian's built-in NBO 3.1 (`Pop=NBO6` or
  `NBO7`);
- charges that sum to more than 0.001 e from the net charge;
- no net charge for `uniform` or `column` from an `.xyz`, or a `--net-charge` that disagrees
  with the output;
- an element not in the table of a gas asked for;
- more than 200,000 atoms, the bound the programs are built with;
- an `.xyz` with more than one frame, a charge on some atoms but not all, or a line that is not
  an element symbol and three coordinates;
- a `.mfj` the 2012 program would not read to the end, a key no shipped table defines, or
  `--charges` or `--net-charge` given with a `.mfj`;
- a nine-column MobCal-MPI `.mfj` with more than one coordinate set, an atom line of other than
  nine fields, a run line of other than six to eight fields beginning with five integers, a
  mass within 0.25 u of no element of the shipped tables or of two, or lines after the last
  atom.

Each refusal exits with status 2, writes nothing, and says why.

## The record

The `import` block of the ion file ([The ion file](ion-file.md#the-record-of-how-the-file-was-made))
records the source file's path and SHA-256, the program and version that
wrote it and whether the import is tested on that version, the reader (cclib and its version for
an ORCA or Gaussian output), the route keywords and input file name an ORCA output reports or the
route of a Gaussian log, the charges chosen with their sum, the net charge and where it came
from, the tolerance, the blocks the file held and any it refused, each element's key with the
name and SHA-256 of each table checked. The declaration of the charge column names the charges
and the output they came from, e.g., `chelpg charges from choline_sp.out (ORCA 6.1.1)`. The
label, i.e., line 1 of the `.mfj`, holds 30 characters, and the import writes the source file's
name and the charge choice there, joined by `_`; the ion file is where the rest goes.

ORCA and Gaussian outputs are read with cclib 1.9rc1, which the package pins. cclib 1.8.1, the
last stable release, stops with an error on every ORCA 6.1.1 output in `tests/data/qm/`. cclib
reads Gaussian's ESP fits only from a log printed at `#P`, so the import reads the ESP charges from
the log's text itself, at any print level, and where cclib has read the same fit the two must
agree.
