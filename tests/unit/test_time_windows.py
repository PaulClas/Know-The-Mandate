"""Budget windows are calendar days/months in the mandate's IANA zone. Check them across DST transitions and month ends (open item O-20)."""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from kym import policy

ZONES = ["America/Toronto", "Europe/London", "Australia/Lord_Howe", "America/St_Johns", "Asia/Kolkata", "Pacific/Auckland", "UTC"]
instants = st.datetimes(min_value=datetime(2024, 1, 1), max_value=datetime(2031, 12, 31), timezones=st.just(UTC))


@settings(max_examples=300, deadline=None)
@given(now=instants, zone=st.sampled_from(ZONES))
def test_windows_contain_now_start_at_local_midnight_and_are_contiguous(now, zone):
    tz = ZoneInfo(zone)
    w = policy.window_bounds(now, zone)
    (d0, d1), (m0, m1) = w["day"], w["month"]
    assert d0 <= now < d1 and m0 <= now < m1 and m0 <= d0 and d1 <= m1
    for edge in (d0, d1, m0, m1):
        local = edge.astimezone(tz)
        assert (local.hour, local.minute, local.second) == (0, 0, 0)  # every boundary is local midnight
    assert m0.astimezone(tz).day == 1 and m1.astimezone(tz).day == 1
    assert policy.window_bounds(d1, zone)["day"][0] == d1  # the next day starts exactly where this one ends: no gap, no overlap
    assert timedelta(hours=22) <= d1 - d0 <= timedelta(hours=26)


@pytest.mark.parametrize("zone,day,hours", [("America/Toronto", datetime(2026, 3, 8, 15, tzinfo=UTC), 23), ("America/Toronto", datetime(2026, 11, 1, 15, tzinfo=UTC), 25),
                                             ("Australia/Lord_Howe", datetime(2026, 4, 5, 3, tzinfo=UTC), 24.5)])
def test_dst_days_have_the_real_length(zone, day, hours):
    d0, d1 = policy.window_bounds(day, zone)["day"]
    assert (d1 - d0) == timedelta(hours=hours)


def test_month_end_rolls_into_the_next_month_and_year():
    m0, m1 = policy.window_bounds(datetime(2026, 12, 31, 23, 30, tzinfo=ZoneInfo("America/Toronto")), "America/Toronto")["month"]
    assert m0.astimezone(ZoneInfo("America/Toronto")) == datetime(2026, 12, 1, tzinfo=ZoneInfo("America/Toronto"))
    assert m1.astimezone(ZoneInfo("America/Toronto")) == datetime(2027, 1, 1, tzinfo=ZoneInfo("America/Toronto"))
    feb = policy.window_bounds(datetime(2028, 2, 29, 12, tzinfo=UTC), "UTC")["month"]  # leap year
    assert feb[1] == datetime(2028, 3, 1, tzinfo=UTC)
