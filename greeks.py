"""Black-Scholes Greeks calculator for European options."""

import numpy as np
from scipy.stats import norm
from dataclasses import dataclass


@dataclass
class Greeks:
    delta: float
    gamma: float
    theta: float  # per day
    vega: float   # per 1% vol move
    iv: float
    option_price: float


def bs_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str = "call") -> float:
    if T <= 0:
        if option_type == "call":
            return max(S - K, 0.0)
        return max(K - S, 0.0)

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == "call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def implied_volatility(market_price: float, S: float, K: float, T: float, r: float,
                       option_type: str = "call", tol: float = 1e-6, max_iter: int = 100) -> float:
    """Newton-Raphson implied volatility solver."""
    if T <= 0:
        return 0.0

    sigma = 0.3  # initial guess
    for _ in range(max_iter):
        price = bs_price(S, K, T, r, sigma, option_type)
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        vega = S * norm.pdf(d1) * np.sqrt(T)
        if vega < 1e-10:
            break
        sigma -= (price - market_price) / vega
        sigma = max(sigma, 0.01)
        if abs(price - market_price) < tol:
            break
    return sigma


def calculate_greeks(S: float, K: float, T: float, r: float, sigma: float,
                     option_type: str = "call") -> Greeks:
    if T <= 0:
        intrinsic = max(S - K, 0.0) if option_type == "call" else max(K - S, 0.0)
        delta = 1.0 if (option_type == "call" and S > K) else (-1.0 if option_type == "put" and S < K else 0.0)
        return Greeks(delta=delta, gamma=0.0, theta=0.0, vega=0.0, iv=sigma, option_price=intrinsic)

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == "call":
        delta = norm.cdf(d1)
        theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                 - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
    else:
        delta = norm.cdf(d1) - 1
        theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                 + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365

    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100  # per 1% move

    price = bs_price(S, K, T, r, sigma, option_type)

    return Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega, iv=sigma, option_price=price)
