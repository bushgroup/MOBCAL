# The element tables

Each MOBCAL program assigns every atom of an ion four numbers by the atom's integer mass key:
a mass, a Lennard-Jones well depth, a Lennard-Jones radius, and a hard-sphere radius. The 2012
release wrote these tables into the Fortran as a chain of `if(imass(iatom).eq.NN)` blocks, nine
elements for helium and ten for nitrogen, and wrote each chain twice, once in each of the two
routines that read coordinates. This repository keeps each gas's table as one data file instead,
`src/mobcal/parameters/mobcal_He.toml` and `src/mobcal/parameters/mobcal_N2.toml`, and the
package renders a short table from it into the directory of every run. No number has changed:
every value in the two files is the literal the 2012 source spells, character for character, and
the test suite holds each file to the source row for row.

This page describes the file format (format 1), the table the package renders from it, and how a
run names its table and records which one it used.

## Why every number is a string

The precision of a Fortran literal is in its spelling. `0.4020` is a single-precision (REAL(4))
literal and `0.4020d0` a double-precision (REAL(8)) one, and the two differ in the eighth
significant digit once promoted to double precision. The nitrogen table's well depths and radii
are single-precision literals in the 2012 source, so every nitrogen cross section the program
has produced was computed with them in that form. A TOML number would be parsed as a double, and
the difference would be lost before the program saw it.

So every number in a parameter file is a TOML string holding the Fortran literal, and the file
declares the precision of each column. A literal with a `d` exponent is double precision and a
literal without an exponent is single precision; the package refuses a file in which a token's
spelling disagrees with its column's declared kind. Measured with gfortran 16.2.0, each of the 80
numbers in the two files, read back from its rendered token at run time by its declared kind,
gives the same 64-bit pattern as the compiled literal in the 2012 source, whereas none of the 20
single-precision literals does when read as double precision. Do not tidy a literal: `1.35d-3`
written as `1.35e-3` is a single-precision number, and `0.4020` written as `0.4020d0` is a
different number.

## The file

A parameter file is TOML, UTF-8, with four keys at the top, a `[kinds]` table, a `[combining]`
table for nitrogen only, and one `[[element]]` table per element:

```toml
format = 1                    # the schema version
name = "MOBCAL 2012 helium"   # the set's name, one line
gas = "He"                    # He or N2; must match the program the run uses
form = "pair"                 # pair for He, combining for N2

[kinds]                       # the precision of each column's literals: single or double
mass = "double"
epsilon = "double"
sigma = "double"
rhs = "double"

[[element]]
key = 12                      # the integer mass key, as the coordinate file carries it
symbol = "C"
mass = "12.01d0"
epsilon = "1.3266d-3"
sigma = "3.0126d0"
rhs = "2.7d0"
status = "fitted"             # fitted or provisional
rhs_status = "own"            # own, or borrowed from another element
provenance = "fitted to the mobility of C60 (2012 source)"
```

What the two numeric columns mean depends on `form`. In a `pair` table (helium) they are He–X
pair parameters used as they stand: the well depth in eV and σ in Å. In a `combining` table
(nitrogen) they are the element's own X–X parameters, f·D_I in kcal/mol and f·x_I in Å, the
universal force field (UFF) values of Rappé et al. scaled by one factor per element, and the
program combines each with the gas by a geometric mean using the four constants in
`[combining]`:

| Column | `pair` (helium) | `combining` (nitrogen) |
|---|---|---|
| `epsilon` | `eolj = epsilon*xe` | `eolj = dsqrt(eogas*epsilon)*conve*xe` |
| `sigma` | `rolj = sigma*1.0d-10` | `rolj = dsqrt(rogas*sigma)*convr*1.0d-10` |
| `rhs` | `rhs = rhs*1.0d-10` | `rhs = rhs*1.0d-10` |
| `mass` | the atom's mass | the atom's mass |

The nitrogen file's `[combining]` table holds `eogas` and `rogas`, the gas's own UFF parameters,
`convr`, which is 2^(-1/6) and converts UFF's r_min to a Lennard-Jones σ, and `conve`, which
converts kcal/mol to eV. `conve` is written `4.2d0*0.01036427d0` in the 2012 source, with 4.2
kJ/kcal where the conversion is 4.184, so every nitrogen well depth is 0.382 % higher than the
literal conversion would make it. The per-element factors were fitted with that constant in
place, and it stays as the source writes it.

`status`, `rhs_status` and `provenance` describe a row and do not enter the calculation. Every
row of the two shipped files is `fitted` and `own`, and its provenance line says where the 2012
source says the row came from. Format 1 keeps this record to a minimum on purpose; a later
format will extend it.

