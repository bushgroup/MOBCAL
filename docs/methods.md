# Methods

A method is everything a calculation depends on except its input: the buffer gas, the element
table, the random number generator, and the six run settings, i.e., the temperature and the five
sampling counts ([The run settings](settings.md)). A method file other than a shipped one may
also carry a seed. **Method** in the window and `mobcal run --method` choose a method, and every
run records the method it used, so a cross section can be traced to the calculation that gave
it. A batch runs one method, and so one gas; helium and nitrogen are two batches, which the queue
of the window or two commands run one after the other.

## The five shipped methods

| Key | Name in the window | Gas | Element table | Generator | Settings |
|---|---|---|---|---|---|
| `2012-he` | **MOBCAL 2012 (He)** | helium | 2012 | RANLUX | 2012 |
| `2012-n2` | **MOBCAL 2012 (N2)** | nitrogen | 2012 | RANLUX | 2012 |
| `2012-philox-he` | **MOBCAL 2012 with Philox (He)** | helium | 2012 | Philox4x32-10 | 2012 |
| `2012-philox-n2` | **MOBCAL 2012 with Philox (N2)** | nitrogen | 2012 | Philox4x32-10 | 2012 |
| `2000-he` | **MOBCAL 2000 (He)** | helium | 2000 | RANLUX | 298 K, `imp` 25 |

The 2012 settings are 301 K, `imp` 1,000, `itn` 10, `inp` 40, `inum` 250,000, and `inor` 30.
`2012-he` and `2012-n2` are the calculation of the 2012 release, which at the 2012 seed
reproduces its outputs ([Reproducing MOBCAL 2012](mobcal-2012.md)). `2012-philox-he` and
`2012-philox-n2` are the same tables and settings under Philox4x32-10, under which a divided
run, i.e., one calculation run as several processes, equals the serial run by construction
([Random numbers](random-numbers.md)); `2012-philox-he` is the default of `mobcal run` and of
the first launch of the window. `2000-he` is the calculation of the 2000 helium release of the
Jarrold group ([Reproducing MOBCAL 2000](mobcal-2000.md)), which has no nitrogen form.

