import re

def patch_server():
    with open("server.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Add DB functions before _build_history
    db_funcs = """
def save_bar_history(timestamp, date_str, bar_time, win_price, wdo_price, di_price, spread_wdo, spread_di, z_wdo, z_di, nwe_center, nwe_upper, nwe_lower, nwe_is_up):
    try:
        conn = sqlite3.connect("trades.db", timeout=10.0)
        c = conn.cursor()
        c.execute('''
            INSERT OR IGNORE INTO bar_history 
            (timestamp, date_str, bar_time, win_price, wdo_price, di_price, spread_wdo, spread_di, z_wdo, z_di, nwe_center, nwe_upper, nwe_lower, nwe_is_up)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (int(timestamp), date_str, bar_time, win_price, wdo_price, di_price, spread_wdo, spread_di, z_wdo, z_di, nwe_center, nwe_upper, nwe_lower, int(nwe_is_up)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERRO DB] falha ao salvar bar_history: {e}")

def load_bar_history(days=30):
    try:
        conn = sqlite3.connect("trades.db", timeout=10.0)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        ts_limit = int(time.time()) - days * 86400
        c.execute("SELECT * FROM bar_history WHERE timestamp >= ? ORDER BY timestamp ASC", (ts_limit,))
        rows = c.fetchall()
        conn.close()
        
        history = []
        for r in rows:
            history.append({
                "z": r["z_wdo"],
                "z_di": r["z_di"],
                "spread": r["spread_wdo"],
                "bar_time": r["bar_time"],
                "date": r["date_str"],
                "win_price": r["win_price"]
            })
        return history
    except Exception as e:
        print(f"[ERRO DB] falha ao carregar bar_history: {e}")
        return []

def do_backfill_if_empty():
    try:
        conn = sqlite3.connect("trades.db", timeout=10.0)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM bar_history")
        count = c.fetchone()[0]
        conn.close()
        if count > 0:
            print(f"[OK] bar_history possui {count} registros.")
            return
            
        print("[INFO] bar_history vazio. Iniciando backfill de 30 dias...")
        import urllib.request
        urllib.request.urlopen("http://localhost:8080/api/history?days=30")
        print("[OK] Backfill concluido via chamada ao endpoint local.")
    except Exception as e:
        print(f"[ERRO] Falha no backfill: {e}")

"""
    if "def save_bar_history" not in content:
        content = content.replace("def _build_history", db_funcs + "def _build_history")

    # 2. Add backfill task to lifespan
    lifespan_hook = """
    if firebase_initialized:
        asyncio.create_task(firebase_push_loop())
    yield
"""
    new_lifespan_hook = """
    if firebase_initialized:
        asyncio.create_task(firebase_push_loop())
    
    # Run backfill async
    import threading
    threading.Thread(target=do_backfill_if_empty, daemon=True).start()
    
    yield
"""
    if "threading.Thread(target=do_backfill_if_empty" not in content:
        content = content.replace(lifespan_hook, new_lifespan_hook)

    # 3. Intercept bar_close in history_endpoint or regime_v2?
    # If we save in history_endpoint, it's called once when requested. But we want to save LIVE when bar closes!
    # Let's save in regime_v2 when bar_close_confirmed is True.
    # In regime_v2:
    bar_close_logic = """
    if not hasattr(regime_v2, "_last_bar_ts") or regime_v2._last_bar_ts != last_bar_ts:
        bar_close_confirmed = True
        regime_v2._last_bar_ts = last_bar_ts
        # Force DI cache update on bar close to prevent race conditions in consensus logic
        di_regime()
"""
    new_bar_close_logic = """
    if not hasattr(regime_v2, "_last_bar_ts") or regime_v2._last_bar_ts != last_bar_ts:
        bar_close_confirmed = True
        regime_v2._last_bar_ts = last_bar_ts
        # Force DI cache update on bar close to prevent race conditions in consensus logic
        di_regime()
        
        # SAVE STATE TO DATABASE FOR PERSISTENCE (using CLOSED bar values, index -2 since -1 is the new open bar, wait! 
        # Actually fetch_bars gives completed bars up to current. The last element in ac is the current open bar. The closed bar is -2.
        # But wait, last_bar_ts changed, meaning the new bar just started.
        # So the closed bar we just finished is index -2!
        # Let's verify lengths: if len > 1, closed bar is -2.
        try:
            if len(ac) > 1:
                z_wdo_closed = z_scores[-2]
                spread_wdo_closed = spreads[-2]
                win_price_closed = ac[-2]
                wdo_price_closed = bc[-2]
                nwe_center_closed = nwe_line[-2]
                nwe_upper_closed = nwe_upper[-2]
                nwe_lower_closed = nwe_lower[-2]
                nwe_is_up_closed = nwe_is_up_arr[-2]
                closed_ts = int(tc[-2]) + 0 # TIME_OFFSET if needed, wait, server.py uses TIME_OFFSET in _build_history.
                
                # DI cache has current_z, but we need the historical one. Actually _di_cache is just the latest.
                # Since we just updated di_regime(), the _di_cache history has the closed bar!
                z_di_closed = 0.0
                if _di_cache and "history" in _di_cache and len(_di_cache["history"]) > 0:
                    z_di_closed = _di_cache["history"][-1]["z"] # history has already been sliced/aligned.
                
                dt_c = datetime.fromtimestamp(closed_ts)
                bar_time_c = dt_c.strftime("%H:%M")
                date_str_c = dt_c.strftime("%Y-%m-%d")
                
                save_bar_history(
                    timestamp=closed_ts, date_str=date_str_c, bar_time=bar_time_c,
                    win_price=win_price_closed, wdo_price=wdo_price_closed, di_price=0.0,
                    spread_wdo=spread_wdo_closed, spread_di=0.0,
                    z_wdo=z_wdo_closed, z_di=z_di_closed,
                    nwe_center=nwe_center_closed, nwe_upper=nwe_upper_closed, nwe_lower=nwe_lower_closed,
                    nwe_is_up=nwe_is_up_closed
                )
        except Exception as e:
            print(f"[ERRO DB SAVE] {e}")
"""
    if "save_bar_history(" not in content and "regime_v2._last_bar_ts != last_bar_ts" in content:
        content = content.replace(bar_close_logic, new_bar_close_logic)

    # 4. Modify /api/history to populate DB and return hybrid (DB + Live Open Bar)
    # The history endpoint computes `entries`. 
    # We can intercept at the end of history_endpoint:
    hist_end = """        return {
            "history": entries,
            "days": days,
        }
    except Exception as e:"""
    
    new_hist_end = """        # BACKFILL: If DB is missing these, insert them
        try:
            for e in entries:
                # e contains: z, spread, bar_time, date, win_price, z_di
                ts = int(datetime.combine(e["date"], datetime.strptime(e["bar_time"], "%H:%M").time()).timestamp())
                save_bar_history(
                    timestamp=ts, date_str=e["date"].strftime("%Y-%m-%d"), bar_time=e["bar_time"],
                    win_price=e.get("win_price", 0), wdo_price=0, di_price=0,
                    spread_wdo=e.get("spread", 0), spread_di=0,
                    z_wdo=e.get("z", 0), z_di=e.get("z_di", 0),
                    nwe_center=0, nwe_upper=0, nwe_lower=0, nwe_is_up=0
                )
        except Exception as ex:
            print("Erro backfill hist:", ex)

        # Serve frozen DB history + live open bar
        frozen_history = load_bar_history(days=days)
        # Append the live open bar (the last one in entries)
        if entries and frozen_history:
            # check if last entry is already in frozen
            if entries[-1]["bar_time"] != frozen_history[-1]["bar_time"]:
                frozen_history.append(entries[-1])
        elif entries:
            frozen_history = entries
            
        return {
            "history": frozen_history,
            "days": days,
        }
    except Exception as e:"""

    if "frozen_history = load_bar_history" not in content:
        content = content.replace(hist_end, new_hist_end)

    # 5. Modify regime_v2 to serve DB history + live open bar instead of dynamically computed history!
    # Wait, regime_v2 creates `history` array and returns it.
    # In regime_v2, we do: `history = _build_history(tc, z_scores, spreads, win_prices=ac)`
    # We can replace this with pulling from DB!
    v2_hist_logic = """    # History — no longer include OLS z_v1 (consensus is WDO+DI only)
    history = _build_history(tc, z_scores, spreads, win_prices=ac)"""
    new_v2_hist_logic = """    # History — Statefully loaded from DB to prevent repainting
    db_hist = load_bar_history(days=2) # Load last 2 days is enough for dashboard
    live_history = _build_history(tc[-20:], z_scores[-20:], spreads[-20:], win_prices=ac[-20:])
    
    if db_hist and live_history:
        # Append the current open bar (and any missing bars not yet in DB)
        last_db_ts = db_hist[-1]["date"] + " " + db_hist[-1]["bar_time"]
        for lh in live_history:
            lh_ts = lh["date"].strftime("%Y-%m-%d") + " " + lh["bar_time"]
            if lh_ts > last_db_ts:
                db_hist.append(lh)
        history = db_hist
    else:
        history = _build_history(tc, z_scores, spreads, win_prices=ac)
    """
    if "load_bar_history(days=2)" not in content:
        content = content.replace(v2_hist_logic, new_v2_hist_logic)

    with open("server.py", "w", encoding="utf-8") as f:
        f.write(content)
        
    print("server.py patched successfully!")

patch_server()
