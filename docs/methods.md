# Methods

A method is everything a calculation depends on except its input and its seed: the buffer gas, the
element table, the random number generator and the six run settings (the temperature and the five
sampling counts, [The run settings](settings.md)). The window's Method list and `mobcal run
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
`2012-philox-he` run. The seed is not part of a method, and the first seed is the
2012 seed, 5013489, under every method.

## Method files

To keep a calculation of one's own, write its method to a file. File ▸ Save method… in the
window writes the gas, element table, generator and six settings the form holds, and asks for
the name the Method list will show; File ▸ Load method… adds a file written by hand or on
another computer. Either way the file joins the Method list under its name, the list remembers
it at the next launch, and `mobcal run --method PATH` runs the same file:

```toml
format = 1
name = "Choline at 298.15 K"
gas = "he"
parameters = "2012"
generator = "philox"
temperature = 298.15
imp = 1000
itn = 10
inp = 40
inum = 250000
inor = 30
```

`format`, `name`, `gas` (`he` or `n2`), `parameters` and `generator` (`philox` or `ranlux`) are
required, and a key the file does not know is refused by name. The six settings are optional,
and a setting left out takes its 2012 value, as in a settings file. The name is 1 to 60
characters and must differ from the shipped methods' names and from every other file in the
list. `parameters` is the name of a shipped table for the gas (`2012`, or `2000` in helium), or
a table of one's own ([The element tables](parameters.md)) named by its path and its SHA-256:

```toml
[parameters]
path = "C:/Users/me/tables/my_helium.toml"
sha256 = "6e19c7ce13dbff2035bac9c762226db61316e706b23f52f2336028af76da18f0"
```

A relative path is read from the method file's folder. Save method writes the table's absolute
path and its SHA-256 at the time of saving. Loading or running the method refuses it, naming the
table, when the table is no longer at that path or its bytes have changed, so a method file
always means the calculation it was saved as. The window applies the same rule to its list: a
remembered file that has been moved, deleted or edited since it was added is removed from the
list at the next launch, with a message that names it and says why. Loading it again adds it as
it is now.

## What a run records

Every run directory's `record.json` names the method in `method`: a shipped method's key, the
name of the method file, or `custom` when an option given beside the method changed it. A run
from a method file also records the file in `method_file`, its path and its SHA-256, which is
`null` for the other runs. `summary.csv` and `summary.json` carry the same, and the methods
paragraph (`mobcal methods-text`, the window's Copy methods text) names the method. Run
directories are named for the input, the gas, the seed, the generator when it is RANLUX, the
table when it is not the gas's 2012 table, and each setting that differs from 2012
(`choline-he-5013486-ranlux-lj2000-t298-imp25`), never for the method, so the same calculation
lands in the same directory whichever way it was asked for.

Runs made before methods carried their gas recorded `current`, `2012` or `2000`. These are read
as `2012-philox-he` or `2012-philox-n2`, as `2012-he` or `2012-n2`, and as `2000-he`, by the gas
of the run, so a folder holding runs from both versions gives one methods paragraph. A queue the
window saved before this change, in which one batch ran both gases, comes back as one batch for
each gas.
