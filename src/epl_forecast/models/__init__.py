"""Models share the same fit/predict interface; score distributions are optional."""

from epl_forecast.models.baselines import AttackDefensePoisson, LeagueFrequency, LeaguePoisson
from epl_forecast.models.centered_quality_tilt import CenteredQualityTiltFilter
from epl_forecast.models.dynamic import DynamicAttackDefense
from epl_forecast.models.elo import EloOrderedLogit
from epl_forecast.models.process_quality_tilt import BayesianProcessQualityTilt
from epl_forecast.models.quality_tilt import BayesianQualityTilt
from epl_forecast.models.xg_quality_tilt import BayesianXGQualityTilt

MODEL_TYPES = {
    "bayesian_process_quality_tilt": BayesianProcessQualityTilt,
    "centered_quality_tilt": CenteredQualityTiltFilter,
    "bayesian_xg_quality_tilt": BayesianXGQualityTilt,
    "bayesian_quality_tilt": BayesianQualityTilt,
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
        return model
    except TypeError as error:
        raise ValueError(f"Invalid parameters for {spec['kind']}: {error}") from error