In the window, choosing a method fills every field of the form, and a field changed afterwards
shows the method as Custom ([The window](window.md#method-basics-and-advanced)). From a terminal,

```
mobcal run choline.mfj
mobcal run choline.mfj --method 2012-n2
```

runs choline under `2012-philox-he`, then under the nitrogen calculation of the 2012 release. A
table, generator, or setting given beside `--method` replaces that one value, and the run records
`custom`, or the shipped method its values make: `--method 2012-he --rng philox` is a
`2012-philox-he` run. The shipped methods carry no seed, so a run of one starts at the 2012 seed,
5013489, unless `--seeds` gives others ([The seed](random-numbers.md#the-seed)).

## Method files

To keep a calculation that no shipped method gives, write its method to a file. **File ▸ Save
method…** in the window writes the gas, the element table, the generator, and the six settings
the form holds, and asks for the name the list will show. **File ▸ Load method…** adds a file
written by hand or on another computer. Either way the file joins the list of **Method** under
its name, and `mobcal run --method PATH` runs the same file. The window keeps its list of method
files by path and SHA-256: a remembered file that has been moved, deleted, or edited since it
was added is removed from the list at the next launch, with a message that names it and says
why, and loading it again adds it as it is now.

A method file is JSON, named `NAME.method.json`, and **File ▸ Save method…** gives that ending
to whatever name is typed. The five shipped methods are files of the same form, under
`src/mobcal/methods/` in the source code. The format is named `ccs-method`, for the collision
cross section a calculation gives rather than for this program, and this page specifies version
1. A method saved from **MOBCAL 2012 with Philox (He)** with the temperature changed reads as
follows, with a description added by hand, the lines of the temperature joined, and the element
table shortened to its first row:

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

The file has two parts. The core, every key but `mobcal`, is what a method of any program that
computes cross sections has: the format and its version, the name, a description, the gas by
formula (`He` or `N2`), the temperature in kelvin, and a seed. The `mobcal` block holds what
only the calculation of this program has: the random number generator (`philox` or `ranlux`),
the five sampling counts, and the element table. Every key is required except `description` and
`seed`, in the core and in the block alike, and a key the format does not have is refused by
name.

A file is read strictly, so that nothing in it is taken for something else. `format` and
`version` are checked first, and a file of another format or version is refused for that alone,
so a later version of the format cannot be misread as this one. A method whose only block is
named for another program is refused with a message that names that program, since MOBCAL runs
a method with a `mobcal` block. The counts are integers and are written as integers, `1000` and
never `1000.0` or `1e3`. A key written twice in the file is refused rather than read as either
of its values, and so are `NaN` and `Infinity`, which are not JSON numbers, as for the ion file
([The ion file](ion-file.md)).

The name is 1 to 60 printable characters with no space at either end. A run records a method
file by its name, and the methods text describes a shipped method by its key, so a method file
of your own may not carry the name or the key of a shipped method, such as `MOBCAL 2012 (He)` or
`2012-he`, nor `custom`, which a record gives to settings that no method gives; letter case does
not count. `mobcal run --method PATH`, **File ▸ Load method…**, and **File ▸ Save method…**
refuse such a file with the same message, whatever its values. A file that equals the shipped
method in every field that identifies a method is refused too, and the message says that the
shipped method makes the same runs. The window also refuses a file whose name another file in
its list carries.

`description` is optional, a sentence or two on what the method is. The list of **Method** shows
it as the tooltip of the method, and each shipped method carries one, on where the method comes
from. **File ▸ Save method…** writes the description of the method file the form came from, and
none for a shipped method, whose description says what that method is. The description is not
one of the fields that identify a method: two files that differ only in their descriptions make
the same runs.

`seed` is optional too, a positive integer up to 2147483647, such as `"seed": 42`. A run of a
method that carries a seed starts there unless `--seeds` gives others, and a file without `seed`
starts at 5013489, as the shipped methods do ([The seed](random-numbers.md#the-seed)). **File ▸
Save method…** writes the seed only when the method the form came from carries one, and then
writes that seed. Like the description, the seed is not one of the fields that identify a
method.

### The element table in a method

`parameters` is the element table itself, carried whole, whether it is one of the shipped
tables or any other, so that a method, and the result file that records a run of it, runs on a
computer that has never seen the TOML file of the table. It is the content of the TOML file
written as JSON, key for key and in the same order, with the provenance of each row included,
the comments of the file left out, and, for nitrogen, the four constants under `combining`
([The element tables](parameters.md)). Every number stays a string that holds the Fortran
literal, for the reason it is a string in the TOML file: the program converts the literal
itself, by the kind of its column, whereas a JSON number would be read and written back as a
double by every tool that touched it. The two expressions stay expressions. The table has three
keys of its own:

| Key | Value |
|---|---|
| `sha256` | the SHA-256 of the TOML file the rows were taken from |
| `rows_sha256` | the SHA-256 of the table the program reads, `parameters.tab`, from its second line on, i.e., of every byte the program converts |
| `shipped` | `true` when `sha256` is that of one of the shipped tables for the gas |

The table rendered from a method is the table rendered from its TOML file, byte for byte, since
its first line carries the SHA-256 of the TOML file, which the carried table keeps, and every
other line is written from the same strings. The name of the run directory, the table hash in
the record, and the method a run is identified as are therefore the same whichever of the two
the table came from, and the test suite holds the rendering of each shipped table from its file
and from its method to the same bytes.

Loading a method checks its rows against `rows_sha256`, and a table marked `shipped` against the
shipped file, field for field, and refuses a method that fails either check, naming the element
and the field where a shipped table differs. **File ▸ Save method…** writes the table from its
TOML file as the file is at the time of saving, so a method file runs on any computer with no
other file present, and moving, editing, or deleting the TOML file afterwards changes nothing
about the method. A method that carries a table other than a shipped one shows it in **Element
table** as the name of the table followed by "(in the method)". To change a table, edit the TOML
file and save the method again; rows edited in the method file itself no longer hash to
`rows_sha256` and are refused.

### The schema

The format is also published as a JSON Schema,
[`src/mobcal/methods/method.schema.json`](../src/mobcal/methods/method.schema.json), for other
programs and for editors that check a file as it is typed. The schema checks every key, its type,
and its bounds, those of the element table included. Loading a method also checks what the
schema cannot express:

- of the element table, that every number is spelled with the kind its column declares and is
  greater than zero, that only the two expressions of the 2012 source hold an operator, that no
  element key appears twice, that the rows hash to `rows_sha256`, and that `shipped` is `true`
  exactly when `sha256` is that of a shipped table, which the table must then equal;
- of the settings, that the temperature is finite and that `itn` × `inp` × `imp` is at most
  9,999,999;
- of the name, that every character is printable and that the name is not the name or the key
  of a shipped method, nor `custom`, in any letter case;
- and the three rules of reading above: integers written as integers, no key twice, and no `NaN`
  or `Infinity`.

In VS Code, a `json.schemas` entry in the settings that maps the file pattern `*.method.json` to
the schema checks every method file as it is typed, without a line in the file itself:

```json
"json.schemas": [
  {"fileMatch": ["*.method.json"], "url": "./src/mobcal/methods/method.schema.json"}
]
```

### For developers of other codes

A program other than MOBCAL writes the same core with one block of its own, named for the
program, the way MOBCAL writes `mobcal`, and publishes a schema for that block. A reader of the
core reads the name, the gas, the temperature, and the seed from the method of any program and
skips a block it does not know. The keys of the core change only with the version number. A
result file records the method of its run as a document of this format ([The
method](result-file.md#the-method)), so that the calculation behind a cross section travels with
it.

## What a run records

In every run directory, `record.json` names the method in `method`: the key of a shipped method,
the name of the method file, or `custom` for a run whose values, changed beside its method, are
those of no shipped method. A run from a method file also records the file in `method_file`, its path and its
SHA-256, which is `null` for the other runs. `summary.json` carries both, `summary.csv` carries
the method, and the methods paragraph (`mobcal methods-text`, **Copy methods text** in the
window) names it. The record does not depend on the method file to say what the method was, and
a run directory is never named for its method ([The results folder](results-folder.md)).

To carry the method of a run outside the run directory, use its result file, `NAME.result.json`
beside `record.json` ([The result file](result-file.md)). It holds the method as a method
document whatever the run was made from: the file of a shipped method, any other method file, or,
for a run made `custom`, the method its gas, table, generator, and settings make, with the method
it was made from and the values that differ. Written to a file, that document is a method that
makes the calculation of the run again, and `mobcal unpack` writes it, beside the ion
([Reading it back](result-file.md#reading-it-back)).
