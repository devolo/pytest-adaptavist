import pytest


def test_T1(meta_block):
    with meta_block(1) as mb_1:
        mb_1.check(True)


@pytest.mark.xfail
def test_T2(meta_block):
    with meta_block(1) as mb_1:
        mb_1.check(False)


@pytest.mark.xfail
def test_T3(meta_block):
    with meta_block(1) as mb_1:
        mb_1.check(True)
    with meta_block(2) as mb_2:
        mb_2.check(False)


def test_T4(meta_block):
    with meta_block(1) as mb_1:
        mb_1.check(True)
    with meta_block(2) as mb_2:
        pytest.block("Testing block")  # pylint: disable=no-member
        mb_2.check(False)


@pytest.mark.block("TESTING BLOCK DECORATOR")
def test_T5(meta_block):
    with meta_block(1) as mb_1:
        mb_1.check(False)
