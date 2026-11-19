"""Names compare as ERPNext's tables compare them (REQ-001-PRS-F027). The fake ERPNext folds
names the same way, so only this table, taken from MariaDB's utf8mb4_unicode_ci on the
end-to-end site, shows a fold that strays from the database."""

import pytest

from enterich.tools.drafts import folded

# Each pair as `SELECT a = b COLLATE utf8mb4_unicode_ci` answered it
ALIKE = [
    ("Müller GmbH", "Muller GmbH"),
    ("straße", "strasse"),
    ("SKU-1", "sku-1"),
    ("SKU-1 ", "SKU-1"),
    ("Åsa", "Asa"),
    ("ﬁsh", "fish"),
    ("\uff33\uff2b\uff35", "SKU"),  # full-width
]
APART = [
    ("Sørensen", "Sorensen"),
    ("Łódź", "Lodz"),
    ("Æbeltoft", "Aebeltoft"),
    ("Đorđe", "Dorde"),
    ("Þór", "Thor"),
    ("\u0131", "i"),  # dotless
    (" SKU-1", "SKU-1"),
]


@pytest.mark.parametrize(("given", "stored"), ALIKE)
def test_names_the_database_takes_as_one_fold_alike(given: str, stored: str) -> None:
    assert folded(given) == folded(stored)


@pytest.mark.parametrize(("given", "stored"), APART)
def test_names_the_database_keeps_apart_fold_apart(given: str, stored: str) -> None:
    assert folded(given) != folded(stored)
