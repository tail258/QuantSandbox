import pandas as pd
import pytest
from pydantic import ValidationError

from backend.api.schemas import StrategyConfig
from backend.core.strategy import StrategyFactory
from backend.core.strategy_catalog import normalize_parameters, strategy_catalog, strategy_defaults


@pytest.mark.parametrize("metadata", strategy_catalog(), ids=lambda item: item["name"])
def test_catalog_defaults_are_accepted_and_match_engine(metadata):
    name = metadata["name"]
    defaults = {p["key"]: p["default"] for p in metadata["parameters"]}
    assert StrategyConfig(name=name).parameters == defaults == strategy_defaults(name)
    frame = pd.DataFrame({"close": [100 + (i % 11) for i in range(80)]})
    pd.testing.assert_frame_equal(StrategyFactory.generate_signals(frame, name),
                                  StrategyFactory.generate_signals(frame, name, defaults))


def test_alias_collision_policies_and_metadata_are_stable():
    assert StrategyConfig(name="sma_cross", parameters={"fast": 3}).parameters == {"fast_period": 3, "slow_period": 20}
    assert StrategyConfig(name="rsi_reversion", parameters={"period": 7}).parameters["window"] == 7
    params = {"fast_period": 3, "fast": 4}
    assert normalize_parameters(params)["fast_period"] == 4
    assert normalize_parameters(params, canonical_wins=True)["fast_period"] == 3
    assert normalize_parameters({"period": 7, "lookback": 8}, canonical_wins=True)["window"] == 7
    changed = strategy_catalog()
    changed[0]["parameters"][0]["default"] = 99
    assert strategy_catalog()[0]["parameters"][0]["default"] == 5
    assert strategy_catalog()[0]["parameters"][0]["max"] == 500


def test_existing_api_parameter_boundaries_are_preserved():
    assert StrategyConfig(parameters={"fast_period": 499, "slow_period": 500})
    for parameters in [{"fast_period": 1}, {"slow_period": 501}, {"fast_period": 20}, {"unknown": 3}]:
        with pytest.raises(ValidationError):
            StrategyConfig(parameters=parameters)
    for name, parameters in [("rsi_reversal", {"buy_threshold": 0}), ("momentum", {"threshold": 1}),
                             ("bollinger_bands", {"std_dev": 0})]:
        with pytest.raises(ValidationError):
            StrategyConfig(name=name, parameters=parameters)
