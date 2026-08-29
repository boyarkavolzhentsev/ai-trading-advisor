"""Stage 4G ``expected_analysts`` constructor tests.

``expected_analysts`` defines the analyst-*type* set only - never expected
currencies/symbols/assets/networks/scopes/scope counts.
"""

from __future__ import annotations

import pytest

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.external_intelligence_supervisor.errors import ExternalIntelligenceSupervisorInputError
from app.external_intelligence_supervisor.supervisor import DEFAULT_EXPECTED_ANALYSTS, ExternalIntelligenceSupervisor
from tests.external_intelligence_supervisor_support import NOW, analyzed_result


def test_default_expected_analysts_is_exactly_four() -> None:
    supervisor = ExternalIntelligenceSupervisor()
    assert supervisor.expected_analysts == DEFAULT_EXPECTED_ANALYSTS
    assert set(supervisor.expected_analysts) == set(ExternalIntelligenceAnalystType)
    assert len(supervisor.expected_analysts) == 4


def test_custom_subset_is_accepted() -> None:
    subset = (ExternalIntelligenceAnalystType.NEWS_SENTIMENT, ExternalIntelligenceAnalystType.ON_CHAIN)
    supervisor = ExternalIntelligenceSupervisor(subset)
    assert set(supervisor.expected_analysts) == set(subset)

    result = supervisor.aggregate(
        (analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT),), analysis_time=NOW
    )
    assert ExternalIntelligenceAnalystType.MACRO_EVENT not in result.expected_analyst_types


def test_empty_expected_set_is_rejected() -> None:
    with pytest.raises(ExternalIntelligenceSupervisorInputError):
        ExternalIntelligenceSupervisor(())


def test_duplicate_expected_type_is_rejected() -> None:
    with pytest.raises(ExternalIntelligenceSupervisorInputError):
        ExternalIntelligenceSupervisor(
            (ExternalIntelligenceAnalystType.MACRO_EVENT, ExternalIntelligenceAnalystType.MACRO_EVENT)
        )


def test_expected_analysts_canonicalized_regardless_of_constructor_order() -> None:
    reversed_order = tuple(reversed(list(ExternalIntelligenceAnalystType)))
    supervisor = ExternalIntelligenceSupervisor(reversed_order)
    assert supervisor.expected_analysts == tuple(ExternalIntelligenceAnalystType)
