# MOBCAL — public-role code repo

Package `mobcal`: the 2012 MOBCAL trajectory-method Fortran, kept under `fortran/` with every
change since 2012 counted, and a Python package around it that builds the Fortran, runs
calculations in parallel across processes, parses inputs and outputs, and (later) presents a
PySide6 window, shipped as installers on Windows, macOS and Linux. This is the **public-role half of a
two-repo arrangement**: it carries `fortran/`, `src/mobcal/`, `tools/`, `tests/`, `docs/`,
`packaging/` and the public self-check — nothing else. The development record lives in the
private sibling **`bushgroup/MOBCAL-lab`** (tasks, notes, explorations, digests of the
abandoned v1.1 line, and the working CLAUDE.md with the full project state and never-do list).

**Sessions are based here.** A gitignored `CLAUDE.local.md` imports the lab repo's CLAUDE.md; if
you are reading this file *without* that import, you have a public clone — the package and
`tools/check_public.py` are fully usable, the lab material is not yours to see.

## Rules that live with the code

- **Run anything with `uv run <path/to/script.py>`** — no flags, no venv activation. Never rely on
  the `python` on PATH.
- **`uv run tools/check_public.py`** after touching `src/mobcal/` or `fortran/`. A clone with no
  gfortran and no lab repo must pass it; checks that need one report SKIPPED, never FAIL.
- **`fortran/` is the 2012 code plus the changes `fortran/README.md` lists, and changes no other
  way.** `mobcal.fortran.SHA256` pins every file there and the self-check compares. A change to
  any of them happens only in a commit a lab task calls for, updates the pins and that list in
  the same commit, and counts its diff line by line in the message. No change moves a value the
  2012 program computes; the gate proves it on every push.
  The reference outputs under `fortran/sample-output/` are the 2012 originals; a test normalizes
  its own output to compare, and never edits them.
- **The build recipe lives in one place**, `mobcal.fortran.FFLAGS`: `-O3 -fno-automatic
  -std=legacy`, plus `LINK_FLAGS` per platform so the shipped binary needs no gfortran runtime. `-fno-automatic` is mandatory, not a preference: without
  it an optimized build loses every trajectory. Nothing else — CI, docs, packaging — restates the
  flags; they import or cite them.
- **Layers under one seam.** `mobcal.fortran` (locate, verify, build), `mobcal.io` (the `.mfj`,
  `mobcal.in` and `.out` formats) and `mobcal.run` (the process-fanout driver) **never import
  Qt**; `mobcal.app` is PySide6 on top of them. A script that runs one calculation must not pull a
  GUI in.
- **Never run a calculation on the UI thread.** A choline run is minutes in helium and an hour in
  nitrogen; runs are subprocesses the driver supervises and reports on.
- **All three platforms are targets.** Windows is where the first installer ships, but nothing
  here is Windows-only without a reason stated in the lab notes, and CI runs the three.
- **Lab-side paths resolve through `mobcal.lab_dir()`**: `$MOBCAL_LAB`, then this root, then the
  sibling `../MOBCAL-lab`. Nothing in this repo, code or docs, refers to lab material except in
  opaque form ("lab record, task NN"), and never to any other private repository of the lab's.
- **Public commit messages are self-contained statements of the change.** Task IDs may appear as
  opaque references at most. Trailer is `Assisted-by: <model name>`, no email — never
  `Co-Authored-By:`. `.githooks/commit-msg` rewrites, `.githooks/pre-commit` rejects staged files
  over 5 MiB; both need `git config core.hooksPath .githooks` once per clone.
- **`.gitattributes` pins LF** in the repository and the working tree. The program itself writes
  CRLF on Windows; a comparison strips end-of-line CR itself and never relies on git for it.
- **Outward-facing prose (README, `docs/`, user guide) follows the `manuscript-voice` skill**
  from the lab repo. Repo-internal prose (this file, docstrings, commit messages) does not.
- **GPL-3.0, `LICENSE` as the 2012 release carried it, copyright University of Washington for the
  new work.** Written from the first commit (2026-10-21) as if public. The version is declared in
  `pyproject.toml` and `mobcal.__version__` (and in the installer scripts once they exist);
  `check_public.py` fails unless they agree.

## Maintaining this file

This file stays lean: rules for working *in this repo*, nothing about the science or the project's
state. Those belong in the lab repo's CLAUDE.md and notes. Keep it under 65 lines.
