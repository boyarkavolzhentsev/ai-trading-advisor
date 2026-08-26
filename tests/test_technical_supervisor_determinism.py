"""Stage 3C determinism and statelessness tests.

Input order must never change the result; the same instance must not leak
state across independent calls for different symbols or contract types.
"""

from __future__ import annotations

import random

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.technical_analysis import TechnicalAnalystType
from app.technical_supervisor.supervisor import DEFAULT_EXPECTED_ANALYSTS, DEFAULT_EXPECTED_TIMEFRAMES, TechnicalSupervisor
from tests.technical_supervisor_support import OTHER_SYMBOL, SYMBOL, analyzed_result, full_matrix


def test_input_order_does_not_change_result() -> None:
    results = list(full_matrix())
    reversed_results = results[::-1]

    supervisor = TechnicalSupervisor()

    assert supervisor.aggregate(results) == supervisor.aggregate(reversed_results)


def test_input_order_does_not_change_result_random_shuffle() -> None:
    results = list(full_matrix())
    shuffled = list(results)
    random.Random(42).shuffle(shuffled)

    supervisor = TechnicalSupervisor()

    assert supervisor.aggregate(results) == supervisor.aggregate(shuffled)


def test_analyst_results_use_timeframe_major_analyst_minor_canonical_order() -> None:
    results = list(full_matrix())
    random.Random(7).shuffle(results)

    result = TechnicalSupervisor().aggregate(results)

    expected_order = tuple((a, t) for t in DEFAULT_EXPECTED_TIMEFRAMES for a in DEFAULT_EXPECTED_ANALYSTS)
    actual_order = tuple((r.analyst_type, r.timeframe) for r in result.analyst_results)
    assert actual_order == expected_order


def test_repeated_calls_are_identical() -> None:
    results = full_matrix()
    supervisor = TechnicalSupervisor()

    assert supervisor.aggregate(results) == supervisor.aggregate(results)


def test_same_instance_multiple_symbols_without_leakage() -> None:
    supervisor = TechnicalSupervisor()

    btc_results = full_matrix(symbol=SYMBOL)
    eth_results = full_matrix(symbol=OTHER_SYMBOL)

    btc_result = supervisor.aggregate(btc_results)
    eth_result = supervisor.aggregate(eth_results)

    assert btc_result.symbol == SYMBOL
    assert eth_result.symbol == OTHER_SYMBOL
    assert supervisor.expected_analysts == DEFAULT_EXPECTED_ANALYSTS

    btc_result_again = supervisor.aggregate(btc_results)
    assert btc_result_again == btc_result


def test_same_instance_multiple_contract_types_without_leakage() -> None:
    supervisor = TechnicalSupervisor(expected_analysts=(TechnicalAnalystType.TREND,), expected_timeframes=(Timeframe.M1,))

    perpetual_results = (analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, contract_type=ContractType.PERPETUAL),)
    spot_results = (analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, contract_type=ContractType.SPOT),)

    perpetual_result = supervisor.aggregate(perpetual_results)
    spot_result = supervisor.aggregate(spot_results)

    assert perpetual_result.contract_type is ContractType.PERPETUAL
    assert spot_result.contract_type is ContractType.SPOT

    perpetual_result_again = supervisor.aggregate(perpetual_results)
    assert perpetual_result_again == perpetual_result
