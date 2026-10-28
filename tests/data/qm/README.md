# tests/data/qm/

Quantum-chemistry outputs that `mobcal import` reads, kept whole: what `tests/test_import.py`
imports, and the worked examples `docs/import.md` points at. Six ORCA 6.1.1 jobs on the choline
cation (C5H14NO+, 21 atoms, z = +1, singlet), the test ion of the 2012 reference calculations,
run on 2026-10-26 on Windows 11 with `%pal nprocs 8` and `%maxcore 3000`. Every job starts from
the geometry of `fortran/Choline.mfj` (its first three columns, in ångström, as
`choline_2012.xyz`) or from an optimized geometry another job here produced. Three Gaussian 16
jobs on the same ion follow (below).

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

## Gaussian 16 jobs

`gaussian/` holds three Gaussian 16 jobs, each an input written on 2026-10-26 from the geometry
of `fortran/Choline.mfj` at its five decimals and the log Gaussian 16 Rev. B.01 wrote from it on
2026-10-27, run by Yarra Hassan at the University of Washington. All three are
B3LYP/6-31++G(d,p), the basis named in the label of the 2012 charge column
(`Choline_631G++dp_pop`), with Gaussian's B3LYP (VWN functional III) and its default Cartesian d
functions for this basis, which every log confirms (`6-31++G(d,p) (6D, 7F)`).

| Job | Route | Start geometry | Charge blocks the `.log` prints |
|---|---|---|---|
| `choline_2012_mk` | `# B3LYP/6-31++G(d,p) SP NoSymm Pop=(MK,Hirshfeld)` | `Choline.mfj`, not optimized | Mulliken, Hirshfeld and CM5 in one block, and a Merz-Kollman ESP fit (861 points), once each, after the input orientation |
| `choline_2012_chelpg` | `# B3LYP/6-31++G(d,p) SP NoSymm Pop=(CHELPG,NBO)` | `Choline.mfj`, not optimized | Mulliken, a CHELPG ESP fit (12,034 points) and NBO 3.1's natural population analysis, once each |
| `choline_optfreq` | `# B3LYP/6-31++G(d,p) Opt Freq Pop=CHELPG` | `Choline.mfj` | Mulliken and CHELPG three times: at the start geometry, at the stationary point (step 1), and in the frequency calculation (step 2) |

`NoSymm` keeps the two single points at the coordinates as given, so that their charges compare
atom by atom with the 2012 column; the optimization keeps Gaussian's symmetry handling, as most
users run it, and prints its blocks after the standard orientation.

The jobs ran on a Linux cluster with 40 cores and 128 GB of memory, so the `%nprocshared` and
`%mem` lines of each `.gjf` say so, and the `%chk` line names the checkpoint file by its path in
the scratch directory the jobs ran in. Each `.gjf` here is the file the log was run from, and the
route, title, charge, multiplicity and coordinates are the ones written on 2026-10-26. The logs
are as Gaussian wrote them, LF and ASCII, and carry the user name and host name in the archive
entry at the end of each job step and in the checkpoint path, published with the runner's
agreement.

What the tests rely on, and what the logs show:

- Gaussian prints each block after the coordinate block it belongs to. `Opt Freq` writes two job
  steps to one log. The optimization took two steps from the 2012 geometry, lowering the energy
  by 3e-6 hartree, and the frequency step reads the stationary point from the checkpoint file,
  prints it again as a coordinate block of its own, equal to step 1's last to the printed digits,
  and prints its own Mulliken and CHELPG blocks after it: `Pop=CHELPG` carries into step 2. No
  frequency is imaginary.
- Each job step ends in its own `Normal termination`, two in `choline_optfreq.log`.
- The Hirshfeld and CM5 charges sum to +1.00002; Mulliken, the ESP fits and the natural charges
  sum to +1.0000 at the printed digits.
- The Merz-Kollman charges of `choline_2012_mk` are the 2012 column to within 0.005 e on every
  atom, and the CHELPG charges of `choline_2012_chelpg` are 0.17 e from it on one.
- The logs are printed at Gaussian's default print level (`#`), which cclib 1.9rc1 needs at `#P`
  to read the ESP fits; the import reads those from the text.

`SHA256SUMS` pins every file here except this README and itself, in the format `sha256sum -c`
reads, and `tests/test_import.py` compares. A fixture changes only in a commit that updates its
line there and says why. The files are distributed under this repository's licence.
