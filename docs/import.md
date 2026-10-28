# Importing a structure and its charges

A MOBCAL input file (`.mfj`) gives, for every atom of the ion, its x, y and z coordinates, the
integer key of its element, and a partial charge. The 2012 model needs nothing else from a
structure: no atom types, no bonds and no force-field labels. `mobcal import` writes that file
from an ORCA output or from an `.xyz` file, with the charges you name, and writes beside it a
record of where every number came from. The written file has one coordinate set, coordinates in
ångström, and charges in `calc` mode, i.e., one explicit charge on every atom line, which is the
form both 2012 programs read the same way.

This page describes what the import reads, how the charges are chosen, and what it refuses. It
does not choose a level of theory or a charge scheme for you.

## The command

In the window, an ORCA output or an `.xyz` file added to the inputs is imported by the rules on
this page, and its row offers the charges the file holds
([The window](window.md#inputs)). From a terminal,

```
mobcal import choline_sp.out --charges chelpg
```

reads the ORCA output `choline_sp.out` and writes `choline_sp_chelpg.mfj` and
`choline_sp_chelpg.import.json` in the current directory:

```
wrote choline_sp_chelpg.mfj: 21 atoms from choline_sp.out (ORCA 6.1.1), chelpg charges summing to +1.000000 (net charge +1), element keys of the He and N2 tables
wrote choline_sp_chelpg.import.json
```

`-o NAME.mfj` names the file instead, and its record goes beside it as `NAME.import.json`. The
import never replaces an existing file unless given `--force`. The written file runs like any
other input, in helium under the default method and in nitrogen under its nitrogen form:

```
mobcal run choline_sp_chelpg.mfj
mobcal run choline_sp_chelpg.mfj --method 2012-philox-n2
```

The installed program carries this ORCA output as `examples/choline_sp.out`. It is one of six
ORCA jobs on the choline cation in the source code's `tests/data/qm/orca/`, and
[their README](../tests/data/qm/README.md) gives each job's route and which charge blocks it
prints.

## Choosing the charges

There is no default. The charge distribution enters every trajectory through the ion-induced
dipole potential, so the choice belongs to the person running the calculation, and the import
refuses until one is named. Without `--charges` it lists what the file holds:

```
error: choose the charges: choline_opt_chelpg.out holds mulliken, lowdin, chelpg; or uniform (Q/N on every atom, from the net charge)
```

The names are the ones ORCA's blocks are read under:

| `--charges` | ORCA block |
|---|---|
| `mulliken` | MULLIKEN ATOMIC CHARGES |
| `lowdin` | LOEWDIN ATOMIC CHARGES |
| `chelpg` | CHELPG Charges (requested with `CHELPG` on the route) |
| `hirshfeld` | HIRSHFELD ANALYSIS (requested with `Hirshfeld`) |
| `column` | the fifth column of an `.xyz` file |
| `uniform` | Q/N on every atom |

The net charge Q is the charge the ORCA calculation was run at. `--net-charge Q` may be given as
well, and the import refuses when the two disagree. An `.xyz` file carries no net charge, so
`--net-charge` is required for one.

Named charges are written as the output prints them and are never rescaled. They must sum to Q
within 0.001 e, and the import refuses a block that does not, giving the sum. ORCA prints
Mulliken, Löwdin and CHELPG charges that sum to Q at the printed digits, whereas it integrates
Hirshfeld charges on a grid, and for the 21-atom choline cation they sum to +1.0002.

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

An output from a run that did not terminate normally is refused, and so is an optimization that
did not converge, because its last geometry is not a stationary point.

An `.xyz` file holds one geometry: an atom count, a comment line, and one line per atom with the
element symbol, x, y and z in ångström, and optionally a charge in a fifth column. ORCA's
`<job>.chelpg.xyz` file has that form, so it imports with `--charges column --net-charge Q`. A
file with more than one frame is refused; conformers are separate inputs, which `mobcal run`
runs side by side.

## Elements

Each atom's key is its element's key in the element table of each gas
([The element tables](parameters.md)). By default the import checks both tables, so the file
runs in both gases. An element a table lacks is refused, naming the gas and what the table holds.
The helium table has no phosphorus, so an ion with phosphorus imports only with `--gas n2`. The
import adds no element to either table.

## What is refused

- a Gaussian output (not yet supported), or an output of any program but ORCA;
- an ORCA output that did not terminate normally, or an optimization that did not converge;
- no `--charges`, or a block the file does not hold, or one printed only before the last
  geometry;
- charges that sum to more than 0.001 e from the net charge;
- no net charge for `uniform` or `column` from an `.xyz`, or a `--net-charge` that disagrees
  with the output;
- an element not in the table of a gas asked for;
- more than 200,000 atoms, the bound the programs are built with;
- an `.xyz` with more than one frame, a charge on some atoms but not all, or a line that is not
  an element symbol and three coordinates.

Each refusal exits with status 2, writes nothing, and says why.

## The record

`NAME.import.json` records the source file's path and SHA-256, the program and version that
wrote it, the reader (cclib and its version for an ORCA output), the route keywords and input
file name the output reports, the charges chosen with their sum, the net charge and where it came
from, the tolerance, the blocks the file held and any it refused, each element's key with the
name and SHA-256 of each table checked, and the label, atom count and SHA-256 of the written
`.mfj`. The `.mfj` label holds 30 characters, the import writes the source file's name and the
charge choice there, and the record is where the rest goes.

ORCA outputs are read with cclib 1.9rc1, which the package pins. cclib 1.8.1, the last stable
release, stops with an error on every ORCA 6.1.1 output in `tests/data/qm/`.
