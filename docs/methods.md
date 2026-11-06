# Methods

A method is everything a calculation depends on except its input: the buffer gas, the element
table, the random number generator and the six run settings (the temperature and the five
sampling counts, [The run settings](settings.md)), and, in a method file of one's own, a seed if
one is wanted. The window's Method list and `mobcal run
--method` choose one, and every run records the method it used, so a cross section can be traced to
the calculation that gave it. A batch runs one method, and so one gas; helium and nitrogen are two
batches, which the window's queue or two commands run one after the other.

## The five shipped methods

| Key | Name in the window | Gas | Element table | Generator | Settings |
|---|---|---|---|---|---|
| `2012-he` | MOBCAL 2012 (He) | helium | 2012 | RANLUX | 2012 |
| `2012-n2` | MOBCAL 2012 (N2) | nitrogen | 2012 | RANLUX | 2012 |
| `2012-philox-he` | MOBCAL 2012 with Philox (He) | helium | 2012 | Philox4x32-10 | 2012 |
| `2012-philox-n2` | MOBCAL 2012 with Philox (N2) | nitrogen | 2012 | Philox4x32-10 | 2012 |
| `2000-he` | MOBCAL 2000 (He) | helium | 2000 | RANLUX | 298 K, `imp` 25 |

The 2012 settings are 301 K, `imp` 1,000, `itn` 10, `inp` 40, `inum` 250,000 and `inor` 30.
`2012-he` and `2012-n2` are the calculation of the 2012 release, which at the 2012 seed
reproduces its outputs ([Reproducing MOBCAL 2012](mobcal-2012.md)). `2012-philox-he` and
`2012-philox-n2` are the same tables and settings under Philox4x32-10, whose divided runs give
the serial result exactly ([Random numbers](random-numbers.md)); `2012-philox-he` is the
default of `mobcal run` and of the window's first launch. `2000-he` is the calculation of the
Jarrold group's 2000 helium release ([Reproducing MOBCAL 2000](mobcal-2000.md)), which has no
nitrogen form.

In the window, choosing a method fills every field of the form, and a field changed afterwards
makes the method *Custom* ([The window](window.md#method-basics-and-advanced)). From a terminal,

```
mobcal run choline.mfj
mobcal run choline.mfj --method 2012-n2
```

runs choline under `2012-philox-he`, then under the 2012 release's nitrogen calculation. A
table, generator or setting given beside `--method` replaces that one value, and the run records
`custom`, or the shipped method its values make: `--method 2012-he --rng philox` is a
`2012-philox-he` run. The shipped methods carry no seed, and a run of one starts at the 2012
seed, 5013489, unless `--seeds` gives others.

## Method files

To keep a calculation of one's own, write its method to a file. File ▸ Save method… in the
window writes the gas, element table, generator and six settings the form holds, and asks for
the name the Method list will show; File ▸ Load method… adds a file written by hand or on
another computer. Either way the file joins the Method list under its name, the list remembers
it at the next launch, and `mobcal run --method PATH` runs the same file.

A method file is JSON, named `NAME.method.json`, and Save method gives that ending to whatever
name is typed. The five shipped methods are files of the same form, under
`src/mobcal/methods/` in the source code. The format is named `ccs-method`, for the collision
cross section a calculation gives rather than for this program, and this page specifies version
1. A method file of one's own reads, with the element table shortened here to its first row,

```json
{
  "format": "ccs-method",
  "version": 1,
  "name": "Choline at 298.15 K",
  "description": "The 2012 helium calculation at the temperature of our drift tube.",
  "gas": "He",
  "temperature": {"value": 298.15, "unit": "K"},
  "mobcal": {
    "generator": "philox",
    "imp": 1000,
    "itn": 10,
    "inp": 40,
    "inum": 250000,
    "inor": 30,
    "parameters": {
      "format": 1,
      "name": "MOBCAL 2012 helium",
      "sha256": "6e19c7ce13dbff2035bac9c762226db61316e706b23f52f2336028af76da18f0",
      "rows_sha256": "7717e975d73f1c828a42958672273c0403cd2e64c27845f4c08e321e9d445f31",
      "shipped": true,
      "gas": "He",
      "form": "pair",
      "kinds": {"mass": "double", "epsilon": "double", "sigma": "double", "rhs": "double"},
      "element": [
        {"key": 1, "symbol": "H", "mass": "1.008d0", "epsilon": "0.6175d-03",
         "sigma": "2.2610d0", "rhs": "2.2d0", "status": "fitted", "rhs_status": "own",
         "provenance": "epsilon an average of ab initio values; sigma fitted to ..."},
        ...
      ]
    }
  }
}
```

The file has two parts. The **core**, every key but `mobcal`, is what a method of any program
that computes cross sections has: the format and its version, the name, a description, the gas
by formula (`He` or `N2`), the temperature in kelvin, and a seed. The **`mobcal` block** holds
what only this program's calculation has: the random number generator (`philox` or `ranlux`),
the five sampling counts and the element table. `format` and `version` come first, and a file
of another format or version is refused for that alone, so a later version of the format cannot
be misread as this one. Every key is required except `description` and `seed`, in the core and
in the block alike, and a key the file does not know is refused by name. A method whose only
block is named for another program is refused by that program's name, since MOBCAL runs a
method with a `mobcal` block. The counts are integers and are written as integers, `1000` and
never `1000.0` or `1e3`. A key written twice in the file is refused rather than read as either
of its values, and so are `NaN` and `Infinity`, which are not JSON numbers, as for the ion file
([The ion file](ion-file.md)).

`description` is optional, a sentence or two on what the method is. The Method list shows it as
the method's tooltip, and each shipped method carries one, on where the method comes from.
Save method writes the description of the method file the form came from, and none for a shipped
method, whose description says what that method is. The description is not one of the fields
that identify a method: two files that differ only in their descriptions make the same runs.

`seed` is optional too, a positive integer up to 2147483647, such as `"seed": 42`. A run of a
method that carries a seed starts there: `mobcal run --method PATH` runs at that seed, and the
window's seeds per ion count up from it (42, 43, 44 for three). `--seeds` on the command line
wins over the method's seed, and the run is still a run of the method, since the seed is not one
of the fields that identify it. A file without `seed` starts at 5013489, as the shipped methods
do. Save method writes the seed only when the method the form came from carries one, and then
writes that seed. The name is 1 to 60 characters and must differ from the shipped methods' names
and from every other file in the list.

### The element table in a method

`parameters` is the element table itself, carried whole, whether it is one of the shipped
tables or a table of one's own. It is the content of the table's TOML file written as JSON, key
for key and in the same order, every value a string that holds the Fortran literal as the TOML
file does ([The element tables](parameters.md)), with three keys of its own:

| Key | Value |
|---|---|
| `sha256` | the SHA-256 of the TOML file the rows were taken from |
| `rows_sha256` | the SHA-256 of the table the program reads, `parameters.tab`, from its second line on |
| `shipped` | `true` when `sha256` is that of one of the gas's shipped tables |

The table rendered from a method is the table rendered from its TOML file, byte for byte, since
its first line carries the TOML file's SHA-256 and every other line is written from the same
strings ([The table inside a method](parameters.md#the-table-inside-a-method)). Loading a method
checks its rows against `rows_sha256`, and a table marked `shipped` against the shipped file,
field for field, and refuses a method that fails either check, naming the element and the field
where a shipped table differs. Save method writes the table from its TOML file as the file is at
the time of saving, so a method file runs on any computer with no other file present, and
moving, editing or deleting the TOML file afterwards changes nothing about the method. To change
a table, edit the TOML file and save the method again; rows edited in the method file itself no
longer hash to `rows_sha256` and are refused.

The window keeps its list of method files by path and SHA-256: a remembered file that has been
moved, deleted or edited since it was added is removed from the list at the next launch, with a
message that names it and says why, and loading it again adds it as it is now. A method that
carries a table of one's own shows it in the Element table field as the table's name followed by
*(in the method)*.

Before 2.1.0 this format was written under the name `mobcal-method`, by development versions
only, and no release wrote it. Such a file named its table by name or by path rather than
carrying its rows, and it is refused with a message to load a shipped method, set the fields
again and save it. Version 2.0 wrote method files in TOML, `NAME.toml`, and this version refuses
a TOML method file with a message that says a method file is now `NAME.method.json`; a window
that remembered one removes it from the list at the next launch with that message. The element
tables stay TOML files, since each of their values is a Fortran literal kept as a string beside
a note on where it came from, and a method carries the table it was saved with.

The format is also published as a JSON Schema,
[`src/mobcal/methods/method.schema.json`](../src/mobcal/methods/method.schema.json), for other
programs and for editors that check a file as it is typed. The schema checks every key, its type
and its bounds, the element table's included. Loading a method also checks what the schema
cannot express, i.e., that the table's rows hash to `rows_sha256` and a shipped table equals its
file, that no element key appears twice, that no other method in the list has the name, that
`itn` × `inp` × `imp` is at most 9,999,999, and that every character of the name is printable,
along with the three rules of reading above: integers written as integers, no key twice, and no
`NaN` or `Infinity`. In VS Code, a `json.schemas` entry in the settings that maps the file
pattern `*.method.json` to the schema checks every method file as it is typed, without a line
in the file itself:

```json
"json.schemas": [
  {"fileMatch": ["*.method.json"], "url": "./src/mobcal/methods/method.schema.json"}
]
```

### For developers of other codes

A program other than MOBCAL writes the same core with one block of its own, named for the
program, the way MOBCAL writes `mobcal`, and publishes a schema for that block. A reader of the
core reads the name, the gas, the temperature and the seed from any program's method and skips
a block it does not know. The keys of the core change only with the version number. A result
file records the method of its run as a document of this format ([The
method](result-file.md#the-method)), so that the calculation behind a cross section travels with
it.

## What a run records

Every run directory's `record.json` names the method in `method`: a shipped method's key, the
name of the method file, or `custom` when an option given beside the method changed it. A run
from a method file also records the file in `method_file`, its path and its SHA-256, which is
`null` for the other runs. `summary.csv` and `summary.json` carry the same, and the methods
paragraph (`mobcal methods-text`, the window's Copy methods text) names the method. The record
does not depend on the method file to say what the method was: the gas, the generator, the
seed, the element table by name and SHA-256 (with its path when the run read a TOML file)
and the six settings are each in it, so a run stays described after its method file is
moved, edited or deleted. Run
directories are named for the input, the gas, the seed, the generator when it is RANLUX, the
table when it is not the gas's 2012 table, and each setting that differs from 2012
(`choline-he-5013486-ranlux-lj2000-t298-imp25`), never for the method, so the same calculation
lands in the same directory whichever way it was asked for.

To carry a run's method outside its directory, use the run's result file, `NAME.result.json`
beside `record.json` ([The result file](result-file.md)). It holds the method as a method
document whatever the run was made from: a shipped method's file, a method file of one's own, or,
for a run made `custom`, the method its gas, table, generator and settings make, with the method
it was made from and the values that differ. Written to a file, that document is a method that
makes the run's calculation again, and `mobcal unpack` writes it, beside the ion
([Reading it back](result-file.md#reading-it-back)).

Runs made before methods carried their gas recorded `current`, `2012` or `2000`. These are read
as `2012-philox-he` or `2012-philox-n2`, as `2012-he` or `2012-n2`, and as `2000-he`, by the gas
of the run, so a folder holding runs from both versions gives one methods paragraph. A queue the
window saved before this change, in which one batch ran both gases, comes back as one batch for
each gas.
