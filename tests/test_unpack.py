"""Reading a result file back (``mobcal.io.result``) and ``mobcal unpack``: every shape the writer
makes unpacks into an ion file and a method file that check against the hashes recorded, the
command it prints makes the same job again, and the 2012 choline run unpacked and run again
gives the reference's digits. The stand-in binary for every shape; the built one under the gate.
"""

import dataclasses
import json
import os
import re
import shutil
from pathlib import Path

import pytest

import gate
from mobcal import cli, methods, parameters, run, settings
from mobcal.io import result
from mobcal.io.outfile import OutFile
from mobcal.run import Job, run_one
from test_result import ion_file
from test_run import CHOLINE_ION, launcher, write_input

SEED = 5013489


def cli_job(*argv: str) -> Job:
    """The one job ``mobcal run`` makes of these arguments, its split set as the run's is."""
    jobs = cli.batch_from_args(cli.parser().parse_args(["run", *argv])).plan().jobs
    assert len(jobs) == 1
    return jobs[0]


def ran(tmp_path: Path, inp: Path, *opts: str) -> Job:
    """A job as ``mobcal run`` makes it, run on the stand-in."""
    job = cli_job(str(inp), "--out", str(tmp_path / "runs"), *opts)
    run_one(job, launcher)
    assert job.result_path.is_file()
    return job


def again(job: Job, u: result.Unpacked) -> Job:
    """The job the printed command makes, into the original's folder."""
    assert u.rerun[:2] == ("mobcal", "run")
    return cli_job(*u.rerun[2:], "--out", str(job.out_dir))


def table(job: Job) -> parameters.ParameterSet:
    return parameters.load(job.parameters_path, gas=job.gas)


def same_job(new: Job, old: Job) -> None:
    """Every field of the calculation, the label and the staged name included; the input's
    path is the one difference, an ion file where a .mfj may have been."""
    assert dataclasses.replace(new, input=old.input) == old
    assert new.label == old.label and new.staged == old.staged


# --- every shape the writer makes -------------------------------------------------------------

def test_a_mfj_input_unpacks_as_the_ion_file_it_reads_as(tmp_path):
    job = ran(tmp_path, write_input(tmp_path / "ok.mfj", "ok"), "--method", "2012-he",
              "--seeds", str(SEED))
    u = result.unpack(result.Result.read(job.result_path), tmp_path / "u")
    assert u.ion.path == tmp_path / "u" / "ok.ion.json" and u.converted_from == "mfj"
    assert not u.ion.identical  # the recorded hash is the .mfj's
    assert u.staged is False and any("laid out as MOBCAL writes" in n for n in u.notes)
    assert u.method.path.name == "2012-he.method.json" and u.method.identical
    assert u.method.path.read_bytes() == methods.METHODS["2012-he"].path.read_bytes()
    assert u.rerun == ("mobcal", "run", str(u.ion.path), "--method", "2012-he", "--seeds",
                       str(SEED))
    new = again(job, u)
    same_job(new, job)
    # the program reads the same values from the .mfj the ion file gives, in another layout
    old_staged, new_staged = run.stage(job.input, table(job)), run.stage(new.input, table(new))
    assert new_staged.mfj == old_staged.mfj and new_staged.data != old_staged.data


def test_an_ion_file_unpacks_byte_for_byte_and_stages_the_same_bytes(tmp_path):
    inp = ion_file(tmp_path / "ok.ion.json", "ok")
    job = ran(tmp_path, inp)
    u = result.unpack(result.Result.read(job.result_path), tmp_path / "u")
    assert u.ion.path.name == "ok.ion.json" and u.converted_from is None
    assert u.ion.identical and u.ion.path.read_bytes() == inp.read_bytes()
    assert u.staged is True
    assert u.method.path.name == f"{methods.DEFAULT}.method.json" and u.method.identical
    new = again(job, u)
    same_job(new, job)
    assert run.stage(new.input, table(new)).data == run.stage(job.input, table(job)).data


