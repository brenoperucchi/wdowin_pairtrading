# core/signals.py
"""
Signal generation and health classification for WIN×WDO regime monitoring.

Extracted from server.py — contains all pure computation functions
that don't depend on MT5 or network I/O.
"""
import numpy as np
from core.config import WINDOW, BARS, Z_ENTRY, Z_ATTENTION


def calc_beta_ols(closes_a: np.ndarray, closes_b: np.ndarray, window: int | None = None) -> float:
    """
    Calcula o hedge ratio β via OLS (mínimos quadrados).
    closes_a = α + β · closes_b
    Usa numpy.linalg.lstsq — sem dependências extras.
    """
    y = closes_a[-window:] if window else closes_a
    x = closes_b[-window:] if window else closes_b
    X = np.column_stack([np.ones(len(x)), x])
    coefs, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(coefs[1])  # β


def calc_half_life(spread: np.ndarray) -> float:
    """
    Calcula o half-life (meia-vida) de reversão à média via regressão AR(1).
    spread_curr = c + lambda * spread_lag
    """
    if len(spread) < 3:
        return 0.0
    lag = spread[:-1]
    curr = spread[1:]
    X = np.column_stack([np.ones(len(lag)), lag])
    coefs, *_ = np.linalg.lstsq(X, curr, rcond=None)
    lamb = coefs[1]
    if lamb >= 1.0 or lamb <= 0.0:
        return float("inf")  # Random walk ou divergente
    hl = -np.log(2) / np.log(lamb)
    return float(hl)


def calc_zscore(
    closes_a: np.ndarray, closes_b: np.ndarray, beta: float,
    window: int | None = None, max_bars: int | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Calcula o spread e o z-score rolling.
    Retorna (spread, z_scores, correlation).
    
    window:   janela do z-score rolling (default: WINDOW global)
    max_bars: trunca resultado nos últimos N bars (default: BARS global, None=sem truncar)
    """
    w = window if window is not None else WINDOW
    tail = max_bars if max_bars is not None else BARS

    spread = closes_a - beta * closes_b

    n = len(spread)
    z = np.zeros(n)
    for i in range(w, n):
        win = spread[i - w:i]
        mu = win.mean()
        sd = win.std() or 1e-6
        z[i] = (spread[i] - mu) / sd

    # Correlação rolling de Pearson (janela = w)
    rho_arr = np.zeros(n)
    for i in range(w, n):
        wa = closes_a[i - w:i]
        wb = closes_b[i - w:i]
        if wa.std() > 0 and wb.std() > 0:
            rho_arr[i] = np.corrcoef(wa, wb)[0, 1]

    return spread[-tail:], z[-tail:], rho_arr[-tail:]


def get_signal(z: float, spread_sd: float = 1.0, beta: float = 1.0, **kwargs) -> dict:
    """
    Traduz o z-score transversal em ação de trading e size dinâmico.
    O target_risk é de ~R$ 1.500 projetando um retorno à média de 'Z' pontos de spread.
    """
    target_risk = 1500.0
    pts = spread_sd * abs(z) if (spread_sd * abs(z)) != 0 else 1.0
    w_wdo = 10.0
    w_win = 0.20 * abs(beta)
    peso_total = w_wdo + w_win
    qty_base = max(1, int(target_risk / (pts * peso_total)))

    qty_wdo = qty_base
    qty_win = int(qty_base * abs(beta))

    az = abs(z)
    
    if az >= 4.0:
        return {"id": "anomalia", "label": "ANOMALIA", "sub": "Não operar — breakdown", "wdo": None, "win": None, "qty_wdo": 0, "qty_win": 0, "color": "#ff3860"}
    
    if z >= Z_ENTRY:
        return {"id": "compraWdo", "label": "VENDE WIN", "sub": "Z-Score positivo — spread revertendo", "wdo": "IGNORAR", "win": "VENDER", "qty_wdo": 0, "qty_win": qty_win, "color": "#ff3860"}
        
    if z <= -Z_ENTRY:
        return {"id": "compraWin", "label": "COMPRA WIN", "sub": "Z-Score negativo — spread revertendo", "wdo": "IGNORAR", "win": "COMPRAR", "qty_wdo": 0, "qty_win": qty_win, "color": "#00e87a"}
        
    if az >= Z_ATTENTION:
        return {"id": "atencao", "label": "ZONA DE DIVERGÊNCIA", "sub": f"Aguardando Z atingir ±{Z_ENTRY}", "wdo": None, "win": None, "qty_wdo": 0, "qty_win": 0, "color": "#f5a623"}
        
    return {"id": "neutro", "label": "AGUARDAR", "sub": "Spread em equilíbrio central", "wdo": None, "win": None, "qty_wdo": 0, "qty_win": 0, "color": "#445560"}


def get_rho_status(rho: float) -> dict:
    """
    Classifica a correlação ρ conforme tabela de risco.
    ρ é o sinal mais precoce de instabilidade na relação WIN×WDO.
    """
    if rho <= -0.70:
        return {"label": "FORTE",      "action": "Operar normalmente",               "color": "#00e87a", "level": 0}
    if rho <= -0.55:
        return {"label": "ATENÇÃO",    "action": "Sizing menor, monitorar",           "color": "#f5a623", "level": 1}
    if rho <= -0.40:
        return {"label": "FRACA",      "action": "Não abrir novas posições",          "color": "#ff6b35", "level": 2}
    return     {"label": "QUEBRADA",   "action": "Parar completamente",              "color": "#ff3860", "level": 3}


def get_beta_status(delta_pct: float) -> dict:
    """
    Classifica a variação percentual do beta vs referência 20d.
    """
    ap = abs(delta_pct)
    if ap < 5:
        return {"label": "ESTÁVEL",     "action": "Operar normalmente",               "color": "#00e87a", "level": 0}
    if ap < 15:
        return {"label": "DERIVANDO",   "action": "Reduzir tamanho, monitorar",       "color": "#f5a623", "level": 1}
    if ap < 25:
        return {"label": "INSTÁVEL",    "action": "Suspender novas entradas",         "color": "#ff6b35", "level": 2}
    return     {"label": "BREAKDOWN",   "action": "Não operar, aguardar estabilizar", "color": "#ff3860", "level": 3}


def calc_nwe_with_bands(prices: np.ndarray, bandwidth: int = 8,
                        lookback: int = 20, mult_mae: float = 3.0):
    """
    Nadaraya-Watson Envelope with upper/lower bands.
    Returns (nwe_line, upper_band, lower_band, is_up).
    
    Parameters validated OOS (2022-2026):
        bandwidth=8, lookback=20, mult_mae=3.0
    """
    n = len(prices)
    nwe = np.zeros(n)
    mae = np.zeros(n)

    for t in range(n):
        lb = min(t, lookback)
        if lb == 0:
            nwe[t] = prices[t]
            continue
        i_arr = np.arange(lb + 1)
        w = np.exp(-(i_arr * i_arr) / (2 * bandwidth * bandwidth))
        p_slice = prices[t - lb : t + 1][::-1]
        nwe[t] = np.sum(p_slice * w) / np.sum(w)

    for t in range(n):
        lb = min(t, lookback)
        if lb == 0:
            continue
        err = np.abs(prices[t - lb : t + 1] - nwe[t - lb : t + 1])
        mae[t] = np.mean(err) * mult_mae

    upper = nwe + mae
    lower = nwe - mae

    # Direction: NWE slope (current vs previous bar)
    is_up = np.zeros(n, dtype=bool)
    is_up[0] = True
    is_up[1:] = nwe[1:] >= nwe[:-1]

    return nwe, upper, lower, is_up

