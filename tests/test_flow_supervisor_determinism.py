"""Stage 2C determinism and statelessness tests.

Input order must never change the result; the same instance must not leak
state across independent calls for different symbols or contract types.
"""

from __future__ import annotations

import random

from app.core.enums.flow_analysis import AnalystType
from app.core.enums.instrument import ContractType
from app.flow_supervisor.supervisor import DEFAULT_EXPECTED_ANALYSTS, FlowSupervisor
from tests.flow_supervisor_support import OTHER_SYMBOL, SYMBOL, analyzed_result, full_analyzed_set


def test_input_order_does_not_change_result() -> None:
    results = list(full_analyzed_set())
    shuffled = results[::-1]

    supervisor = FlowSupervisor()
    result_in_order = supervisor.aggregate(results)
    result_shuffled = supervisor.aggregate(shuffled)

    assert result_in_order == result_shuffled


def test_analyst_results_use_canonical_declaration_order() -> None:
    results = list(full_analyzed_set())
    random.Random(42).shuffle(results)

    result = FlowSupervisor().aggregate(results)

    provided_types = {r.analyst_type for r in results}
    expected_order = tuple(t for t in AnalystType if t in provided_types)
    assert tuple(r.analyst_type for r in result.analyst_results) == expected_order


def test_participation_tuples_use_canonical_order() -> None:
    result = FlowSupervisor().aggregate(full_analyzed_set())
    expected_order = tuple(t for t in AnalystType if t in DEFAULT_EXPECTED_ANALYSTS)
    assert result.analyzed_analysts == expected_order
    assert result.expected_analysts == expected_order


def test_repeated_calls_are_identical() -> None:
    results = full_analyzed_set()
    supervisor = FlowSupervisor()

    first = supervisor.aggregate(results)
    second = supervisor.aggregate(results)

    assert first == second


def test_same_instance_multiple_symbols_without_leakage() -> None:
    supervisor = FlowSupervisor()

    btc_results = full_analyzed_set(symbol=SYMBOL)
    eth_results = full_analyzed_set(symbol=OTHER_SYMBOL)

    btc_result = supervisor.aggregate(btc_results)
    eth_result = supervisor.aggregate(eth_results)

    assert btc_result.symbol == SYMBOL
    assert eth_result.symbol == OTHER_SYMBOL
    assert supervisor.expected_analysts == DEFAULT_EXPECTED_ANALYSTS

    # re-running the BTC aggregation after the ETH call must be unaffected
    btc_result_again = supervisor.aggregate(btc_results)
    assert btc_result_again == btc_result


def test_same_instance_multiple_contract_types_without_leakage() -> None:
    supervisor = FlowSupervisor()

    perpetual_results = (analyzed_result(AnalystType.TAKER_FLOW, contract_type=ContractType.PERPETUAL),)
    spot_results = (analyzed_result(AnalystType.TAKER_FLOW, contract_type=ContractType.SPOT),)

    perpetual_result = supervisor.aggregate(perpetual_results)
    spot_result = supervisor.aggregate(spot_results)

    assert perpetual_result.contract_type is ContractType.PERPETUAL
    assert spot_result.contract_type is ContractType.SPOT

    perpetual_result_again = supervisor.aggregate(perpetual_results)
    assert perpetual_result_again == perpetual_result
