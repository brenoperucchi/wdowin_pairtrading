# Testing Strategy

This document outlines the testing methodologies used in the WIN×WDO Pair Trading system. Given the quantitative nature of the project, testing is divided into traditional software tests (unit tests) and quantitative trading tests (Walk-Forward Analysis).

## 1. Walk-Forward Analysis (WFA)

Because this is a trading system, standard Unit Tests are insufficient to prove profitability or prevent overfitting. We rely on **Walk-Forward Analysis**.

- The `research/wfa_runner.py` script splits historical M30 data into rolling windows (e.g., Train on 12 months, Test on 3 months).
- The models (GaussianHMM, LSTM, XGBoost) are trained independently on the rolling in-sample periods and evaluated on the out-of-sample periods.
- The output of the WFA is stored in `data/processed/wfa_results/` and compared using `research/compare_models.py`.

## 2. Unit Testing (Pytest)

The mathematical models and data transformations should be rigorously tested for lookahead bias and numerical stability using `pytest`.

To run the existing unit test suite:

```bash
pytest tests/
```

### Key Areas of Focus for Unit Tests:

1. **Causal Smoothing (Nadaraya-Watson)**: Ensure `nwe_causal()` only uses data from $t \le T$ and does not peek into future bars.
2. **Beta Stability**: Ensure `np.linalg.lstsq` returns expected Beta bounds under synthesized deterministic asset paths.
3. **Cointegration Integrity**: Test that the `statsmodels.tsa.stattools.coint` function properly flags synthetic stationary and non-stationary series.

## 3. UI and Integration Testing

The React dashboard (`App.jsx`) relies heavily on the `Simulated` mode for UI testing when the B3 market is closed.

- Run the Python server on weekends or after 18:30 BRT. The server will automatically output a simulated Gaussian random walk JSON payload.
- Verify that the `IndexChart` correctly renders the NWE bands dynamically as new data arrives.
- Verify the `SignalHistogram` correctly maps the color thresholds without crashing.

No End-to-End browser tests (like Cypress/Playwright) are currently required, as visual charting data validation is prioritized.
