"""Models share the same fit/predict interface; score distributions are optional."""

from epl_forecast.models.baselines import AttackDefensePoisson, LeagueFrequency, LeaguePoisson
from epl_forecast.models.dynamic import DynamicAttackDefense
from epl_forecast.models.elo import EloOrderedLogit

MODEL_TYPES = {
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
    try:
        return model_type(**spec.get("parameters", {}))
    except TypeError as error:
        raise ValueError(f"Invalid parameters for {spec['kind']}: {error}") from error