def test_an_ion_file_laid_out_otherwise_unpacks_as_the_same_document(tmp_path):
    inp = ion_file(tmp_path / "ok.ion.json", "ok")
    doc = json.loads(inp.read_text(encoding="utf-8"))
    inp.write_text(json.dumps(doc), encoding="utf-8")  # one line, the same value
    job = ran(tmp_path, inp)
    u = result.unpack(result.Result.read(job.result_path), tmp_path / "u")
    assert not u.ion.identical and u.ion.recorded == run.stage(inp, table(job)).sha256
    assert json.loads(u.ion.path.read_text(encoding="utf-8")) == doc
    assert u.staged is True
    same_job(again(job, u), job)


def test_a_method_file_unpacks_byte_for_byte(tmp_path):
    st = settings.DEFAULTS.replace(temperature=298.15, imp=25)
    m = methods.save(tmp_path / "mine", "Mine at 298.15 K", "he", "2000", "ranlux", st,
                     seed=42, description="ours")
    job = ran(tmp_path, ion_file(tmp_path / "ok.ion.json", "ok"), "--method", str(m.path))
    assert job.seed == 42
    u = result.unpack(result.Result.read(job.result_path), tmp_path / "u")
    assert u.method.path.name == "mine.method.json" and u.method.identical
    assert u.rerun[-4:] == ("--method", str(u.method.path), "--seeds", "42")
    same_job(again(job, u), job)


def test_a_custom_method_is_named_by_the_result(tmp_path):
    job = ran(tmp_path, ion_file(tmp_path / "ok.ion.json", "ok"), "--method", "2012-philox-he",
              "--temperature", "298", "--imp", "25")
    assert job.method == "custom"
    u = result.unpack(result.Result.read(job.result_path), tmp_path / "u")
    assert u.method.path.name == f"{job.label}.method.json" and u.method.recorded is None
    m = methods.load(u.method.path)
    assert m.name == job.label and m.settings == job.settings
    new = again(job, u)
    same_job(new, job)


def test_a_table_of_ones_own_is_found_where_the_method_names_it(tmp_path):
    mine = tmp_path / "mine.toml"
    mine.write_bytes(parameters.default_path("he").read_bytes() + b"\n# a copy of my own\n")
    inp = ion_file(tmp_path / "ok.ion.json", "ok")
    job = ran(tmp_path, inp, "--parameters", str(mine))
    u = result.unpack(result.Result.read(job.result_path), tmp_path / "u")
    assert u.staged is True and any(str(mine.resolve()) in n for n in u.notes)
    same_job(again(job, u), dataclasses.replace(job, parameters=mine.resolve()))
    # moved away, the staged input cannot be checked, and unpack says so
    mine.rename(tmp_path / "moved.toml")
    u = result.unpack(result.Result.read(job.result_path), tmp_path / "v")
    assert u.staged is None and any("is not on this computer" in n for n in u.notes)


def test_a_divided_run_reruns_divided(tmp_path):
    job = ran(tmp_path, ion_file(tmp_path / "ok.ion.json", "ok"), "--split", "4")
    u = result.unpack(result.Result.read(job.result_path), tmp_path / "u")
    assert u.rerun[-2:] == ("--split", "4")
    same_job(again(job, u), job)


def test_a_run_that_failed_still_unpacks(tmp_path):
    job = ran(tmp_path, ion_file(tmp_path / "refuse.ion.json", "refuse"))
    r = result.Result.read(job.result_path)
    assert r.status == "failed"
    u = result.unpack(r, tmp_path / "u")
    assert u.ion.identical and u.staged is True


# --- refusals ---------------------------------------------------------------------------------

def test_a_referenced_ion_is_refused_with_its_hash(tmp_path, capsys):
    inp = ion_file(tmp_path / "ok.ion.json", "ok")
    job = ran(tmp_path, inp, "--result-ion", "reference")
    sha = run.stage(inp, table(job)).sha256
    with pytest.raises(result.ResultError, match=f"by reference, as ok.ion.json .SHA-256 {sha}"):
        result.unpack(result.Result.read(job.result_path), tmp_path / "u")
    assert cli.main(["unpack", str(job.result_path), "-o", str(tmp_path / "u")]) == 1
    assert "by reference" in capsys.readouterr().err
    assert not (tmp_path / "u").exists()


