import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from ta.volatility import AverageTrueRange
from ta.trend import ADXIndicator, WMAIndicator, SMAIndicator
import matplotlib.pyplot as plt
import datetime

WIN_CSV = r"base de dados\WIN$N_M1_202103100900_202603261831.csv"

def prepare_hmm_data():
    print("Carregando e Resampleando WIN para M30...")
    cols = ['date','time','open','high','low','close','tickvol','vol','spread']
    win = pd.read_csv(WIN_CSV, sep='\t', names=cols, skiprows=1)
    win['dt'] = pd.to_datetime(win['date']+' '+win['time'], format='%Y.%m.%d %H:%M:%S')
    win.set_index('dt', inplace=True)
    
    # Resample M30 (ignora outside hours se necessario, mas vamos pegar todos os dados para estacao base)
    agg = {'open':'first','high':'max','low':'min','close':'last'}
    df = win.resample('30min').agg(agg).dropna()
    print(f"Total barras M30: {len(df)}")
    
    # 5.1 Source (HLC3)
    df['hlc3'] = (df['high'] + df['low'] + df['close']) / 3
    
    # 5.2 Basis (Media das WMAs)
    wma_fast = WMAIndicator(close=df['hlc3'], window=20).wma()
    wma_slow = WMAIndicator(close=df['hlc3'], window=40).wma()
    df['basis'] = (wma_fast + wma_slow) / 2
    
    # 5.3 Banda de Volatilidade
    atr_20 = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=20).average_true_range()
    sm = WMAIndicator(close=SMAIndicator(close=atr_20, window=20).sma_indicator().fillna(0), window=20).wma()
    df['upper'] = df['basis'] + sm
    df['lower'] = df['basis'] - sm
    
    # 5.4 Trail Level
    trail_level = np.zeros(len(df))
    trend = 1 # 1 para ALTA, -1 para BAIXA
    tl = df['lower'].iloc[0] if not pd.isna(df['lower'].iloc[0]) else df['close'].iloc[0]
    
    closes = df['close'].values
    uppers = df['upper'].values
    lowers = df['lower'].values
    
    for i in range(1, len(df)):
        c = closes[i]
        u = uppers[i]
        l = lowers[i]
        
        # Ignora nans do inicio
        if np.isnan(u) or np.isnan(l):
            trail_level[i] = c
            tl = c
            continue
            
        if trend == 1:
            if c < tl: # Flip para BAIXA
                trend = -1
                tl = u
            else:
                tl = max(tl, l) # Trailing SL longo na alta
        else:
            if c > tl: # Flip para ALTA
                trend = 1
                tl = l
            else:
                tl = min(tl, u) # Trailing SL curto na baixa
                
        trail_level[i] = tl
        
    df['trail_level'] = trail_level
    df['atr14'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
    
    # ========================================================
    # OBSERVATIONS
    # ========================================================
    # 1. TPos (Distancia Normalizada)
    df['tpos_raw'] = (df['close'] - df['trail_level']) / (df['atr14'] + 1e-6)
    
    # 2. Log Returns
    df['log_ret'] = np.log(df['close'] / df['close'].shift(1)).fillna(0)
    
    # 3. Volatilidade Relativa
    df['norm_vol'] = df['atr14'] / df['close']
    
    # 4. ADX (Forca)
    df['adx'] = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14).adx()
    
    df.dropna(inplace=True)
    
    # Z-Score Scaling 50 periodos
    def rolling_zscore(s, w=50):
        mu = s.rolling(w).mean()
        sd = s.rolling(w).std() + 1e-6
        return (s - mu) / sd
        
    df['obs_tpos'] = rolling_zscore(df['tpos_raw'])
    df['obs_ret'] = rolling_zscore(df['log_ret'])
    df['obs_vol'] = rolling_zscore(df['norm_vol'])
    df['obs_adx'] = rolling_zscore(df['adx'])
    
    # Drop rows that still have Nans from rolling
    df.dropna(inplace=True)
    
    return df

def train_hmm(df):
    features = ['obs_tpos', 'obs_ret', 'obs_vol', 'obs_adx']
    X = df[features].values
    
    print(f"Treinando HMM com shape = {X.shape} ... aguarde.")
    
    # Dirichlet Prior (Persistencia)
    transmat_prior = np.ones((3, 3)) + np.eye(3) * 5.0
    
    model = GaussianHMM(
        n_components=3, 
        covariance_type="full", 
        n_iter=2000, 
        random_state=42, 
        transmat_prior=transmat_prior,
        tol=1e-4
    )
    
    model.fit(X)
    print(f"Convergência alcançada: {model.monitor_.converged}")
    
    # Predict clusters
    hidden_states = model.predict(X)
    df['raw_state'] = hidden_states
    
    # Labelling Semântico
    means = model.means_
    state_idx_bull = np.argmax(means[:, 0]) # Maior TPos
    state_idx_bear = np.argmin(means[:, 0]) # Menor TPos
    state_idx_chop = [i for i in range(3) if i not in [state_idx_bull, state_idx_bear]][0]
    
    # Map raw_state to semantic: 0=BULL, 1=BEAR, 2=CHOP
    state_map = {
        state_idx_bull: 0,
        state_idx_bear: 1,
        state_idx_chop: 2
    }
    
    df['regime_id'] = df['raw_state'].map(state_map)
    df['regime_name'] = df['regime_id'].map({0: 'BULL', 1: 'BEAR', 2: 'CHOP'})
    
    print("\nDistribuição de Regimes:")
    print(df['regime_name'].value_counts(normalize=True) * 100)
    
    print(f"\nMédias por Estado (BULL=0, BEAR=1, CHOP=2):")
    print(f"{features}")
    print(f"BULL: {means[state_idx_bull]}")
    print(f"BEAR: {means[state_idx_bear]}")
    print(f"CHOP: {means[state_idx_chop]}")
    
    # Export for timeline filtering
    df[['close', 'obs_tpos', 'regime_id', 'regime_name']].to_csv("win_m30_regimes.csv")
    print("Vetor de Viterbi salvo em win_m30_regimes.csv")
    return df

if __name__ == '__main__':
    st = datetime.datetime.now()
    df = prepare_hmm_data()
    train_hmm(df)
    print(f"\nTempo Total HMM: {(datetime.datetime.now() - st).total_seconds():.1f}s")
