"""Taker buy/sell volume contract.

Carries only observed volumes and their plain arithmetic combinations - no
imbalance signal, pressure score or directional conclusion. Interpreting this
data belongs to the future Flow Supervisor (``app/flow``).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.base import DomainModel, Symbol, Timestamp, Volume


class TakerFlowSnapshot(DomainModel):
    """Taker buy/sell volume of one symbol over one candle interval.

    ``sell_volume`` is the provider's total traded volume minus its reported
    taker buy volume - normalization of the provider payload, not an
    inference. ``buy_quote_volume`` is ``None`` when the provider does not
    report it.
    """

    symbol: Symbol
    contract_type: ContractType
    timeframe: Timeframe
    timestamp: Timestamp
    buy_volume: Volume
    sell_volume: Volume
    buy_quote_volume: Volume | None = None
    source: str = Field(min_length=1)

    @property
    def total_volume(self) -> Decimal:
        """Sum of buy and sell volume."""
        return self.buy_volume + self.sell_volume

    @property
    def delta(self) -> Decimal:
        """Buy volume minus sell volume."""
        return self.buy_volume - self.sell_volume

    @property
    def buy_ratio(self) -> float:
        """Share of total volume that was taker buy volume, in ``[0, 1]``.

        ``0.0`` when the candle carries no volume at all - a fixed default to
        avoid division by zero, not an inferred market condition.
        """
        total = self.total_volume
        if total == 0:
            return 0.0
        return float(self.buy_volume / total)
