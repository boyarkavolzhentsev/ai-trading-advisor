"""Deterministic Macro Event Analyst (Stage 4F).

Interprets caller-supplied ``EconomicEvent`` observations only - never
touches ``app.macro.history`` itself (no hidden windowing; the caller
selects which events to supply, mirroring how Flow analysts take an
already-materialized snapshot rather than a live history store). Every
per-event dimension is computed independently for every supplied event;
nothing is fabricated when a required field is ``None``.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.enums.external_intelligence_analysis import (
    ActualVsPreviousDirection,
    EventPresenceState,
    EventProximityState,
    ExternalIntelligenceAnalystType,
    ExternalIntelligenceDimension,
    ExternalIntelligenceOutcome,
    RevisionDirection,
    SurpriseDirection,
)
from app.core.models.economic_event import CurrencyCode, EconomicEvent
from app.core.models.external_intelligence_analysis_result import (
    ExternalIntelligenceAnalysisObservation,
    ExternalIntelligenceAnalysisResult,
)
from app.core.models.external_intelligence_evidence import ExternalIntelligenceEvidence
from app.core.models.base import Timestamp
from app.external_intelligence_analysts.base import abstain, classify_quality, make_evidence, sign_category, worse_of_many
from app.external_intelligence_analysts.config import MacroAnalystConfig

ABSTENTION_REASON = "no economic events supplied for this currency"


class MacroEventAnalyst:
    """Deterministic interpretation of ``EconomicEvent`` release/surprise/proximity facts."""

    analyst_type = ExternalIntelligenceAnalystType.MACRO_EVENT

    def analyze(
        self,
        events: Sequence[EconomicEvent],
        *,
        currency: CurrencyCode,
        analysis_time: Timestamp,
        config: MacroAnalystConfig,
    ) -> ExternalIntelligenceAnalysisResult:
        if not events:
            return abstain(
                ExternalIntelligenceAnalystType.MACRO_EVENT,
                analysis_time=analysis_time,
                reason=ABSTENTION_REASON,
                currency=currency,
            )

        ordered = sorted(events, key=lambda e: (e.provider, e.provider_event_id, e.revision_number))

        evidence: list[ExternalIntelligenceEvidence] = []
        observations: list[ExternalIntelligenceAnalysisObservation] = []
        presence_evidence_refs: list[int] = []

        for event in ordered:
            subject = f"{event.provider}:{event.provider_event_id}"
            provenance = f"app.macro:{event.provider}"
            quality = classify_quality(event.event_time, analysis_time, config.staleness_threshold)

            if event.importance is not None:
                idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="economic_event.importance",
                        observed_value=event.importance.value,
                        reference_value=None,
                        quality=quality,
                        source_timestamp=event.event_time,
                        source_provider=event.provider,
                        source_record_id=event.provider_event_id,
                        source_received_at=event.received_at,
                        provenance=provenance,
                    )
                )
                observations.append(
                    ExternalIntelligenceAnalysisObservation(
                        dimension=ExternalIntelligenceDimension.EVENT_IMPORTANCE,
                        value=event.importance.value,
                        quality=quality,
                        subject=subject,
                        evidence_refs=(idx,),
                    )
                )

            proximity_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="economic_event.event_time",
                    observed_value=event.event_time.isoformat(),
                    reference_value=analysis_time.isoformat(),
                    quality=quality,
                    source_timestamp=event.event_time,
                    source_provider=event.provider,
                    source_record_id=event.provider_event_id,
                    source_received_at=event.received_at,
                    provenance=provenance,
                )
            )
            presence_evidence_refs.append(proximity_idx)
            if event.event_time < analysis_time:
                proximity_state = EventProximityState.ALREADY_OCCURRED
            elif (event.event_time - analysis_time) <= config.proximity_window:
                proximity_state = EventProximityState.WITHIN_WINDOW
            else:
                proximity_state = EventProximityState.OUTSIDE_WINDOW
            observations.append(
                ExternalIntelligenceAnalysisObservation(
                    dimension=ExternalIntelligenceDimension.EVENT_PROXIMITY,
                    value=proximity_state.value,
                    quality=quality,
                    subject=subject,
                    evidence_refs=(proximity_idx,),
                )
            )

            if event.actual is not None and event.forecast is not None:
                idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="economic_event.actual_vs_forecast",
                        observed_value=event.actual,
                        reference_value=event.forecast,
                        quality=quality,
                        source_timestamp=event.event_time,
                        source_provider=event.provider,
                        source_record_id=event.provider_event_id,
                        source_received_at=event.received_at,
                        provenance=provenance,
                    )
                )
                surprise = sign_category(
                    event.actual - event.forecast,
                    positive=SurpriseDirection.ABOVE_FORECAST,
                    negative=SurpriseDirection.BELOW_FORECAST,
                    zero=SurpriseDirection.AT_FORECAST,
                )
                assert surprise is not None
                observations.append(
                    ExternalIntelligenceAnalysisObservation(
                        dimension=ExternalIntelligenceDimension.SURPRISE,
                        value=surprise.value,
                        quality=quality,
                        subject=subject,
                        evidence_refs=(idx,),
                    )
                )

            if event.actual is not None and event.previous is not None:
                idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="economic_event.actual_vs_previous",
                        observed_value=event.actual,
                        reference_value=event.previous,
                        quality=quality,
                        source_timestamp=event.event_time,
                        source_provider=event.provider,
                        source_record_id=event.provider_event_id,
                        source_received_at=event.received_at,
                        provenance=provenance,
                    )
                )
                actual_vs_previous = sign_category(
                    event.actual - event.previous,
                    positive=ActualVsPreviousDirection.ABOVE_PREVIOUS,
                    negative=ActualVsPreviousDirection.BELOW_PREVIOUS,
                    zero=ActualVsPreviousDirection.AT_PREVIOUS,
                )
                assert actual_vs_previous is not None
                observations.append(
                    ExternalIntelligenceAnalysisObservation(
                        dimension=ExternalIntelligenceDimension.ACTUAL_VS_PREVIOUS,
                        value=actual_vs_previous.value,
                        quality=quality,
                        subject=subject,
                        evidence_refs=(idx,),
                    )
                )

        presence_state = (
            EventPresenceState.NO_EVENTS
            if len(ordered) == 0
            else EventPresenceState.SINGLE_EVENT
            if len(ordered) == 1
            else EventPresenceState.MULTIPLE_EVENTS
        )
        observations.append(
            ExternalIntelligenceAnalysisObservation(
                dimension=ExternalIntelligenceDimension.EVENT_PRESENCE,
                value=presence_state.value,
                quality=worse_of_many([evidence[i].quality for i in presence_evidence_refs]),
                evidence_refs=tuple(presence_evidence_refs),
            )
        )

        revision_groups: dict[tuple[str, str], list[EconomicEvent]] = {}
        for event in ordered:
            if event.actual is None:
                continue
            revision_groups.setdefault((event.provider, event.provider_event_id), []).append(event)

        for (provider, provider_event_id), members in revision_groups.items():
            if len(members) < 2:
                continue
            ranked = sorted(members, key=lambda e: e.revision_number)
            prior, latest = ranked[-2], ranked[-1]
            subject = f"{provider}:{provider_event_id}:rev{prior.revision_number}->{latest.revision_number}"
            provenance = f"app.macro:{provider}"

            prior_quality = classify_quality(prior.event_time, analysis_time, config.staleness_threshold)
            latest_quality = classify_quality(latest.event_time, analysis_time, config.staleness_threshold)

            prior_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="economic_event.actual",
                    observed_value=prior.actual,
                    reference_value=None,
                    quality=prior_quality,
                    source_timestamp=prior.event_time,
                    source_provider=prior.provider,
                    source_record_id=prior.provider_event_id,
                    source_received_at=prior.received_at,
                    provenance=provenance,
                )
            )
            latest_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="economic_event.actual",
                    observed_value=latest.actual,
                    reference_value=None,
                    quality=latest_quality,
                    source_timestamp=latest.event_time,
                    source_provider=latest.provider,
                    source_record_id=latest.provider_event_id,
                    source_received_at=latest.received_at,
                    provenance=provenance,
                )
            )
            revision_direction = sign_category(
                latest.actual - prior.actual,
                positive=RevisionDirection.REVISED_UP,
                negative=RevisionDirection.REVISED_DOWN,
                zero=RevisionDirection.UNCHANGED,
            )
            assert revision_direction is not None
            observations.append(
                ExternalIntelligenceAnalysisObservation(
                    dimension=ExternalIntelligenceDimension.REVISION_DIRECTION,
                    value=revision_direction.value,
                    quality=worse_of_many([prior_quality, latest_quality]),
                    subject=subject,
                    evidence_refs=(prior_idx, latest_idx),
                )
            )

        return ExternalIntelligenceAnalysisResult(
            analyst_type=ExternalIntelligenceAnalystType.MACRO_EVENT,
            currency=currency,
            analysis_time=analysis_time,
            status=ExternalIntelligenceOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=worse_of_many([observation.quality for observation in observations]),
        )


__all__ = ["MacroEventAnalyst"]