def test_a_mfj_no_table_can_name_is_refused_as_referenced(tmp_path):
    inp = tmp_path / "hbr.mfj"
    inp.write_text("refuse\n1\n2\nang\ncalc\n1.0000\n 0.0 0.0 0.0 35 0.5\n 1.41 0.0 0.0 1 0.5\n",
                   encoding="latin-1", newline="\n")
    job = Job(inp, "he", 1, tmp_path)
    run_one(job, launcher)
    with pytest.raises(result.ResultError, match="by reference, as hbr.mfj"):
        result.unpack(result.Result.read(job.result_path), tmp_path / "u")


@pytest.fixture
def done(tmp_path) -> Job:
    return ran(tmp_path, ion_file(tmp_path / "ok.ion.json", "ok"))


def edited(job: Job, tmp_path: Path, change) -> Path:
    doc = json.loads(job.result_path.read_text(encoding="utf-8"))
    change(doc)
    path = tmp_path / "edited.result.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


@pytest.mark.parametrize("change, message", [
    (lambda d: d.update(format="mobcal-result"), "format is 'mobcal-result'"),
    (lambda d: d.update(version=2), "version is 2; this version of MOBCAL reads version 1"),
    (lambda d: d.pop("seed"), "has no 'seed'"),
    (lambda d: d.update(gas="Ar"), "gas is 'Ar'"),
    (lambda d: d["inputs"]["ion"]["document"].pop("symbols"), "inputs.ion.document: "),
    (lambda d: d["inputs"]["method"]["document"].update(gas="xe"), "inputs.method.document: "),
    (lambda d: d["inputs"]["ion"].update(embedded=False), "embedded does not say"),
])
def test_the_reader_refuses_what_is_not_a_result_it_reads(done, tmp_path, change, message):
    path = edited(done, tmp_path, change)
    with pytest.raises(result.ResultError, match=f"^{re.escape(str(path))}: .*{message}"):
        result.Result.read(path)


def test_the_reader_refuses_a_key_twice_and_non_json(done, tmp_path):
    text = done.result_path.read_text(encoding="utf-8")
    twice = tmp_path / "twice.result.json"
    twice.write_text(text.replace('"seed":', '"seed": 1, "seed":', 1), encoding="utf-8")
    with pytest.raises(result.ResultError, match="key 'seed' appears twice"):
        result.Result.read(twice)
    nan = tmp_path / "nan.result.json"
    nan.write_text(text.replace('"seconds": ', '"seconds": NaN, "x": ', 1), encoding="utf-8")
    with pytest.raises(result.ResultError, match="NaN is not a JSON number"):
        result.Result.read(nan)


@pytest.mark.parametrize("change, message", [
    (lambda d: d["mobcal"]["staged_input"].update(sha256="0" * 64),
     "has SHA-256 [0-9a-f]{64}, not the 0{64} the program read"),
    (lambda d: d["mobcal"].update(generator="ranlux"), "generator is 'philox' and the run's"),
    (lambda d: d["mobcal"]["settings"].update(imp=25), "settings is"),
    (lambda d: d["mobcal"]["parameters"].update(sha256="0" * 64), "element table's SHA-256"),
])
def test_unpack_refuses_a_record_of_no_one_calculation(done, tmp_path, change, message):
    r = result.Result.read(edited(done, tmp_path, change))
    with pytest.raises(result.ResultError, match=message):
        result.unpack(r, tmp_path / "u")
    assert not (tmp_path / "u").exists()


def test_a_file_already_there_is_kept_unless_forced(done, tmp_path, capsys):
    out = tmp_path / "u"
    argv = ["unpack", str(done.result_path), "-o", str(out)]
    assert cli.main(argv) == 0
    assert "wrote" in capsys.readouterr().out
    assert cli.main(argv) == 0  # the same bytes: found, not refused
    assert capsys.readouterr().out.count("found unchanged") == 2
    (out / "ok.ion.json").write_text("{}\n", encoding="utf-8")
    assert cli.main(argv) == 1
    assert "exists with other contents" in capsys.readouterr().err
    assert (out / "ok.ion.json").read_text(encoding="utf-8") == "{}\n"
    assert cli.main([*argv, "--force"]) == 0
    assert (out / "ok.ion.json").read_bytes() == (tmp_path / "ok.ion.json").read_bytes()


