"""Deterministic News/Sentiment Analyst (Stage 4F).

Interprets caller-supplied ``NewsItem``/``NewsSentimentObservation`` records
for one ``symbol`` only. Relevance is computed exclusively via
``app.news_intel.relevance.compute_relevance`` - no keyword/tag/fuzzy
matching, and no reading of ``headline``/``body`` text at all. Sentiment is
aggregated by sign only, strictly within one sentiment provider at a time -
raw scores from different providers are never averaged together, since
their scales may be incompatible (see
``app.core.models.news_sentiment_observation``).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.enums.external_intelligence_analysis import (
    ExternalIntelligenceAnalystType,
    ExternalIntelligenceDimension,
    ExternalIntelligenceOutcome,
    RelevantItemPresence,
    SentimentAgreementVerdict,
    SentimentSign,
)
from app.core.enums.quality import FeatureQuality
from app.core.models.base import Symbol, Timestamp
from app.core.models.external_intelligence_analysis_result import (
    ExternalIntelligenceAnalysisObservation,
    ExternalIntelligenceAnalysisResult,
)
from app.core.models.external_intelligence_evidence import ExternalIntelligenceEvidence
from app.core.models.news_item import NewsItem
from app.core.models.news_sentiment_observation import NewsSentimentObservation
from app.external_intelligence_analysts.base import abstain, classify_quality, make_evidence, sign_category, worse_of_many
from app.external_intelligence_analysts.config import NewsSentimentAnalystConfig
from app.news_intel.relevance import compute_relevance

ABSTENTION_REASON = "no news items supplied for this symbol"
NO_ANALYZABLE_DIMENSION_REASON = "no relevance-determined items and no matched sentiment for this symbol"


class NewsSentimentAnalyst:
    """Deterministic interpretation of exact-relevance and provider-native sentiment facts."""

    analyst_type = ExternalIntelligenceAnalystType.NEWS_SENTIMENT

    def analyze(
        self,
        news_items: Sequence[NewsItem],
        sentiment_observations: Sequence[NewsSentimentObservation],
        *,
        symbol: Symbol,
        analysis_time: Timestamp,
        config: NewsSentimentAnalystConfig,
    ) -> ExternalIntelligenceAnalysisResult:
        if not news_items:
            return abstain(
                ExternalIntelligenceAnalystType.NEWS_SENTIMENT,
                analysis_time=analysis_time,
                reason=ABSTENTION_REASON,
                symbol=symbol,
            )

        evidence: list[ExternalIntelligenceEvidence] = []
        observations: list[ExternalIntelligenceAnalysisObservation] = []

        ordered_items = sorted(news_items, key=lambda i: (i.provider, i.provider_item_id, i.received_at))

        presence_evidence_refs: list[int] = []
        any_matched = False
        matched_recent_keys: set[tuple[str, str, Timestamp]] = set()

        for item in ordered_items:
            relevance = compute_relevance(item, symbol, analysis_time)
            if relevance.quality is not FeatureQuality.VALID:
                # Relevance could not be determined for this item - never
                # treated as evidence of absence, per the Stage 4D
                # VALID/UNAVAILABLE distinction.
                continue

            quality = classify_quality(item.published_at, analysis_time, config.staleness_threshold)
            idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="news_relevance.matched",
                    observed_value=str(relevance.matched),
                    reference_value=symbol,
                    quality=quality,
                    source_timestamp=item.published_at,
                    source_provider=item.provider,
                    source_record_id=item.provider_item_id,
                    source_received_at=item.received_at,
                    provenance=f"app.news:{item.provider}",
                )
            )
            presence_evidence_refs.append(idx)

            if relevance.matched:
                any_matched = True
                age = analysis_time - item.published_at
                if age <= config.recency_window:
                    matched_recent_keys.add((item.provider, item.provider_item_id, item.received_at))

        if presence_evidence_refs:
            presence_state = RelevantItemPresence.ITEMS_FOUND if any_matched else RelevantItemPresence.NO_ITEMS
            observations.append(
                ExternalIntelligenceAnalysisObservation(
                    dimension=ExternalIntelligenceDimension.RELEVANT_ITEM_PRESENCE,
                    value=presence_state.value,
                    quality=worse_of_many([evidence[i].quality for i in presence_evidence_refs]),
                    evidence_refs=tuple(presence_evidence_refs),
                )
            )

        eligible_sentiment = [
            obs
            for obs in sentiment_observations
            if (obs.source_provider, obs.source_provider_item_id, obs.source_received_at) in matched_recent_keys
            and obs.sentiment_score is not None
        ]

        provider_signs: dict[str, SentimentSign] = {}
        provider_evidence_refs: dict[str, list[int]] = {}
        by_provider: dict[str, list[NewsSentimentObservation]] = {}
        for obs in sorted(eligible_sentiment, key=lambda o: (o.provider, o.source_provider_item_id, o.received_at)):
            by_provider.setdefault(obs.provider, []).append(obs)

        for provider in sorted(by_provider):
            members = by_provider[provider]
            signs_found: set[SentimentSign] = set()
            refs: list[int] = []
            for obs in members:
                quality = classify_quality(obs.published_at, analysis_time, config.staleness_threshold)
                idx = len(evidence)
                evidence.append(
                    make_evidence(
                        feature_name="news_sentiment_observation.sentiment_score",
                        observed_value=obs.sentiment_score,
                        reference_value=None,
                        quality=quality,
                        source_timestamp=obs.published_at,
                        source_provider=obs.provider,
                        source_record_id=obs.source_provider_item_id,
                        source_received_at=obs.received_at,
                        provenance=f"app.news_intel:{obs.provider}",
                    )
                )
                refs.append(idx)
                sign = sign_category(
                    obs.sentiment_score, positive=SentimentSign.POSITIVE, negative=SentimentSign.NEGATIVE, zero=SentimentSign.ZERO
                )
                assert sign is not None
                signs_found.add(sign)

            provider_sign = signs_found.pop() if len(signs_found) == 1 else SentimentSign.MIXED
            provider_signs[provider] = provider_sign
            provider_evidence_refs[provider] = refs
            observations.append(
                ExternalIntelligenceAnalysisObservation(
                    dimension=ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN,
                    value=provider_sign.value,
                    quality=worse_of_many([evidence[i].quality for i in refs]),
                    subject=provider,
                    evidence_refs=tuple(refs),
                )
            )

        if provider_signs:
            unambiguous = [sign for sign in provider_signs.values() if sign is not SentimentSign.MIXED]
            agreement = (
                SentimentAgreementVerdict.ALL_AGREE
                if len(unambiguous) >= 2 and len(set(unambiguous)) == 1
                else SentimentAgreementVerdict.MIXED
                if len(unambiguous) >= 2
                else SentimentAgreementVerdict.INSUFFICIENT_DATA
            )
            all_refs = tuple(idx for provider in sorted(provider_evidence_refs) for idx in provider_evidence_refs[provider])
            observations.append(
                ExternalIntelligenceAnalysisObservation(
                    dimension=ExternalIntelligenceDimension.SENTIMENT_PROVIDER_AGREEMENT,
                    value=agreement.value,
                    quality=worse_of_many([evidence[i].quality for i in all_refs]),
                    evidence_refs=all_refs,
                )
            )

        if not observations:
            return abstain(
                ExternalIntelligenceAnalystType.NEWS_SENTIMENT,
                analysis_time=analysis_time,
                reason=NO_ANALYZABLE_DIMENSION_REASON,
                symbol=symbol,
            )

        return ExternalIntelligenceAnalysisResult(
            analyst_type=ExternalIntelligenceAnalystType.NEWS_SENTIMENT,
            symbol=symbol,
            analysis_time=analysis_time,
            status=ExternalIntelligenceOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=worse_of_many([observation.quality for observation in observations]),
        )


__all__ = ["NewsSentimentAnalyst"]
