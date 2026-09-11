"""Shared fixtures for ``app.api``/``app.bootstrap`` tests.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.

``FakeApplicationAdvisoryService`` never constructs a real
``ProductionAdvisoryComposer``/touches MT5/Binance/OpenAI - it records calls
and returns/raises a caller-configured result, mirroring
``tests/application_support.py``'s/``tests/production_advisory_support.py``'s
own established fake-over-real-network convention.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.application.dto import (
    AdvisoryResponse,
    ApplicationAdvisoryStatus,
    ExplanationDTO,
    NoTradeReasonDTO,
    OperationalDiagnosticsDTO,
    RecommendationDTO,
    TradingDataQualityDTO,
)
from app.core.enums.explanation import ExplanationProviderStatus
from app.core.enums.mt5_runtime import MT5ConnectivityState
from app.core.enums.runtime_cycle import RuntimeCycleOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.stream import StreamStatus
from app.core.enums.trade import TradeDirection

AS_OF = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
VALID_UNTIL = datetime(2026, 5, 1, 16, 0, 0, tzinfo=UTC)


def build_recommendation(*, trade_id: str = "cyc__TREND_FOLLOWING") -> RecommendationDTO:
    return RecommendationDTO(
        trade_id=trade_id,
        strategy_family=StrategyFamily.TREND_FOLLOWING,
        symbol="EURUSD",
        direction=TradeDirection.LONG,
        entry_price=Decimal("1.10000"),
        stop_loss=Decimal("1.09000"),
        take_profit_levels=(Decimal("1.12000"),),
        approved_volume=Decimal("0.50"),
        approved_risk_amount=Decimal("25.00"),
        account_currency="USD",
        signal_time=AS_OF,
        valid_until=VALID_UNTIL,
    )


def _data_quality(*, runtime_outcome: RuntimeCycleOutcome) -> TradingDataQualityDTO:
    return TradingDataQualityDTO(
        runtime_outcome=runtime_outcome,
        mt5_connectivity_state=MT5ConnectivityState.AVAILABLE,
        positions_read_status="OK",
        history_read_status="OK",
        technical_fetch_failed_timeframes=(),
        calendar_data_quality=None,
        account_risk_snapshot_ready=True,
        account_risk_snapshot_block_reasons=(),
    )


def _diagnostics() -> OperationalDiagnosticsDTO:
    return OperationalDiagnosticsDTO(
        flow_market_stream_status=StreamStatus.CONNECTED,
        flow_order_book_stream_status=StreamStatus.CONNECTED,
        flow_open_interest_last_success_at=None,
        llm_enabled=False,
        llm_provider_status=ExplanationProviderStatus.LLM_UNAVAILABLE,
        cycle_duration_seconds=0.01,
        issuance_persistence=(),
    )


def _explanation() -> ExplanationDTO:
    return ExplanationDTO(
        headline="test headline",
        cycle_summary="test cycle summary",
        no_trade_explanation=None,
        warnings=(),
        data_quality_notes=(),
        risk_notes=(),
        provider_status=ExplanationProviderStatus.LLM_UNAVAILABLE,
        llm_enabled=False,
        deterministic_fallback_used=True,
    )


def build_advisory_response(
    *,
    status: ApplicationAdvisoryStatus = ApplicationAdvisoryStatus.NO_TRADE,
    recommendations: tuple[RecommendationDTO, ...] = (),
    no_trade_reasons: tuple[NoTradeReasonDTO, ...] = (),
    logical_cycle_id: str = "cyc",
    runtime_outcome: RuntimeCycleOutcome = RuntimeCycleOutcome.READY,
) -> AdvisoryResponse:
    return AdvisoryResponse(
        logical_cycle_id=logical_cycle_id,
        as_of=AS_OF,
        symbol="EURUSD",
        market_data_symbol="EURUSD",
        status=status,
        recommendations=recommendations,
        no_trade_reasons=no_trade_reasons,
        data_quality=_data_quality(runtime_outcome=runtime_outcome),
        diagnostics=_diagnostics(),
        explanation=_explanation(),
    )


class FakeApplicationAdvisoryService:
    def __init__(
        self,
        *,
        result: AdvisoryResponse | None = None,
        create_advisory_exception: Exception | None = None,
    ) -> None:
        self._result = result
        self._create_advisory_exception = create_advisory_exception
        self.startup_calls = 0
        self.shutdown_calls = 0
        self.create_advisory_calls: list[str] = []

    async def startup(self) -> None:
        self.startup_calls += 1

    async def shutdown(self) -> None:
        self.shutdown_calls += 1

    async def create_advisory(self, *, logical_cycle_id: str) -> AdvisoryResponse:
        self.create_advisory_calls.append(logical_cycle_id)
        if self._create_advisory_exception is not None:
            raise self._create_advisory_exception
        assert self._result is not None
        return self._result


__all__ = [
    "AS_OF",
    "VALID_UNTIL",
    "FakeApplicationAdvisoryService",
    "build_advisory_response",
    "build_recommendation",
]
