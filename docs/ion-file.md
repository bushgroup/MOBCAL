# The ion file

An ion file holds what MOBCAL needs to know about an ion: the element of every atom, the
coordinates of every conformer, the partial charges, the net charge, and a record of where each
of these came from. Its format is named `mobcal-ion`, this page specifies version 1, and a file
is named `X.ion.json`, i.e., a JSON document that any JSON tool opens. The 2012 programs do not
read it. Before a run, MOBCAL writes the `.mfj` input file the 2012 program reads from the ion
file and the element table of the run, and keeps that `.mfj` in the run directory beside the
other files the run used. The ion file is what a user keeps; the `.mfj` is written per run.

> **Draft.** Version 1 is not frozen. Until a release declares it frozen, the format changes
> as MOBCAL is developed, and a file written by a development version carries no guarantee.

Three things decide what a calculation computes: the ion file, the method
([Methods](methods.md)), and the seed. A run's record names the ion file's SHA-256 and the
SHA-256 of the `.mfj` written from it, so the bytes the program read can be traced to the file
the user holds.

The machine-readable schema is [`src/mobcal/io/ion.schema.json`](../src/mobcal/io/ion.schema.json)
(JSON Schema, draft 2020-12). It checks the structure of a file. The rules that relate one field
to another (array lengths, the charge sum, the charge mode) are listed under
[What a reader refuses](#what-a-reader-refuses), and MOBCAL checks all of them whenever it reads
a file. Field names follow the `molecule` object of QCSchema where the two describe the same
quantity (`symbols`, `geometry`, `molecular_charge`, `masses`, `connectivity`), without being
bound to it: QCSchema stores coordinates in bohr, and an ion file states its unit.

## An example

The choline cation of the 2012 release (`fortran/Choline.mfj`, 21 atoms, one conformer,
Merz-Kollman charges in `calc` mode) as an ion file, with the coordinate and charge arrays
shortened here:

```json
{
  "format": "mobcal-ion",
  "version": 1,
  "label": "Choline_631G++dp_pop",
  "molecular_charge": 1,
  "units": "angstrom",
  "correction_factor": 1.0,
  "charge_mode": "calc",
  "symbols": ["N", "C", "C", "C", "C", "H", "H", ...],
  "columns": {
    "charges": {"unit": "e", "source": "Choline.mfj, column 5 (calc mode)"}
  },
  "conformers": [
    {
      "geometry": [
        [-0.878, 0.022, 0.0],
        [-1.834, 1.194, -0.008],
        ...
      ],
      "charges": [-0.021059, -0.439073, ...]
    }
  ],
  "import": {
    "source": {"path": "Choline.mfj", "sha256": "a4cf1c4a...", "program": "mfj",
               "version": null, "reader": "mobcal 2.0.1.dev0"},
    "charges": {"choice": "column", "net_charge_from": "charges"},
    "elements": {"keys": {"H": 1, "C": 12, "N": 14, "O": 16},
                 "tables": {"He": {"name": "MOBCAL 2012 helium", "sha256": "6e19c7ce..."},
                            "N2": {"name": "MOBCAL 2012 nitrogen", "sha256": "06a2528e..."}}}
  },
  "written": "2026-11-02T16:45:02+00:00",
  "written_by": {"program": "mobcal", "version": "2.0.1.dev0", "commit": "341b0bdf..."}
}
```

The `.mfj` written from this file for a helium run and for a nitrogen run each reads back as
the same input as `Choline.mfj`: the same label, units, charge mode and correction factor, and
the same coordinates, element keys and charges on every atom.

## The header

| Field | Required | Value |
|---|---|---|
| `format` | yes | `"mobcal-ion"` |
| `version` | yes | `1` |
| `label` | yes | line 1 of the written `.mfj` (below) |
| `comment` | no | any string; not read by MOBCAL |
| `molecular_charge` | yes | the ion's net charge z in e, an integer, or `null` where it is not known |
| `units` | yes | `"angstrom"` or `"bohr"`, the unit of every coordinate in the file |
| `correction_factor` | yes | line 6 of the `.mfj`, a real |
| `charge_mode` | yes | `"calc"`, `"equal"` or `"none"`, line 5 of the `.mfj` |
| `symbols` | yes | the element of each atom, in order |
| `columns` | yes | a declaration for each optional column the file carries (below); `{}` for none |
| `conformers` | yes | 1 to 100 coordinate sets (below) |
| `import` | no | how the geometry and charges were made (below) |
| `written` | no | when the file was written, ISO 8601, UTC |
| `written_by` | yes | `program`, `version`, and `commit` (40 hexadecimal digits, with `-dirty` when the program was built from a tree with changes no commit holds), or `null` where the program does not know its commit |

**The label.** Line 1 of a `.mfj` is read as the first 30 characters of the line, with leading
blanks kept and trailing blanks dropped, and the 2012 program prints it in its output. The ion
file stores the label as that line will be written: at most 30 characters, no line break (none
of the characters U+000A to U+000D, U+001C to U+001E and U+0085, each of which ends a line for
some reader), no trailing blank, and only characters of ISO 8859-1 (the `.mfj` is written in
that encoding). The
label is never derived from the file's name when the `.mfj` is written, so renaming an ion file
does not change a run's input. `mobcal import` chooses the label once, as the source file's
stem and the charge choice joined by `_` with every blank or non-printing character replaced by
`_`, cut to 30 characters ([Importing a structure](import.md)), and the user can edit it in the file.

**The unit and the correction factor.** Coordinates are stored as they were read, in the unit
`units` names, and the correction factor is stored beside them and never applied. The 2012
program converts bohr to ångström with its own constant (0.52917706) and multiplies every
centred coordinate by the correction factor, after it centres the ion on its centre of mass.
Applying either before the file is written would change the last digits of the coordinates the
program reads, and would put the 2012 constant into a file that should not depend on it, so the
ion file leaves both to the program. Files written by `mobcal import` are in ångström with a
correction factor of 1.

## Atoms and conformers

`symbols` names the element of each atom with its standard symbol, in standard case (`C`, `Cl`,
`Na`); `CL` or `cl` is refused. Each entry of `conformers` is one coordinate set of the `.mfj`,
up to 100 (the bound of the 2012 program), every one with the same number of atoms, from 1 to
200,000 (the bound of `fortran/mobcal_arrays.inc`). The 2012 program weights every conformer
equally, and the ion file carries no weights.

| Field of a conformer | Required | Value |
|---|---|---|
| `geometry` | yes | one `[x, y, z]` per atom, in the unit `units` names |
| `charges` | see [Charges](#charges) | one partial charge per atom, in e |
| `symbols` | no | this conformer's elements, only where its atom order differs from the top-level `symbols` |

A `.mfj` lets each coordinate set list its atoms in its own order, and the 2012 program checks
only that every set weighs the same as the first. A conformer's own `symbols` keeps that order
when such a file is read. A file whose conformers carry their own `symbols` cannot also carry the
per-atom columns `masses`, `mmff94_*` or `connectivity`, which would then be ambiguous.

Every real is a JSON number, read as a double precision value; an integer literal such as `0`
stands for the same real as `0.0`. `NaN` and `Infinity` are not JSON and are refused, and so is
a number too large for a double. MOBCAL writes every real as the shortest decimal that reads
back as the same double, two spaces of indent, and an array of numbers or strings on one line,
so that each atom's coordinates take one line of the file.

## Charges

**The net charge.** `molecular_charge` is the integer z the ion carries, stored apart from the
partial charges. In `calc` mode, when z is given, the charges of every conformer must sum to z
within 0.001 e, the tolerance `mobcal import` applies to a quantum chemistry output's charges
(the Hirshfeld charges of the 21-atom choline cation, integrated on a grid, sum to
z + 0.00022). The charges are written as read and never rescaled to z. A file with no charges,
or one read from a `.mfj` whose charges do not sum to an integer, carries `null`.

**The charge mode.** `charge_mode` is line 5 of the `.mfj` and keeps the meaning the 2012 programs
give it, which differs between them:

| `charge_mode` | Helium program | Nitrogen program | `charges` |
|---|---|---|---|
| `calc` | each atom's charge as written | the same | required on every atom of every conformer |
| `equal` | 1/N on every atom, whatever the charges | Σq/N on every atom, from the charges of the first conformer | optional, as read |
| `none` | no charge | no charge | optional, as read |

`mobcal import` writes `calc` mode, with Q/N written out on every atom when the user asks for
`uniform` charges, because `calc` is the one mode both programs read the same way. A file read
from a `.mfj` in `equal` or `none` mode keeps that mode and keeps the charge column as it was
read, with `null` for an atom whose line had no fifth field; the ion file never rewrites an
`equal` file as explicit charges. The nitrogen program reads five fields on every atom of the
first coordinate set in every mode, so a nitrogen run needs a charge on every atom of the first
conformer even in `equal` or `none` mode, and MOBCAL refuses the run, before the program starts,
when one is missing.

## Optional columns

A file carries the columns it uses and no others. Each one present is declared in `columns`
with its unit and a `source`, a sentence saying where its values came from (for example
`"chelpg charges from choline_sp.out (ORCA 6.1.1)"`), and a declaration without its column, or a
column without its declaration, is refused.

| Column | Where | Unit | Value |
|---|---|---|---|
| `charges` | each conformer | `e` | partial charge of each atom |
| `masses` | top level | `u` | mass of each atom |
| `mmff94_types` | top level | `1` | MMFF94 atom type, an integer |
| `mmff94_alpha` | top level | `angstrom^3` | MMFF94 polarizability α |
| `mmff94_n`, `mmff94_a`, `mmff94_g` | top level | `1` | MMFF94 van der Waals parameters N, A and G |
| `connectivity` | top level | `1` | bonds, each `[i, j, order]` with atoms counted from 0 and i < j |

Only `charges` enters a 2012 calculation. The 2012 program weighs each atom by the mass its
element table gives the atom's element, so a `masses` column is a record of the source file,
and the `.mfj` written from the ion file never takes an atom's mass or key from it. The MMFF94
columns and the masses hold what a nine-column `.mfj` written for MobCal-MPI carries, so that
such a file read as an import source loses nothing. MOBCAL does not assign MMFF94 types.

## The record of how the file was made

`import` carries the fields of the provenance record that `mobcal import` wrote beside a `.mfj`
before the ion file existed (`X.import.json`, format 2), under the same names, so that a
quantity has one name wherever it is recorded:

| Field | Value |
|---|---|
| `import.source` | `path`, `sha256` of the source file's bytes, `program` (`ORCA`, `Gaussian`, `xyz`, `mfj`, `MobCal-MPI`), `version`, `reader`, and what the source program printed about the job: `keywords`, `input_file_name`, `route`, `comment`, `untested_version`, or, for a MobCal-MPI input, its `line_6` and `run_line` as written |
| `import.charges` | `choice`, `net_charge`, `net_charge_from` (`output`, `given`, or `charges` when z was taken from the charge sum of a `.mfj`), `sum`, `difference`, `tolerance`, `available`, `refused` |
| `import.elements` | `keys`, the key of each element in the tables the import checked, and `tables`, each table's name and SHA-256 |

The format-2 record's `format`, `mobcal` and `written` become the ion file's own `format`,
`written_by` and `written`. Its `mfj` block (label, atom count, units, charge mode, and the
written `.mfj`'s name and SHA-256) is gone: the label, units and charge mode are fields of the
ion file, and the name and SHA-256 of a written `.mfj` belong to the run that wrote it. The
keys under `import.source` follow the source program and are kept as written, not refused,
because MOBCAL does not read them back.

## Writing the `.mfj`

The `.mfj` is written from three inputs: the ion file, the element table of the run, and the
gas. The same three give the same bytes on every platform: LF line ends, one atom per line,
and every real as the shortest decimal that reads back as the same double.

1. Line 1 is `label`; line 2 the number of conformers; line 3 the number of atoms; line 4 `ang`
   or `au` from `units`; line 5 `charge_mode`; line 6 `correction_factor`.
2. Each atom line is x, y, z, the element's key, and the charge when the atom has one. The key is
   looked up by element symbol in the run's element table ([The element tables](parameters.md)),
   so a run with another table, such as the 2000 helium table, which has no fluorine row, is a
   change of method and not an edit of the ion file. An element the table lacks is refused
   before the program starts, naming the element and the table.
3. Each conformer after the first is preceded by the line `coordinate set k`, which the program
   reads and discards.

`mobcal run X.ion.json` writes this file into each run directory as `X.mfj`, or as `input.mfj`
when that name is longer than the 30 characters the program reads, from the run's table and
gas, and the run's record (`record.json`) names the SHA-256 of the ion file and of the `.mfj`
written from it. A split run gives each of its processes a copy of the same file.
`mobcal export X.ion.json` writes this file as `X.mfj` beside the ion file, from the default
table of each gas, or of the gas `--gas` names, or from the table `--parameters` names
([Importing a structure and its charges](import.md#the-command)).

A file read from a `.mfj` and written back gives the same input as the original: the same
label, units, charge mode and correction factor, and on every atom of every coordinate set the
same coordinates, key and charge, with four or five fields as the original had. The written
file is byte for byte the original when the original was itself written by MOBCAL. A `.mfj`
written by hand differs in layout, in the number of digits printed for a real that reads back
the same, and in the separator lines, and in nothing the program reads.

## Reading a `.mfj` into an ion file

A `.mfj` has element keys where the ion file has symbols. MOBCAL names each key's element from
its shipped element tables, which agree on every key they share (1 H, 12 C, 14 N, 16 O, 19 F,
23 Na, 28 Si, 31 P, 32 S, 56 Fe); a key no table defines is refused. The tables used are named
under `import.elements`. When every coordinate set has a charge on every atom and every set's
charges sum to the same integer within 0.001 e, that integer becomes `molecular_charge`, with
`net_charge_from` set to `charges`; otherwise it is `null`. The charge column is declared with
the `.mfj`'s name and charge mode as its source, `import.charges.choice` is `column`, and
`import.source` records the `.mfj`'s full path and SHA-256 with `mfj` as its program. A
coordinate set whose atoms come in another order than the first set's keeps that order in its
own `symbols`, and an atom line with four fields becomes a `null` charge, so that nothing the
program reads is lost.

A nine-column `.mfj` written for MobCal-MPI is read by its own layout, which MOBCAL recognizes
by a run line at line 7 (six to eight fields, the first five integers) and nine fields on the
first atom line. It holds one coordinate set, whose atom lines give x, y, z, a mass, a charge
and the MMFF94 parameters α, N, A and G. Each atom's element is the one whose mass in the
shipped tables lies within 0.25 u of the mass given, and a mass within that window of no
element, or of two, is refused. The masses become the `masses` column and α, N, A and G the
`mmff94_alpha`, `mmff94_n`, `mmff94_a` and `mmff94_g` columns, each declared with its column
of the source as its `source`; the charge column and the charge mode are kept as for a 2012
file. Line 6, which MobCal-MPI reads as the switch of its empirical high-field correction and
never applies to the coordinates, and the run line are kept as written under
`import.source.line_6` and `import.source.run_line`, with `MobCal-MPI` as the program, and
`correction_factor` is 1. The `.mfj` written from such a file carries the 2012 layout, five
fields per atom with each element's key from the run's table, so the masses and the MMFF94
parameters inform the record and move no number a 2012 calculation computes.

## What a reader refuses

MOBCAL refuses a file, naming the field, when

- `format` is not `mobcal-ion`, or `version` is not one this version of MOBCAL reads (a file of
  version 2 is refused by name, not read as version 1);
- the file is not JSON, holds `NaN`, `Infinity` or a number too large for a double, or names
  the same key twice in one object;
- a key appears that this page does not define, anywhere outside `import.source`;
- a required field is missing, or a value has the wrong type (`true` is not a number, and
  `1.5` is not an integer);
- `label` is longer than 30 characters, holds a line break or a character outside ISO 8859-1,
  or ends in a blank;
- a symbol is not one or two letters in standard case;
- there are no conformers or more than 100, no atoms or more than 200,000, or a conformer's
  `geometry`, `charges` or `symbols`, or a top-level column, does not have one entry per atom;
- a column is present without its declaration in `columns`, or declared and absent, or
  declared with a unit other than its own or an empty `source`;
- an MMFF94 type is below 1;
- `charge_mode` is `calc` and an atom of any conformer has no charge;
- `molecular_charge` is an integer, `charge_mode` is `calc`, and a conformer's charges sum to a
  value more than 0.001 e from it;
- a conformer carries its own `symbols` and the file carries a per-atom column;
- a bond names an atom that does not exist, names its atoms out of order, or has an order
  that is not positive;
- `written` is not an ISO 8601 date and time, `written_by.commit` is neither null nor 40
  hexadecimal digits (with `-dirty`), or a SHA-256 under `import` is not 64 lowercase
  hexadecimal digits.

Writing the `.mfj` refuses, in addition, an element the run's table lacks and, for a nitrogen
run, a first conformer without a charge on every atom. MOBCAL never replaces an existing ion
file unless it is told to.
