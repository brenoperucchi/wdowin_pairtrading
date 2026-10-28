import os
import sqlite3
import datetime
import json


def get_mt5_common_files_dir():
    appdata = os.environ.get("APPDATA", r"C:\Users\ryzen\AppData\Roaming")
    common_files = os.path.join(appdata, "MetaQuotes", "Terminal", "Common", "Files")
    os.makedirs(common_files, exist_ok=True)
    return common_files


def _norm_wall_type(raw_t):
    t = str(raw_t).strip().lower()
    if t in ("wall",):
        return "Wall"
    if t in ("mid_wall", "midwall"):
        return "MidWall"
    if t in ("gamma_flip", "gammaflip"):
        return "GammaFlip"
    if t in ("max_gamma", "maxgamma"):
        return "MaxGamma"
    if t in ("min_gamma", "mingamma"):
        return "MinGamma"
    return str(raw_t)


def export_to_mt5_common(walls, ref_date=None, session_date=None, current_win=None):
    """
    Exporta os níveis GEX MagicWalls do WIN para a pasta universal Common\\Files do MetaTrader 5:
      1. jumba_gex_win_daily.csv   -> Níveis ativos para o pregão de hoje (Operação ao Vivo / Demo)
      2. jumba_gex_win_history.csv -> Histórico completo sincronizado com irai_live.db + pregão atual
                                      (Permite rodar Backtest no Strategy Tester do MT5 e plotar histórico)
      3. jumba_gex_win_daily.json  -> Espelho JSON local do nó Firebase (/daily_levels/win_gex)
    """
    common_dir = get_mt5_common_files_dir()
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    local_mt5_dir = os.path.join(project_root, "mt5", "Files")
    os.makedirs(local_mt5_dir, exist_ok=True)

    if ref_date is None:
        ref_date_str = datetime.date.today().isoformat()
    elif isinstance(ref_date, (datetime.date, datetime.datetime)):
        ref_date_str = ref_date.strftime("%Y-%m-%d")
    else:
        ref_date_str = str(ref_date)[:10]

    if session_date is None:
        session_date_str = datetime.date.today().isoformat()
    elif isinstance(session_date, (datetime.date, datetime.datetime)):
        session_date_str = session_date.strftime("%Y-%m-%d")
    else:
        session_date_str = str(session_date)[:10]

    # 1. Gravar jumba_gex_win_daily.csv (ANSI/ASCII, separador ';')
    daily_lines = ["session_date;ref_oi_date;type;price;width;strike_ibov"]
    for w in walls:
        w_type = _norm_wall_type(w.get("type", "Wall"))
        w_price = float(w.get("price", 0.0))
        w_width = int(w.get("width", 1))
        w_strike = w.get("strike_ibov") or 0
        daily_lines.append(f"{session_date_str};{ref_date_str};{w_type};{w_price:.2f};{w_width};{w_strike}")

    daily_content = "\n".join(daily_lines) + "\n"
    for target_dir in (common_dir, local_mt5_dir):
        daily_path = os.path.join(target_dir, "jumba_gex_win_daily.csv")
        with open(daily_path, "w", encoding="ascii", errors="ignore") as f:
            f.write(daily_content)

    # 2. Gravar espelho JSON local
    json_payload = {
        "session_date": session_date_str,
        "ref_oi_date": ref_date_str,
        "current_win": current_win,
        "last_update": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "walls": walls,
    }
    for target_dir in (common_dir, local_mt5_dir):
        json_path = os.path.join(target_dir, "jumba_gex_win_daily.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_payload, f, indent=2)

    # 3. Sincronizar jumba_gex_win_history.csv preservando datas anteriores + irai_live.db + walls atuais
    db_path = r"C:\Users\ryzen\Downloads\Antigravity\rastro_irado\data\irai_live.db"
    hist_map = {}  # session_date -> list of (type, price, width)

    existing_hist = os.path.join(local_mt5_dir, "jumba_gex_win_history.csv")
    if os.path.exists(existing_hist):
        with open(existing_hist, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "session_date" in line or len(line.strip()) < 5:
                    continue
                parts = line.strip().split(";")
                if len(parts) >= 4:
                    d = parts[0]
                    hist_map.setdefault(d, []).append((parts[1], float(parts[2]), int(parts[3])))

    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("""
                SELECT session_date, run_name, levels_json
                FROM gex_levels
                WHERE target = 'WIN$N'
                ORDER BY session_date ASC, run_name ASC
            """)
            for s_date, r_name, l_json in cur.fetchall():
                if s_date not in hist_map:
                    lvls = json.loads(l_json)
                    day_entries = []
                    for x in lvls:
                        day_entries.append((
                            _norm_wall_type(x.get("type", "Wall")),
                            float(x.get("price", 0.0)),
                            int(x.get("width", 1))
                        ))
                    hist_map[s_date] = day_entries
            conn.close()
        except Exception as e:
            print(f"      [MT5 Exporter] Aviso ao ler irai_live.db: {e}")

    # Atualiza/insere apenas o pregão atual (session_date_str) no histórico
    if walls:
        hist_map[session_date_str] = [
            (_norm_wall_type(w.get("type", "Wall")), float(w.get("price", 0.0)), int(w.get("width", 1)))
            for w in walls
        ]

    hist_lines = ["session_date;type;price;width"]
    for d in sorted(hist_map.keys()):
        for ltype, pr, wd in hist_map[d]:
            hist_lines.append(f"{d};{ltype};{pr:.2f};{wd}")

    hist_content = "\n".join(hist_lines) + "\n"
    for target_dir in (common_dir, local_mt5_dir):
        hist_path = os.path.join(target_dir, "jumba_gex_win_history.csv")
        with open(hist_path, "w", encoding="ascii", errors="ignore") as f:
            f.write(hist_content)

    print(f"      [MT5 Exporter] Arquivos atualizados em Common\\Files ({len(walls)} niveis hoje | {len(hist_map)} dias no historico)")
    return common_dir


def export_wdo_to_mt5_common(walls, ref_date=None, session_date=None, current_wdo=None):
    """
    Exporta os níveis GEX MagicWalls do WDO/DOL para Common\\Files e mt5\\Files:
      1. jumba_gex_wdo_daily.csv   -> Níveis ativos para o pregão atual
      2. jumba_gex_wdo_history.csv -> Histórico completo acumulado + pregão atual
      3. jumba_gex_wdo_daily.json  -> Espelho JSON local
    """
    common_dir = get_mt5_common_files_dir()
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    local_mt5_dir = os.path.join(project_root, "mt5", "Files")
    os.makedirs(local_mt5_dir, exist_ok=True)

    if session_date is None:
        session_date_str = datetime.date.today().isoformat()
    elif isinstance(session_date, (datetime.date, datetime.datetime)):
        session_date_str = session_date.strftime("%Y-%m-%d")
    else:
        session_date_str = str(session_date)[:10]

    daily_lines = ["session_date;type;price;width"]
    for w in walls:
        w_type = _norm_wall_type(w.get("type", "Wall"))
        w_price = float(w.get("price", 0.0))
        w_width = int(w.get("width", 1))
        daily_lines.append(f"{session_date_str};{w_type};{w_price:.2f};{w_width}")

    daily_content = "\n".join(daily_lines) + "\n"
    for target_dir in (common_dir, local_mt5_dir):
        with open(os.path.join(target_dir, "jumba_gex_wdo_daily.csv"), "w", encoding="ascii", errors="ignore") as f:
            f.write(daily_content)

    # Atualiza jumba_gex_wdo_history.csv preservando datas anteriores
    hist_map = {}
    existing_hist = os.path.join(local_mt5_dir, "jumba_gex_wdo_history.csv")
    if os.path.exists(existing_hist):
        with open(existing_hist, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "session_date" in line or len(line.strip()) < 5:
                    continue
                parts = line.strip().split(";")
                if len(parts) >= 4:
                    d = parts[0]
                    hist_map.setdefault(d, []).append((parts[1], float(parts[2]), int(parts[3])))

    if walls:
        hist_map[session_date_str] = [
            (_norm_wall_type(w.get("type", "Wall")), float(w.get("price", 0.0)), int(w.get("width", 1)))
            for w in walls
        ]

    hist_lines = ["session_date;type;price;width"]
    for d in sorted(hist_map.keys()):
        for ltype, pr, wd in hist_map[d]:
            hist_lines.append(f"{d};{ltype};{pr:.2f};{wd}")

    hist_content = "\n".join(hist_lines) + "\n"
    for target_dir in (common_dir, local_mt5_dir):
        with open(os.path.join(target_dir, "jumba_gex_wdo_history.csv"), "w", encoding="ascii", errors="ignore") as f:
            f.write(hist_content)

    try:
        import json
        gex_data_dir = os.path.join(project_root, "gex", "data")
        os.makedirs(gex_data_dir, exist_ok=True)
        with open(os.path.join(gex_data_dir, "jumba_gex_wdo_daily.json"), "w", encoding="utf-8") as jf:
            json.dump({"session_date": session_date_str, "current_wdo": current_wdo, "walls": walls}, jf, indent=2)
    except Exception:
        pass
    print(f"      [MT5 WDO Exporter] Arquivos WDO atualizados em Common\\Files ({len(walls)} niveis hoje | {len(hist_map)} dias no historico)")
    return common_dir

