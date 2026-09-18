from backend.assistant import plan_research
import pytest


def test_chinese_research_command_is_explicit_and_repeatable():
    prompt = "用五粮液和中国平安，双均线，快线 8 慢线 30，2023到2025年，本金20万，仓位25%，滑点10基点"
    plan = plan_research(prompt)
    assert plan == plan_research(prompt)
    config = plan["config"]
    assert config["tickers"] == ["000858", "601318"]
    assert config["strategy"]["parameters"] == {"fast_period": 8, "slow_period": 30}
    assert config["start_date"] == "2023-01-01"
    assert config["account"]["initial_cash"] == 200000
    assert config["account"]["position_size"] == .25
    assert config["account"]["slippage_bps"] == 10
    assert plan["mode"] == "local_rules"


def test_unknown_command_does_not_pretend_to_understand():
    assert not plan_research("预测明天哪个股票涨停")["recognized"]


def test_base_config_is_never_mutated():
    config = {"strategy": {"name": "dual_ma", "parameters": {"fast_period": 4, "slow_period": 18}}}
    plan = plan_research("慢线30", config)
    assert config["strategy"]["parameters"]["slow_period"] == 18
    assert plan["config"]["strategy"]["parameters"]["slow_period"] == 30


def test_strategy_switch_drops_incompatible_parameters():
    plan = plan_research("布林带窗口25，慢线30")
    assert plan["config"]["strategy"]["parameters"] == {"window": 25, "std_dev": 2}
    assert plan["warnings"]


def test_invalid_empty_or_oversize_input_is_rejected():
    for prompt in ["", " " * 4, "x" * 1001]:
        with pytest.raises(ValueError):
            plan_research(prompt)
