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

def black76_vega(F, K, T, sigma, r):
    """
    Calculates the Vega of an option using Black-76.
    Vega is the derivative of the option price with respect to volatility.
    It is identical for Calls and Puts.
    """
    if T <= 0 or sigma <= 0 or F <= 0 or K <= 0:
        return 0.0
        
    d1 = (np.log(F / K) + (0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    n_prime_d1 = norm.pdf(d1)
    
    vega = np.exp(-r * T) * F * np.sqrt(T) * n_prime_d1
    return vega

def implied_volatility_newton_raphson(C_market, F, K, T, r, is_call=True, initial_guess=0.20, max_iter=100, tolerance=1e-4):
    """
    Calculates the Implied Volatility (IV) using the Newton-Raphson method.
    
    :param C_market: The actual market price of the option
    :param F: Current futures price
    :param K: Strike price
    :param T: Time to expiration in years
    :param r: Risk-free interest rate
    :param is_call: True for Call option, False for Put option
    :return: Estimated Implied Volatility (sigma)
    """
    # Se o preco de mercado for muito baixo (ex: zero liquidez), retorna o guess
    if C_market <= 0.01:
        return initial_guess
        
    sigma = initial_guess
    
    for i in range(max_iter):
        if is_call:
            price_calc = black76_call_price(F, K, T, sigma, r)
        else:
            price_calc = black76_put_price(F, K, T, sigma, r)
            
        diff = price_calc - C_market
        
        if abs(diff) < tolerance:
            return sigma
            
        vega = black76_vega(F, K, T, sigma, r)
        
        # Se Vega e quase zero, o Newton-Raphson pode explodir (divisao por zero)
        if vega < 1e-6:
            # Fallback for near-zero vega (deep ITM/OTM or zero time)
            break
            
        sigma = sigma - diff / vega
        
        # Volatilidade nao pode ser negativa e nem astronomica
        if sigma <= 0.001:
            sigma = 0.001
        elif sigma > 2.0:  # Max 200% IV for sanity
            sigma = 2.0
            
    # Retorna a melhor estimativa mesmo que nao convirja perfeitamente
    return sigma
