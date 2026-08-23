"""Raw exchange order-side vocabulary.

``OrderSide`` names the side of a provider-reported order exactly as the venue
reports it (e.g. the forced order behind a liquidation). It is not a trading
recommendation: interpretive directional bias uses ``TradeDirection`` instead.
"""

from __future__ import annotations

from enum import StrEnum


class OrderSide(StrEnum):
    """Side of a raw, venue-reported order."""

    BUY = "BUY"
    SELL = "SELL"
