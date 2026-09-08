"""High-Impact Event Risk Gate behavioral tests (Corrective V1 Integration,
test groups B-M, N-P, AD, AE).

Every scenario builds a real ``StrategySetupResult`` via the real Stage
5A-6C-Setup Construction chain (``tests.high_impact_event_support``) and
runs it through the real ``HighImpactEventGate`` - never a hand-rolled
result.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.enums.high_impact_event import HighImpactEventDataQuality, HighImpactEventVerdict
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.high_impact_event import HighImpactEventSymbolOverride, HighImpactEventSymbolScopeConfig
from app.decision.high_impact_event_gate import HighImpactEventGate
from tests.high_impact_event_support import (
    EVENT_TIME,
    btc_context,
    constructed_setup_result,
    constructed_setup_result_with_event_driven_blocked,
    degraded_context,
    fresh_context,
    record,
    unrelated_context,
    usd_context,
    wti_context,
)


def _trend_following(setup_result, context, as_of, *, symbol_scope_config=None):
    result = HighImpactEventGate().evaluate(
        strategy_setup_result=setup_result, context=context, as_of=as_of, symbol_scope_config=symbol_scope_config
    )
    return next(r for r in result.family_results if r.family is StrategyFamily.TREND_FOLLOWING), result


# --- B/C/D: no/unrelated/ignored events ---


def test_no_event_context_allows() -> None:
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    family, result = _trend_following(setup, None, as_of)
    assert family.verdict is HighImpactEventVerdict.ALLOWED
    assert family.data_quality is HighImpactEventDataQuality.UNAVAILABLE


def test_unrelated_scope_event_allows() -> None:
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result(context=unrelated_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_code="US_NFP", event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.ALLOWED
    assert family.relevant_events == ()


def test_low_and_none_importance_ignored_even_at_block_time() -> None:
    as_of = EVENT_TIME - timedelta(minutes=1)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    for importance in ("LOW", "NONE"):
        ctx = fresh_context(events=(record(event_code="US_NFP", event_time=EVENT_TIME, importance=importance),), as_of=as_of)
        family, _ = _trend_following(setup, ctx, as_of)
        assert family.verdict is HighImpactEventVerdict.ALLOWED
        assert family.relevant_events == ()


def test_moderate_allowlisted_event_is_warn_only_never_blocks() -> None:
    as_of = EVENT_TIME - timedelta(minutes=1)  # deep inside the BLOCK window for HIGH
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_code="US_NFP", event_time=EVENT_TIME, importance="MODERATE"),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.WARNED


def test_warn_only_event_code_never_blocks_even_at_high_importance() -> None:
    as_of = EVENT_TIME - timedelta(minutes=1)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_code="US_GDP", event_time=EVENT_TIME, importance="HIGH"),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.WARNED


# --- F-M: temporal window semantics ---


def test_t_minus_20_allows() -> None:
    as_of = EVENT_TIME - timedelta(minutes=20)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.ALLOWED


def test_t_minus_10_warns() -> None:
    as_of = EVENT_TIME - timedelta(minutes=10)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.WARNED


def test_t_minus_4_blocks() -> None:
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.BLOCKED
    assert family.next_safe_time == EVENT_TIME + timedelta(minutes=5)


def test_valid_until_crossing_into_block_window_blocks_even_though_signal_time_alone_looks_safe() -> None:
    """signal_time=T-3, valid_until=T+2 (signal_time alone is outside a
    naive +-2min proximity check, but the setup's own 5-minute validity
    window crosses the event) - the canonical worked example from the
    approved design report."""
    as_of = EVENT_TIME - timedelta(minutes=3)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    assert setup.family_results[0].setup.valid_until == as_of + timedelta(minutes=5)
    ctx = fresh_context(events=(record(event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.BLOCKED


def test_t_plus_30s_blocks() -> None:
    as_of = EVENT_TIME + timedelta(seconds=30)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.BLOCKED


def test_t_plus_3m_blocks() -> None:
    as_of = EVENT_TIME + timedelta(minutes=3)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.BLOCKED


def test_t_plus_8m_warns() -> None:
    as_of = EVENT_TIME + timedelta(minutes=8)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.WARNED


def test_t_plus_11m_allows() -> None:
    as_of = EVENT_TIME + timedelta(minutes=11)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.ALLOWED


# --- N/O/P: market relevance ---

_TEST_WTI_SYMBOL = "TEST_WTI_INSTRUMENT"
_TEST_BRENT_SYMBOL = "TEST_BRENT_INSTRUMENT"
"""Deliberately NOT broker-naming-convention-looking strings (no
'XTI'/'WTI'/'XBR'/'BRENT' substring pattern the gate could accidentally be
keying off of) - proves relevance comes only from the explicit override
config, never from the symbol's own name."""


