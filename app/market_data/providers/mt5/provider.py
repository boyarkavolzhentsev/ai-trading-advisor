"""MT5-backed ``OHLCVProvider``.

Wired into ``TechnicalProductionComposer``/``ProductionAdvisoryComposer`` as
of the MT5 Price Authority Stage B production bootstrap wiring
(``app.production_advisory.composer``) - this module itself still contains
no import of either: bootstrap wiring is the only place that imports both
``MT5OHLCVProvider`` and ``TechnicalProductionComposer`` together. This
module owns the one place MT5-specific
timeframe semantics are resolved: M1/M5/M15/H1 are direct normalized MT5
bars; H4 is derived from normalized closed H1 via ``app.market_data.
providers.mt5.resampler.resample_h4``; D1 is not supported in MT5 V1 (per
the approved MT5 Price Authority D1-deferred design) and fails
deterministically rather than silently falling back to raw MT5 D1 bars.

Depends on the concrete ``MT5Client`` (never ``MT5ClientProtocol`` - that
protocol's approved method set is closed by
``tests/test_mt5_module_hygiene.py`` and deliberately excludes ``rates()``),
and on a plain ``server_timezone: str`` - never
``MT5RolloverPolicyConfig`` or any other Stage 10B config type, so this
package gains no import edge onto ``app.core.config.mt5_rollover``. The one
place that value is shared is bootstrap wiring, a later stage.

``as_of`` determinism (Stage A corrective review, later promoted into
``app.market_data.protocols.OHLCVProvider`` itself by the Stage A contract
correction): H4 synthesis must decide which raw H1 bars are CLOSED using the
same authoritative cycle ``as_of`` a future orchestrator's Technical
composition uses for the SAME cycle - never an independently sampled wall
clock, which could disagree with Technical's own classification of the
identical H1 bar within the same logical cycle (a real boundary race, not a
hypothetical one). ``get_ohlcv`` therefore takes an ``as_of`` keyword,
REQUIRED only for ``Timeframe.H4`` (raises deterministically, before any
I/O, if omitted) - direct timeframes accept it (satisfying the shared
protocol) but ignore it: they do no closed/forming filtering here at all
(that stays ``TechnicalProductionComposer``'s job, unchanged). Deliberately
NOT stored as instance state (no per-cycle mutable attribute, no
constructor-bound clock callable) - a plain per-call argument is the
smallest design that is both deterministic and reusable across an unbounded
number of future cycles from one long-lived provider instance.
"""

from __future__ import annotations

from app.core.enums.market import Timeframe
from app.core.models.base import Timestamp
from app.core.models.candle import OHLCVCandle
from app.market_data.candle_time import split_closed_and_forming
from app.market_data.exceptions import ProviderUnavailableError, UnsupportedTimeframeError
from app.market_data.protocols import DEFAULT_OHLCV_LIMIT
from app.market_data.providers.mt5.mapper import map_mt5_rates
from app.market_data.providers.mt5.resampler import resample_h4
from app.mt5.client import MT5Client

_DIRECT_TIMEFRAMES: frozenset[Timeframe] = frozenset({Timeframe.M1, Timeframe.M5, Timeframe.M15, Timeframe.H1})
"""Timeframes MT5 reports directly - read via ``MT5Client.rates()`` and
mapped unchanged, including the still-forming last candle (never filtered
here: ``TechnicalProductionComposer`` already owns closed-vs-forming
handling for direct timeframes today, and must continue to)."""

MT5_V1_TECHNICAL_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe.M1,
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.H1,
    Timeframe.H4,
)
"""The MT5 V1 Technical timeframe preset (MT5 Price Authority Stage B
wiring): every timeframe this provider actually supports, in canonical
order. Deliberately excludes ``Timeframe.D1`` - D1 is not enabled in MT5 V1
(see this module's own docstring) - so bootstrap wiring must inject this
preset, never ``app.technical.timeframes.DEFAULT_TECHNICAL_TIMEFRAMES``
(which still includes D1 for the Binance-native default contour), into
``TechnicalProductionComposer`` when it is composed against
``MT5OHLCVProvider``."""

