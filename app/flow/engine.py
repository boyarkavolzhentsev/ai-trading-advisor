"""Stage 2A orchestration: strict per-(symbol, contract_type) state isolation.

``FlowFeatureEngine`` owns bounded history and composes a
``FlowFeatureSnapshot`` from it via the pure calculators in this package.
It performs no network I/O, no polling and no interpretation - only state
isolation and wiring. No symbol is ever hard-coded: every method is
parameterized by ``(symbol, contract_type)``, and each pair gets its own
independent ``SymbolFeatureHistory``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.cross_feature_observation import CrossFeatureObservation
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot
from app.core.models.funding import FundingRate
from app.core.models.liquidation import LiquidationEvent
from app.core.models.open_interest import OpenInterest
from app.core.models.order_book import OrderBookSnapshot
from app.core.models.order_book_features import DepthBand
from app.core.models.price_context_features import PriceContextWindowFeatures
from app.core.models.taker_flow_features import TakerFlowWindowFeatures
from app.core.models.trade_event import TradeEvent
from app.flow.cross_features import compute_cross_feature_observation
from app.flow.funding import compute_funding_features
from app.flow.history import SymbolFeatureHistory
from app.flow.liquidation import compute_liquidation_features
from app.flow.open_interest import compute_open_interest_features
from app.flow.order_book import DEFAULT_DEPTH_BANDS, compute_order_book_features
from app.flow.price_context import compute_price_context_features
from app.flow.taker_flow import compute_taker_flow_features
from app.flow.windows import DEFAULT_WINDOWS, validate_unique_labels

CROSS_FEATURE_PAIR_LABEL = "return_pct_vs_taker_delta"


def _latest_source(items: Sequence[Any], default: str) -> str:
    """Return the most recent retained item's ``source``, or ``default`` if empty.

    ``BoundedBuffer.latest()`` returns items oldest-first, so the last
    element is the most recent one.
    """
    return items[-1].source if items else default


class FlowFeatureEngine:
    """Owns bounded per-(symbol, contract_type) history and builds snapshots."""

    def __init__(
        self,
        *,
        windows: Sequence[AnalyticsWindow] = DEFAULT_WINDOWS,
        depth_bands: Sequence[DepthBand] = DEFAULT_DEPTH_BANDS,
    ) -> None:
        validate_unique_labels(windows)
        self._windows = tuple(windows)
        self._depth_bands = tuple(depth_bands)
        self._state: dict[tuple[str, ContractType], SymbolFeatureHistory] = {}

    def _history_for(self, symbol: str, contract_type: ContractType) -> SymbolFeatureHistory:
        key = (symbol.upper(), contract_type)
        history = self._state.get(key)
        if history is None:
            history = SymbolFeatureHistory.with_capacity()
            self._state[key] = history
        return history

    def record_trade(self, trade: TradeEvent) -> None:
        self._history_for(trade.symbol, trade.contract_type).trades.append(trade)

    def record_liquidation(self, event: LiquidationEvent) -> None:
        self._history_for(event.symbol, event.contract_type).liquidations.append(event)

    def record_order_book(self, snapshot: OrderBookSnapshot) -> None:
        self._history_for(snapshot.symbol, snapshot.contract_type).order_book.append(snapshot)

    def record_open_interest(self, observation: OpenInterest) -> None:
        self._history_for(observation.symbol, observation.contract_type).open_interest.append(observation)

    def record_funding(self, observation: FundingRate) -> None:
        self._history_for(observation.symbol, observation.contract_type).funding.append(observation)

    def history_for(self, symbol: str, contract_type: ContractType) -> SymbolFeatureHistory:
        """Expose the bounded history of one symbol/contract type (read/inspect only)."""
        return self._history_for(symbol, contract_type)

    def build_snapshot(
        self,
        *,
        symbol: str,
        contract_type: ContractType,
        observation_time: datetime,
        default_source: str = "flow_engine",
    ) -> FlowFeatureSnapshot:
        """Compose one synchronized ``FlowFeatureSnapshot`` from retained history.

        Each domain's ``source`` is derived from the most recent retained
        event of that domain (every raw event already carries its own
        ``source``) - never a single flat label applied uniformly, since
        different domains genuinely come from different streams/polls.
        ``default_source`` is used only when a domain has no history at all
        yet (its calculator still needs a non-empty ``source`` string even
        while reporting ``UNAVAILABLE``).
        """
        symbol = symbol.upper()
        history = self._history_for(symbol, contract_type)

        trades = history.trades.latest()
        liquidations = history.liquidations.latest()
        order_books = history.order_book.latest()
        open_interests = history.open_interest.latest()
        fundings = history.funding.latest()

        taker_flow = compute_taker_flow_features(
            symbol=symbol,
            contract_type=contract_type,
            trades=trades,
            windows=self._windows,
            observation_time=observation_time,
            source=_latest_source(trades, default_source),
            dropped_count=history.trades.dropped_count,
        )
        liquidation = compute_liquidation_features(
            symbol=symbol,
            contract_type=contract_type,
            liquidations=liquidations,
            windows=self._windows,
            observation_time=observation_time,
            source=_latest_source(liquidations, default_source),
            dropped_count=history.liquidations.dropped_count,
        )
        order_book = compute_order_book_features(
            symbol=symbol,
            contract_type=contract_type,
            history=order_books,
            bands=self._depth_bands,
            windows=self._windows,
            observation_time=observation_time,
            source=_latest_source(order_books, default_source),
        )
        open_interest = compute_open_interest_features(
            symbol=symbol,
            contract_type=contract_type,
            history=open_interests,
            windows=self._windows,
            observation_time=observation_time,
            source=_latest_source(open_interests, default_source),
        )
        funding = compute_funding_features(
            symbol=symbol,
            contract_type=contract_type,
            history=fundings,
            windows=self._windows,
            observation_time=observation_time,
            source=_latest_source(fundings, default_source),
        )
        price_context = compute_price_context_features(
            symbol=symbol,
            contract_type=contract_type,
            trades=trades,
            mark_prices=fundings,
            windows=self._windows,
            observation_time=observation_time,
            source=_latest_source(trades, default_source),
        )

        cross_features = self._compute_cross_features(
            symbol=symbol,
            contract_type=contract_type,
            prior_snapshots=history.snapshots.latest(),
            taker_flow=taker_flow,
            price_context=price_context,
        )

        provenance: dict[str, str] = {
            "order_book": order_book.source,
            "open_interest": open_interest.source,
            "funding": funding.source,
        }
        if taker_flow:
            provenance["taker_flow"] = next(iter(taker_flow.values())).source
        if liquidation:
            provenance["liquidation"] = next(iter(liquidation.values())).source
        if price_context:
            provenance["price_context"] = next(iter(price_context.values())).source

        snapshot = FlowFeatureSnapshot(
            symbol=symbol,
            contract_type=contract_type,
            observation_time=observation_time,
            windows=self._windows,
            taker_flow=taker_flow,
            liquidation=liquidation,
            order_book=order_book,
            open_interest=open_interest,
            funding=funding,
            price_context=price_context,
            cross_features=cross_features,
            provenance=provenance,
        )
        history.snapshots.append(snapshot)
        return snapshot

    def _compute_cross_features(
        self,
        *,
        symbol: str,
        contract_type: ContractType,
        prior_snapshots: Sequence[FlowFeatureSnapshot],
        taker_flow: dict[str, TakerFlowWindowFeatures],
        price_context: dict[str, PriceContextWindowFeatures],
    ) -> dict[str, CrossFeatureObservation]:
        cross_features: dict[str, CrossFeatureObservation] = {}
        for window in self._windows:
            series_a: list[float | None] = []
            series_b: list[float | None] = []
            for snap in prior_snapshots:
                pc = snap.price_context.get(window.label)
                tf = snap.taker_flow.get(window.label)
                series_a.append(float(pc.return_pct) if pc is not None and pc.return_pct is not None else None)
                series_b.append(float(tf.delta) if tf is not None else None)
            pc_now = price_context.get(window.label)
            tf_now = taker_flow.get(window.label)
            series_a.append(float(pc_now.return_pct) if pc_now is not None and pc_now.return_pct is not None else None)
            series_b.append(float(tf_now.delta) if tf_now is not None else None)

            cross_features[window.label] = compute_cross_feature_observation(
                symbol=symbol,
                contract_type=contract_type,
                window=window,
                pair_label=CROSS_FEATURE_PAIR_LABEL,
                series_a=series_a,
                series_b=series_b,
            )
        return cross_features


__all__ = ["CROSS_FEATURE_PAIR_LABEL", "FlowFeatureEngine"]