def _eia_symbol_scope_config() -> HighImpactEventSymbolScopeConfig:
    return HighImpactEventSymbolScopeConfig(
        overrides=(
            HighImpactEventSymbolOverride(
                event_code="EIA_CRUDE_INVENTORIES", symbols=(_TEST_WTI_SYMBOL, _TEST_BRENT_SYMBOL)
            ),
        )
    )


def test_eia_blocks_explicitly_configured_wti_like_symbol() -> None:
    """(6.A) EIA blocks a configured WTI-like test symbol."""
    as_of = EVENT_TIME + timedelta(minutes=3)
    ctx_market = wti_context(symbol=_TEST_WTI_SYMBOL)
    setup = constructed_setup_result(context=ctx_market, as_of=as_of)
    ctx = fresh_context(events=(record(event_code="EIA_CRUDE_INVENTORIES", event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of, symbol_scope_config=_eia_symbol_scope_config())
    assert family.verdict is HighImpactEventVerdict.BLOCKED


def test_eia_blocks_explicitly_configured_brent_like_symbol() -> None:
    """(6.B) EIA blocks a configured Brent-like test symbol."""
    as_of = EVENT_TIME + timedelta(minutes=3)
    ctx_market = wti_context(symbol=_TEST_BRENT_SYMBOL)
    setup = constructed_setup_result(context=ctx_market, as_of=as_of)
    ctx = fresh_context(events=(record(event_code="EIA_CRUDE_INVENTORIES", event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of, symbol_scope_config=_eia_symbol_scope_config())
    assert family.verdict is HighImpactEventVerdict.BLOCKED


def test_eia_does_not_block_btc_even_with_config_supplied() -> None:
    """(6.C) EIA does NOT block BTC, even when a symbol_scope_config is
    supplied (BTC is simply absent from its EIA_CRUDE_INVENTORIES entry)."""
    as_of = EVENT_TIME + timedelta(minutes=3)
    setup = constructed_setup_result(context=btc_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_code="EIA_CRUDE_INVENTORIES", event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of, symbol_scope_config=_eia_symbol_scope_config())
    assert family.verdict is HighImpactEventVerdict.ALLOWED
    assert family.relevant_events == ()


def test_eia_never_guesses_an_unconfigured_energy_looking_symbol() -> None:
    """(6.D) An unconfigured arbitrary energy-looking symbol (deliberately
    named to look like a plausible WTI ticker) is NOT guessed as relevant -
    no config entry means no match, ever, regardless of the symbol's name."""
    as_of = EVENT_TIME + timedelta(minutes=3)
    ctx_market = wti_context(symbol="XTIUSD")  # looks like a real WTI CFD ticker - deliberately NOT in the config below
    setup = constructed_setup_result(context=ctx_market, as_of=as_of)
    ctx = fresh_context(events=(record(event_code="EIA_CRUDE_INVENTORIES", event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of, symbol_scope_config=_eia_symbol_scope_config())
    assert family.verdict is HighImpactEventVerdict.ALLOWED
    assert family.relevant_events == ()


def test_eia_no_config_supplied_never_matches_any_symbol() -> None:
    as_of = EVENT_TIME + timedelta(minutes=3)
    setup = constructed_setup_result(context=wti_context(symbol=_TEST_WTI_SYMBOL), as_of=as_of)
    ctx = fresh_context(events=(record(event_code="EIA_CRUDE_INVENTORIES", event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of, symbol_scope_config=None)
    assert family.verdict is HighImpactEventVerdict.ALLOWED


def test_eia_relevance_is_deterministic_same_config_same_output() -> None:
    """(6.E) Same explicit mapping + same inputs -> deterministic same
    output."""
    as_of = EVENT_TIME + timedelta(minutes=3)
    setup = constructed_setup_result(context=wti_context(symbol=_TEST_WTI_SYMBOL), as_of=as_of)
    ctx = fresh_context(events=(record(event_code="EIA_CRUDE_INVENTORIES", event_time=EVENT_TIME),), as_of=as_of)
    config = _eia_symbol_scope_config()

    first, _ = _trend_following(setup, ctx, as_of, symbol_scope_config=config)
    second, _ = _trend_following(setup, ctx, as_of, symbol_scope_config=config)
    assert first == second
    assert first.verdict is HighImpactEventVerdict.BLOCKED


def test_gate_module_contains_no_symbol_name_heuristics() -> None:
    """(6.F) No symbol-name heuristics - contains()/startswith() calls, or
    literal 'WTI'/'BRENT'/'XTI'/'XBR' substrings - exist anywhere in the
    gate module's source."""
    import inspect

    import app.decision.high_impact_event_gate as gate_module

    source = inspect.getsource(gate_module)
    for forbidden in (".contains(", ".startswith(", '"WTI"', '"BRENT"', '"XTI', '"XBR'):
        assert forbidden not in source, forbidden
    assert "XTIUSD" not in source
    assert "XBRUSD" not in source


def test_fomc_blocks_usd_sensitive_btc_scope() -> None:
    as_of = EVENT_TIME + timedelta(minutes=3)
    setup = constructed_setup_result(context=btc_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_code="FOMC", event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.BLOCKED


def test_fomc_blocks_eur_usd_fx_scope() -> None:
    as_of = EVENT_TIME + timedelta(minutes=3)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_code="FOMC", event_time=EVENT_TIME),), as_of=as_of)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.BLOCKED


# --- Q: Setup-BLOCKED family omitted ---


def test_setup_blocked_family_omitted_from_event_family_results() -> None:
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result_with_event_driven_blocked(context=btc_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_code="FOMC", event_time=EVENT_TIME),), as_of=as_of)
    result = HighImpactEventGate().evaluate(strategy_setup_result=setup, context=ctx, as_of=as_of)

    non_constructed = {r.family for r in setup.family_results if r.outcome.value != "CONSTRUCTED"}
    assert StrategyFamily.EVENT_DRIVEN in non_constructed  # unconditionally Setup-BLOCKED (FAMILY_SETUP_UNAVAILABLE)

    present_families = {r.family for r in result.family_results}
    assert StrategyFamily.TREND_FOLLOWING in present_families
    assert present_families.isdisjoint(non_constructed)


# --- AD: determinism ---


def test_deterministic_same_input_same_output() -> None:
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_time=EVENT_TIME),), as_of=as_of)

    first = HighImpactEventGate().evaluate(strategy_setup_result=setup, context=ctx, as_of=as_of)
    second = HighImpactEventGate().evaluate(strategy_setup_result=setup, context=ctx, as_of=as_of)
    assert first == second


# --- AE: no auto-execution behavior ---


def test_gate_result_has_no_execution_or_order_surface() -> None:
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    result = HighImpactEventGate().evaluate(strategy_setup_result=setup, context=None, as_of=as_of)
    assert not hasattr(result, "order")
    assert not hasattr(result, "execute")
    assert not hasattr(result, "send")


# --- fail-open with a supplied but degraded context ---


def test_stale_context_fails_open() -> None:
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = degraded_context(data_quality=HighImpactEventDataQuality.STALE, generated_at=as_of - timedelta(hours=2))
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.ALLOWED
    assert family.data_quality is HighImpactEventDataQuality.STALE


def test_malformed_context_fails_open() -> None:
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = degraded_context(data_quality=HighImpactEventDataQuality.MALFORMED)
    family, _ = _trend_following(setup, ctx, as_of)
    assert family.verdict is HighImpactEventVerdict.ALLOWED
    assert family.data_quality is HighImpactEventDataQuality.MALFORMED
