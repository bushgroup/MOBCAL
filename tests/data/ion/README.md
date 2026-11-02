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
