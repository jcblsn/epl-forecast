from datetime import UTC, datetime, timedelta

from epl_forecast.pipeline import due, snapshot_id

NOW = datetime(2026, 9, 10, 22, 43, 3, tzinfo=UTC)


def test_snapshot_id_is_a_sortable_second():
    assert snapshot_id(NOW) == "2026-09-10T224303Z"


def test_new_information_or_a_stale_publication_is_due():
    state = {"fingerprint": "abc", "published_at": NOW.isoformat()}
    assert not due(state, "abc", NOW + timedelta(hours=6), 12)
    assert due(state, "def", NOW + timedelta(hours=6), 12)
    assert due(state, "abc", NOW + timedelta(hours=12), 12)
    assert due({}, "abc", NOW, 12)
    assert due({"fingerprint": "abc"}, "abc", NOW, 12)
