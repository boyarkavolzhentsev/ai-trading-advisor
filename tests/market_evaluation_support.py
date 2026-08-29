"""Shared builders for Stage 5A market-evaluation tests.

Builds real ``FlowSupervisorResult``/``TechnicalSupervisorResult``/
``ExternalIntelligenceSupervisorResult`` fixtures via their own already-
tested supervisors (reusing ``tests/flow_supervisor_support.py``,
``tests/technical_supervisor_support.py``,
``tests/external_intelligence_supervisor_support.py``) rather than
hand-rolling supervisor-result objects: Stage 5A aggregates already-produced
supervisor contracts, independent of how those contracts were produced. Not
a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.enums.flow_analysis import AnalystType as FlowAnalystType
from app.core.enums.instrument import ContractType
from app.core.enums.technical_analysis import TechnicalAnalystType
from app.core.models.base import Timestamp
from app.core.models.external_intelligence_analysis_result import ExternalIntelligenceAnalysisResult
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor
from app.flow_supervisor.supervisor import DEFAULT_EXPECTED_ANALYSTS as FLOW_DEFAULT_ANALYSTS
from app.flow_supervisor.supervisor import FlowSupervisor
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.external_intelligence_supervisor_support import analyzed_result as ext_analyzed_result
from tests.external_intelligence_supervisor_support import abstained_result as ext_abstained_result
from tests.external_intelligence_supervisor_support import full_analyzed_set as ext_full_analyzed_set
from tests.flow_supervisor_support import abstained_result as flow_abstained_result_
from tests.flow_supervisor_support import analyzed_result as flow_analyzed_result_
from tests.flow_supervisor_support import full_analyzed_set as flow_full_analyzed_set
from tests.technical_supervisor_support import DEFAULT_ANALYSTS as TECHNICAL_DEFAULT_ANALYSTS
from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES as TECHNICAL_DEFAULT_TIMEFRAMES
from tests.technical_supervisor_support import abstained_result as technical_abstained_result_
from tests.technical_supervisor_support import analyzed_result as technical_analyzed_result_
from tests.technical_supervisor_support import full_matrix as technical_full_matrix

NOW: Timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

SYMBOL = "BTCUSDT"
OTHER_SYMBOL = "ETHUSDT"
CONTRACT_TYPE = ContractType.PERPETUAL
OTHER_CONTRACT_TYPE = ContractType.SPOT

ASSET = "BTC"
OTHER_ASSET = "ETH"
NETWORK = "bitcoin"
OTHER_NETWORK = "ethereum"
CURRENCY = "USD"
OTHER_CURRENCY = "EUR"


def make_context(**overrides: object) -> MarketEvaluationContext:
    fields: dict[str, object] = {"symbol": SYMBOL, "contract_type": CONTRACT_TYPE}
    fields.update(overrides)
    return MarketEvaluationContext(**fields)


# --- Flow ---


def full_flow_result(
    *, symbol: str = SYMBOL, contract_type: ContractType = CONTRACT_TYPE, observation_time: Timestamp = NOW
) -> FlowSupervisorResult:
    return FlowSupervisor().aggregate(
        flow_full_analyzed_set(symbol=symbol, contract_type=contract_type, observation_time=observation_time)
    )


def partial_flow_result(
    *, symbol: str = SYMBOL, contract_type: ContractType = CONTRACT_TYPE, observation_time: Timestamp = NOW
) -> FlowSupervisorResult:
    return FlowSupervisor().aggregate(
        (flow_analyzed_result_(FlowAnalystType.TAKER_FLOW, symbol=symbol, contract_type=contract_type, observation_time=observation_time),)
    )


def insufficient_flow_result(
    *, symbol: str = SYMBOL, contract_type: ContractType = CONTRACT_TYPE, observation_time: Timestamp = NOW
) -> FlowSupervisorResult:
    return FlowSupervisor().aggregate(
        (flow_abstained_result_(FlowAnalystType.TAKER_FLOW, symbol=symbol, contract_type=contract_type, observation_time=observation_time),)
    )


# --- Technical ---


def full_technical_result(
    *, symbol: str = SYMBOL, contract_type: ContractType = CONTRACT_TYPE, observation_time: Timestamp = NOW
) -> TechnicalSupervisorResult:
    return TechnicalSupervisor().aggregate(
        technical_full_matrix(symbol=symbol, contract_type=contract_type, observation_time=observation_time)
    )


def partial_technical_result(
    *, symbol: str = SYMBOL, contract_type: ContractType = CONTRACT_TYPE, observation_time: Timestamp = NOW
) -> TechnicalSupervisorResult:
    return TechnicalSupervisor().aggregate(
        (
            technical_analyzed_result_(
                TechnicalAnalystType.TREND,
                TECHNICAL_DEFAULT_TIMEFRAMES[0],
                symbol=symbol,
                contract_type=contract_type,
                observation_time=observation_time,
            ),
        )
    )


def insufficient_technical_result(
    *, symbol: str = SYMBOL, contract_type: ContractType = CONTRACT_TYPE, observation_time: Timestamp = NOW
) -> TechnicalSupervisorResult:
    return TechnicalSupervisor().aggregate(
        (
            technical_abstained_result_(
                TechnicalAnalystType.TREND,
                TECHNICAL_DEFAULT_TIMEFRAMES[0],
                symbol=symbol,
                contract_type=contract_type,
                observation_time=observation_time,
            ),
        )
    )


# --- External Intelligence ---


def full_external_result(*, analysis_time: Timestamp = NOW) -> ExternalIntelligenceSupervisorResult:
    return ExternalIntelligenceSupervisor().aggregate(ext_full_analyzed_set(analysis_time=analysis_time), analysis_time=analysis_time)


def partial_external_result(*, analysis_time: Timestamp = NOW) -> ExternalIntelligenceSupervisorResult:
    return ExternalIntelligenceSupervisor().aggregate(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, analysis_time=analysis_time),),
        analysis_time=analysis_time,
    )


def insufficient_external_result(*, analysis_time: Timestamp = NOW) -> ExternalIntelligenceSupervisorResult:
    return ExternalIntelligenceSupervisor().aggregate(
        (ext_abstained_result(ExternalIntelligenceAnalystType.MACRO_EVENT, analysis_time=analysis_time),),
        analysis_time=analysis_time,
    )


def external_result_with_scopes(
    results: tuple[ExternalIntelligenceAnalysisResult, ...], *, analysis_time: Timestamp = NOW
) -> ExternalIntelligenceSupervisorResult:
    return ExternalIntelligenceSupervisor().aggregate(results, analysis_time=analysis_time)


__all__ = [
    "ASSET",
    "CONTRACT_TYPE",
    "CURRENCY",
    "FLOW_DEFAULT_ANALYSTS",
    "NETWORK",
    "NOW",
    "OTHER_ASSET",
    "OTHER_CONTRACT_TYPE",
    "OTHER_CURRENCY",
    "OTHER_NETWORK",
    "OTHER_SYMBOL",
    "SYMBOL",
    "TECHNICAL_DEFAULT_ANALYSTS",
    "TECHNICAL_DEFAULT_TIMEFRAMES",
    "external_result_with_scopes",
    "full_external_result",
    "full_flow_result",
    "full_technical_result",
    "insufficient_external_result",
    "insufficient_flow_result",
    "insufficient_technical_result",
    "make_context",
    "partial_external_result",
    "partial_flow_result",
    "partial_technical_result",
]
