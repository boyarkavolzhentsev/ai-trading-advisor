"""Stage 4G protocol conformance tests.

``ExternalIntelligenceSupervisorProtocol`` is runtime-checkable, exposes
only ``aggregate()``, and ``ExternalIntelligenceSupervisor`` structurally
satisfies it.
"""

from __future__ import annotations

import typing

from app.external_intelligence_supervisor.protocols import ExternalIntelligenceSupervisorProtocol
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor


def test_protocol_is_runtime_checkable() -> None:
    assert typing.runtime_checkable(ExternalIntelligenceSupervisorProtocol) is ExternalIntelligenceSupervisorProtocol
    assert isinstance(ExternalIntelligenceSupervisor(), ExternalIntelligenceSupervisorProtocol)


def test_protocol_exposes_only_aggregate() -> None:
    public_methods = {
        name
        for name in vars(ExternalIntelligenceSupervisorProtocol)
        if not name.startswith("_")
    }
    assert public_methods == {"aggregate"}
