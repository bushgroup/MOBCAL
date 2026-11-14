# tests/data/mobcal-2000/

The example of the 2000 helium release of the Jarrold group, as distributed: three files of
[bushgroup/MOBCAL-2000](https://github.com/bushgroup/MOBCAL-2000) at tag `v1.0`, copied byte for
byte and never edited. That release is GPL-3, with the permission of Martin Jarrold, as this
package is.

| File | What it is | SHA-256 |
|---|---|---|
| `a10A1.mfj` | The example input, a sodiated alanine decamer (104 atoms), 50 coordinate sets, with calculated partial charges | `6df8bde863d775cfaf42581ffb81f54a176494854394cb06e5358b6a51d206ed` |
| `a10A1.out.orig` | The output of the 2000 program for that input, at the seed in `mobcal.run` | `dd09d9f346e2321034476c86d6aa4bcd10f815e854019227f991cff247955836` |
| `mobcal.run` | The run file: input file name, output file name, and the seed, 5013486 | `949d1e433eb33ad2d36e611517fe34ef4723f3463c32bc7eda6127242a09fc00` |

`tests/test_mobcal_2000.py` holds each file to its SHA-256, the pins the release lists, and runs
the example through the shipped helium program under the method `2000-he`.
`tests/reference/a10A1.out` is what that program prints, and `tests/test_reference.py` ties it to
`a10A1.out.orig` line by line.
