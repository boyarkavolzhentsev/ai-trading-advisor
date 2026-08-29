"""Stage 4G time-consistency tests.

``result.analysis_time <= analysis_time`` is required for every supplied
result; a future result raises ``FutureResultTimeError``. No age tolerance,
no second staleness threshold, no wall clock.
"""

from __future__ import annotations

import ast
import inspect
from datetime import timedelta
from pathlib import Path

import pytest

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.external_intelligence_supervisor import errors, protocols, supervisor
from app.external_intelligence_supervisor.errors import FutureResultTimeError
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor
from tests.external_intelligence_supervisor_support import NOW, analyzed_result

MODULES = (errors, protocols, supervisor)


def test_earlier_result_time_is_accepted() -> None:
    earlier = NOW - timedelta(hours=1)
    result = analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, analysis_time=earlier)
    aggregated = ExternalIntelligenceSupervisor().aggregate((result,), analysis_time=NOW)
    assert aggregated.analysis_time == NOW


def test_equal_result_time_is_accepted() -> None:
    result = analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, analysis_time=NOW)
    aggregated = ExternalIntelligenceSupervisor().aggregate((result,), analysis_time=NOW)
    assert aggregated.analysis_time == NOW


def test_future_result_time_is_rejected() -> None:
    later = NOW + timedelta(hours=1)
    result = analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, analysis_time=later)
    with pytest.raises(FutureResultTimeError):
        ExternalIntelligenceSupervisor().aggregate((result,), analysis_time=NOW)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_wall_clock_usage(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"now", "utcnow", "today"}:
            pytest.fail(f"{module.__name__} calls a wall-clock method: .{node.attr}")
