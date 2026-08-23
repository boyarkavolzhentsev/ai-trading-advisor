"""Binance forced-liquidation data: REST placeholder.

Binance does not expose historical or recent forced liquidations through any
public REST endpoint - the only source is the ``forceOrder`` WebSocket stream.
This module satisfies ``LiquidationProvider`` today so callers can already
depend on the contract, but it never issues an HTTP request: every call raises
``DataNotAvailableError`` immediately. Real data arrives in Stage 1C once the
WebSocket transport exists.
"""

from __future__ import annotations

from app.core.models.liquidation import LiquidationEvent
from app.market_data.exceptions import DataNotAvailableError
from app.market_data.protocols import DEFAULT_LIQUIDATION_LIMIT


class BinanceRestLiquidationProvider:
    """REST stub of ``LiquidationProvider`` for Binance USD-M futures."""

    def get_recent_liquidations(
        self,
        symbol: str,
        limit: int = DEFAULT_LIQUIDATION_LIMIT,
    ) -> list[LiquidationEvent]:
        """Always raise: no public REST source exists for this data.

        Raises:
            DataNotAvailableError: unconditionally, without issuing any
                HTTP request.
        """
        raise DataNotAvailableError(
            "binance liquidation data has no public REST endpoint; "
            "it is only available via the forceOrder WebSocket stream "
            "(planned for Stage 1C)"
        )


__all__ = ["BinanceRestLiquidationProvider"]
