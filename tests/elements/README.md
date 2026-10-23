# What the 2012 element chains computed

Fixtures for `tests/test_elements.py`: the numbers and outputs the programs produced while their
element tables were still the `if(imass(iatom).eq.NN)` chains in `fcoord` and `ncoord`, captured
on 2026-10-22 from the sources as committed at `ca38716`, the last commit to carry the chains,
compiled with MSYS2 gfortran 16.2.0 under the recorded flags (`-O3 -fno-automatic -std=legacy
-static`) on Windows 11. They are never regenerated: the chains they record are gone.

| File | What it is |
|---|---|
| `rows.json` | Every row of both tables, from both readers' chains, as 64-bit patterns and at 17 significant digits: the mass, well depth (`eolj`, in joules), radius and hard-sphere radius (`rolj`, `rhs`, in metres) an atom of each key was assigned, evaluated by a program that holds the chain's own statements. Nitrogen's `ncoord` rows show silicon with iron's well depth and radius, the copy error the file corrects. |
| `he.mfj`, `n2.mfj`, `n2-no-si.mfj` | The probe inputs `tests/probe.py` generates: one atom per row of the table, two identical coordinate sets; the third without silicon. |
| `he.out`, `n2.out`, `n2-no-si.out` | What the programs wrote for them as worker 400 of 400 at seed 5013489, one block of trajectories per set, normalized as the regression test normalizes (end-of-line CR stripped), LF. |

The tests hold the programs that read `parameters.tab` to these: every row of the rendered
table read back through the programs' own reader must give the pattern in `rows.json`, bit for
bit, and the probe outputs must match byte for byte, except the second coordinate set of
`n2.out`, where the chain gave silicon iron's parameters and the table gives silicon's.
