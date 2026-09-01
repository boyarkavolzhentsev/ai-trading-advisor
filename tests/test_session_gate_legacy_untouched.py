"""Stage 9 must not modify any legacy Stage-0 contract, nor any Stage 5/6/7/8
production file.

Pins each file's exact content via a SHA-256 hash computed against the
approved Stage 9 baseline (HEAD ``71b540b138ec6b3befae6c557462a0ada3848ca3``)
- any byte-level change to these files fails this test. Mirrors
``tests/test_portfolio_legacy_untouched.py`` one stage over.
``app/core/config/trading_cycle.py`` is pinned here (unlike Stage 8's own
guard, which excluded it because Stage 8 was the stage that extended it):
Stage 9 needs no new config field, so it stays byte-identical from this
baseline forward. ``README.md`` is deliberately not pinned, for the same
reason every prior stage's guard gives: it is expected to evolve as the
project roadmap evolves.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_SHA256 = {
    # Legacy Stage-0 contracts
    "app/core/models/decision.py": "f264c2d9f34b629ad554e978b276760b8dedeee866b8371f5b41cc1613418841",
    "app/core/models/judge.py": "541478a7ad6f3998c198e38e0810ca7f87f7d5241e53d28a6131c9ba129a6de5",
    "app/core/models/assessment.py": "00202695f9057b3c069676a91ff751cf5f6972bae603d06a69e06db0f36e5cb0",
    "app/core/models/risk.py": "8d6e3b10231272715429f65f7c2f641b133837a38dbf47f59f6e9925c14b294e",
    "app/core/models/money_management.py": "f103cdd5aa9febd0890a2b2d5b470eab823136a6cafbb2daba7b129b3afc6117",
    "app/core/models/trade_setup.py": "e60780fce7d656716e749ceb73db26da46a3cf68917695a001caa46bf1681f3e",
    "app/core/models/position.py": "4a19771c45fa71f81e57bc0b307bbc4a474c99674fba7bc035965d97d571a3b1",
    "app/core/models/performance.py": "fe3d3927021b302858a9e21de939725f55a4f776db9f5fd72e0b404338611a0d",
    "app/core/enums/trade.py": "7da3c8eb65bb90a9ab37ba7111cbc81192d8ea2eb112a90225fa215bf0295078",
    "app/core/enums/judge.py": "3b576fbe57d6240b60b4c2f9e726e52eee56ba51aa8d4abbbbfaf076c98e8825",
    "app/core/enums/session.py": "069e783222d4b375599691ac75c3f5ca792811b8e7d5eb6b8ae7b743c306eac8",
    # Config - not extended by Stage 9, pinned from this baseline forward
    "app/core/config/trading_cycle.py": "78cc258dacc283e7dd5a8c16920fff53596449cec9774b10192518344ed58df0",
    # Stage 6A production files
    "app/core/enums/strategy_router.py": "b324f9b6f34bbdf754ed8def05aa3ecb2ceed8e3b25ad2f70d92079280905d27",
    "app/core/models/strategy_router_result.py": "c21ad782b917350419f446a9a2ad27d289342a3f3cfe783b3f32a451c5b9ee69",
    "app/strategies/__init__.py": "26b0f38b00fd056215e32ba7ac49ef7724488c08f12ba0a912d4090c9778406c",
    "app/strategies/router.py": "a56f0fffc28bb10535932bf6abba6070d6d9226de38dc962d98f2edcfa109b1e",
    "app/strategies/protocols.py": "b43e7c9a8890b9c6da0c7b0bd90b25dd1908b7c05f9e4664d71b2d10872759ee",
    # Stage 6B production files
    "app/core/enums/strategy_judge.py": "a04c88c7565f171752eeea6d5ccb8278fc8f2f0a95306b93fb9d84625ae95c20",
    "app/core/models/strategy_judge_result.py": "5664dd6d0925dc1fa058dcc41382f91f8867091c62d3e940048a92f2d95186c6",
    "app/judge/__init__.py": "ccb001d5d9d8ed0f48936b6362c8da38c255d217f7edd3a8e5caec40bf3017da",
    "app/judge/judge.py": "436164e06d42bbabd040af536cb618ec2d230edab3d3f786fa2c9465aaf7706c",
    "app/judge/protocols.py": "a9c88a96548eded6737787dfc20d59cad9b70e928c5bb65653753a69e520283e",
    # Stage 6C production files
    "app/core/enums/policy_gate.py": "51a904273d1dbe8124491c3ebd3824086faf4026d4abb0ac7ed7cc5ae8aff48b",
    "app/core/models/policy_gate_result.py": "e5244bd75afb5063b00b0ee171c6828b7b0196a01c99d6ae42bfad1392518e5c",
    "app/decision/__init__.py": "240d788f647b7534412b1ed29208d392cbd3d6a3276cd74c13e994a276ac6282",
    "app/decision/gate.py": "62ebf788fafe88d5f8adb28a5bf3035e081be1430117afac8a0f4e9f7bbcd231",
    "app/decision/protocols.py": "79e02296fdf259d2d98e1597ae9507af4d196c669a945f7949d0afa8db42cf01",
    # Stage 7 production files
    "app/core/enums/risk_gate.py": "ff6c1c36985d4a7527bf5ba6246d0bca8bcbf54b7677239c9edf5e9fddb52b07",
    "app/core/models/risk_gate_result.py": "af8036acbc3a0c92f51fec038afb18cd27bb79770c5f028daaedcf907e53a568",
    "app/risk/__init__.py": "79c39403c243960bab47ff55ce21e914f81a0d87ad6d4de635cced83870c9c53",
    "app/risk/engine.py": "74a6ac1095d8ac4627b0d5d11d240d249e06ec3f69bb5df4a51724b0bdb53041",
    "app/risk/protocols.py": "82259f4f9eb3a42ca8ce649d79187f64de63e736112465860883146421bae5d4",
    "app/risk/errors.py": "637dfe4591e0ce12eb18aab044dfdf6aa0fc8f11c278121727c95f01fb539dab",
    "app/money_management/__init__.py": "9c4369b4dcd4583210e7729a07fcca32d044280d1092a59b79d0f43958a26907",
    "app/money_management/sizing.py": "0e5c209935aa008d3f1d34e62157d9f0a0dba1bbe11c7bb6c17cdf09755787cc",
    # Stage 8 production files
    # NOTE: portfolio.py, portfolio_result.py and supervisor.py were
    # deliberately, approvedly modified after this baseline was pinned, to
    # correct the Stage 7/Stage 8 joint-risk-allocation gap (see the Stage
    # 7->8 corrective-design audit): Stage 8 previously enforced only its own
    # portfolio-percent capacity, allowing aggregate new-trade risk to exceed
    # Stage 7's shared daily-loss capacity even though every individual
    # Stage 7 family verdict and the Stage 8 portfolio cap were each
    # independently valid. These three hashes were bumped to the corrected
    # content as part of that approved, out-of-band fix - not by Stage 9.
    "app/core/enums/portfolio.py": "16c9d295a0c6915e126b6b84d78de8a7af7eee913ba556a78a868f9dfdfaf56f",
    "app/core/models/portfolio_result.py": "9282bafa3fc6064173e4e0cc80feec70be9d31a69f1fdc0c00e23729683b341c",
    "app/diversification/__init__.py": "16737f2cd3895c7b64b2f88780f6db9a256b95c238d0c2cfd60387fc5d8aa2ae",
    "app/diversification/supervisor.py": "75c51ffb2f14333a6a641482196e2f1d4990ce7c578139c35c51cd6eb72651aa",
    "app/diversification/protocols.py": "303f369771c12d9ac41247337af2f7c899adb5e1f36badaae90eaa1140c6084f",
    # Stage 5 production files (upstream of 6/7/8/9, must also stay untouched)
    "app/market_evaluation/__init__.py": "cd97fcd8afc4e3da5292f8cb911c83e49b18ee313c0d9638ea4b14bed23a1e12",
    "app/market_evaluation/evaluator.py": "2f75f6c8004647057dae8ab55fe26cb349419789d26bdea4ef779b9458a48e93",
    "app/market_evaluation/protocols.py": "ab646e27995a979886b583dca0c01accc374cd335ba0916ee6b360edb6580cc1",
    "app/market_evaluation/errors.py": "f17bc3f13278d2bb0251d574aeca0582df6edeb031ca49ef385a260b8001e0d6",
}


@pytest.mark.parametrize("relative_path, expected_hash", sorted(EXPECTED_SHA256.items()))
def test_file_byte_identical_to_pre_stage_9_baseline(relative_path, expected_hash) -> None:
    content = (REPO_ROOT / relative_path).read_bytes()
    actual_hash = hashlib.sha256(content).hexdigest()
    assert actual_hash == expected_hash, f"{relative_path} was modified since the Stage 9 baseline"
