"""Concrete market data provider adapters.

One subpackage per venue. Each adapter maps its provider's payloads onto the
internal contracts and raises only ``app.market_data.exceptions`` errors.
"""
