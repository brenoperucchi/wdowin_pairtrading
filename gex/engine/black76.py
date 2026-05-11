import math
import numpy as np
from scipy.stats import norm

def black76_gamma(F, K, T, sigma):
    """
    Calculates the Gamma of an option on a futures contract using the Black-76 model.
    Gamma is identical for Calls and Puts in Black-76.

    :param F: Current futures price (e.g., WIN price)
    :param K: Strike price (converted to WIN equivalent)
    :param T: Time to expiration in years (e.g., days / 252)
    :param sigma: Implied volatility (e.g., 0.20 for 20%)
    :return: Gamma value
    """
    if T <= 0 or sigma <= 0 or F <= 0 or K <= 0:
        return 0.0

    d1 = (np.log(F / K) + (0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    
    # N'(d1) is the standard normal probability density function (PDF)
    n_prime_d1 = norm.pdf(d1)
    
    # Gamma formula for Black-76
    gamma = n_prime_d1 / (F * sigma * np.sqrt(T))
    return gamma

def black76_call_price(F, K, T, sigma, r):
    """
    Calculates Call price using Black-76.
    """
    if T <= 0 or sigma <= 0 or F <= 0 or K <= 0:
        return max(0.0, F - K) * np.exp(-r * max(T, 0))
    d1 = (np.log(F / K) + (0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return np.exp(-r * T) * (F * norm.cdf(d1) - K * norm.cdf(d2))

def black76_put_price(F, K, T, sigma, r):
    """
    Calculates Put price using Black-76.
    """
    if T <= 0 or sigma <= 0 or F <= 0 or K <= 0:
        return max(0.0, K - F) * np.exp(-r * max(T, 0))
    d1 = (np.log(F / K) + (0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return np.exp(-r * T) * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
