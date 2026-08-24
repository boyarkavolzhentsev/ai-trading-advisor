"""Deterministic Order Book / Liquidity Analyst (Stage 2B).

Interprets Stage 2A ``OrderBookFeatures`` only. ``spread``/``spread_bps``/
``best_bid``/``best_ask``/``mid_price`` are carried as evidence only - no
"wide/narrow spread" label is derived from them (abnormality, deferred). No
weighted (distance-discounted) depth imbalance - Stage 2A itself only
computes the unweighted figure. A band's ``PARTIAL``/``STALE`` quality
(already resolved by Stage 2A's own ``worse_of``) is read as-is, never
recomputed here.
"""

from __future__ import annotations

from app.core.enums.flow_analysis import AnalysisDimension, AnalystOutcome, AnalystType, DepthTrend, OrderBookPressure
from app.core.enums.quality import FeatureQuality
from app.core.models.flow_analysis_result import FlowAnalysisObservation, FlowAnalysisResult
from app.core.models.flow_evidence import FlowEvidence
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot
from app.flow_analysts.base import agreement_of, make_evidence, qualifies, sign_category, worse_of_many

ABSTENTION_REASON = "no order book snapshot available"

_TOP_OF_BOOK_EVIDENCE: tuple[str, ...] = (
    "best_bid",
    "best_ask",
    "spread",
    "spread_bps",
    "mid_price",
)


class OrderBookLiquidityAnalyst:
    """Deterministic interpretation of order-book depth/liquidity imbalance."""

    analyst_type = AnalystType.ORDER_BOOK_LIQUIDITY

    def analyze(self, snapshot: FlowFeatureSnapshot) -> FlowAnalysisResult:
        order_book = snapshot.order_book
        provenance_label = snapshot.provenance.get("order_book", "unknown")

        if order_book is None or not qualifies(order_book.status):
            return self._abstain(snapshot)

        evidence: list[FlowEvidence] = []
        observations: list[FlowAnalysisObservation] = []

        for field_name in _TOP_OF_BOOK_EVIDENCE:
            value = getattr(order_book, field_name)
            if value is not None:
                evidence.append(
                    make_evidence(
                        feature_name=f"order_book.{field_name}",
                        window=None,
                        observed_value=value,
                        reference_value=None,
                        quality=order_book.status.quality,
                        source_timestamp=snapshot.observation_time,
                        provenance=provenance_label,
                    )
                )

        band_pressures: dict[str, OrderBookPressure] = {}
        band_pressure_evidence: dict[str, int] = {}
        band_qualities: dict[str, FeatureQuality] = {}

        for band_label, band in order_book.bands.items():
            if not qualifies(band.status):
                continue
            band_qualities[band_label] = band.status.quality

            if band.depth_imbalance is not None:
                idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="order_book.depth_imbalance",
                        window=None,
                        observed_value=band.depth_imbalance,
                        reference_value=None,
                        quality=band.status.quality,
                        source_timestamp=snapshot.observation_time,
                        provenance=provenance_label,
                    )
                )
                pressure = sign_category(
                    band.depth_imbalance,
                    positive=OrderBookPressure.BID_HEAVIER,
                    negative=OrderBookPressure.ASK_HEAVIER,
                    zero=OrderBookPressure.BALANCED,
                )
                assert pressure is not None
                band_pressures[band_label] = pressure
                band_pressure_evidence[band_label] = idx
                observations.append(
                    FlowAnalysisObservation(
                        dimension=AnalysisDimension.DIRECTIONAL_PRESSURE,
                        subject=band_label,
                        value=pressure.value,
                        quality=band.status.quality,
                        evidence_refs=(idx,),
                    )
                )

            for side, changes in (("bid", band.bid_depth_change), ("ask", band.ask_depth_change)):
                for window_label, change in changes.items():
                    idx = len(evidence)
                    evidence.append(
                        make_evidence(
                            feature_name=f"order_book.{side}_depth_change",
                            window=window_label,
                            observed_value=change,
                            reference_value=None,
                            quality=band.status.quality,
                            source_timestamp=snapshot.observation_time,
                            provenance=provenance_label,
                        )
                    )
                    trend = sign_category(
                        change,
                        positive=DepthTrend.THICKENING,
                        negative=DepthTrend.THINNING,
                        zero=DepthTrend.UNCHANGED,
                    )
                    assert trend is not None
                    observations.append(
                        FlowAnalysisObservation(
                            dimension=AnalysisDimension.DEPTH_TREND,
                            subject=f"{band_label}:{side}",
                            window=window_label,
                            value=trend.value,
                            quality=band.status.quality,
                            evidence_refs=(idx,),
                        )
                    )

        if band_pressures:
            observations.append(
                FlowAnalysisObservation(
                    dimension=AnalysisDimension.CROSS_BAND_AGREEMENT,
                    value=agreement_of(list(band_pressures.values())).value,
                    quality=worse_of_many(band_qualities[label] for label in band_pressures),
                    evidence_refs=tuple(band_pressure_evidence.values()),
                )
            )

        if not observations:
            return self._abstain(snapshot)

        return FlowAnalysisResult(
            analyst_type=AnalystType.ORDER_BOOK_LIQUIDITY,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            observation_time=snapshot.observation_time,
            windows=snapshot.windows,
            status=AnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=worse_of_many(observation.quality for observation in observations),
            provenance={"order_book": provenance_label},
        )

    @staticmethod
    def _abstain(snapshot: FlowFeatureSnapshot) -> FlowAnalysisResult:
        return FlowAnalysisResult(
            analyst_type=AnalystType.ORDER_BOOK_LIQUIDITY,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            observation_time=snapshot.observation_time,
            windows=snapshot.windows,
            status=AnalystOutcome.ABSTAINED,
            quality=FeatureQuality.UNAVAILABLE,
            abstention_reasons=(ABSTENTION_REASON,),
        )


__all__ = ["OrderBookLiquidityAnalyst"]
