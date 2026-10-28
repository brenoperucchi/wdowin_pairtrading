# research/tune_single.py
"""
WIN×WDO — Grid Search por Modelo (Otimização de Memória)
===================================================================
A computação do backtest agora é feita DENTRO do worker para
evitar envio de DataFrames pesados entre processos IPC, zerando 
as falhas de memória (ArrayMemoryError) com 30 núcleos.
"""
import os, sys, time, itertools, warnings, argparse, csv
import numpy as np
import pandas as pd
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DATA_PROC = PROJECT_ROOT / "data" / "processed"
REPORT_DIR = PROJECT_ROOT / "data" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

Z_THRESHOLD = 1.8
TARGET_THR = 100
TRAIN_RATIO = 0.70

HMM_GRID = {
    "ret_threshold": [0.0001, 0.0005, 0.001, 0.002, 0.0025, 0.003, 0.0035, 0.004, 0.0045, 0.005],
    "covariance_type": ["full", "diag", "tied"],
    "n_iter": [50, 100, 150, 200, 250, 300, 350, 400, 450, 500],
}

LSTM_GRID = {
    "seq_len": [5, 10, 15, 20, 25, 30, 35, 40, 45, 50],
    "hidden_dim": [32, 64, 96, 128, 160, 192, 224, 256, 288, 320],
    "dropout": [0.1, 0.3, 0.5, 0.7, 0.9],
}

XGB_GRID = {
    "max_depth": [3, 5, 7, 9, 11, 13, 15, 17, 19, 21],
    "n_estimators": [100, 150, 200, 250, 300, 350, 400, 450, 500, 550],
    "learning_rate": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50],
}


# Variável global para cada worker instanciado não precisar recarregar o M5 em cada job
global_m5 = None

def init_worker():
    global global_m5
    from research.backtest_ml_zscore import load_m5_dataset
    global_m5 = load_m5_dataset()

# ─── WORKERS ───────────────────────────────────────────────────────────
def run_hmm(args):
    ret_thr, cov_type, n_iter, parquet_path, idx, total = args
    import warnings; warnings.filterwarnings("ignore")
    try:
        from research.models.features import compute_features, make_target, HMM_FEATURES
        from research.backtest_ml_zscore import simulate_trades, compute_metrics
        from hmmlearn.hmm import GaussianHMM

        df = pd.read_parquet(parquet_path)
        df = compute_features(df)
        split_idx = int(len(df) * TRAIN_RATIO)
        df_train = df.iloc[:split_idx].copy()
        df_test = df.iloc[split_idx:].copy()

        X_train = np.nan_to_num(df_train[HMM_FEATURES].values, nan=0.0)
        X_test = np.nan_to_num(df_test[HMM_FEATURES].values, nan=0.0)

        mean = X_train.mean(axis=0)
        std = X_train.std(axis=0) + 1e-8
        X_train_n = (X_train - mean) / std
        X_test_n = (X_test - mean) / std

        n_components = 3
        model = GaussianHMM(n_components=n_components, covariance_type=cov_type,
                            n_iter=n_iter, random_state=42,
                            transmat_prior=np.ones((n_components, n_components)) + np.eye(n_components)*5.0)
        model.fit(X_train_n)

        means = model.means_
        state_scores = means[:, 0]
        idx_bull = np.argmax(state_scores)
        idx_bear = np.argmin(state_scores)
        idx_chop = [i for i in range(n_components) if i not in [idx_bull, idx_bear]][0]
        state_map = {idx_bull: "SELL", idx_bear: "BUY", idx_chop: "FLAT"}

        hidden_test = model.predict(X_test_n)
        preds = np.array([state_map[s] for s in hidden_test])

        for s_idx in range(n_components):
            if abs(means[s_idx, 0]) < ret_thr:
                preds[hidden_test == s_idx] = "FLAT"

        y_test = make_target(df_test["fwd_ret_pts"], threshold_pts=TARGET_THR)
        valid = df_test["fwd_ret_pts"].notna().values
        acc = (preds[valid] == y_test.values[valid]).mean() * 100 if valid.sum() > 0 else 0

        predictions = pd.DataFrame({
            "dt": df_test["dt"].values, "direction": preds, "close": df_test["close"].values,
            "fwd_ret_pts": df_test["fwd_ret_pts"].values, "zscore_ols": df_test["zscore_ols"].values,
        })
        
        # Faz backtest NA SOURCE DO WORKER
        trades = simulate_trades(predictions, global_m5, Z_THRESHOLD, use_ml=True)
        metrics = compute_metrics(trades)
        dd = abs(metrics["max_drawdown"]) if metrics["max_drawdown"] != 0 else 1.0
        calmar = round(metrics["total_pnl"] / dd, 2)
        flat_pct = round(predictions["direction"].value_counts().get("FLAT", 0) / len(predictions) * 100, 1)

        print(f"[{idx}/{total}] HMM -> acc={acc:.1f}% Calmar={calmar}", flush=True)

        return {
            "model": "HMM", "param1_name": "ret_threshold", "param1_value": ret_thr,
            "param2_name": "covariance_type", "param2_value": cov_type,
            "param3_name": "n_iter", "param3_value": n_iter,
            "oos_accuracy": round(acc, 1), "flat_pct": flat_pct,
            "total_trades": metrics["total_trades"], "total_pnl": metrics["total_pnl"],
            "max_drawdown": metrics["max_drawdown"], "calmar_ratio": calmar,
            "profit_factor": metrics["profit_factor"],
        }
    except Exception as e:
        return None

