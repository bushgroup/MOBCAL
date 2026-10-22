"""mobcal.io.block: the 44-byte record, its name, and who owns which block."""

import pytest

from mobcal.io.block import BLOCKS_PER_SET, Block, BlockError, block_name, expected_names, owned


def test_write_and_read_back(tmp_path):
    b = Block(2, 7, 13, 5013489, 0.12345678901234567, 9.87654321e-3, 1)
    p = b.write(tmp_path)
    assert p == tmp_path / "block-002-0127.dat" and p.stat().st_size == 44
    assert b.k == 127 and b.name == block_name(2, 127)  # velocity-major: (13 - 1) * 10 + 7
    assert Block.cycle_point(127) == (7, 13) and Block.cycle_point(1) == (1, 1)
    assert Block.cycle_point(400) == (10, 40)
    assert Block.read(p) == b  # the doubles survive to the bit


def test_a_file_of_the_wrong_size_or_framing_is_refused(tmp_path):
    p = tmp_path / "block-001-0001.dat"
    p.write_bytes(b"\0" * 43)
    with pytest.raises(BlockError, match="43 bytes, not 44"):
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
    assert names == ["block-001-0400.dat"]
