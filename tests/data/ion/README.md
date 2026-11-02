# tests/data/ion/

The reference pair that pins the ion-file writers (`tests/test_ion.py`).

- `choline.ion.json`: `fortran/Choline.mfj` (the choline cation of the 2012 release, 21 atoms,
  one conformer, `calc` mode) converted by `mobcal.io.ion.from_mfj`, written by `Ion.write`,
  with `import.source.path` set to the repository-relative `fortran/Choline.mfj` in place of
  the absolute path of the machine that wrote it. Nothing else was edited.
- `choline.mfj`: what `Ion.mfj` writes from it for a run on either shipped 2012 table (H, C, N
  and O have the same keys in both). It parses to the same `Mfj` as `fortran/Choline.mfj`, and
  differs from it only in layout.

A change to either writer that changes these bytes fails the test, so it is made on purpose:
regenerate both and say why in the commit.

`choline_mobcalmpi.mfj` is the input of `tests/test_mobcalmpi.py`: the same choline cation in
the nine-column layout MobCal-MPI 2.1 reads. Its coordinates, charges and charge mode are the
tokens of `fortran/Choline.mfj`; its masses are the 2012 nitrogen table's (14.01, 12.01, 1.008,
16.00), so that the ion read from it stages the same `.mfj` as `fortran/Choline.mfj`; α, N, A
and G are those of MobCal-MPI's `vdW.prm` (GPL-3.0) for the MMFF94 type RDKit assigns each
atom; line 6 is 0 (MobCal-MPI's high-field correction off) and the run line is
`10 40 1000 2 5013489 301.0`. It was written for this repository and is not a file of the
MobCal-MPI distribution.