def test_the_command_prints_the_checks_and_the_rerun(done, tmp_path, capsys):
    assert cli.main(["unpack", str(done.result_path), "-o", str(tmp_path / "u")]) == 0
    out = capsys.readouterr().out
    assert out.count("SHA-256 matches") == 3  # the ion, the method and the staged .mfj
    u = result.unpack(result.Result.read(done.result_path), tmp_path / "u")
    assert out.endswith(f"to run it again:\n  {u.command}\n")


# --- the methods text -------------------------------------------------------------------------

def test_the_methods_text_from_a_result_file_is_the_records(tmp_path):
    jobs = [ran(tmp_path, CHOLINE_ION), ran(tmp_path, write_input(tmp_path / "ok.mfj", "ok"))]
    for j in jobs:
        assert methods.text(methods.read_records([j.result_path])) \
            == methods.text(methods.read_records([j.run_dir]))
    assert "partial charges" in methods.text(methods.read_records([jobs[0].result_path]))
    # a folder of result files, gathered from their run directories
    gathered = tmp_path / "gathered"
    gathered.mkdir()
    for j in jobs:
        shutil.copy(j.result_path, gathered)
    assert methods.text(methods.read_records([gathered])) \
        == methods.text(methods.read_records([tmp_path / "runs"]))


def test_methods_text_takes_result_files_on_the_command_line(tmp_path, capsys):
    job = ran(tmp_path, CHOLINE_ION)
    assert cli.main(["methods-text", str(job.result_path)]) == 0
    assert capsys.readouterr().out == methods.text(methods.read_records([job.run_dir]))
    assert cli.main(["methods-text", str(tmp_path / "missing.result.json")]) == 2


def test_a_referenced_ion_still_gives_the_methods_text(tmp_path):
    job = ran(tmp_path, CHOLINE_ION, "--result-ion", "reference")
    text = methods.text(methods.read_records([job.result_path]))
    assert "partial charges" not in text and "trajectory method" in text


def test_the_writer_and_reader_share_the_constants():
    assert (run.RESULT_FORMAT, run.RESULT_VERSION, run.RESULT_SUFFIX, run.GAS_FORMULA) \
        == (result.FORMAT, result.VERSION, result.SUFFIX, result.GAS_FORMULA)
    assert result.VERSION in result.VERSIONS


# --- under the gate ---------------------------------------------------------------------------

def test_choline_unpacked_and_run_again_gives_the_reference_digits(pool, tmp_path):
    """The 2012 choline run of the gate, unpacked from its result file and run again from the
    ion file and method file alone, divided across this machine's cores (split = serial to the
    bit), reports the 2012 reference's numbers."""
    gr = pool.runs["he"]
    u = result.unpack(result.Result.read(gr.result), tmp_path / "u")
    assert u.ion.path.name == "Choline.ion.json" and u.converted_from == "mfj"
    assert u.method.path.name == "2012-he.method.json" and u.method.identical
    original = cli_job(str(gate.CHOLINE), "--method", "2012-he", "--seeds", str(gr.ref.seed),
                       "--out", str(tmp_path / "runs"))
    new = cli_job(*u.rerun[2:], "--out", str(tmp_path / "runs"))
    same_job(new, original)
    w = max(2, min(os.cpu_count() or 2, 40))
    r = run_one(dataclasses.replace(new, split=w), pool.launcher)
    assert r.ok, r.message
    o = OutFile.read(r.output)
    for k in ("cross_sections", "tm_standard_deviation", "inverse_mobilities",
              "asymmetry_parameter", "failed_trajectories", "input_label"):
        assert getattr(o, k) == getattr(gr.ref, k), k
