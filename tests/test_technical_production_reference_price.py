"""``TechnicalProductionResult.m15_last_closed_close`` (corrective design
closure, "PROVIDER SYMBOL SPLIT + PRICE-BASIS RECONCILIATION"): the Binance
M15 reference price Setup Construction needs to translate a structural stop
onto MT5's own price axis - the retained M15 candle store's own most recent
CLOSED candle close, never the forming candle, never an extra REST call.

No real network access happens anywhere in this file - the same fake,
in-process Futures OHLCV provider convention as ``tests/test_technical_
production.py`` is reused throughout.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.market import Timeframe
from app.market_data.exceptions import ProviderUnavailableError
from app.technical.production import TechnicalProductionComposer
from tests.technical_production_support import NOW, FakeFuturesOHLCVProvider, make_candles, make_config


def test_m15_last_closed_close_reflects_last_closed_candle() -> None:
    """3 M15 candles at start_price=100 -> closes 100, 101, 102 - the LAST
    (102) is the current/forming candle as of NOW (see make_candles' own
    docstring), so the last CLOSED close is 101."""
    provider = FakeFuturesOHLCVProvider()
    provider.set_response(Timeframe.M15, make_candles(Timeframe.M15, 3, as_of=NOW, start_price=Decimal("100")))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    assert result.m15_last_closed_close == Decimal("101")


def test_m15_last_closed_close_never_uses_forming_candle() -> None:
    provider = FakeFuturesOHLCVProvider()
    provider.set_response(Timeframe.M15, make_candles(Timeframe.M15, 3, as_of=NOW, start_price=Decimal("100")))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    assert result.m15_last_closed_close != Decimal("102")  # the forming candle's own close


def test_m15_last_closed_close_none_when_no_history_ever_retained() -> None:
    """The very first cycle, with the M15 fetch itself failing and nothing
    ever retained before it - None, never fabricated."""
    provider = FakeFuturesOHLCVProvider()
    provider.fail(Timeframe.M15, ProviderUnavailableError("simulated outage"))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    result = composer.build_technical_result(as_of=NOW)

    assert result.m15_last_closed_close is None
    assert any(f.timeframe is Timeframe.M15 for f in result.fetch_failures)


def test_m15_last_closed_close_survives_a_later_fetch_failure_via_retained_history() -> None:
    """First cycle succeeds and retains real M15 history; a later cycle's
    OWN M15 fetch fails, but this composer-level fact still reflects
    whatever is currently retained (unchanged) - the composer's own
    established "always build from whatever history is retained" policy
    (see its own module docstring). The SAFETY DISCARD for a fetch failure
    is a separate, one-layer-up Stage0D/ProductionAdvisoryComposer
    responsibility (see tests/test_production_advisory_composer.py's own
    binance_reference_price discard-safety tests) - this composer itself
    never discards anything on a failure, exactly like m15_market_structure/
    technical today."""
    provider = FakeFuturesOHLCVProvider()
    provider.set_response(Timeframe.M15, make_candles(Timeframe.M15, 3, as_of=NOW, start_price=Decimal("100")))
    composer = TechnicalProductionComposer(config=make_config(), provider=provider)

    first = composer.build_technical_result(as_of=NOW)
    assert first.m15_last_closed_close == Decimal("101")

    provider.fail(Timeframe.M15, ProviderUnavailableError("simulated outage"))
    second = composer.build_technical_result(as_of=NOW)

    assert second.m15_last_closed_close == Decimal("101")  # retained, unchanged
    assert any(f.timeframe is Timeframe.M15 for f in second.fetch_failures)