def run_lstm(args):
    seq_len, hidden_dim, dropout, parquet_path, idx, total = args
    import warnings; warnings.filterwarnings("ignore")
    import torch
    torch.set_num_threads(1)
    try:
        from research.models.features import compute_features, make_target, ALL_FEATURES
        from research.models.lstm_direction import CLASS_INV, CLASS_MAP
        from research.backtest_ml_zscore import simulate_trades, compute_metrics
        
        df = pd.read_parquet(parquet_path)
        df = compute_features(df)
        split_idx = int(len(df) * TRAIN_RATIO)
        df_train = df.iloc[:split_idx].copy()
        df_test = df.iloc[split_idx:].copy()

        X_train = np.nan_to_num(df_train[ALL_FEATURES].values, nan=0.0)
        X_test = np.nan_to_num(df_test[ALL_FEATURES].values, nan=0.0)
        y_train = make_target(df_train["fwd_ret_pts"], threshold_pts=TARGET_THR).values
        valid_train = df_train["fwd_ret_pts"].notna().values
        X_train = X_train[valid_train]
        y_train = y_train[valid_train]

        class _LSTMNetCustom(torch.nn.Module):
            def __init__(self, input_dim, hidden_dim, dropout_rate, n_classes=3):
                super().__init__()
                self.lstm = torch.nn.LSTM(input_dim, hidden_dim, batch_first=True, num_layers=1)
                self.dropout = torch.nn.Dropout(dropout_rate)
                self.fc1 = torch.nn.Linear(hidden_dim, 32)
                self.relu = torch.nn.ReLU()
                self.fc2 = torch.nn.Linear(32, n_classes)
            def forward(self, x):
                _, (h_n, _) = self.lstm(x)
                out = self.dropout(h_n.squeeze(0))
                out = self.relu(self.fc1(out))
                return self.fc2(out)

        mean = X_train.mean(axis=0)
        std = X_train.std(axis=0) + 1e-8
        X_train_n = (X_train - mean) / std
        X_test_n = (X_test - mean) / std

        y_enc = np.array([CLASS_INV[v] for v in y_train])
        seqs, labels = [], []
        for i in range(seq_len, len(X_train_n)):
            seqs.append(X_train_n[i - seq_len:i])
            labels.append(y_enc[i])
        X_seq = np.array(seqs, dtype=np.float32)
        y_seq = np.array(labels, dtype=np.int64)

        counts = np.bincount(y_seq, minlength=3)
        weights = len(y_seq) / (3.0 * counts + 1e-8)
        class_weights = torch.FloatTensor(weights)

        dataset = torch.utils.data.TensorDataset(torch.FloatTensor(X_seq), torch.LongTensor(y_seq))
        loader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=True)

        val_size = max(1, len(X_seq) // 5)
        X_val = torch.FloatTensor(X_seq[-val_size:])
        y_val = torch.LongTensor(y_seq[-val_size:])

        net = _LSTMNetCustom(X_train.shape[1], hidden_dim, dropout)
        optimizer = torch.optim.Adam(net.parameters(), lr=1e-3)
        criterion = torch.nn.CrossEntropyLoss(weight=class_weights)

        best_val_loss = float("inf")
        patience_counter = 0
        best_state = None

        for epoch in range(50):
            net.train()
            for xb, yb in loader:
                optimizer.zero_grad()
                loss = criterion(net(xb), yb)
                loss.backward()
                optimizer.step()
            net.eval()
            with torch.no_grad():
                val_loss = criterion(net(X_val), y_val).item()
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_state = {k: v.clone() for k, v in net.state_dict().items()}
                patience_counter = 0
            else:
                patience_counter += 1
            if patience_counter >= 10:
                break

        if best_state:
            net.load_state_dict(best_state)

        net.eval()
        seqs_test = [X_test_n[i - seq_len:i] for i in range(seq_len, len(X_test_n))]
        X_test_seq = np.array(seqs_test, dtype=np.float32)

        with torch.no_grad():
            preds_enc = []
            for bi in range(0, len(X_test_seq), 64):
                batch = torch.FloatTensor(X_test_seq[bi:bi+64])
                preds_enc.append(net(batch).argmax(dim=1).numpy())
            pred_classes = np.concatenate(preds_enc) if preds_enc else []

        pad = np.full(seq_len, CLASS_INV["FLAT"])
        full_preds = np.concatenate([pad, pred_classes])[:len(df_test)]
        preds = np.array([CLASS_MAP[c] for c in full_preds])

        y_test = make_target(df_test["fwd_ret_pts"], threshold_pts=TARGET_THR)
        valid = df_test["fwd_ret_pts"].notna().values
        acc = (preds[valid] == y_test.values[valid]).mean() * 100 if valid.sum() > 0 else 0

        predictions = pd.DataFrame({
            "dt": df_test["dt"].values[:len(preds)], "direction": preds, "close": df_test["close"].values[:len(preds)],
            "fwd_ret_pts": df_test["fwd_ret_pts"].values[:len(preds)], "zscore_ols": df_test["zscore_ols"].values[:len(preds)],
        })
        
        trades = simulate_trades(predictions, global_m5, Z_THRESHOLD, use_ml=True)
        metrics = compute_metrics(trades)
        dd = abs(metrics["max_drawdown"]) if metrics["max_drawdown"] != 0 else 1.0
        calmar = round(metrics["total_pnl"] / dd, 2)
        flat_pct = round(predictions["direction"].value_counts().get("FLAT", 0) / len(predictions) * 100, 1)

        print(f"[{idx}/{total}] LSTM -> acc={acc:.1f}% Calmar={calmar}", flush=True)

        return {
            "model": "LSTM", "param1_name": "seq_len", "param1_value": seq_len,
            "param2_name": "hidden_dim", "param2_value": hidden_dim,
            "param3_name": "dropout", "param3_value": dropout,
            "oos_accuracy": round(acc, 1), "flat_pct": flat_pct,
            "total_trades": metrics["total_trades"], "total_pnl": metrics["total_pnl"],
            "max_drawdown": metrics["max_drawdown"], "calmar_ratio": calmar,
            "profit_factor": metrics["profit_factor"],
        }
    except Exception as e:
        return None

def run_xgb(args):
    max_depth, n_estimators, lr, parquet_path, idx, total = args
    import warnings; warnings.filterwarnings("ignore")
    try:
        from research.models.features import compute_features, make_target, ALL_FEATURES
        from research.backtest_ml_zscore import simulate_trades, compute_metrics
        from xgboost import XGBClassifier

        df = pd.read_parquet(parquet_path)
        df = compute_features(df)
        split_idx = int(len(df) * TRAIN_RATIO)
        df_train = df.iloc[:split_idx].copy()
        df_test = df.iloc[split_idx:].copy()

        X_train = np.nan_to_num(df_train[ALL_FEATURES].values, nan=0.0)
        X_test = np.nan_to_num(df_test[ALL_FEATURES].values, nan=0.0)
        y_train_raw = make_target(df_train["fwd_ret_pts"], threshold_pts=TARGET_THR).values
        valid_train = df_train["fwd_ret_pts"].notna().values
        X_train = X_train[valid_train]
        y_train_raw = y_train_raw[valid_train]

        CLASS_INV = {"BUY": 0, "FLAT": 1, "SELL": 2}
        CLASS_MAP = {0: "BUY", 1: "FLAT", 2: "SELL"}
        y_enc = np.array([CLASS_INV[v] for v in y_train_raw])

        counts = np.bincount(y_enc, minlength=3)
        sample_weights = np.array([len(y_enc) / (3.0 * counts[c] + 1e-8) for c in y_enc])

        model = XGBClassifier(max_depth=max_depth, n_estimators=n_estimators, learning_rate=lr,
                              objective="multi:softmax", num_class=3, random_state=42,
                              use_label_encoder=False, eval_metric="mlogloss", verbosity=0, n_jobs=1)
        model.fit(X_train, y_enc, sample_weight=sample_weights)

        pred_classes = model.predict(X_test)
        preds = np.array([CLASS_MAP[int(c)] for c in pred_classes])

        y_test = make_target(df_test["fwd_ret_pts"], threshold_pts=TARGET_THR)
        valid = df_test["fwd_ret_pts"].notna().values
        acc = (preds[valid] == y_test.values[valid]).mean() * 100 if valid.sum() > 0 else 0

        predictions = pd.DataFrame({
            "dt": df_test["dt"].values[:len(preds)], "direction": preds, "close": df_test["close"].values[:len(preds)],
            "fwd_ret_pts": df_test["fwd_ret_pts"].values[:len(preds)], "zscore_ols": df_test["zscore_ols"].values[:len(preds)],
        })
        
        trades = simulate_trades(predictions, global_m5, Z_THRESHOLD, use_ml=True)
        metrics = compute_metrics(trades)
        dd = abs(metrics["max_drawdown"]) if metrics["max_drawdown"] != 0 else 1.0
        calmar = round(metrics["total_pnl"] / dd, 2)
        flat_pct = round(predictions["direction"].value_counts().get("FLAT", 0) / len(predictions) * 100, 1)

        print(f"[{idx}/{total}] XGB -> acc={acc:.1f}% Calmar={calmar}", flush=True)

        return {
            "model": "XGBoost", "param1_name": "max_depth", "param1_value": max_depth,
            "param2_name": "n_estimators", "param2_value": n_estimators,
            "param3_name": "learning_rate", "param3_value": lr,
            "oos_accuracy": round(acc, 1), "flat_pct": flat_pct,
            "total_trades": metrics["total_trades"], "total_pnl": metrics["total_pnl"],
            "max_drawdown": metrics["max_drawdown"], "calmar_ratio": calmar,
            "profit_factor": metrics["profit_factor"],
        }
    except Exception as e:
        return None

# ─── MAIN ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True, choices=["HMM", "LSTM", "XGB"])
    parser.add_argument("--workers", type=int, default=30)
    args = parser.parse_args()

    parquet_path = str(DATA_PROC / "dataset_m30.parquet")

    # The CSV that merges all tests seamlessly, as requested by Plot grid scripts
    out_csv = REPORT_DIR / "grid_search_all_models.csv"
    
    if not out_csv.exists():
        with open(out_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["model", "param1_name", "param1_value", "param2_name", "param2_value", 
                        "param3_name", "param3_value", "oos_accuracy", "flat_pct", 
                        "total_trades", "total_pnl", "max_drawdown", "calmar_ratio", "profit_factor"])

    def _norm(v):
        """Normalize value for checkpoint key: 5.0 -> '5', 0.1 -> '0.1', 'full' -> 'full'"""
        try:
            f = float(v)
            return str(int(f)) if f == int(f) else str(f)
        except (ValueError, TypeError):
            return str(v)

    completed_configs = set()
    if out_csv.exists():
        try:
            df_done = pd.read_csv(out_csv)
            for _, row in df_done.iterrows():
                key = f"{row['model']}_{_norm(row['param1_value'])}_{_norm(row['param2_value'])}_{_norm(row['param3_value'])}"
                completed_configs.add(key)
        except Exception as e:
            print(f"Warning: could not read {out_csv} for checkpointing ({e})")

    if args.model == "HMM":
        jobs = []
        n_hmm = len(HMM_GRID["ret_threshold"]) * len(HMM_GRID["covariance_type"]) * len(HMM_GRID["n_iter"])
        for i, (ret_thr, cov, n_iter) in enumerate(itertools.product(HMM_GRID["ret_threshold"], HMM_GRID["covariance_type"], HMM_GRID["n_iter"]), 1):
            if f"HMM_{_norm(ret_thr)}_{_norm(cov)}_{_norm(n_iter)}" not in completed_configs:
                jobs.append((ret_thr, cov, n_iter, parquet_path, i, n_hmm))
        worker_fn = run_hmm
    elif args.model == "LSTM":
        jobs = []
        n_lstm = len(LSTM_GRID["seq_len"]) * len(LSTM_GRID["hidden_dim"]) * len(LSTM_GRID["dropout"])
        for i, (seq, hid, drop) in enumerate(itertools.product(LSTM_GRID["seq_len"], LSTM_GRID["hidden_dim"], LSTM_GRID["dropout"]), 1):
            if f"LSTM_{_norm(seq)}_{_norm(hid)}_{_norm(drop)}" not in completed_configs:
                jobs.append((seq, hid, drop, parquet_path, i, n_lstm))
        worker_fn = run_lstm
    else:
        jobs = []
        n_xgb = len(XGB_GRID["max_depth"]) * len(XGB_GRID["n_estimators"]) * len(XGB_GRID["learning_rate"])
        for i, (depth, trees, lr) in enumerate(itertools.product(XGB_GRID["max_depth"], XGB_GRID["n_estimators"], XGB_GRID["learning_rate"]), 1):
            if f"XGBoost_{_norm(depth)}_{_norm(trees)}_{_norm(lr)}" not in completed_configs:
                jobs.append((depth, trees, lr, parquet_path, i, n_xgb))
        worker_fn = run_xgb

    print(f"Starting {args.model} grid search with {len(jobs)} configs (skipped some via checkpoint) and {args.workers} workers...")
    
    completed = 0
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker) as ex:
        futures = {ex.submit(worker_fn, j): j for j in jobs}
        for f in as_completed(futures):
            r = f.result()
            completed += 1
            if r is not None:
                with open(out_csv, "a", newline="") as fp:
                    w = csv.writer(fp)
                    w.writerow([
                        r["model"], r["param1_name"], r["param1_value"], 
                        r["param2_name"], r["param2_value"], r["param3_name"], r["param3_value"],
                        r["oos_accuracy"], r["flat_pct"],
                        r["total_trades"], r["total_pnl"], 
                        r["max_drawdown"], r["calmar_ratio"], r["profit_factor"]
                    ])

    print(f"\n{args.model} tuning completed! Saved incrementally to {out_csv}")

if __name__ == "__main__":
    main()
