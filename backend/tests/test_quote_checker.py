"""Tests for the quote checker's rules. Run from backend/:  pytest -v"""
from app.services.quote_checker import classify, saving_at_fair_price


def test_classify():
    assert classify(12.0) == "overpriced"   # more than 6% above market
    assert classify(6.0) == "fair"          # exactly 6% is still fair
    assert classify(2.5) == "fair"
    assert classify(0.0) == "fair"
    assert classify(-1.0) == "good_deal"    # below market
    assert classify(None) == "unknown"      # material not recognised


def test_saving_at_fair_price():
    # market ₹100 -> fair ₹103. Quoted ₹110 for 500 kg -> (110 - 103) x 500 = ₹3,500
    assert saving_at_fair_price(110, 100, 500) == 3500


def test_no_saving_when_price_is_fair_or_cheaper():
    assert saving_at_fair_price(102, 100, 500) == 0
    assert saving_at_fair_price(95, 100, 500) == 0
