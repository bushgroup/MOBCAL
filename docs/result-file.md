# The result file

A result file holds one calculation of the collision cross section of an ion: the program that
ran it, both of its inputs, the gas, the temperature, the seed, how the run ended, and every
value the program reported, each with its unit. MOBCAL writes one into every run directory as
`NAME.result.json`, beside `record.json` and `mobcal.out`, where NAME is the name of the run
directory. Its format is named `ccs-result`, for the collision cross section it reports rather
than for this program, and this page specifies version 1. A result file is written to be read
without MOBCAL: it is JSON, its keys say what they hold, and a copy of it sent to a colleague
carries what the calculation was and what it gave.

The format has two layers. The core, every top-level key but one, holds what any ion-mobility
program can report, so that a reader can take cross sections from MOBCAL and from another
program by the same keys. The `mobcal` block holds what only MOBCAL reports, such as the
inverse mobilities and the trajectory parameters the program prints. A program other than
MOBCAL writes the core and a block of its own ([For developers of other
codes](#for-developers-of-other-codes)).

Version 1 is frozen. Every later version of MOBCAL reads a version 1 file as this page
describes it, and a change to what the file holds will be a new version number.

The result file adds to the run directory and replaces nothing in it. `mobcal.out` is the output
of the program itself and stays the evidence for every number, and `record.json` stays the
record the driver keeps of the run, which the window and the batch summaries read ([The results
folder](results-folder.md)). Every value of the result file that the program printed is read
from `mobcal.out` as printed, and none is computed by the Python layer of MOBCAL.

## An example

To show the document whole, the choline cation of the 2012 release (`fortran/Choline.mfj`,
21 atoms, one conformer) was run under `2012-he`, the 2012 helium calculation, at the 2012 seed,
which reproduces the three cross sections of the 2012 reference output (PA 61.075, EHS 63.473,
and TM 55.402 Å²). Its result file reads as follows, with the embedded ion document, the build
entry, the element table, and the lines of the SUMMARY shortened here:

```json
{
  "format": "ccs-result",
  "version": 1,
  "status": "ok",
  "message": null,
  "software": {
    "name": "mobcal",
    "version": "2.0.1.dev0",
    "commit": "91d07b245eda6df039edd7ab24ef1be768ffd911",
    "build": {"source": "mobcal_He.f", "source_sha256": "0f267d9b...", "sha256": "2eba4251...",
              "compiler": "GNU Fortran (Rev6, Built by MSYS2 project) 16.2.0",
              "flags": ["-O3", "-fno-automatic", "-std=legacy", "-static"], ...}
  },
  "started": "2026-11-05T07:38:40-08:00",
  "finished": "2026-11-05T07:41:34-08:00",
  "seconds": 174.09,
  "gas": "He",
  "temperature": {"value": 301, "unit": "K"},
  "seed": 5013489,
  "inputs": {
    "ion": {
      "format": "ccs-ion",
      "file": {"name": "Choline.mfj", "sha256": "a4cf1c4a..."},
      "converted_from": "mfj",
      "embedded": true,
      "document": {"format": "ccs-ion", "version": 1, "label": "Choline_631G++dp_pop", ...}
    },
    "method": {
      "format": "ccs-method",
      "source": "shipped",
      "name": "2012-he",
      "file": {"name": "2012-he.method.json", "sha256": "..."},
      "from": null,
      "overrides": {},
      "embedded": true,
      "document": {
        "format": "ccs-method",
        "version": 1,
        "name": "MOBCAL 2012 (He)",
        "description": "The calculation of the 2012 release in helium: ...",
        "gas": "He",
        "temperature": {"value": 301, "unit": "K"},
        "mobcal": {
          "generator": "ranlux",
          "imp": 1000,
          "itn": 10,
          "inp": 40,
          "inum": 250000,
          "inor": 30,
          "parameters": {"format": 1, "name": "MOBCAL 2012 helium", "sha256": "6e19c7ce...",
                         "rows_sha256": "7717e975...", "shipped": true, ...}
        }
      }
    }
  },
  "results": {
    "cross_sections": {
      "PA": {"value": 61.075, "unit": "angstrom^2"},
      "EHS": {"value": 63.473, "unit": "angstrom^2"},
      "TM": {"value": 55.402, "unit": "angstrom^2",
             "standard_deviation": {"value": 0.92127, "unit": "percent"}}
    },
    "conformers": [
      {"set": 1,
       "PA": {"value": 61.075, "unit": "angstrom^2"},
       "EHS": {"value": 63.473, "unit": "angstrom^2"},
       "TM": {"value": 55.402, "unit": "angstrom^2",
              "standard_deviation": {"value": 0.92127, "unit": "percent"}}}
    ],
    "trajectories": {"total": 400000, "failed": 3}
  },
  "mobcal": {
    "generator": "ranlux",
    "split": null,
    "settings": {"temperature": 301, "imp": 1000, "itn": 10, "inp": 40, "inum": 250000,
                 "inor": 30},
    "parameters": {"name": "MOBCAL 2012 helium", "sha256": "6e19c7ce...", "shipped": true},
    "staged_input": {"name": "Choline.mfj", "sha256": "a4cf1c4a..."},
    "files": {"output": "mobcal.out", "record": "record.json", "console_log": "stdout.log"},
    "summary": {
      "program_version": "junkn.f",
      "input_file_name": "Choline.mfj",
      "input_label": "Choline_631G++dp_pop",
      "hard_sphere": {"trajectories": 250000, "minimum_reflections": null,
                      "maximum_reflections": 4},
      "trajectory_parameters": {"sw1": 5e-05, "sw2": 0.005, "dtsf1": 0.5, "dtsf2": 0.1},
      "inverse_mobilities": {
        "PA": {"value": 1123.9, "unit": "V s m^-2"},
        "EHS": {"value": 1168.0, "unit": "V s m^-2"},
        "TM": {"value": 1019.5, "unit": "V s m^-2"}
      },
      "asymmetry_parameter": 1.2982,
      "conformers": [
        {"set": 1, "inverse_mobilities": {...}, "asymmetry_parameter": 1.2982}
      ],
      "lines": [" SUMMARY", "", " program version = junkn.f", ...]
    }
  }
}
```

The whole document is 15.8 kB, of which the ion entry is 5.0 kB, the method entry 5.2 kB, most
of it the element table, and the `mobcal` block 3.3 kB. The keys appear in the order this page
lists them, with two spaces of indent, LF line ends, and UTF-8, so two result files of the same
calculation can be compared line by line.

## The document

| Key | Value |
|---|---|
| `format` | `"ccs-result"` |
| `version` | `1` |
| `status` | `"ok"`, `"failed"`, or `"stopped"` |
| `message` | why the run did not end `ok`, with the exit status; `null` when it did |
| `software` | `name` (`"mobcal"`), `version`, `commit`, and `build`, the entry for the executable in the `build.json` written beside it when it was built |
| `started`, `finished` | ISO 8601 date and time to the second, with the offset from UTC |
| `seconds` | wall time of the program in seconds, of every process and the combining run for a divided run |
| `gas` | the buffer gas by formula, `"He"` or `"N2"` |
| `temperature` | `{"value": T, "unit": "K"}` |
| `seed` | the seed of the random number generator; `mobcal.generator` names the generator |
| `inputs` | `ion` and `method` ([The inputs](#the-inputs)) |
| `results` | what the program reported ([The results](#the-results)), or `null` |
| `mobcal` | what only MOBCAL reports ([The mobcal block](#the-mobcal-block)) |

`status` is `ok` when the program completed and printed its SUMMARY block, `failed` when it did
not, and `stopped` when the user ended the run, from the window or the command line, before it
completed. `commit` is the commit the installed program was packaged from or, in a source
checkout, the commit checked out. It is 40 hexadecimal digits, with `-dirty` when the tree held
changes no commit holds, or `null` where MOBCAL does not know it. `build.commit` is the commit
the Fortran executable was built from, which is the same commit unless the executable was built
earlier and kept. `build` is `null` for an executable with no `build.json` beside it.

## The inputs

Three things decide what a calculation computes: the ion, the method ([Methods](methods.md)),
and the seed ([The seed](random-numbers.md#the-seed)). The seed is a top-level key, and `inputs`
carries the other two, each as an entry that names its file by name and SHA-256 and, by default,
carries the document of that file whole. Paths are not recorded, since a result file is meant to
travel and the path of a file on the computer that ran it says nothing to the computer that
reads it; `record.json` keeps them.

### The ion

| Key | Value |
|---|---|
| `format` | `"ccs-ion"`, the format of `document` |
| `file` | `name` and `sha256` of the input file as given to the run |
| `converted_from` | `"mfj"` when the input was a `.mfj`; `null` for an ion file |
| `embedded` | `true` when `document` carries the ion, `false` when it is recorded by `file` alone |
| `document` | the ion document ([The ion file](ion-file.md)), or `null` when `embedded` is `false` |

An ion file is embedded as the document it holds. The SHA-256 is of the bytes of the file and
identifies the file the run read; the embedded document is the same JSON value as that file, not
the same bytes. A `.mfj` input is embedded as the ion document that reading it gives ([Reading a
`.mfj` into an ion file](ion-file.md#reading-a-mfj-into-an-ion-file)), with `converted_from` set
to `mfj`. That conversion keeps everything the program reads, so the `.mfj` written back from
the embedded document gives the program the same input, and `file.sha256` remains the hash of
the `.mfj` itself.

To keep result files small when the geometries are kept elsewhere, as in a study of thousands
of frames from a molecular dynamics trajectory, a run records the ion by its file alone:

```
mobcal run frames/*.ion.json --result-ion reference
```

The window has the same choice as a check box below the results folder, **Keep the ion in each
result file**, checked by default ([The window](window.md#the-results-folder)), and a queued
batch keeps the choice it was added with. A referenced ion has `embedded` set to `false` and
`document` set to `null`, and the name and SHA-256 of the file identify which file the
calculation read. MOBCAL never chooses between the two by the size of the ion, so the shape of a
file follows from the option, with one exception. A `.mfj` holding an element key that no
shipped element table defines cannot be read into an ion document, since the element of each
atom is named from those tables, so it is recorded by its file alone, with `embedded` set to
`false`, whatever the option says.

### The method

| Key | Value |
|---|---|
| `format` | `"ccs-method"`, the format of `document` |
| `source` | `"shipped"`, `"file"`, or `"custom"` |
| `name` | what `method` in `record.json` says: the key of a shipped method, the name of a method file, or `custom` |
| `file` | `name` and `sha256` of the method file, for `shipped` and `file`; `null` for `custom` |
| `from` | for `custom`, the method the changed values were given beside, by key or name, or `null` when none was; `null` otherwise |
| `overrides` | for `custom`, each value of the method document that differs from that of the `from` method, with the value of the run, keyed `temperature` for a value of the core and by dotted path for a value of the `mobcal` block (`mobcal.imp`, `mobcal.parameters`); `{}` otherwise |
| `embedded` | always `true` |
| `document` | the method of the run as a method document ([Method files](methods.md#method-files)) |

The method is always embedded, whatever the ion option, because the method of a run is otherwise
hard to recover: a run made `custom` by `--temperature 298` beside `--method 2012-he` has no
method file at all. For `shipped` and `file`, `document` is the document of the method file as
it was at the run, and `file.sha256` the hash of that file. For `custom`, `document` is the
method that the gas, element table, generator, and six settings of the run make, written as
**File ▸ Save method…** would write it under the name `Custom`. Every method document carries
its element table whole ([The element table in a
method](methods.md#the-element-table-in-a-method)), a few kilobytes, so a run made with
`--parameters` and a table of your own reruns from the result file on a computer without the
TOML file of that table. `seed` appears in `document` only when the method file carried one; the
seed of the run itself is the top-level `seed`, which `--seeds` may have set apart from the seed
of the method. Every embedded method document is a valid method document of `ccs-method`
version 1, so the method of any run can be written back to a file and run again.

## The results

`results` is `null` exactly when the output holds no SUMMARY block, as for every `stopped`
run. Otherwise:

| Key | Value |
|---|---|
| `cross_sections` | the cross sections of the run, each the mean over conformers, keyed by method |
| `conformers` | one entry per conformer in the order of the input: `set`, its number counted from 1, and the cross sections of that conformer, keyed as `cross_sections` is |
| `trajectories` | `total`, the product itn × inp × imp of the trajectory method, and `failed`, those the program counted as failed |

The methods are `PA`, the projection approximation, `EHS`, the exact hard-sphere scattering,
and `TM`, the trajectory method. The helium program reports all three, and the nitrogen
program reports `TM` only, having no hard-sphere pass. Each cross section is
`{"value": Ω, "unit": "angstrom^2"}`, with Ω as printed: the program prints five significant
digits, `6.1075E+01`, and the file holds `61.075`, never a value rounded or extended from it.
For one conformer, `TM` adds `standard_deviation`, `{"value": s, "unit": "percent"}`, the
standard deviation of the values of Ω*(1,1) over the itn cycles as a percentage of their mean,
which the program prints as `standard deviation (percent)`. For several conformers, which the
output calls coordinate sets, the program prints no standard deviation, and the key is absent.
A run of one conformer has one entry in `conformers`, equal to `cross_sections`, so that a
reader takes the values of each conformer from the same place for one and for a hundred.

Note that `failed` counts trajectories the program abandoned, not a run that failed: the 2012
choline reference abandoned 3 of 400,000 and its cross section is the reference value.

## The mobcal block

`mobcal` holds what the program and the MOBCAL driver report beyond the core:

| Key | Value |
|---|---|
| `generator` | `"ranlux"` or `"philox"` ([Random numbers](random-numbers.md)) |
| `split` | W, the processes the calculation was divided among, or `null` for a serial run |
| `settings` | the six run settings, `temperature`, `imp`, `itn`, `inp`, `inum`, `inor` ([The run settings](settings.md)) |
| `parameters` | the element table: `name`, `sha256` of the file, `shipped` ([The element tables](parameters.md)) |
| `staged_input` | `name` and `sha256` of the `.mfj` the program read, as named in the run directory |
| `files` | the names, within the run directory, of the program output (`output`), the run record (`record`), and the program console output (`console_log`) |
| `summary` | everything else the SUMMARY block prints, typed (below), or `null` exactly when `results` is |

`staged_input` is the file the program read. For a `.mfj` input it is the bytes of the input
itself, and for an ion file it is the `.mfj` written from it for the table and gas of the run, so
its hash changes with the table where the hash of the ion file does not.

| Key of `summary` | Value |
|---|---|
| `program_version` | the `program version` line, `junkn.f` in every output |
| `input_file_name`, `input_label` | the name and label of the input as the program read them |
| `hard_sphere` | the MOBIL4 pass of the helium program: `trajectories` (inum), `maximum_reflections`, and `minimum_reflections` for several conformers (`null` for one, where the program prints the maximum only); `null` in nitrogen |
| `trajectory_parameters` | `sw1`, `sw2`, `dtsf1`, `dtsf2`, as printed |
| `inverse_mobilities` | the inverse mobility of each method `cross_sections` names, `{"value": 1/K0, "unit": "V s m^-2"}`: of the average for one conformer, and the `AVGE` row, the inverse of the mean mobility, for several |
| `asymmetry_parameter` | the structural asymmetry parameter of the one conformer, or the mean over conformers; `null` in nitrogen for several, where the SUMMARY prints none |
| `conformers` | one entry per conformer, in the order of `results.conformers`: `set`, `inverse_mobilities`, `asymmetry_parameter` |
| `lines` | the SUMMARY block as printed, from the line `SUMMARY` to the end of the output, one string per line with the end-of-line CR removed |

The inverse mobilities are in the `mobcal` block, not the core, because their conditions are
those of the program itself. The program computes a reduced mobility K0 with one elementary
charge whatever the charge of the ion, at the number density of a gas at 273.15 K and
101,325 Pa, and prints 1/K0 in V s m⁻²: the TM value of 1019.5 V s m⁻² for choline is a K0 of
9.81 × 10⁻⁴ m² V⁻¹ s⁻¹. A reader who wants the mobility of an ion of charge z divides 1/K0 by z,
or computes K0 from the cross section, its mass, and the gas by the Mason–Schamp equation;
MOBCAL does neither, so that every number in the file is one the program printed. `lines` keeps
the block verbatim, so a reader can check any typed value against the text it came from without
opening `mobcal.out`.

## Units

Every physical quantity in the core and in `inverse_mobilities` is an object of a `value` and a
`unit`, and every unit string is fixed per key in version 1:

| Quantity | Unit string |
|---|---|
| temperature | `K` |
| cross section | `angstrom^2` |
| standard deviation of a cross section | `percent` |
| inverse reduced mobility | `V s m^-2` |

A reader may assert the unit it expects and refuse a file that differs, rather than convert. A
later version may allow other units under a key, and will say so with its version number. The
counts (`seed`, `trajectories`, the settings) and the trajectory parameters, which are
dimensionless or carry the internal units of the program itself, are bare numbers.

## A run that does not end ok

A result file is written for every run that got as far as its directory, in the same step as
`record.json`, whether it ended `ok`, `failed`, or `stopped`. A run that MOBCAL refused before
the program started, for an input it could not read or an element the table lacks, makes no
directory, and neither does a run that a stopped or paused batch never started; the
`summary.csv` and `summary.json` of the batch report it. For a run without a SUMMARY block,
`results` and `mobcal.summary` are `null`, `message` says why, and every other key is filled, so
the result file of a stopped run still says what was being calculated and holds both inputs. A
failure to write the result file is reported with the run and leaves `record.json` as it is.

## Reading it back

Because a result file holds both inputs, the calculation can be run again from the result file
alone. `ccs-result unpack` writes the ion and the method back as files, gives the seed of the
run, and prints the command that runs them at that seed. The command is named for the format,
as the format is named for the quantity and not the program:

```
ccs-result unpack Choline-he-5013489-ranlux.result.json -o again
```

For the choline example above, the command writes `again/Choline.ion.json` and
`again/2012-he.method.json`, gives the seed on a line of its own after the two files,

```
seed: 5013489, the seed of the run, which the command below passes as --seeds
```

and ends with the following, in which Windows prints each path with a backslash:

```
to run it again:
  mobcal run again/Choline.ion.json --method 2012-he --seeds 5013489
```

The ion file is named for the input of the run, `X.ion.json` for an ion file of that name or for
a `.mfj` named `X.mfj`, so that the run of it lands in a run directory of the same name as the
original. The method file takes the name of the file the method came from, `2012-he.method.json`
for a shipped method and the name of the file itself for a method file of your own. A `custom`
run has no method file, and its method is written as `NAME.method.json` under the name NAME,
that of the result file, in place of `Custom`, so that the methods of several custom runs can be
loaded side by side. The command names a shipped method by its key when the values of the method
are those of the shipped method that the run recorded, or whose name the method carries, and the
written file otherwise. A result file made under a shipped method of another version, whose file
differs from the one this version ships in its description alone, therefore runs again under the
key. A method file of your own that carried the name of a shipped method with other values,
which `mobcal run` now refuses ([Methods](methods.md#method-files)), is written under the name of
its file without `.method.json`, or under the name of the result file when that is the name of a
shipped method too, and `unpack` says so. It adds
`--split W` for a run that was divided among W processes, which gives the same numbers as a run
in one process.

Each file is checked as it is written, and `unpack` says what each check found:

- The method written back has the bytes of the file the run was given, for every method file
  MOBCAL wrote and that `unpack` did not rename, and its SHA-256 is then the one the result
  records. Whatever its bytes, its gas,
  generator, element table, and six settings must be those the `mobcal` block records, and a
  result file in which they differ is refused.
- The ion file written back has the bytes of the file the run was given when MOBCAL wrote that
  file, by `ccs-ion import` or the window, and its SHA-256 is then the recorded one. An ion file
  laid out otherwise, by hand or by another program, is written back as the same document in
  the MOBCAL layout, with another SHA-256, and `unpack` reports both hashes.
- The input the program read is checked for an ion file: the `.mfj` the written ion file gives
  for the element table of the run must have the SHA-256 of `mobcal.staged_input`, and a result
  file for which it does not is refused. The table is the one the method carries, so the check
  needs no other file and runs for every ion file.

A run of a `.mfj` is written back as an ion file, since the result file holds the ion document
that reading the `.mfj` gives and not the `.mfj` itself, and `unpack` says so. The `.mfj` that
this ion file gives holds every value the program read from the original, which the program
reads as numbers and not as text, so the calculation is the same. It is laid out as MOBCAL
writes a `.mfj` (`1.0` where the 2012 choline input has `1.0000`, and wider columns), so its
SHA-256 is not the recorded one, which is that of the original `.mfj`. For the choline input of
the 2012 release, `ccs-result unpack` followed by the command it prints reproduces the cross
sections of the 2012 reference output to the last printed digit, and the tests check this on
every change to MOBCAL. A run made with a table of your own reruns the same way after its TOML file has
been deleted, into a run directory of the same name, with the same `parameters.tab` and the same
output file.

A result file that records its ion by reference holds no ion to write, and `unpack` refuses it,
naming the ion file by the name and SHA-256 the result records, so that the file can be found
and run with the method again. `unpack` also refuses a file of another format or version, and
it does not replace a file of the same name with other contents unless given `--force`. A
file already there with the same bytes is left as it is, so the results of several runs of one
ion can be unpacked into one folder.

`mobcal methods-text` reads result files as it reads run directories, so a methods paragraph
can be written for runs whose directories are not at hand:

```
mobcal methods-text results/*.result.json
```

A folder named on the command line may hold run directories, result files, or both. The
paragraph names the partial charges when the result file holds the ion and the ion file carried
its import record, as for a run directory.

## The schema

The machine-readable schema is
[`src/mobcal/io/result.schema.json`](../src/mobcal/io/result.schema.json) (JSON Schema, draft
2020-12), under the same `$id` pattern as the schemas of the ion file and the method file. An
installed copy of MOBCAL carries all three among its own files, under `mobcal/io/` and
`mobcal/methods/`, so a result file can be checked against the schemas of the version that
wrote it without the source code or a network. The schema refuses a key it does not define, a
unit string other than that of its key, a status that does not match its `message` and
`results`, and a nitrogen result with a cross section other than `TM`. The embedded ion and
method documents are checked by reference to the schemas of their own formats: the references
`ion.schema.json` and `../methods/method.schema.json` resolve, against the `$id` of this schema,
to exactly the `$id` of [`src/mobcal/io/ion.schema.json`](../src/mobcal/io/ion.schema.json)
and [`src/mobcal/methods/method.schema.json`](../src/mobcal/methods/method.schema.json), so a
validator given the three schemas checks a whole result file. The rules of those two formats
that a schema cannot express (the charge sum of an ion, the trajectory budget of a method) are
checked by MOBCAL when it reads an embedded document back, and a result file MOBCAL writes
satisfies them, since each embedded document is one MOBCAL read to make the run.

In VS Code, a `json.schemas` entry maps the file pattern to the schema:

```json
"json.schemas": [
  {"fileMatch": ["*.result.json"], "url": "./src/mobcal/io/result.schema.json"}
]
```

## For developers of other codes

The format is named for the quantity, not the program, so that another program computing
collision cross sections can write the same core. Its two inputs follow the same rule: the ion
file and the method file each have a core that any program can write
([The ion file](ion-file.md#for-developers-of-other-codes),
[Methods](methods.md#for-developers-of-other-codes)). The core is the top-level keys other than
`mobcal`: `format`, `version`, `status`, `message`, `software`, `started`, `finished`,
`seconds`, `gas`, `temperature`, `seed`, `inputs`, and `results`, with the meanings this page
gives them. To write a result file from another program,

1. fill `software.name` with the name of the program and `software.build` with whatever
   identifies its executable, or `null`;
2. give `seed` as `null` if the program has no seed, and `gas` by formula (`He`, `N2`, `Ar`,
   `CO2`);
3. give `inputs` the two entries `ion` and `method` that [The inputs](#the-inputs) describes,
   the ion as an ion document ([The ion file](ion-file.md#for-developers-of-other-codes)) and
   the method as a method document of the core and a block of the program
   ([Methods](methods.md#for-developers-of-other-codes)). A program that takes its method as
   values, from a run line or a command line, and not from a file, writes the method entry as
   `custom`, with `file` and `from` set to `null` and `overrides` to `{}`: a method of no file,
   made from the values of the run;
4. report under `results.cross_sections` the methods the program computes, by the keys `PA`,
   `EHS`, and `TM` where the method is one of these three, each in `angstrom^2`, and under
   `results.conformers` the same per structure. `standard_deviation` is the standard deviation
   of the values over cycles that [The results](#the-results) defines, and a program that
   reports another measure of uncertainty, such as an interval of the mean, puts it in its own
   block and leaves `standard_deviation` out;
5. put whatever else the program reports in one block named by `software.name`, the way MOBCAL
   uses `mobcal`, and publish a schema for it.

A reader of the core reads those keys from the file of any program and skips a block it does not
know. MOBCAL reads a result file of another program this way: it checks the core, reads the
embedded ion as it reads any ion file, checks the core of the embedded method, and skips the
block. `ccs-result unpack` and `mobcal methods-text` refuse such a file, naming the program that
wrote it, since both work from the `mobcal` block of a calculation MOBCAL ran.
`result.schema.json` is the schema of the file as MOBCAL writes it, with `software.name`, `gas`,
and the two inputs fixed to those of MOBCAL. Another program writes its own schema, which keeps
the keys, types, and unit strings of the core and replaces the `mobcal` block with its own. The
keys of the core change only with the version number, as those of MOBCAL do.
