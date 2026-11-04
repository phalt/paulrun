"""Tests for the helpers that match run's terminal output."""

from tests.output import normalized, overview

FOLDED = """\
╭─ One ────────────────╮
│ directory  /tmp/aaaa │
│            bbbb      │
│ steps      1. Only   │
│            2. Next   │
╰──────────────────────╯
"""


def test_normalized_drops_the_rows_a_long_directory_folds_onto():
    """A directory that carries on over more rows is DIR once, and the rows after it are left alone."""
    assert normalized(FOLDED) == "╭─ One ─╮\n│ directory  DIR │\n│ steps      1. Only │\n│            2. Next │\n╰─╯\n"


def test_overview_puts_each_row_a_value_takes_under_its_label():
    """Rows with no label belong to the row above, so a folded directory can be joined back up."""
    assert overview(FOLDED) == {"directory": ["/tmp/aaaa", "bbbb"], "steps": ["1. Only", "2. Next"]}
