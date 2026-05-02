import numpy as np
import pytest
from core.kalman_filter import KalmanBetaFilter

def test_kalman_filter_updates_beta():
    kf = KalmanBetaFilter(initial_beta=-20.0)
    # Simulate some price movements
    prices_wdo = np.array([5000, 5010, 5020, 5015])
    prices_win = np.array([100000, 100200, 100400, 100250])
    
    # Update filter iteratively
    beta, spread, var = 0, 0, 0
    for y, x in zip(prices_win, prices_wdo):
        beta, spread, var = kf.update(y, x)
    
    assert beta is not None
    assert beta != -20.0  # Beta should have drifted
    assert var > 0

if __name__ == "__main__":
    test_kalman_filter_updates_beta()
    print("Test passed!")
