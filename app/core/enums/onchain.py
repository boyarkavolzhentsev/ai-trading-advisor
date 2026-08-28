"""Stage 4E on-chain enums - normalized facts only, no interpretation.

No member here encodes a bullish/bearish, accumulation/distribution,
risk-on/risk-off, or any other qualitative judgment - see
``app.core.models.network_activity_observation``,
``app.core.models.supply_observation``,
``app.core.models.exchange_flow_observation`` and
``app.core.models.stablecoin_supply_observation`` for the facts-only
contracts this vocabulary backs. Deliberately compact: v1 covers only the
four approved metric families - no provider-native derived-metric vocabulary
(MVRV/SOPR/NVT/...) exists here, or anywhere in Stage 4E.
"""

from __future__ import annotations

from enum import StrEnum


class OnChainUnit(StrEnum):
    """Unit an on-chain quantity's value is expressed in.

    Deliberately closed to only what the four approved v1 metric families
    need - no hashes/sec, bytes, or gas member exists here because no v1
    metric uses them (mirrors ``app.core.enums.rates.SeriesUnit``'s
    "deliberately closed" stance).
    """

    NATIVE_ASSET = "NATIVE_ASSET"
    USD = "USD"


__all__ = ["OnChainUnit"]
