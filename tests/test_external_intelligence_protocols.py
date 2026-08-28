"""Stage 4F analyst structural protocol conformance - four narrow protocols, not one."""

from __future__ import annotations

from app.external_intelligence_analysts import MacroEventAnalyst, NewsSentimentAnalyst, OnChainAnalyst, RatesYieldAnalyst
from app.external_intelligence_analysts.protocols import (
    MacroEventAnalystProtocol,
    NewsSentimentAnalystProtocol,
    OnChainAnalystProtocol,
    RatesYieldAnalystProtocol,
)


def test_macro_event_analyst_satisfies_its_protocol() -> None:
    assert isinstance(MacroEventAnalyst(), MacroEventAnalystProtocol)


def test_rates_yield_analyst_satisfies_its_protocol() -> None:
    assert isinstance(RatesYieldAnalyst(), RatesYieldAnalystProtocol)


def test_news_sentiment_analyst_satisfies_its_protocol() -> None:
    assert isinstance(NewsSentimentAnalyst(), NewsSentimentAnalystProtocol)


def test_on_chain_analyst_satisfies_its_protocol() -> None:
    assert isinstance(OnChainAnalyst(), OnChainAnalystProtocol)


def test_protocols_have_distinct_analyze_signatures() -> None:
    """Four distinct protocols, not one shared shape. ``isinstance`` against
    a ``runtime_checkable`` ``Protocol`` only checks that a method of the
    right *name* exists (Python does not verify parameter signatures at
    runtime), so a genuinely different-shaped analyst can still structurally
    satisfy an unrelated Protocol via ``isinstance`` - that is a known
    Python typing limitation, not a Stage 4F defect. The real, checkable
    guarantee is that the four ``analyze`` signatures are not identical."""
    import inspect

    signatures = {
        protocol_cls.__name__: tuple(inspect.signature(protocol_cls.analyze).parameters)
        for protocol_cls in (
            MacroEventAnalystProtocol,
            RatesYieldAnalystProtocol,
            NewsSentimentAnalystProtocol,
            OnChainAnalystProtocol,
        )
    }
    assert len(set(signatures.values())) == 4, signatures


def test_analysts_carry_the_correct_analyst_type() -> None:
    from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType

    assert MacroEventAnalyst.analyst_type is ExternalIntelligenceAnalystType.MACRO_EVENT
    assert RatesYieldAnalyst.analyst_type is ExternalIntelligenceAnalystType.RATES_YIELD
    assert NewsSentimentAnalyst.analyst_type is ExternalIntelligenceAnalystType.NEWS_SENTIMENT
    assert OnChainAnalyst.analyst_type is ExternalIntelligenceAnalystType.ON_CHAIN


def test_no_generic_analyze_args_protocol_exists() -> None:
    """No fake generic analyze(*args) protocol was created to force one
    shared shape - each Protocol's analyze method has explicit typed
    parameters, checked via signature inspection."""
    import inspect

    for protocol_cls in (
        MacroEventAnalystProtocol,
        RatesYieldAnalystProtocol,
        NewsSentimentAnalystProtocol,
        OnChainAnalystProtocol,
    ):
        signature = inspect.signature(protocol_cls.analyze)
        params = list(signature.parameters.values())
        assert not any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in params)
        assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params)
