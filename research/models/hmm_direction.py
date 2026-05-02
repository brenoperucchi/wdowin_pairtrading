# research/models/hmm_direction.py
"""
WIN×WDO ML Direction — HMM Directional Model
===============================================
3-state Gaussian HMM that classifies market regime and infers
direction from the mean log-return of each state.

Evolution of the original HMM filter (which only blocked BULL).
Now maps each regime to BUY/SELL/FLAT based on observed returns.
"""
import numpy as np
from hmmlearn.hmm import GaussianHMM
from research.models.features import HMM_FEATURES, _rolling_zscore


class HMMDirection:
    """
    HMM-based directional model.

    Trains an unsupervised 3-state HMM, then maps states to directions
    based on the mean log_return in each state.
    """

    def __init__(self, n_components: int = 3, ret_threshold: float = 0.0005):
        """
        Args:
            n_components: Number of hidden states
            ret_threshold: Minimum |mean(log_ret)| to classify as BUY/SELL
                          States with |mean| < threshold → FLAT
        """
        self.n_components = n_components
        self.ret_threshold = ret_threshold
        self.model = None
        self.state_map = {}

    def fit(self, X_train: np.ndarray, y_train: np.ndarray = None) -> "HMMDirection":
        """
        Fit the HMM on training features.

        Args:
            X_train: Feature matrix (n_samples, n_features).
                     Features should include log_ret as first column for mapping.
            y_train: Ignored (unsupervised), accepted for interface compatibility.
        """
        # Normalize features for HMM
        self._mean = X_train.mean(axis=0)
        self._std = X_train.std(axis=0) + 1e-8
        X_norm = (X_train - self._mean) / self._std

        transmat_prior = np.ones((self.n_components, self.n_components)) + \
                         np.eye(self.n_components) * 5.0

        self.model = GaussianHMM(
            n_components=self.n_components,
            covariance_type="full",
            n_iter=200,
            random_state=42,
            transmat_prior=transmat_prior,
        )
        self.model.fit(X_norm)

        # Map states to directions based on mean of first feature (log_ret proxy)
        hidden = self.model.predict(X_norm)
        means = self.model.means_

        # Use trend_pos (first feature in HMM_FEATURES) as direction indicator
        state_scores = means[:, 0]  # trend_pos mean per state

        idx_bull = np.argmax(state_scores)
        idx_bear = np.argmin(state_scores)
        idx_chop = [i for i in range(self.n_components) if i not in [idx_bull, idx_bear]][0]

        self.state_map = {
            idx_bull: "SELL",   # BULL regime → sell signal (mean reversion context)
            idx_bear: "BUY",   # BEAR regime → buy signal
            idx_chop: "FLAT",  # Choppy → no direction
        }

        # Print regime stats
        for state_idx, label in self.state_map.items():
            mask = hidden == state_idx
            pct = mask.sum() / len(hidden) * 100
            mean_tpos = means[state_idx, 0]
            print(f"  State {state_idx} ({label}): {pct:.1f}% of bars, mean_tpos={mean_tpos:.3f}")

        return self

    def predict(self, X_test: np.ndarray) -> np.ndarray:
        """
        Predict direction for each bar.

        Args:
            X_test: Feature matrix (n_samples, n_features)

        Returns:
            Array of 'BUY', 'SELL', 'FLAT' strings
        """
        X_norm = (X_test - self._mean) / self._std
        hidden = self.model.predict(X_norm)
        return np.array([self.state_map[s] for s in hidden])

    def predict_proba(self, X_test: np.ndarray) -> np.ndarray:
        """
        State probabilities for confidence scoring.

        Returns:
            Array of shape (n_samples, n_components) with posterior probabilities
        """
        X_norm = (X_test - self._mean) / self._std
        return self.model.predict_proba(X_norm)
