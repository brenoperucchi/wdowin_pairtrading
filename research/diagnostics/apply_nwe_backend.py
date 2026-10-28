import re

with open('server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Modify _build_history
old_build_history = """def _build_history(bar_times, z_arr, spread_arr, z_v1_arr=None, win_prices=None):
    \"\"\"Build filtered session history from bar data.\"\"\"
    n = len(z_arr)
    v1_len = len(z_v1_arr) if z_v1_arr is not None else 0
    win_len = len(win_prices) if win_prices is not None else 0

    bar_info = []
    for i in range(n):
        local_ts = int(bar_times[i]) + TIME_OFFSET
        dt = datetime.fromtimestamp(local_ts)
        t_min = dt.hour * 60 + dt.minute
        entry = {
            "z": round(float(z_arr[i]), 3),
            "spread": round(float(spread_arr[i]), 2),
            "bar_time": dt.strftime("%H:%M"),
            "date": dt.strftime("%Y-%m-%d"),
            "t_min": t_min,
        }
        if z_v1_arr is not None:
            v1_idx = i - (n - v1_len)
            entry["z_v1"] = round(float(z_v1_arr[v1_idx]), 3) if 0 <= v1_idx < v1_len else 0.0
        if win_prices is not None:
            win_idx = i - (n - win_len)
            entry["win_price"] = float(win_prices[win_idx]) if 0 <= win_idx < win_len else 0.0
        bar_info.append(entry)

    today = datetime.now().date()
    today_str = today.strftime("%Y-%m-%d")
    target_day = today_str

    history = []
    if target_day:
        for b in bar_info:
            if b["date"] == target_day and SESSION_START <= b["t_min"] <= SESSION_END:
                entry = {"i": len(history), "z": b["z"], "spread": b["spread"], "bar_time": b["bar_time"], "date": b["date"], "t_min": b["t_min"]}
                if "z_v1" in b:
                    entry["z_v1"] = b["z_v1"]
                if "win_price" in b:
                    entry["win_price"] = b["win_price"]
                history.append(entry)


    return history"""

new_build_history = """def _build_history(bar_times, z_arr, spread_arr, z_v1_arr=None, win_prices=None, nwe_data=None, di_map=None):
    \"\"\"Build filtered session history from bar data, including NWE and DI.\"\"\"
    n = len(z_arr)
    v1_len = len(z_v1_arr) if z_v1_arr is not None else 0
    win_len = len(win_prices) if win_prices is not None else 0
    
    nwe_line, nwe_upper, nwe_lower, nwe_is_up = nwe_data if nwe_data else (None, None, None, None)
    nwe_len = len(nwe_line) if nwe_line is not None else 0

    bar_info = []
    for i in range(n):
        local_ts = int(bar_times[i]) + TIME_OFFSET
        dt = datetime.fromtimestamp(local_ts)
        t_min = dt.hour * 60 + dt.minute
        entry = {
            "z": round(float(z_arr[i]), 3),
            "spread": round(float(spread_arr[i]), 2),
            "bar_time": dt.strftime("%H:%M"),
            "date": dt.strftime("%Y-%m-%d"),
            "t_min": t_min,
        }
        if z_v1_arr is not None:
            v1_idx = i - (n - v1_len)
            entry["z_v1"] = round(float(z_v1_arr[v1_idx]), 3) if 0 <= v1_idx < v1_len else 0.0
            
        win_val = None
        if win_prices is not None:
            win_idx = i - (n - win_len)
            win_val = float(win_prices[win_idx]) if 0 <= win_idx < win_len else 0.0
            entry["win_price"] = win_val
            
        z_di_val = di_map.get(local_ts, 0.0) if di_map else 0.0
        entry["z_di"] = z_di_val
        
        z_wdo = round(float(z_arr[i]), 3)
        cons_wdo_sig = -1 if z_wdo <= -1.4 else (1 if z_wdo >= 1.4 else 0)
        cons_di_sig = -1 if z_di_val <= -1.4 else (1 if z_di_val >= 1.4 else 0)
        
        sig_wdo = cons_wdo_sig
        sig_di = cons_di_sig
        
        if nwe_line is not None:
            nwe_idx = i - (n - nwe_len)
            if 0 <= nwe_idx < nwe_len:
                nv = float(nwe_line[nwe_idx])
                nu = float(nwe_upper[nwe_idx])
                nl = float(nwe_lower[nwe_idx])
                n_is_up = bool(nwe_is_up[nwe_idx])
                
                envW = nu - nv
                PROX_PCT = 0.10
                npu = nu - (2 * envW) * PROX_PCT
                npl = nl + (2 * envW) * PROX_PCT
                
                entry["nwe"] = round(nv, 2)
                entry["nweUpper"] = round(nu, 2)
                entry["nweLower"] = round(nl, 2)
                entry["nweProxUpper"] = round(npu, 2)
                entry["nweProxLower"] = round(npl, 2)
                entry["isUp"] = n_is_up
                entry["is_up"] = n_is_up
                
                if win_val is not None:
                    isBuyBlocked = n_is_up or (win_val > npl)
                    isSellBlocked = not n_is_up or (win_val < npu)
                    
                    if isBuyBlocked:
                        if z_wdo < 0: sig_wdo, z_wdo = 0, 0
                        if z_di_val < 0: sig_di, z_di_val = 0, 0
                    if isSellBlocked:
                        if z_wdo > 0: sig_wdo, z_wdo = 0, 0
                        if z_di_val > 0: sig_di, z_di_val = 0, 0
                        
        entry["z_raw_wdo"] = z_wdo
        entry["z_raw_di"] = z_di_val
        entry["z_unfiltered_wdo"] = round(float(z_arr[i]), 3)
        entry["z_unfiltered_di"] = z_di_val
        entry["sig_wdo"] = sig_wdo
        entry["sig_di"] = sig_di
        entry["cons_wdo_sig"] = cons_wdo_sig
        entry["cons_di_sig"] = cons_di_sig

        bar_info.append(entry)

    today = datetime.now().date()
    today_str = today.strftime("%Y-%m-%d")

    history = []
    for b in bar_info:
        if b["date"] == today_str and SESSION_START <= b["t_min"] <= SESSION_END:
            entry = {k: v for k, v in b.items()}
            entry["i"] = len(history)
            history.append(entry)

    return history"""

if old_build_history in content:
    content = content.replace(old_build_history, new_build_history)
else:
    print("ERRO: _build_history não encontrado.")


# 2. Modify regime_v2 slicing and NWE calculation
old_v2_slice = """    # ── Slice after burn-in to keep payload and NWE/OLS fast ────────────
    if len(ac) > BARS:
        ac, bc, tc = ac[-BARS:], bc[-BARS:], tc[-BARS:]
        spreads = spreads[-BARS:]
        kf_betas = kf_betas[-BARS:]
        z_scores = z_scores_full[-BARS:]
    else:
        z_scores = z_scores_full

    current_z = float(z_scores[-1])
    current_spread_sd = np.std(spreads[-40:]) if len(spreads) >= 40 else 1.0

    # V1 OLS z-scores + rho (keep for trade engine, not for display)
    beta_ols_real = beta_state["current_beta"]
    spread_v1, z_v1_arr, rho_arr = calc_zscore(ac, bc, beta=beta_ols_real)
    current_rho = float(rho_arr[-1])
    rho_status = get_rho_status(current_rho)

    # Johansen gate
    joh_open, joh_ratio, joh_conv, joh_beta = _compute_johansen_gate(
        ac, bc, _joh_wdo_state, len(ac)
    )

    # Beta health
    beta_ref_20d = float(np.mean(kf_betas[-80:-40]) if len(kf_betas) > 80 else kf_betas[0])
    beta_delta_pct = ((beta_current - beta_ref_20d) / abs(beta_ref_20d) * 100) if beta_ref_20d != 0 else 0
    beta_status_d = get_beta_status(beta_delta_pct)
    safe_to_trade = bool(rho_status["level"] < 2 and beta_status_d["level"] < 2)

    # ── NWE computation ─────────────────────────────────────────────────
    nwe_line, nwe_upper, nwe_lower, nwe_is_up_arr = calc_nwe_with_bands(
        ac, bandwidth=NWE_BANDWIDTH, lookback=NWE_LOOKBACK, mult_mae=NWE_MULT_MAE
    )"""

new_v2_slice = """    # ── NWE computation BEFORE slicing ───────────────────────────────────
    # Compute on the last 200 bars to prevent cone effect
    nwe_lookback_bars = min(len(ac), BARS + 200)
    ac_nwe = ac[-nwe_lookback_bars:]
    nwe_line_full, nwe_upper_full, nwe_lower_full, nwe_is_up_full = calc_nwe_with_bands(
        ac_nwe, bandwidth=NWE_BANDWIDTH, lookback=NWE_LOOKBACK, mult_mae=NWE_MULT_MAE
    )

    # ── Slice after burn-in to keep payload and NWE/OLS fast ────────────
    if len(ac) > BARS:
        ac, bc, tc = ac[-BARS:], bc[-BARS:], tc[-BARS:]
        spreads = spreads[-BARS:]
        kf_betas = kf_betas[-BARS:]
        z_scores = z_scores_full[-BARS:]
        nwe_line = nwe_line_full[-BARS:]
        nwe_upper = nwe_upper_full[-BARS:]
        nwe_lower = nwe_lower_full[-BARS:]
        nwe_is_up_arr = nwe_is_up_full[-BARS:]
    else:
        z_scores = z_scores_full
        nwe_line = nwe_line_full
        nwe_upper = nwe_upper_full
        nwe_lower = nwe_lower_full
        nwe_is_up_arr = nwe_is_up_full

    current_z = float(z_scores[-1])
    current_spread_sd = np.std(spreads[-40:]) if len(spreads) >= 40 else 1.0

    # V1 OLS z-scores + rho (keep for trade engine, not for display)
    beta_ols_real = beta_state["current_beta"]
    spread_v1, z_v1_arr, rho_arr = calc_zscore(ac, bc, beta=beta_ols_real)
    current_rho = float(rho_arr[-1])
    rho_status = get_rho_status(current_rho)

    # Johansen gate
    joh_open, joh_ratio, joh_conv, joh_beta = _compute_johansen_gate(
        ac, bc, _joh_wdo_state, len(ac)
    )

    # Beta health
    beta_ref_20d = float(np.mean(kf_betas[-80:-40]) if len(kf_betas) > 80 else kf_betas[0])
    beta_delta_pct = ((beta_current - beta_ref_20d) / abs(beta_ref_20d) * 100) if beta_ref_20d != 0 else 0
    beta_status_d = get_beta_status(beta_delta_pct)
    safe_to_trade = bool(rho_status["level"] < 2 and beta_status_d["level"] < 2)"""

if old_v2_slice in content:
    content = content.replace(old_v2_slice, new_v2_slice)
else:
    print("ERRO: regime_v2 slice não encontrado.")


# 3. Modify regime_v2 _build_history call
old_v2_call = """    live_history = _build_history(tc[-20:], z_scores[-20:], spreads[-20:], win_prices=ac[-20:])"""
new_v2_call = """    
    di_map = {}
    if _di_cache and "history" in _di_cache:
        for dh in _di_cache["history"]:
            dt_time = datetime.strptime(dh["bar_time"], "%H:%M")
            local_dt = datetime.now().replace(hour=dt_time.hour, minute=dt_time.minute, second=0, microsecond=0)
            di_map[int(local_dt.timestamp())] = dh.get("z", 0.0)

    live_history = _build_history(
        tc[-20:], z_scores[-20:], spreads[-20:], win_prices=ac[-20:],
        nwe_data=(nwe_line[-20:], nwe_upper[-20:], nwe_lower[-20:], nwe_is_up_arr[-20:]),
        di_map=di_map
    )"""
if old_v2_call in content:
    content = content.replace(old_v2_call, new_v2_call)
else:
    print("ERRO: regime_v2 _build_history call não encontrado.")


# 4. Modify history_endpoint
old_hist_loop = """        # --- Build history with session filter ---
        n = len(z_kalman)
        ols_offset = len(z_ols) - n  # align arrays

        entries = []
        for i in range(n):
            local_ts = int(tc[i + (len(tc) - n)]) + TIME_OFFSET
            dt = datetime.fromtimestamp(local_ts)
            t_min = dt.hour * 60 + dt.minute

            if not (SESSION_START <= t_min <= SESSION_END):
                continue

            ols_idx = i + ols_offset
            z_ols_val = round(float(z_ols[ols_idx]), 3) if 0 <= ols_idx < len(z_ols) else 0.0
            z_di_val = z_di_map.get(local_ts, None)

            win_idx = i + (len(tc) - n)
            win_val = float(ac[win_idx]) if 0 <= win_idx < len(ac) else 0.0

            entries.append({
                "date": dt.strftime("%Y-%m-%d"),
                "bar_time": dt.strftime("%H:%M"),
                "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                "z": round(float(z_kalman[i]), 3),
                "z_v1": z_ols_val,
                "z_di": z_di_val,
                "win_price": win_val,
            })"""

new_hist_loop = """        # --- NWE for history ---
        nwe_line, nwe_u, nwe_l, nwe_is_up = calc_nwe_with_bands(
            ac, bandwidth=NWE_BANDWIDTH, lookback=NWE_LOOKBACK, mult_mae=NWE_MULT_MAE
        )

        # --- Build history with session filter ---
        n = len(z_kalman)
        ols_offset = len(z_ols) - n  # align arrays
        nwe_offset = len(nwe_line) - n

        entries = []
        for i in range(n):
            local_ts = int(tc[i + (len(tc) - n)]) + TIME_OFFSET
            dt = datetime.fromtimestamp(local_ts)
            t_min = dt.hour * 60 + dt.minute

            if not (SESSION_START <= t_min <= SESSION_END):
                continue

            ols_idx = i + ols_offset
            z_ols_val = round(float(z_ols[ols_idx]), 3) if 0 <= ols_idx < len(z_ols) else 0.0
            z_di_val = z_di_map.get(local_ts, None)

            win_idx = i + (len(tc) - n)
            win_val = float(ac[win_idx]) if 0 <= win_idx < len(ac) else 0.0

            entry = {
                "date": dt.strftime("%Y-%m-%d"),
                "bar_time": dt.strftime("%H:%M"),
                "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                "z": round(float(z_kalman[i]), 3),
                "z_v1": z_ols_val,
                "z_di": z_di_val,
                "win_price": win_val,
            }
            
            nwe_idx = i + nwe_offset
            if 0 <= nwe_idx < len(nwe_line):
                nv = float(nwe_line[nwe_idx])
                nu = float(nwe_u[nwe_idx])
                nl = float(nwe_l[nwe_idx])
                n_up = bool(nwe_is_up[nwe_idx])
                
                envW = nu - nv
                PROX_PCT = 0.10
                npu = nu - (2 * envW) * PROX_PCT
                npl = nl + (2 * envW) * PROX_PCT
                
                entry["nwe"] = round(nv, 2)
                entry["nweUpper"] = round(nu, 2)
                entry["nweLower"] = round(nl, 2)
                entry["nweProxUpper"] = round(npu, 2)
                entry["nweProxLower"] = round(npl, 2)
                entry["isUp"] = n_up
                entry["is_up"] = n_up

            entries.append(entry)"""

if old_hist_loop in content:
    content = content.replace(old_hist_loop, new_hist_loop)
else:
    print("ERRO: history loop não encontrado.")

with open('server.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Sucesso!")
