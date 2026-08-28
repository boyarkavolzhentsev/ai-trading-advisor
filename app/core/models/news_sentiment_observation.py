"""Stage 4D provider-native news-sentiment fact.

One sentiment-feed-reported observation about one retained ``NewsItem``
observation, at one point in that sentiment feed's own lifecycle. Facts
only - a provider-native pass-through, never an internally-derived
interpretation: nothing in ``app.news_intel`` parses ``NewsItem.headline``/
``body``/``provider_tags`` to compute a sentiment value. A future
internally-derived sentiment feature belongs to a separately reviewed
feature/analyst contract, never silently mixed into this schema (see the
Stage 4D design report review).

``sentiment_score`` is unconstrained ``Decimal | None`` - this model does
not know, and does not assume, the reporting provider's scale. There is no
canonical bound, no rescaling, and no normalization: the value is preserved
exactly as the provider represented it, using ``Decimal`` (never ``float``)
so that representation is exact rather than subject to binary-float
rounding. ``None`` means the provider did not supply a numeric score;
``Decimal("0")`` is always a real, valid reported value, on the same "genuine
zero is never conflated with missing" discipline used throughout
(``EconomicEvent.actual``, ``PolicyRateObservation.value``, ...). This model
makes no claim about what any endpoint or zero *means* for a given
provider's scale - that interpretation is out of scope here.

``sentiment_label`` is preserved verbatim as an unconstrained string - never
normalized onto an internal closed vocabulary, mirroring
``NewsItem.provider_tags`` staying raw rather than an invented taxonomy.

Identity across versions is ``(provider, source_provider,
source_provider_item_id, target_symbol)`` - see ``app.news_intel.sentiment_history``
for the version-preserving append rules. There is no ``origin`` field: every
record in this model *is* provider-native by definition, so a field that
would read ``PROVIDER_NATIVE`` on every row adds nothing - see the Stage 4D
design review.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import Field, model_validator

from app.core.models.base import DomainModel, Symbol, Timestamp


class NewsSentimentObservation(DomainModel):
    """One sentiment-feed-reported observation about one ``NewsItem``, at one version."""

    provider: str = Field(min_length=1)
    source_provider: str = Field(min_length=1)
    source_provider_item_id: str = Field(min_length=1)
    source_received_at: Timestamp
    published_at: Timestamp
    target_symbol: Symbol | None = None
    sentiment_label: str | None = Field(default=None, min_length=1)
    sentiment_score: Decimal | None = None
    sentiment_scale: str | None = Field(default=None, min_length=1)
    received_at: Timestamp

    @model_validator(mode="after")
    def _validate_at_least_one_sentiment_fact(self) -> Self:
        if self.sentiment_label is None and self.sentiment_score is None:
            raise ValueError("at least one of sentiment_label/sentiment_score must be set")
        return self


__all__ = ["NewsSentimentObservation"]
