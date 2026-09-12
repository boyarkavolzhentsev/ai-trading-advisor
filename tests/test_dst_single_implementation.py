"""Stage A corrective review, concern C: exactly one DST fold-resolution
algorithm may exist - ``app.core.time_normalization.resolve_unambiguous_utc``
- never a second independent copy inside
``app.high_impact_event_bridge.file_reader``."""

from __future__ import annotations

import inspect

import app.high_impact_event_bridge.file_reader as file_reader


def test_file_reader_has_no_private_fold_resolution_function() -> None:
    assert not hasattr(file_reader, "_resolve_unambiguous_utc")


def test_file_reader_delegates_to_shared_utility() -> None:
    source = inspect.getsource(file_reader)
    assert "from app.core.time_normalization import resolve_unambiguous_utc" in source
    assert "resolve_unambiguous_utc(naive_server_time, zone)" in source


def test_file_reader_contains_no_second_fold_comparison_algorithm() -> None:
    """A second, independent fold-resolution implementation would need its
    own ``fold=0``/``fold=1`` comparison - assert that shape does not exist
    in this module's own source (it lives solely in
    ``app.core.time_normalization`` now)."""
    source = inspect.getsource(file_reader)
    assert "fold=0" not in source
    assert "fold=1" not in source


def test_convert_server_time_to_utc_has_exactly_one_return_statement() -> None:
    source = inspect.getsource(file_reader._convert_server_time_to_utc)
    assert source.count("return ") == 1
