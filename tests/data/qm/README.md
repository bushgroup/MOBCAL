# tests/data/qm/

Quantum-chemistry outputs that `mobcal import` reads, kept whole: what `tests/test_import.py`
imports, and the worked examples `docs/import.md` points at. Six ORCA 6.1.1 jobs on the choline
cation (C5H14NO+, 21 atoms, z = +1, singlet), the test ion of the 2012 reference calculations,
run on 2026-10-26 on Windows 11 with `%pal nprocs 8` and `%maxcore 3000`. Every job starts from
the geometry of `fortran/Choline.mfj` (its first three columns, in ångström, as
`choline_2012.xyz`) or from an optimized geometry another job here produced. Three Gaussian 16
inputs on the same ion are here too, waiting for their outputs (below).

| Job | Route | Start geometry | Charge blocks the `.out` prints |
|---|---|---|---|
| `choline_opt` | `! r2SCAN-3c Opt` | `choline_2012.xyz` | Mulliken and Löwdin twice: at the start geometry and at the stationary point |
| `choline_opt_chelpg` | `! r2SCAN-3c Opt CHELPG` | `choline_2012.xyz` | the same, and CHELPG after every cycle's geometry and at the stationary point (5) |
| `choline_sp` | `! B3LYP D3BJ def2-TZVP CHELPG Hirshfeld` | `choline_opt.xyz`, the final geometry of `choline_opt` | Mulliken, Löwdin, CHELPG, Hirshfeld, once each |
| `choline_two_jobs` | job 1 `! B3LYP D3BJ def2-SVP Opt`; `$new_job`; job 2 `! B3LYP D3BJ def2-TZVP CHELPG Hirshfeld` on job 1's final geometry | `choline_2012.xyz` | Mulliken and Löwdin three times (job 1 start, job 1 stationary point, job 2), CHELPG and Hirshfeld once (job 2) |
| `choline_2012_hf` | `! HF 6-31++G(d,p) CHELPG Hirshfeld` | `choline_2012.xyz`, not optimized | Mulliken, Löwdin, CHELPG, Hirshfeld, once each |
| `choline_2012_b3lyp` | `! B3LYP/G 6-31++G(d,p) CHELPG Hirshfeld` | `choline_2012.xyz`, not optimized | the same |

Each job directory holds what ORCA was given and what it wrote that the import or its tests
use: the input `<job>.inp`, the start geometry it names, the complete output `<job>.out`, the
final geometry `<job>.xyz` of a job that optimizes, and `<job>.chelpg.xyz` (`<job>_job2.chelpg.xyz`
for the second job of `choline_two_jobs`), ORCA's own record of the CHELPG charges with the
geometry they were fitted at. The CHELPG file lets a test check the charges an import writes
against a file that never passes through the parser the import uses.

The jobs ran in a neutral working directory, which ORCA prints in each output's header with the
host name, start time and process ID; nothing else was edited. ORCA writes CRLF on Windows and
this repository stores LF (`.gitattributes`), so end-of-line CR was stripped from every file and
the files are otherwise as ORCA wrote them. The outputs are UTF-8.

What the tests rely on, and what the outputs show:

- In an optimization, ORCA 6 prints the population analysis at the first geometry and again
  after the final energy evaluation at the stationary point, which it reports as a coordinate
  block of its own (it differs from the last cycle's by about 5e-4 Å). With `CHELPG` on the route
  the CHELPG fit is printed after every cycle as well. Every charge block follows the coordinate
  block it belongs to, so the last block of a kind belongs to the last geometry when it comes
  after it.
- `$new_job` writes both jobs to one output. Job 2's single coordinate block equals job 1's
  stationary point to the printed digits, and its blocks follow it; job 1's blocks remain
  earlier in the file.
- The Hirshfeld charges of the two unoptimized jobs sum to +1.0002 (ORCA integrates them on a
  grid); Mulliken, Löwdin and CHELPG sum to +1.0000 to the printed digits.

## Gaussian 16 inputs, outputs to come

`gaussian/` holds three Gaussian 16 inputs, written on 2026-10-26 from the geometry of
`fortran/Choline.mfj` at its five decimals. Their outputs are not here yet. Until they are,
`mobcal import` refuses a Gaussian output as not yet supported, and no test reads these inputs
beyond the hash check below. All three are B3LYP/6-31++G(d,p), the basis named in the label of
the 2012 charge column (`Choline_631G++dp_pop`), with Gaussian's B3LYP (VWN functional III) and
its default Cartesian d functions for this basis.

| Job | Route | Start geometry | What the output is for |
|---|---|---|---|
| `choline_2012_mk` | `# B3LYP/6-31++G(d,p) SP NoSymm Pop=(MK,Hirshfeld)` | `Choline.mfj`, not optimized | Merz-Kollman, Hirshfeld and CM5 charges at the 2012 geometry, printed in the input orientation |
| `choline_2012_chelpg` | `# B3LYP/6-31++G(d,p) SP NoSymm Pop=(CHELPG,NBO)` | `Choline.mfj`, not optimized | CHELPG and natural (NBO) charges at the 2012 geometry |
| `choline_optfreq` | `# B3LYP/6-31++G(d,p) Opt Freq Pop=CHELPG` | `Choline.mfj` | an optimization and a frequency calculation, two job steps in one output, printed in the standard orientation |

`NoSymm` keeps the two single points at the coordinates as given, so that their charges compare
atom by atom with the 2012 column; the optimization keeps Gaussian's symmetry handling, as most
users run it. Each input names its checkpoint file without a path and asks for 4 cores and
4 GB of memory, the two lines that may change on another machine without changing a result.
When the outputs arrive, each job directory gains its output, kept whole, and this section
gains what each output prints.

`SHA256SUMS` pins every file here except this README and itself, in the format `sha256sum -c`
reads, and `tests/test_import.py` compares. A fixture changes only in a commit that updates its
line there and says why. The files are distributed under this repository's licence.
