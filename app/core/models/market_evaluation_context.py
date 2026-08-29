"""Stage 5A explicit evaluation-identity contract.

Flow and Technical supervisor results each anchor to one ``(symbol,
contract_type)`` instrument; External Intelligence results carry no single
anchor at all - they are scoped per analyst type by ``currency`` (Macro/
Rates), ``symbol`` (News), or ``asset``+``network`` (On-Chain), potentially
spanning many different instruments in one result. ``Symbol``,
``CurrencyCode`` and ``Asset`` are independent string type aliases with no
conversion table anywhere in the repository - so nothing here is ever
derived. A caller who wants External Intelligence's currency- or asset-
scoped evidence aligned to this evaluation must say so explicitly via
``currency_exposures``/``base_asset``+``network``; Stage 5A never infers
``symbol -> asset``, ``symbol -> currency``, ``symbol -> network``,
``quote_asset -> CurrencyCode``, or ``asset -> network``.
"""

from __future__ import annotations

from typing import Self

from pydantic import model_validator

from app.core.enums.instrument import ContractType
from app.core.models.base import DomainModel, Symbol
from app.core.models.economic_event import CurrencyCode
from app.core.models.instrument import Asset


class MarketEvaluationContext(DomainModel):
    """Explicit, caller-declared identity and scope-mapping for one
    evaluation. Every mapping field is independent, optional, and never
    derived from another field on this model."""

    symbol: Symbol
    contract_type: ContractType

    base_asset: Asset | None = None
    network: str | None = None

    currency_exposures: tuple[CurrencyCode, ...] = ()

    @model_validator(mode="after")
    def _validate_on_chain_pair(self) -> Self:
        if (self.base_asset is None) != (self.network is None):
            raise ValueError("base_asset and network must both be supplied or both omitted")
        return self


__all__ = ["MarketEvaluationContext"]
