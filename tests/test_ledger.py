from test_publication import sample_forecast, sample_run

from epl_forecast.ledger import build_ledger, pre_kickoff_forecasts, realized_outcomes
from epl_forecast.publication import derive_forecast, load_policy, publish_document

MATCH = "eng-premier-league:2026-2027:arsenal:chelsea"


def publish(site, generated, snapshot, p_home=0.5):
    forecast = sample_forecast(generated=generated)
    forecast["matches"][0].update(p_home=p_home, p_draw=(1 - p_home) / 2, p_away=(1 - p_home) / 2)
    document = derive_forecast(forecast, sample_run(), snapshot)
    publish_document(site, document, load_policy())
    return document


def test_realized_outcomes_reads_finished_fixtures():
    fixtures = [
        {"match_id": "a", "status": "finished", "home_goals": 2, "away_goals": 1},
        {"match_id": "b", "status": "finished", "home_goals": 1, "away_goals": 1},
        {"match_id": "c", "status": "finished", "home_goals": 0, "away_goals": 3},
        {"match_id": "d", "status": "scheduled", "home_goals": None, "away_goals": None},
    ]
    assert realized_outcomes(fixtures) == {"a": "H", "b": "D", "c": "A"}


def test_the_last_pre_kickoff_forecast_scores_the_match(tmp_path):
    publish(tmp_path, "2026-09-10T12:00:00+00:00", "2026-09-10T120000Z", p_home=0.5)
    publish(tmp_path, "2026-09-12T06:00:00+00:00", "2026-09-12T060000Z", p_home=0.6)
    publish(tmp_path, "2026-09-12T18:00:00+00:00", "2026-09-12T180000Z", p_home=0.9)
    forecasts = pre_kickoff_forecasts(tmp_path)
    assert forecasts[MATCH]["snapshot_id"] == "2026-09-12T060000Z"
    assert forecasts[MATCH]["p_home"] == 0.6


def test_ledger_scores_settled_matches_and_counts_the_rest(tmp_path):
    publish(tmp_path, "2026-09-10T12:00:00+00:00", "2026-09-10T120000Z", p_home=0.5)
    ledger = build_ledger(tmp_path, {MATCH: "H"}, load_policy())
    assert ledger["unsettled"] == 0
    assert ledger["summary"]["overall"]["scored"] == 1
    assert ledger["summary"]["overall"]["log_loss"] > 0
    assert ledger["settled"][0]["outcome"] == "H"
    assert ledger["pending_season_snapshots"][0]["season_id"] == "2026-2027"

    empty = build_ledger(tmp_path, {}, load_policy())
    assert empty["unsettled"] == 1
    assert empty["summary"] == {}


def test_a_sharper_forecast_scores_better(tmp_path):
    publish(tmp_path, "2026-09-10T12:00:00+00:00", "2026-09-10T120000Z", p_home=0.9)
    sharp = build_ledger(tmp_path, {MATCH: "H"}, load_policy())["summary"]["overall"]
    other = tmp_path / "other"
    publish(other, "2026-09-10T12:00:00+00:00", "2026-09-10T120000Z", p_home=0.2)
    blunt = build_ledger(other, {MATCH: "H"}, load_policy())["summary"]["overall"]
    assert sharp["log_loss"] < blunt["log_loss"]
    assert sharp["brier"] < blunt["brier"]


def test_rebuilding_the_ledger_reproduces_it(tmp_path):
    publish(tmp_path, "2026-09-10T12:00:00+00:00", "2026-09-10T120000Z")
    first = build_ledger(tmp_path, {MATCH: "D"}, load_policy())
    written = (tmp_path / "data" / "ledger.json").read_bytes()
    second = build_ledger(tmp_path, {MATCH: "D"}, load_policy())
    assert first == second
    assert (tmp_path / "data" / "ledger.json").read_bytes() == written
