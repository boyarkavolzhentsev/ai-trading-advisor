"""Tests for app.core.models.technical_supervisor_result: TechnicalSupervisorResult validators."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import TechnicalAgreementVerdict, TechnicalAnalysisDimension, TechnicalAnalystType
from app.core.enums.technical_supervisor import TechnicalSupervisorOutcome
from app.core.models.technical_supervisor_result import (
    TechnicalAnalystSummary,
    TechnicalCoherenceResult,
    TechnicalSupervisorResult,
    TechnicalTimeframeSummary,
)
from tests.technical_supervisor_support import CONTRACT_TYPE, NOW, SYMBOL, abstained_result, analyzed_result, dimension_result


def _valid_result(**overrides: object) -> TechnicalSupervisorResult:
    trend_m1 = analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1)
    fields: dict[str, object] = dict(
        symbol=SYMBOL,
        contract_type=CONTRACT_TYPE,
        observation_time=NOW,
        outcome=TechnicalSupervisorOutcome.PARTIAL,
        expected_analysts=(TechnicalAnalystType.TREND, TechnicalAnalystType.MOMENTUM),
        expected_timeframes=(Timeframe.M1,),
        analyzed_cells=((TechnicalAnalystType.TREND, Timeframe.M1),),
        abstained_cells=(),
        missing_cells=((TechnicalAnalystType.MOMENTUM, Timeframe.M1),),
        expected_count=2,
        analyzed_count=1,
        abstained_count=0,
        missing_count=1,
        usable_cell_ratio=0.5,
        overall_quality=FeatureQuality.VALID,
        per_timeframe_summaries=(
            TechnicalTimeframeSummary(
                timeframe=Timeframe.M1,
                analyzed_analysts=(TechnicalAnalystType.TREND,),
                abstained_analysts=(),
                missing_analysts=(TechnicalAnalystType.MOMENTUM,),
                analyzed_count=1,
                abstained_count=0,
                missing_count=1,
                usable_ratio=0.5,
                quality=FeatureQuality.VALID,
            ),
        ),
        per_analyst_summaries=(
            TechnicalAnalystSummary(
                analyst_type=TechnicalAnalystType.TREND,
                analyzed_timeframes=(Timeframe.M1,),
                abstained_timeframes=(),
                missing_timeframes=(),
                analyzed_count=1,
                abstained_count=0,
                missing_count=0,
                usable_ratio=1.0,
                quality=FeatureQuality.VALID,
            ),
            TechnicalAnalystSummary(
                analyst_type=TechnicalAnalystType.MOMENTUM,
                analyzed_timeframes=(),
                abstained_timeframes=(),
                missing_timeframes=(Timeframe.M1,),
                analyzed_count=0,
                abstained_count=0,
                missing_count=1,
                usable_ratio=0.0,
                quality=FeatureQuality.UNAVAILABLE,
            ),
        ),
        coherence=(
            TechnicalCoherenceResult(
                dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, verdict=TechnicalAgreementVerdict.INSUFFICIENT_DATA
            ),
        ),
        analyst_results=(trend_m1,),
        provenance={"trend": "test"},
    )
    fields.update(overrides)
    return TechnicalSupervisorResult(**fields)


def _coherence_baseline(**overrides: object) -> TechnicalSupervisorResult:
    """Mirrors what ``TechnicalSupervisor.aggregate`` would build for two
    fully ANALYZED, ALL_AGREE cells - isolates coherence/evidence-ref
    validators from the participation validators exercised by ``_valid_result``.
    """
    trend_m1 = dimension_result(TechnicalAnalystType.TREND, Timeframe.M1, TechnicalAnalysisDimension.RETURN_DIRECTION, "UPWARD")
    trend_h4 = dimension_result(TechnicalAnalystType.TREND, Timeframe.H4, TechnicalAnalysisDimension.RETURN_DIRECTION, "UPWARD")
    fields: dict[str, object] = dict(
        symbol=SYMBOL,
        contract_type=CONTRACT_TYPE,
        observation_time=NOW,
        outcome=TechnicalSupervisorOutcome.ANALYZED,
        expected_analysts=(TechnicalAnalystType.TREND,),
        expected_timeframes=(Timeframe.M1, Timeframe.H4),
        analyzed_cells=((TechnicalAnalystType.TREND, Timeframe.M1), (TechnicalAnalystType.TREND, Timeframe.H4)),
        abstained_cells=(),
        missing_cells=(),
        expected_count=2,
        analyzed_count=2,
        abstained_count=0,
        missing_count=0,
        usable_cell_ratio=1.0,
        overall_quality=FeatureQuality.VALID,
        per_timeframe_summaries=(
            TechnicalTimeframeSummary(
                timeframe=Timeframe.M1,
                analyzed_analysts=(TechnicalAnalystType.TREND,),
                abstained_analysts=(),
                missing_analysts=(),
                analyzed_count=1,
                abstained_count=0,
                missing_count=0,
                usable_ratio=1.0,
                quality=FeatureQuality.VALID,
            ),
            TechnicalTimeframeSummary(
                timeframe=Timeframe.H4,
                analyzed_analysts=(TechnicalAnalystType.TREND,),
                abstained_analysts=(),
                missing_analysts=(),
                analyzed_count=1,
                abstained_count=0,
                missing_count=0,
                usable_ratio=1.0,
                quality=FeatureQuality.VALID,
            ),
        ),
        per_analyst_summaries=(
            TechnicalAnalystSummary(
                analyst_type=TechnicalAnalystType.TREND,
                analyzed_timeframes=(Timeframe.M1, Timeframe.H4),
                abstained_timeframes=(),
                missing_timeframes=(),
                analyzed_count=2,
                abstained_count=0,
                missing_count=0,
                usable_ratio=1.0,
                quality=FeatureQuality.VALID,
            ),
        ),
        coherence=(
            TechnicalCoherenceResult(
                dimension=TechnicalAnalysisDimension.RETURN_DIRECTION,
                verdict=TechnicalAgreementVerdict.ALL_AGREE,
                contributing_timeframes=(Timeframe.M1, Timeframe.H4),
                evidence_refs=((0, 0), (1, 0)),
            ),
        ),
        analyst_results=(trend_m1, trend_h4),
        provenance={"trend": "test"},
    )
    fields.update(overrides)
    return TechnicalSupervisorResult(**fields)


def test_valid_result_roundtrips() -> None:
    result = _valid_result()
    restored = TechnicalSupervisorResult.model_validate(result.model_dump())
    assert restored == result


def test_coherence_baseline_roundtrips() -> None:
    result = _coherence_baseline()
    restored = TechnicalSupervisorResult.model_validate(result.model_dump())
    assert restored == result


def test_duplicate_expected_analysts_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_result(expected_analysts=(TechnicalAnalystType.TREND, TechnicalAnalystType.TREND))


def test_duplicate_expected_timeframes_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_result(expected_timeframes=(Timeframe.M1, Timeframe.M1))


def test_cells_must_partition_expected() -> None:
    with pytest.raises(ValidationError):
        _valid_result(missing_cells=())  # MOMENTUM/M1 now belongs nowhere


def test_cell_buckets_must_be_disjoint() -> None:
    with pytest.raises(ValidationError):
        _valid_result(abstained_cells=((TechnicalAnalystType.TREND, Timeframe.M1),))  # also analyzed


def test_expected_count_must_match_matrix_size() -> None:
    with pytest.raises(ValidationError):
        _valid_result(expected_count=3)


def test_usable_cell_ratio_must_equal_analyzed_over_expected() -> None:
    with pytest.raises(ValidationError):
        _valid_result(usable_cell_ratio=0.9)


def test_analyst_result_key_not_in_any_bucket_rejected() -> None:
    stray = analyzed_result(TechnicalAnalystType.VOLATILITY, Timeframe.M1)
    with pytest.raises(ValidationError):
        _valid_result(analyst_results=(analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1), stray))


def test_analyst_result_status_must_match_bucket() -> None:
    mismatched = abstained_result(TechnicalAnalystType.TREND, Timeframe.M1)
    with pytest.raises(ValidationError):
        _valid_result(analyst_results=(mismatched,))


def test_analyst_result_identity_mismatch_rejected() -> None:
    mismatched = analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, symbol="ETHUSDT")
    with pytest.raises(ValidationError):
        _valid_result(analyst_results=(mismatched,))


def test_coherence_duplicate_group_rejected() -> None:
    duplicate = TechnicalCoherenceResult(
        dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, verdict=TechnicalAgreementVerdict.INSUFFICIENT_DATA
    )
    with pytest.raises(ValidationError):
        _valid_result(coherence=(duplicate, duplicate))


def test_coherence_refs_out_of_bounds_result_index_rejected() -> None:
    with pytest.raises(ValidationError):
        _coherence_baseline(
            coherence=(
                TechnicalCoherenceResult(
                    dimension=TechnicalAnalysisDimension.RETURN_DIRECTION,
                    verdict=TechnicalAgreementVerdict.ALL_AGREE,
                    contributing_timeframes=(Timeframe.M1, Timeframe.H4),
                    evidence_refs=((5, 0), (1, 0)),
                ),
            )
        )


def test_coherence_refs_out_of_bounds_observation_index_rejected() -> None:
    with pytest.raises(ValidationError):
        _coherence_baseline(
            coherence=(
                TechnicalCoherenceResult(
                    dimension=TechnicalAnalysisDimension.RETURN_DIRECTION,
                    verdict=TechnicalAgreementVerdict.ALL_AGREE,
                    contributing_timeframes=(Timeframe.M1, Timeframe.H4),
                    evidence_refs=((0, 99), (1, 0)),
                ),
            )
        )


def test_coherence_ref_dimension_mismatch_rejected() -> None:
    with pytest.raises(ValidationError):
        _coherence_baseline(
            coherence=(
                TechnicalCoherenceResult(
                    dimension=TechnicalAnalysisDimension.SLOPE_DIRECTION,
                    verdict=TechnicalAgreementVerdict.ALL_AGREE,
                    contributing_timeframes=(Timeframe.M1, Timeframe.H4),
                    evidence_refs=((0, 0), (1, 0)),
                ),
            )
        )


def test_coherence_ref_subject_mismatch_rejected() -> None:
    with pytest.raises(ValidationError):
        _coherence_baseline(
            coherence=(
                TechnicalCoherenceResult(
                    dimension=TechnicalAnalysisDimension.RETURN_DIRECTION,
                    subject="20",
                    verdict=TechnicalAgreementVerdict.ALL_AGREE,
                    contributing_timeframes=(Timeframe.M1, Timeframe.H4),
                    evidence_refs=((0, 0), (1, 0)),
                ),
            )
        )


def test_insufficient_data_coherence_must_not_carry_refs() -> None:
    with pytest.raises(ValidationError):
        TechnicalCoherenceResult(
            dimension=TechnicalAnalysisDimension.RETURN_DIRECTION,
            verdict=TechnicalAgreementVerdict.INSUFFICIENT_DATA,
            contributing_timeframes=(Timeframe.M1, Timeframe.H4),
            evidence_refs=((0, 0), (1, 0)),
        )


def test_all_agree_coherence_must_carry_refs() -> None:
    with pytest.raises(ValidationError):
        TechnicalCoherenceResult(dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, verdict=TechnicalAgreementVerdict.ALL_AGREE)


def test_per_timeframe_summary_must_cover_expected_analysts() -> None:
    with pytest.raises(ValidationError):
        _valid_result(
            per_timeframe_summaries=(
                TechnicalTimeframeSummary(
                    timeframe=Timeframe.M1,
                    analyzed_analysts=(TechnicalAnalystType.TREND,),
                    abstained_analysts=(),
                    missing_analysts=(),
                    analyzed_count=1,
                    abstained_count=0,
                    missing_count=0,
                    usable_ratio=1.0,
                    quality=FeatureQuality.VALID,
                ),
            )
        )  # MOMENTUM missing from every bucket - does not cover expected_analysts


def test_per_analyst_summary_must_match_cells() -> None:
    with pytest.raises(ValidationError):
        _valid_result(
            per_analyst_summaries=(
                TechnicalAnalystSummary(
                    analyst_type=TechnicalAnalystType.TREND,
                    analyzed_timeframes=(),
                    abstained_timeframes=(),
                    missing_timeframes=(Timeframe.M1,),
                    analyzed_count=0,
                    abstained_count=0,
                    missing_count=1,
                    usable_ratio=0.0,
                    quality=FeatureQuality.UNAVAILABLE,
                ),  # wrong: TREND is actually analyzed at M1
                TechnicalAnalystSummary(
                    analyst_type=TechnicalAnalystType.MOMENTUM,
                    analyzed_timeframes=(),
                    abstained_timeframes=(),
                    missing_timeframes=(Timeframe.M1,),
                    analyzed_count=0,
                    abstained_count=0,
                    missing_count=1,
                    usable_ratio=0.0,
                    quality=FeatureQuality.UNAVAILABLE,
                ),
            )
        )


def test_result_is_frozen() -> None:
    result = _valid_result()
    with pytest.raises(ValidationError):
        result.overall_quality = FeatureQuality.STALE  # type: ignore[misc]
