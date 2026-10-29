"""A frozen clock where Enterich's today, in ENTERICH_TIMEZONE, is already tomorrow in UTC."""

from datetime import UTC, datetime, tzinfo

import pytest

from enterich import shapes

TIMEZONE = "Pacific/Kiritimati"  # UTC+14
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
TODAY = "2026-10-29"  # in Kiritimati at NOW; UTC is still at 2026-10-28


class Frozen(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:  # type: ignore[override]
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shapes, "datetime", Frozen)