### The two expressions

Two tokens are expressions because the 2012 source writes them as expressions: helium sodium's
σ, `3.97d0/1.12246d0` (r_min over an approximation to 2^(1/6)), and nitrogen's `conve`. The files
keep them as written, since the expression is the record, and they are the only tokens allowed
an operator. The package evaluates each in IEEE double precision, one correctly rounded division
or product, and renders the 17-significant-digit literal that reproduces the result exactly:
`3.5368743652335053d+00` and `4.3529933999999999d-02`. A compiled fold of the same expression by
gfortran gives the same 64-bit pattern, and the test suite holds both values to the patterns
measured from the compiled source.

### What a file must satisfy

The package refuses a file, naming the file, the element's key and the field, when any of these
fails:

- `format` is 1, `gas` is `He` or `N2`, and `form` is the one that gas's program implements;
- `name` is 1 to 60 characters of letters, digits, blanks and `._()+-`;
- `[kinds]` declares exactly the four columns, each `single` or `double`, and a nitrogen file's
  `[combining]` gives exactly the four constants, each double precision;
- there are 1 to 100 elements, each with every field and no other, keys positive and unique;
- every numeric token is a string of at most 32 characters, digits, one `.`, digits and an
  optional `d` exponent, with no sign, no `e` exponent, no blank, comma or slash, spelled with
  the column's declared kind, and greater than zero; no token but the two expressions above holds an
  operator;
- `status` is `fitted` or `provisional`, `rhs_status` is `own` or `borrowed`, and `provenance`
  is one line.

## The rendered table

Before a run starts, the package writes `parameters.tab` into the run directory beside
`mobcal.in`. It is the table the program reads, designed so that Fortran's list-directed read
takes it line by line with no parsing of its own: blank-separated tokens, no comments, no free
text, and no comma or slash, either of which would split or end a list-directed record. The
helium table begins

```
MOBCAL-LJ 1 He MOBCAL_2012_helium 6e19c7ce13dbff2035bac9c762226db61316e706b23f52f2336028af76da18f0
8 8 8 8
9
1 1.008d0 0.6175d-03 2.2610d0 2.2d0
12 12.01d0 1.3266d-3 3.0126d0 2.7d0
```

The first line carries a fixed word, the rendered table's own format number, the gas, the set's
name with blanks made underscores, and the SHA-256 of the TOML file it was rendered from. The
second gives the kind of the mass, well-depth, radius and hard-sphere columns in bytes, 4 for
single precision and 8 for double. The nitrogen table has one more line here, the four
`[combining]` constants in the order `eogas rogas conve convr`. Then come the number of elements
and one row per element: the key and the four tokens, each copied verbatim from the file except
the two expressions, which appear as their evaluated literals. The program reads each token as
text and converts it with an internal read into a REAL(4) or REAL(8) variable by its column's
kind, which is how the 80 numbers above were measured.

The table is written for every run, every time, and is never edited by hand. To prepare a
directory for running a program without `mobcal run`, render the table there:

```
uv run mobcal render-parameters he path/to/run
```

The programs read this table and nothing else. Started in a directory without one, or with a
table that is not of this format, is for the other gas, declares a kind other than 4 or 8
bytes, has more than 100 rows or cannot be read to its end, a program stops with status 1 and
says which, on the screen and as the only line of its output file. The set's name and hash are
printed to the screen; the output file gains no line, so it still compares byte for byte with
the 2012 references. The test suite reads every row of both shipped tables back through the
programs' own reader and holds each number to the one the 2012 source computed, to the last
bit.

## Choosing a table for a run

By default a run uses the shipped table for its gas. To name another, pass `--parameters`:

```
uv run mobcal run choline.mfj --gas n2 --parameters my_nitrogen.toml
```

The file is checked the same way as the shipped ones, and a file for the other gas is refused.
The run's record names the table it used, by path, name and hash, so that a result from another
table is never mistaken for one from the shipped one.

## The record of a run

When a run ends, whether it finished or failed, the package writes `record.json` into its
directory: the package version; the program, its path, and the record `mobcal build` wrote when
it compiled it (compiler, flags, source hash); the input file, the name it was copied to, its
SHA-256, its atom count and its number of coordinate sets; the seed, the random number generator
and, for a split run, the number of processes; the parameter table, its path, name, format and
SHA-256, whether it is the
shipped one, and the name of the rendered table; the start time, the wall time, the exit status,
the verdict and its message; the cross sections and the values for each coordinate set; and the
names of the output and console files. The program's output file is unchanged by any of this, so
it still compares byte for byte with the 2012 references. `summary.json` names each run's table
and its SHA-256 as well.
