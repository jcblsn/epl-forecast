from datetime import date

import numpy as np
import pytest
from test_player_layer import history, population

from epl_forecast.research.portable_players import PortablePlayerLayer


def evidence_rows(rows, **evidence):
    return [
        dict(
            row,
            process_evidence=[
                {
                    "retrieved_at": row["retrieved_at"],
                    "evidence_basis": "retrospective",
                    "source_sha256": row["match_id"],
                    **evidence,
                }
            ],
        )
        for row in rows
    ]


def test_portable_distribution_preserves_traits_and_exposure_uncertainty():
    rows = evidence_rows(
        [
            *population(length=40),
            *history("shooter", 30, process_xg=1.2, process_xa=0.01),
            *history("creator", 30, process_xg=0.01, process_xa=1.2),
            *history("thin", 1, process_xg=1.2, process_xa=0.01),
        ]
    )
    layer = PortablePlayerLayer(rows, "snapshot")
    cutoff = date(2025, 8, 1)
    shooter, creator, thin = [layer.freeze(pid, cutoff) for pid in ("shooter", "creator", "thin")]
    assert shooter.traits[0].mean > creator.traits[0].mean
    assert shooter.traits[1].mean < creator.traits[1].mean
    assert (
        thin.traits[0].variance / thin.traits[0].mean ** 2
        > shooter.traits[0].variance / shooter.traits[0].mean ** 2
    )
    draws = shooter.sample(50000, np.random.default_rng(7))
    assert draws.shape == (50000, 2)
    assert draws.mean(axis=0) == pytest.approx([t.mean for t in shooter.traits], rel=0.02)
    assert shooter.as_dict()["snapshot_sha256"] == "snapshot"
    assert shooter.traits[0].source_hashes


def test_late_process_payload_cannot_borrow_api_appearance_timing():
    pool = evidence_rows(population(length=40))
    player = evidence_rows(
        history("p1", 10), evidence_basis="captured", retrieved_at="2025-07-01T00:00:00+00:00"
    )
    layer = PortablePlayerLayer([*pool, *player], "snapshot")
    before = layer.freeze("p1", date(2025, 6, 1))
    after = layer.freeze("p1", date(2025, 8, 1))
    assert before.traits[0].appearances == 0
    assert before.traits[0].source_hashes == ()
    assert before.evidence_audit["late_process"] == 10
    assert after.traits[0].appearances == 10


def test_future_roster_or_process_does_not_change_a_frozen_trait():
    rows = evidence_rows([*population(length=40), *history("p1", 10)])
    cutoff = date(2025, 6, 1)
    expected = PortablePlayerLayer(rows, "snapshot").freeze("p1", cutoff)
    future = evidence_rows(history("p1", 10, date(2026, 1, 1), team="chelsea", process_xg=20))
    actual = PortablePlayerLayer([*rows, *future], "snapshot").freeze("p1", cutoff)
    assert actual.as_dict() == expected.as_dict()


def test_unknown_process_is_audited_without_normalizing_raw_evidence():
    rows = evidence_rows([*population(length=40), *history("p1", 10, process_xa=None)])
    actual = PortablePlayerLayer(rows, "snapshot").freeze("p1", date(2025, 6, 1))
    assert actual.traits[0].appearances == 0
    assert actual.evidence_audit["unknown_process"] == 10
    assert rows[-1]["process_records"] == 1
    assert rows[-1]["process_xa"] is None


def test_portable_player_keeps_identity_across_clubs_and_supports_cold_start():
    rows = evidence_rows(
        [
            *population(length=40),
            *history("mover", 10),
            *history("mover", 10, date(2025, 1, 1), team="chelsea"),
        ]
    )
    layer = PortablePlayerLayer(rows, "snapshot")
    cutoff = date(2025, 6, 1)
    assert layer.freeze("mover", cutoff).traits[0].appearances == 20
    unknown = layer.freeze("unknown", cutoff)
    assert unknown.role == "UNK"
    assert all(t.mean > 0 and t.variance > 0 and t.staleness_days is None for t in unknown.traits)
