"""Stage 8 ``PortfolioSupervisorProtocol`` is runtime-checkable and
``PortfolioSupervisor`` satisfies it structurally."""

from __future__ import annotations

import inspect

from app.diversification.protocols import PortfolioSupervisorProtocol
from app.diversification.supervisor import PortfolioSupervisor


def test_portfolio_supervisor_satisfies_protocol() -> None:
    assert isinstance(PortfolioSupervisor(), PortfolioSupervisorProtocol)


def test_protocol_is_runtime_checkable() -> None:
    assert getattr(PortfolioSupervisorProtocol, "_is_runtime_protocol", False) is True


def test_protocol_evaluate_signature_has_no_extra_parameters() -> None:
    signature = inspect.signature(PortfolioSupervisorProtocol.evaluate)
    params = list(signature.parameters)
    assert params == ["self", "strategy_risk_result"]
    assert signature.parameters["strategy_risk_result"].kind is inspect.Parameter.KEYWORD_ONLY