H4_RAW_H1_LOOKBACK = 208
"""Exact raw H1 bars fetched to synthesize H4, per the approved MT5 Price
Authority design: 50 closed H4 candles need 200 closed, contiguous H1 bars
(50*4); +3 for a possible incomplete leading bucket at the fetch window's
oldest edge, +3 for the always-incomplete trailing bucket (the current H4
bucket can never complete - its 4th H1 member is always either forming or
not yet fetched), +1 for the currently-forming H1 candle itself = 207,
rounded up to 208. This guarantees 50 closed H4 candles regardless of what
wall-clock hour the read happens to land on. Fixed for Stage A - not
parametrized by the caller's ``limit``."""


class MT5OHLCVProvider:
    """Implements ``app.market_data.protocols.OHLCVProvider`` for one MT5
    connection. Structurally satisfies ``OHLCVProvider`` only - deliberately
    does NOT implement ``get_current_price``/``get_bid_ask``/
    ``get_instrument_metadata``/``get_funding_rate``/``get_open_interest``/
    ``get_taker_flow``/``get_order_book_snapshot``: faking any of those for
    an MT5 CFD symbol would misrepresent a capability this provider does not
    have (per the approved provider-protocol audit)."""

    def __init__(self, *, client: MT5Client, server_timezone: str) -> None:
        self._client = client
        self._server_timezone = server_timezone

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = DEFAULT_OHLCV_LIMIT,
        *,
        as_of: Timestamp | None = None,
    ) -> list[OHLCVCandle]:
        if timeframe in _DIRECT_TIMEFRAMES:
            return self._direct_ohlcv(symbol, timeframe, limit)
        if timeframe is Timeframe.H4:
            if as_of is None:
                raise ValueError(
                    "MT5OHLCVProvider.get_ohlcv(timeframe=Timeframe.H4) requires an explicit as_of: "
                    "H1 closed/forming classification for H4 synthesis must use the same authoritative "
                    "cycle as_of Technical uses for this cycle, never an independently sampled wall clock"
                )
            return self._h4_ohlcv(symbol, limit, as_of)
        raise UnsupportedTimeframeError(
            f"MT5 OHLCV provider does not support timeframe {timeframe.value} in V1 "
            "(D1 is explicitly deferred; every other non-direct timeframe is unsupported)"
        )

    def _direct_ohlcv(self, symbol: str, timeframe: Timeframe, limit: int) -> list[OHLCVCandle]:
        status, raw_rates = self._client.rates(symbol=symbol, timeframe=timeframe, count=limit)
        if status == "UNAVAILABLE":
            raise ProviderUnavailableError(f"MT5 rates unavailable for {symbol} {timeframe.value}")
        return map_mt5_rates(raw_rates, server_timezone=self._server_timezone)

    def _h4_ohlcv(self, symbol: str, limit: int, as_of: Timestamp) -> list[OHLCVCandle]:
        status, raw_rates = self._client.rates(symbol=symbol, timeframe=Timeframe.H1, count=H4_RAW_H1_LOOKBACK)
        if status == "UNAVAILABLE":
            raise ProviderUnavailableError(f"MT5 rates unavailable for {symbol} H1 (H4 synthesis)")

        h1_candles = map_mt5_rates(raw_rates, server_timezone=self._server_timezone)
        closed_h1, _forming = split_closed_and_forming(h1_candles, Timeframe.H1, as_of)
        h4_candles = resample_h4(closed_h1)
        return h4_candles[-limit:] if limit < len(h4_candles) else h4_candles


__all__ = ["H4_RAW_H1_LOOKBACK", "MT5OHLCVProvider", "MT5_V1_TECHNICAL_TIMEFRAMES"]
