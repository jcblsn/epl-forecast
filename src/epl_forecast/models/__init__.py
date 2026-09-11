"""Models share the same fit/predict interface; score distributions are optional."""

from epl_forecast.models.baselines import AttackDefensePoisson, LeagueFrequency, LeaguePoisson
from epl_forecast.models.centered_quality_tilt import CenteredQualityTiltFilter
from epl_forecast.models.cross_division import CrossDivisionQualityTilt, CrossDivisionXG
from epl_forecast.models.division_map import DivisionMapQualityTilt, DivisionMapXG
from epl_forecast.models.dynamic import RELEGATION_ENTRY, DynamicAttackDefense
from epl_forecast.models.elo import EloOrderedLogit
from epl_forecast.models.entry_prior import LABELS, LEVELS
from epl_forecast.models.process_quality_tilt import BayesianProcessQualityTilt
from epl_forecast.models.quality_tilt import BayesianQualityTilt, QualityTiltFilter
from epl_forecast.models.xg_quality_tilt import BayesianXGQualityTilt

MODEL_TYPES = {
    "bayesian_process_quality_tilt": BayesianProcessQualityTilt,
    "division_map_quality_tilt": DivisionMapQualityTilt,
    "division_map_xg": DivisionMapXG,
    "cross_division_quality_tilt": CrossDivisionQualityTilt,
    "cross_division_xg": CrossDivisionXG,
    "centered_quality_tilt": CenteredQualityTiltFilter,
    "bayesian_xg_quality_tilt": BayesianXGQualityTilt,
    "bayesian_quality_tilt": BayesianQualityTilt,
    "quality_tilt": QualityTiltFilter,
    "league_frequency": LeagueFrequency,
    "league_poisson": LeaguePoisson,
    "attack_defense_poisson": AttackDefensePoisson,
    "elo_ordered_logit": EloOrderedLogit,
    "dynamic_attack_defense": DynamicAttackDefense,
}


def make_model(spec: dict):
    try:
        model_type = MODEL_TYPES[spec["kind"]]
    except KeyError as error:
        raise ValueError(f"Unknown model kind: {spec.get('kind')}") from error
    parameters = dict(spec.get("parameters", {}))
    competition = parameters.pop("competition_id", "eng-premier-league")
    relegation_entry = parameters.pop("relegation_entry", None)
    entry_prior = parameters.pop("entry_prior", None)
    entry_prior_label = parameters.pop("entry_prior_label", None)
    if entry_prior is not None and entry_prior not in (*LEVELS, "retained_state"):
        raise ValueError(f"Unknown entry-prior rule: {entry_prior}")
    if entry_prior_label is not None and entry_prior_label not in LABELS:
        raise ValueError(f"Unknown entry-prior training label: {entry_prior_label}")
    data_root = parameters.pop("data_root", None)
    if data_root is not None:
        from epl_forecast.datasets import Dataset

        data = Dataset(data_root, parameters.pop("data_cutoff", None))
        try:
            parameters["observations"] = data.process()
        finally:
            data.close()
    try:
        model = model_type(**parameters)
        for member in getattr(model, "members", [model]):
            if hasattr(member, "primary_competition"):
                member.primary_competition = competition
            if relegation_entry is not None and hasattr(member, "relegation_entry"):
                if relegation_entry not in RELEGATION_ENTRY:
                    raise ValueError(f"Unknown relegation entry treatment: {relegation_entry}")
                member.relegation_entry = relegation_entry
            if entry_prior is not None and hasattr(member, "entry_prior"):
                member.entry_prior = None if entry_prior == "retained_state" else entry_prior
            if entry_prior_label is not None and hasattr(member, "entry_prior_label"):
                member.entry_prior_label = entry_prior_label
        return model
    except TypeError as error:
        raise ValueError(f"Invalid parameters for {spec['kind']}: {error}") from error
