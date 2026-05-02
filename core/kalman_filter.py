import numpy as np

class KalmanBetaFilter:
    def __init__(self, initial_beta: float = 0.0, trans_cov: float = 5e-5, obs_cov: float = 1e2):
        """
        Filtro de Kalman para estimação online do hedge-ratio (beta).
        
        Parâmetros calibrados para escala WIN (~130k-190k) vs WDO (~5k-6k):
          - trans_cov: ruído de transição do estado (quanto o beta pode mudar barra-a-barra)
          - obs_cov:   variância esperada do spread residual (~centenas de pontos)
        """
        # State: [alpha, beta]
        self.state_mean = np.array([[0.0], [initial_beta]])
        self.state_cov = np.eye(2) * 1.0
        self.trans_cov = np.eye(2) * trans_cov
        self.obs_cov = obs_cov
        
    def update(self, y: float, x: float):
        """
        y = WIN (Close A)
        x = WDO (Close B)
        Retorna: (beta_atual, spread_residual, variancia_residual)
        """
        # Observation matrix H = [1, x]
        H = np.array([[1.0, x]])
        
        # Prediction (Random Walk)
        pred_state_mean = self.state_mean
        pred_state_cov = self.state_cov + self.trans_cov
        
        # Prediction of observation
        y_pred = H.dot(pred_state_mean)[0, 0]
        
        # Error (Residual / Spread)
        error = y - y_pred
        
        # Variance of the error
        S = H.dot(pred_state_cov).dot(H.T) + self.obs_cov
        S_val = S[0, 0]
        
        # Kalman Gain
        K = pred_state_cov.dot(H.T) / S_val
        
        # State Update
        self.state_mean = pred_state_mean + K * error
        self.state_cov = pred_state_cov - K.dot(H).dot(pred_state_cov)
        
        beta = float(self.state_mean[1, 0])
        return beta, float(error), float(S_val)

    @staticmethod
    def rolling_zscore(spreads: list, window: int = 40) -> list:
        """
        Calcula Z-score rolling (média/desvio de janela) sobre os spreads residuais.
        Isso é essencial: o spread bruto do Kalman NÃO é um Z-score normalizado.
        """
        arr = np.array(spreads)
        z_scores = []
        for i in range(len(arr)):
            if i < window:
                z_scores.append(0.0)
            else:
                w = arr[i - window:i]
                mu = w.mean()
                sd = w.std()
                z_scores.append(float((arr[i] - mu) / (sd + 1e-6)))
        return z_scores
