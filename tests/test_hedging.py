from hedging import calculate_hedge


def test_hedge_holds_inside_rebalance_threshold():
    hedge = calculate_hedge(portfolio_position_delta=-432, current_hedge_shares=410, ticker="PLTR")

    assert hedge.portfolio_delta == -22
    assert hedge.rebalance_needed is False
    assert hedge.signal == "HOLD"


def test_hedge_buys_when_net_delta_too_negative():
    hedge = calculate_hedge(portfolio_position_delta=-432, current_hedge_shares=350, ticker="PLTR")

    assert hedge.rebalance_needed is True
    assert hedge.signal == "BUY"
    assert hedge.shares_needed == 82


def test_hedge_sells_when_net_delta_too_positive():
    hedge = calculate_hedge(portfolio_position_delta=-432, current_hedge_shares=500, ticker="PLTR")

    assert hedge.rebalance_needed is True
    assert hedge.signal == "SELL"
    assert hedge.shares_needed == -68
