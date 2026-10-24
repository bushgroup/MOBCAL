"""mobcal.io.block: the 76-byte record, its name, the settings it carries, and who owns which
block."""

import struct

import pytest

from mobcal.io.block import (
    BLOCKS_PER_SET,
    GENERATOR_CODE,
    Block,
    BlockError,
    block_name,
    expected_names,
    owned,
)
from mobcal.settings import DEFAULTS, Settings


def test_write_and_read_back(tmp_path):
    b = Block(2, 7, 13, 5013489, 0.12345678901234567, 9.87654321e-3, 1)
    p = b.write(tmp_path)
    assert p == tmp_path / "block-002-00127.dat" and p.stat().st_size == 76
    assert b.k == 127 and b.name == block_name(2, 127)  # velocity-major: (13 - 1) * 10 + 7
    assert Block.cycle_point(127) == (7, 13) and Block.cycle_point(1) == (1, 1)
    assert Block.cycle_point(400) == (10, 40)
    assert Block.read(p) == b and b.generator == "ranlux"  # the doubles survive to the bit
    assert Block.read(p).settings == DEFAULTS


def test_the_generator_is_the_fifth_integer(tmp_path):
    assert GENERATOR_CODE == {"ranlux": 1, "philox": 2}  # i5 in the program
    b = Block(1, 1, 1, 5013489, 1.0, 2.0, 0, "philox")
    data = b.write(tmp_path).read_bytes()
    assert struct.unpack("<6i", data[:24]) == (68, 1, 1, 1, 5013489, 2)
    assert Block.read(tmp_path / b.name) == b
    with pytest.raises(BlockError, match="generator 'rand'"):
        Block(1, 1, 1, 1, 1.0, 1.0, 0, "rand")
    (tmp_path / b.name).write_bytes(data[:20] + struct.pack("<i", 3) + data[24:])
    with pytest.raises(BlockError, match="generator code 3"):
        Block.read(tmp_path / b.name)


def test_the_settings_follow_the_generator(tmp_path):
    # imp itn inp inum inor as default integers, then the temperature as a REAL*8, exactly as
    # the program writes them after the generator; the block index follows the block's itn.
    s = Settings(298.15, 25, 3, 7, 200, 5)
    b = Block(1, 2, 4, 5013486, 1.0, 2.0, 0, "ranlux", s)
    assert b.k == (4 - 1) * 3 + 2 and b.name == "block-001-00011.dat"
    assert Block.cycle_point(11, cycles=3) == (2, 4)
    data = b.write(tmp_path).read_bytes()
    assert struct.unpack("<5i", data[24:44]) == (25, 3, 7, 200, 5)
    assert struct.unpack("<d", data[44:52]) == (298.15,)
    back = Block.read(tmp_path / b.name)
    assert back == b and back.settings == s
    # Settings a program would refuse are refused on the way in.
    bad = data[:24] + struct.pack("<5i", 25, 101, 7, 200, 5) + data[44:]
    (tmp_path / b.name).write_bytes(bad)
    with pytest.raises(BlockError, match="itn is 101"):
        Block.read(tmp_path / b.name)


def test_a_file_of_the_wrong_size_or_framing_is_refused(tmp_path):
    p = tmp_path / "block-001-00001.dat"
    p.write_bytes(b"\0" * 75)
    with pytest.raises(BlockError, match="75 bytes, not 76"):
        Block.read(p)
    good = Block(1, 1, 1, 1, 1.0, 1.0, 0).write(tmp_path).read_bytes()
    p.write_bytes(b"\7" + good[1:])
    with pytest.raises(BlockError, match="record markers"):
        Block.read(p)


def test_round_robin_shares():
    assert BLOCKS_PER_SET == 400
    assert [len(expected_names(1, 3, w)) for w in (1, 2, 3)] == [134, 133, 133]
    assert len(expected_names(2, 1, 1)) == 800
    assert expected_names(1, 3, 0) == []  # the combining run owns nothing
    assert owned(1, 3, 1) and owned(2, 3, 2) and owned(4, 3, 1) and not owned(1, 3, 2)
    names = expected_names(1, 400, 400)
    assert names == ["block-001-00400.dat"]
    # At other settings the share is of itn * inp blocks.
    assert [len(expected_names(1, 4, w, 21)) for w in (1, 2, 3, 4)] == [6, 5, 5, 5]
    assert expected_names(1, 21, 21, 21) == ["block-001-00021.dat"]
