"""Stage 6A must not modify any legacy Stage-0 contract or
``app/strategies/__init__.py``.

Pins each file's exact content via a SHA-256 hash computed against the
approved Stage 6A baseline (HEAD ``3d0fb1fe960e7ea526b4bbf0904ed237cede5291``)
- any byte-level change to these files fails this test. ``README.md`` is
deliberately not pinned here: it is expected to evolve as the project
roadmap evolves (see the approved pre-commit documentation-maintenance
turn), and a permanent byte-identical guard on it would fail on every
legitimate future documentation update - this guard protects legacy code
contracts only, never documentation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_SHA256 = {
    "app/core/models/decision.py": "f264c2d9f34b629ad554e978b276760b8dedeee866b8371f5b41cc1613418841",
    "app/core/models/judge.py": "541478a7ad6f3998c198e38e0810ca7f87f7d5241e53d28a6131c9ba129a6de5",
    "app/core/models/assessment.py": "00202695f9057b3c069676a91ff751cf5f6972bae603d06a69e06db0f36e5cb0",
    "app/core/enums/trade.py": "7da3c8eb65bb90a9ab37ba7111cbc81192d8ea2eb112a90225fa215bf0295078",
    "app/core/enums/judge.py": "3b576fbe57d6240b60b4c2f9e726e52eee56ba51aa8d4abbbbfaf076c98e8825",
    "app/strategies/__init__.py": "26b0f38b00fd056215e32ba7ac49ef7724488c08f12ba0a912d4090c9778406c",
}


@pytest.mark.parametrize("relative_path, expected_hash", sorted(EXPECTED_SHA256.items()))
def test_file_byte_identical_to_pre_stage_6a_baseline(relative_path, expected_hash) -> None:
    content = (REPO_ROOT / relative_path).read_bytes()
    actual_hash = hashlib.sha256(content).hexdigest()
    assert actual_hash == expected_hash, f"{relative_path} was modified since the Stage 6A baseline"
