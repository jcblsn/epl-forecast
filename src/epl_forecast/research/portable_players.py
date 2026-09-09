"""Versioned attacking-trait distributions independent of a team forecasting model."""

from dataclasses import asdict, dataclass
from datetime import date

import numpy as np

from epl_forecast.research.player_layer import (
    LayerConfig,
    PlayerLayer,
    observation_rows,
)
from epl_forecast.research.player_prior import london_date

INTERFACE_VERSION = "portable-attacking-traits-v1"
TRAITS = ("shooting", "creation")
MARKS = ("xg", "xa")


def portable_observation_rows(data):
    rows = observation_rows(data)
    evidence = {}
    for row in data.rows(
        "SELECT match_id, player_id, retrieved_at, evidence_basis, source_sha256 "
        "FROM player_process WHERE player_id IS NOT NULL"
    ):
        evidence.setdefault((row["match_id"], row["player_id"]), []).append(row)
    return [
        dict(row, process_evidence=evidence.get((row["match_id"], row["player_id"]), []))
        for row in rows
    ]


@dataclass(frozen=True)
class TraitDistribution:
    name: str
    mark: str
    shape: float
    scale: float
    effective_matches: float
    appearances: int
    staleness_days: int | None
    prior_mean: float
    source_hashes: tuple[str, ...]

    @property
    def mean(self):
        return self.shape * self.scale

    @property
    def variance(self):
        return self.shape * self.scale**2


@dataclass(frozen=True)
class PortablePlayer:
    player_id: str
    cutoff: date
    role: str
    traits: tuple[TraitDistribution, ...]
    snapshot_sha256: str
    config: LayerConfig
    evidence_audit: dict
    version: str = INTERFACE_VERSION

    def sample(self, paths, generator):
        if paths <= 0:
            raise ValueError("A positive number of paths is required")
        return generator.gamma(
            [trait.shape for trait in self.traits],
            [trait.scale for trait in self.traits],
            size=(paths, len(self.traits)),
        )

    def as_dict(self):
        return {
            **asdict(self),
            "cutoff": str(self.cutoff),
            "units": "process per 90 minutes",
            "distribution": "independent Gamma component marginals conditional on role population",
            "mean": [trait.mean for trait in self.traits],
            "covariance": np.diag([trait.variance for trait in self.traits]).tolist(),
            "uncertainty_scope": "Exposure-weighted rate uncertainty; shared population and cross-trait covariance are not estimated. These are latent rate distributions, not future realized-process intervals.",
        }


class PortablePlayerLayer:
    """Freeze long-horizon process rates with provider-specific evidence timing.

    Historical replay admits explicitly retrospective records after the match date.
    Captured observations also wait for their own provider retrieval date. A late
    Understat payload cannot borrow eligibility from an earlier API appearance.
    """

    def __init__(self, rows, snapshot_sha256, config=None):
        if not snapshot_sha256:
            raise ValueError("Portable traits require a retained snapshot fingerprint")
        self.rows = list(rows)
        self.snapshot_sha256 = snapshot_sha256
        self.config = config or LayerConfig()
        self._cutoffs = {}

    def _at(self, cutoff):
        if cutoff in self._cutoffs:
            return self._cutoffs[cutoff]
        eligible, audit = (
            [],
            {
                "late_process": 0,
                "unknown_process": 0,
                "retrospective_process": 0,
                "captured_process": 0,
            },
        )
        for row in self.rows:
            if london_date(row["kickoff_time"]) >= cutoff:
                continue
            if (
                row.get("evidence_basis") != "retrospective"
                and london_date(row["retrieved_at"]) >= cutoff
            ):
                continue
            evidence = row.get("process_evidence", [])
            copied = dict(row)
            valid = len(evidence) == 1 and row.get("process_records") == 1
            valid = valid and all(
                row.get(field) is not None and np.isfinite(row[field]) and row[field] >= 0
                for field in ("process_xg", "process_xa", "process_shots")
            )
            if not valid:
                copied["process_records"] = None
                audit["unknown_process"] += 1
            elif (
                evidence[0]["evidence_basis"] != "retrospective"
                and london_date(evidence[0]["retrieved_at"]) >= cutoff
            ):
                copied["process_records"] = None
                audit["late_process"] += 1
            else:
                key = (
                    "retrospective_process"
                    if evidence[0]["evidence_basis"] == "retrospective"
                    else "captured_process"
                )
                audit[key] += 1
            eligible.append(copied)
        if not eligible:
            raise ValueError("No eligible appearance history at the requested cutoff")
        layer = PlayerLayer(eligible, self.config)
        if any(layer.population(cutoff.toordinal(), mark)["league"] <= 0 for mark in MARKS):
            raise ValueError("Both attacking traits require an eligible nonzero process population")
        self._cutoffs = {cutoff: (layer, audit)}
        return layer, audit

    def freeze(self, player_id, cutoff):
        layer, audit = self._at(cutoff)
        day = cutoff.toordinal()
        role = layer.role(player_id, day)
        traits = []
        indices = layer.by_player.get(player_id, np.array([], dtype=int))
        for name, mark in zip(TRAITS, MARKS, strict=True):
            entry = layer.aggregate(player_id, day, mark, self.config.long_half_life)
            population = layer.population(day, mark)
            dispersion = max(population["dispersion"], 1e-3)
            prior_mean = max(population["by_role"].get(role, population["league"]), 1e-6)
            shape = (entry["total"] + self.config.rate_prior_matches * prior_mean) / dispersion
            scale = dispersion / (entry["exposure"] + self.config.rate_prior_matches)
            sources = {
                record["source_sha256"]
                for i in indices[layer.available[mark][indices]]
                for record in layer.rows[i]["process_evidence"]
                if record.get("source_sha256")
            }
            traits.append(
                TraitDistribution(
                    name=name,
                    mark=mark,
                    shape=float(shape),
                    scale=float(scale),
                    effective_matches=entry["exposure"],
                    appearances=entry["appearances"],
                    staleness_days=cutoff.toordinal() - entry["last_day"]
                    if entry["last_day"] is not None
                    else None,
                    prior_mean=prior_mean,
                    source_hashes=tuple(sorted(sources)),
                )
            )
        return PortablePlayer(
            player_id,
            cutoff,
            role,
            tuple(traits),
            self.snapshot_sha256,
            self.config,
            dict(audit),
        )
