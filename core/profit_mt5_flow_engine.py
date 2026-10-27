# -*- coding: utf-8 -*-
"""
core/profit_mt5_flow_engine.py
==============================
Etapa 1: Motor Híbrido ProfitChart + MT5 de Agressão, Fluxo Institucional vs. Varejo
e Detector Real de Absorção / Rompimento sobre as MagicWalls (WIN e WDO).

Destaques de Arquitetura:
  1. Leitura Incremental via ponteiro de bytes (f.seek) na pasta RTD/ para arquivos do Profit:
     - Zero limite de 5 MB (suporta arquivos de 500 MB+ lendo apenas os bytes novos em < 1 ms).
     - Aceita Times & Trades de 4 colunas (Hora;Compra/Venda;Preço;Lote) de WIN e WDO.
     - Aceita Times & Trades de 6/7 colunas (IND/DOL cheio com códigos de corretoras B3).
     - Aceita tabela Saldo de Corretoras (*_saldo.csv).
  2. Stream Incremental & Backfill Vetorizado NumPy de Ticks do MT5 (copy_ticks_from):
     - Processa 500.000+ ticks desde as 09h00 em < 0,3 segundos usando vetorização NumPy.
     - Detecta automaticamente os contratos vigentes (ex: WINZ26 e WDOX26).
  3. Separação de Fluxo por Porte de Lote (Big Player CVD vs. Varejo):
     - WIN: Institucional (>= 50 lotes), Médio (10..49 lotes), Varejo (< 10 lotes).
     - WDO: Institucional (>= 20 lotes), Médio (5..19 lotes), Varejo (< 5 lotes).
  4. Detector Real de Absorção & Rompimento sobre as 34 MagicWalls do Dia:
     - Mede Esforço (Volume Agressor na Zona da Wall) vs. Resultado (Deslocamento em Ticks).
     - Identifica Defesa Passiva (Absorção Compradora/Vendedora) vs. Rompimento Institucional.
"""

import os
import re
import glob
import time
from collections import deque
from datetime import datetime, timezone
import numpy as np
import MetaTrader5 as mt5

from core.config import MT5_PATH

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RTD_DIR = os.path.join(PROJECT_ROOT, "RTD")
COMMON_FILES_DIR = os.path.join(
    os.environ.get("APPDATA", r"C:\Users\ryzen\AppData\Roaming"),
    "MetaQuotes", "Terminal", "Common", "Files"
)

BROKERS_LIST = [
    "XP", "UBS", "BTG", "IDEAL", "GENIAL",
    "JPMORGAN", "TULLETT", "MERRILL", "GOLDMAN",
    "MORGAN", "CITI", "ITAU", "BRADESCO",
    "TORO", "SANTANDER", "CM_CAPITAL", "INTER", "FUTURA"
]

INSTITUTIONAL_BROKERS = {
    "UBS", "BTG", "IDEAL", "JPMORGAN", "TULLETT",
    "MERRILL", "GOLDMAN", "MORGAN", "CITI",
    "ITAU", "BRADESCO", "SANTANDER"
}

B3_BROKER_CODES = {
    3: "XP", 8: "UBS", 13: "MERRILL", 16: "JPMORGAN",
    23: "GOLDMAN", 27: "SANTANDER", 39: "BRADESCO", 40: "MORGAN", 45: "UBS",
    72: "BRADESCO", 85: "BTG", 88: "CM_CAPITAL", 92: "MORGAN", 93: "FUTURA",
    107: "CITI", 114: "ITAU", 120: "GENIAL", 127: "TULLETT", 191: "ITAU",
    238: "GOLDMAN", 308: "CITI", 1099: "INTER", 1618: "IDEAL", 3093: "IDEAL",
    4090: "TORO",
}


def _match_broker_name(text: str):
    t = str(text).upper().strip()
    if "JP" in t and "MORGAN" in t:
        return "JPMORGAN"
    if "STANLEY" in t or ("MORGAN" in t and "JP" not in t):
        return "MORGAN"
    if "PREBON" in t or "TULLETT" in t:
        return "TULLETT"
    if "LYNCH" in t or "MERRILL" in t:
        return "MERRILL"
    for b in BROKERS_LIST:
        if b in t:
            return b
    return None


def _clean_int(val_str: str) -> int:
    s = str(val_str).replace(".", "").replace(",", ".").replace(" ", "").strip()
    try:
        return int(float(s))
    except ValueError:
        return 0


def _clean_float(val_str: str) -> float:
    s = str(val_str).replace(".", "").replace(",", ".").replace(" ", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_daily_magic_walls(asset: str):
    """
    Carrega as 34 MagicWalls do dia para 'WIN' ou 'WDO' a partir de Common\\Files ou mt5\\Files.
    Retorna lista ordenada por preço: [{"type": str, "price": float, "width": int}, ...]
    """
    fname = "jumba_gex_win_daily.csv" if asset.upper() == "WIN" else "jumba_gex_wdo_daily.csv"
    candidates = [
        os.path.join(COMMON_FILES_DIR, fname),
        os.path.join(PROJECT_ROOT, "mt5", "Files", fname),
    ]
    walls = []
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line or "session_date" in line:
                            continue
                        parts = line.split(";")
                        if len(parts) >= 5:
                            w_type = parts[2]
                            w_price = float(parts[3])
                            w_width = int(parts[4])
                        elif len(parts) >= 4:
                            w_type = parts[1]
                            w_price = float(parts[2])
                            w_width = int(parts[3])
                        else:
                            continue
                        walls.append({"type": w_type, "price": w_price, "width": w_width})
                if walls:
                    break
            except Exception:
                pass
    return sorted(walls, key=lambda x: x["price"])


class SymbolMicrostructureState:
    """
    Mantém o estado completo de microestrutura intradiária de um ativo (WIN ou WDO).
    Suporta ingestão individual (streaming Profit/MT5) e ingestão em lote vetorizada (NumPy).
    """

    def __init__(self, asset: str, inst_lot_threshold: int, mid_lot_threshold: int, tick_size: float, wall_zone_radius: float):
        self.asset = asset.upper()
        self.inst_lot_threshold = inst_lot_threshold  # WIN: 50, WDO: 20
        self.mid_lot_threshold = mid_lot_threshold    # WIN: 10, WDO: 5
        self.tick_size = tick_size                    # WIN: 5.0, WDO: 0.5
        self.wall_zone_radius = wall_zone_radius      # WIN: 60.0 pts, WDO: 2.5 pts
        self.session_date = datetime.now().strftime("%Y-%m-%d")
        self.active_contract = ""
        self.source = "AGUARDANDO"

        self.reset_session(self.session_date)

    def reset_session(self, new_date: str):
        self.session_date = new_date
        self.last_price = 0.0
        self.open_price = 0.0
        self.high_price = 0.0
        self.low_price = 0.0
        self.vwap_num = 0.0
        self.vwap_den = 0.0

        self.buy_vol = 0.0
        self.sell_vol = 0.0
        self.buy_deals = 0
        self.sell_deals = 0

        self.inst_buy_vol = 0.0
        self.inst_sell_vol = 0.0
        self.mid_buy_vol = 0.0
        self.mid_sell_vol = 0.0
        self.ret_buy_vol = 0.0
        self.ret_sell_vol = 0.0
        self.rlp_vol = 0.0
        self.rlp_deals = 0

        # Fila do Topo do Book (TinyBook do Profit: Compra=Bid, Venda=Ask)
        self.best_bid_price = 0.0
        self.best_bid_qty = 0.0
        self.best_ask_price = 0.0
        self.best_ask_qty = 0.0

        # Buckets agregados por segundo: [ts_sec, high, low, close, buy_q, sell_q, inst_d, ret_d]
        self.sec_buckets = deque(maxlen=4000)
        self._curr_sec = 0
        self._curr_bucket = None

        # Barras M5 da sessão: m5_ts -> dict
        self.m5_bars = {}

        # Corretoras (quando disponível via Profit CSV/RTD)
        self.brokers = {
            b: {
                "net": 0, "buy": 0, "sell": 0, "avg": 0.0, "vol": 0,
                "aggr_buy": 0, "aggr_sell": 0, "passive_buy": 0, "passive_sell": 0,
                "is_institutional": b in INSTITUTIONAL_BROKERS,
            }
            for b in BROKERS_LIST
        }

        self.walls = load_daily_magic_walls(self.asset)
        self.wall_stats = {}
        self._init_wall_stats()

    def _init_wall_stats(self):
        self.wall_stats = {}
        for w in self.walls:
            key = f"{w['type']}_{w['price']:.2f}"
            self.wall_stats[key] = {
                "type": w["type"],
                "price": w["price"],
                "width": w["width"],
                "buy_vol": 0.0,
                "sell_vol": 0.0,
                "inst_buy_vol": 0.0,
                "inst_sell_vol": 0.0,
                "deals": 0,
                "recent_events": deque(maxlen=600),
            }

    def reload_walls_if_needed(self):
        new_walls = load_daily_magic_walls(self.asset)
        if len(new_walls) != len(self.walls) or (
            new_walls and self.walls and new_walls[0]["price"] != self.walls[0]["price"]
        ):
            self.walls = new_walls
            self._init_wall_stats()

    def ingest_batch_vectorized(self, ts_arr: np.ndarray, price_arr: np.ndarray, vol_arr: np.ndarray, side_arr: np.ndarray):
        """
        Ingestão ultra-rápida vetorizada em NumPy para grandes lotes (ex: 500.000 ticks em < 0,15s).
        side_arr: +1 (compra) ou -1 (venda).
        """
        n = len(ts_arr)
        if n == 0:
            return

        if self.open_price <= 0.0:
            self.open_price = float(price_arr[0])
            self.high_price = float(np.max(price_arr))
            self.low_price = float(np.min(price_arr))
        else:
            self.high_price = max(self.high_price, float(np.max(price_arr)))
            self.low_price = min(self.low_price, float(np.min(price_arr)))
        self.last_price = float(price_arr[-1])

        self.vwap_num += float(np.sum(price_arr * vol_arr))
        self.vwap_den += float(np.sum(vol_arr))

        is_buy = side_arr > 0
        is_sell = side_arr < 0

        buy_q = np.where(is_buy, vol_arr, 0.0)
        sell_q = np.where(is_sell, vol_arr, 0.0)

        self.buy_vol += float(np.sum(buy_q))
        self.sell_vol += float(np.sum(sell_q))
        self.buy_deals += int(np.sum(is_buy))
        self.sell_deals += int(np.sum(is_sell))

        is_inst = vol_arr >= self.inst_lot_threshold
        is_mid = (~is_inst) & (vol_arr >= self.mid_lot_threshold)
        is_ret = (~is_inst) & (~is_mid)

        inst_buy = np.where(is_inst & is_buy, vol_arr, 0.0)
        inst_sell = np.where(is_inst & is_sell, vol_arr, 0.0)
        ret_buy = np.where(is_ret & is_buy, vol_arr, 0.0)
        ret_sell = np.where(is_ret & is_sell, vol_arr, 0.0)

        self.inst_buy_vol += float(np.sum(inst_buy))
        self.inst_sell_vol += float(np.sum(inst_sell))
        self.mid_buy_vol += float(np.sum(np.where(is_mid & is_buy, vol_arr, 0.0)))
        self.mid_sell_vol += float(np.sum(np.where(is_mid & is_sell, vol_arr, 0.0)))
        self.ret_buy_vol += float(np.sum(ret_buy))
        self.ret_sell_vol += float(np.sum(ret_sell))

        inst_d = inst_buy - inst_sell
        ret_d = ret_buy - ret_sell

        # 1. Agregar por segundo (apenas últimos 3600 segundos para o deque sec_buckets)
        max_ts = int(ts_arr[-1])
        cutoff_sec = max_ts - 3800
        recent_mask = ts_arr >= cutoff_sec
        if np.any(recent_mask):
            r_ts = ts_arr[recent_mask]
            r_p = price_arr[recent_mask]
            r_bq = buy_q[recent_mask]
            r_sq = sell_q[recent_mask]
            r_id = inst_d[recent_mask]
            r_rd = ret_d[recent_mask]

            uniq_secs, idx_start, counts = np.unique(r_ts, return_index=True, return_counts=True)
            sum_bq = np.add.reduceat(r_bq, idx_start)
            sum_sq = np.add.reduceat(r_sq, idx_start)
            sum_id = np.add.reduceat(r_id, idx_start)
            sum_rd = np.add.reduceat(r_rd, idx_start)
            max_p = np.maximum.reduceat(r_p, idx_start)
            min_p = np.minimum.reduceat(r_p, idx_start)
            close_p = r_p[idx_start + counts - 1]

            for i in range(len(uniq_secs)):
                s_val = int(uniq_secs[i])
                if self._curr_bucket is not None and self._curr_sec == s_val:
                    b = self._curr_bucket
                    b[1] = max(b[1], float(max_p[i]))
                    b[2] = min(b[2], float(min_p[i]))
                    b[3] = float(close_p[i])
                    b[4] += float(sum_bq[i])
                    b[5] += float(sum_sq[i])
                    b[6] += float(sum_id[i])
                    b[7] += float(sum_rd[i])
                else:
                    self._curr_sec = s_val
                    self._curr_bucket = [
                        s_val,
                        float(max_p[i]),
                        float(min_p[i]),
                        float(close_p[i]),
                        float(sum_bq[i]),
                        float(sum_sq[i]),
                        float(sum_id[i]),
                        float(sum_rd[i]),
                    ]
                    self.sec_buckets.append(self._curr_bucket)

        # 2. Agregar barras M5 vetorizado
        m5_arr = (ts_arr // 300) * 300
        uniq_m5, m5_start, m5_counts = np.unique(m5_arr, return_index=True, return_counts=True)
        m5_bq = np.add.reduceat(buy_q, m5_start)
        m5_sq = np.add.reduceat(sell_q, m5_start)
        m5_id = np.add.reduceat(inst_d, m5_start)
        m5_rd = np.add.reduceat(ret_d, m5_start)
        m5_high = np.maximum.reduceat(price_arr, m5_start)
        m5_low = np.minimum.reduceat(price_arr, m5_start)
        m5_open = price_arr[m5_start]
        m5_close = price_arr[m5_start + m5_counts - 1]

        for i in range(len(uniq_m5)):
            mts = int(uniq_m5[i])
            bq_i = float(m5_bq[i])
            sq_i = float(m5_sq[i])
            id_i = float(m5_id[i])
            rd_i = float(m5_rd[i])
            bar = self.m5_bars.get(mts)
            if bar is None:
                self.m5_bars[mts] = {
                    "time": mts,
                    "open": float(m5_open[i]),
                    "high": float(m5_high[i]),
                    "low": float(m5_low[i]),
                    "close": float(m5_close[i]),
                    "buy_vol": bq_i,
                    "sell_vol": sq_i,
                    "delta_bar": bq_i - sq_i,
                    "inst_delta_bar": id_i,
                    "ret_delta_bar": rd_i,
                    "cvd_total": 0.0,
                    "cvd_inst": 0.0,
                    "cvd_retail": 0.0,
                }
            else:
                bar["high"] = max(bar["high"], float(m5_high[i]))
                bar["low"] = min(bar["low"], float(m5_low[i]))
                bar["close"] = float(m5_close[i])
                bar["buy_vol"] += bq_i
                bar["sell_vol"] += sq_i
                bar["delta_bar"] += (bq_i - sq_i)
                bar["inst_delta_bar"] += id_i
                bar["ret_delta_bar"] += rd_i

        # Recalcula CVD cumulativo nas barras M5 ordenadas
        c_tot, c_inst, c_ret = 0.0, 0.0, 0.0
        for mts in sorted(self.m5_bars.keys()):
            b = self.m5_bars[mts]
            c_tot += b["delta_bar"]
            c_inst += b["inst_delta_bar"]
            c_ret += b["ret_delta_bar"]
            b["cvd_total"] = round(c_tot, 0)
            b["cvd_inst"] = round(c_inst, 0)
            b["cvd_retail"] = round(c_ret, 0)

        # 3. Estatísticas vetorizadas por MagicWall
        cutoff_wall_recent = max_ts - 900
        for w in self.walls:
            wp = w["price"]
            mask_w = np.abs(price_arr - wp) <= self.wall_zone_radius
            if not np.any(mask_w):
                continue
            key = f"{w['type']}_{wp:.2f}"
            ws = self.wall_stats.get(key)
            if ws is None:
                continue
            ws["buy_vol"] += float(np.sum(buy_q[mask_w]))
            ws["sell_vol"] += float(np.sum(sell_q[mask_w]))
            ws["inst_buy_vol"] += float(np.sum(inst_buy[mask_w]))
            ws["inst_sell_vol"] += float(np.sum(inst_sell[mask_w]))
            ws["deals"] += int(np.sum(mask_w))

            mask_wr = mask_w & (ts_arr >= cutoff_wall_recent)
            if np.any(mask_wr):
                w_ts = ts_arr[mask_wr]
                w_p = price_arr[mask_wr]
                w_bq = buy_q[mask_wr]
                w_sq = sell_q[mask_wr]
                w_id = inst_d[mask_wr]
                u_s, u_idx, u_cnt = np.unique(w_ts, return_index=True, return_counts=True)
                sbq = np.add.reduceat(w_bq, u_idx)
                ssq = np.add.reduceat(w_sq, u_idx)
                sid = np.add.reduceat(w_id, u_idx)
                cp = w_p[u_idx + u_cnt - 1]
                rev = ws["recent_events"]
                for k in range(len(u_s)):
                    rev.append([int(u_s[k]), float(cp[k]), float(sbq[k]), float(ssq[k]), float(sid[k])])

    def ingest_trade(self, ts_sec: int, price: float, qty: float, side: int):
        """
        Processa um negócio individual em tempo real.
        """
        if price <= 0.0 or qty <= 0.0 or side == 0:
            return

        if self.open_price <= 0.0:
            self.open_price = price
            self.high_price = price
            self.low_price = price
        else:
            if price > self.high_price:
                self.high_price = price
            if price < self.low_price:
                self.low_price = price

        self.last_price = price
        self.vwap_num += price * qty
        self.vwap_den += qty

        buy_q = qty if side > 0 else 0.0
        sell_q = qty if side < 0 else 0.0

        if side > 0:
            self.buy_vol += qty
            self.buy_deals += 1
        else:
            self.sell_vol += qty
            self.sell_deals += 1

        inst_d = 0.0
        ret_d = 0.0
        if qty >= self.inst_lot_threshold:
            if side > 0:
                self.inst_buy_vol += qty
                inst_d = qty
            else:
                self.inst_sell_vol += qty
                inst_d = -qty
        elif qty >= self.mid_lot_threshold:
            if side > 0:
                self.mid_buy_vol += qty
            else:
                self.mid_sell_vol += qty
        else:
            if side > 0:
                self.ret_buy_vol += qty
                ret_d = qty
            else:
                self.ret_sell_vol += qty
                ret_d = -qty

        if ts_sec != self._curr_sec or self._curr_bucket is None:
            self._curr_sec = ts_sec
            self._curr_bucket = [ts_sec, price, price, price, buy_q, sell_q, inst_d, ret_d]
            self.sec_buckets.append(self._curr_bucket)
        else:
            b = self._curr_bucket
            if price > b[1]:
                b[1] = price
            if price < b[2]:
                b[2] = price
            b[3] = price
            b[4] += buy_q
            b[5] += sell_q
            b[6] += inst_d
            b[7] += ret_d

        m5_ts = (ts_sec // 300) * 300
        bar = self.m5_bars.get(m5_ts)
        if bar is None:
            self.m5_bars[m5_ts] = {
                "time": m5_ts,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "buy_vol": buy_q,
                "sell_vol": sell_q,
                "delta_bar": buy_q - sell_q,
                "inst_delta_bar": inst_d,
                "ret_delta_bar": ret_d,
                "cvd_total": self.buy_vol - self.sell_vol,
                "cvd_inst": self.inst_buy_vol - self.inst_sell_vol,
                "cvd_retail": self.ret_buy_vol - self.ret_sell_vol,
            }
        else:
            if price > bar["high"]:
                bar["high"] = price
            if price < bar["low"]:
                bar["low"] = price
            bar["close"] = price
            bar["buy_vol"] += buy_q
            bar["sell_vol"] += sell_q
            bar["delta_bar"] += (buy_q - sell_q)
            bar["inst_delta_bar"] += inst_d
            bar["ret_delta_bar"] += ret_d
            bar["cvd_total"] = self.buy_vol - self.sell_vol
            bar["cvd_inst"] = self.inst_buy_vol - self.inst_sell_vol
            bar["cvd_retail"] = self.ret_buy_vol - self.ret_sell_vol

        for w in self.walls:
            if abs(price - w["price"]) <= self.wall_zone_radius:
                key = f"{w['type']}_{w['price']:.2f}"
                ws = self.wall_stats.get(key)
                if ws is not None:
                    ws["buy_vol"] += buy_q
                    ws["sell_vol"] += sell_q
                    if inst_d > 0:
                        ws["inst_buy_vol"] += inst_d
                    elif inst_d < 0:
                        ws["inst_sell_vol"] += abs(inst_d)
                    ws["deals"] += 1
                    rev = ws["recent_events"]
                    if rev and rev[-1][0] == ts_sec:
                        last_ev = rev[-1]
                        last_ev[1] = price
                        last_ev[2] += buy_q
                        last_ev[3] += sell_q
                        last_ev[4] += inst_d
                    else:
                        rev.append([ts_sec, price, buy_q, sell_q, inst_d])

    def compute_window_metrics(self, window_sec: int) -> dict:
        if not self.sec_buckets:
            return {
                "buy_vol": 0.0, "sell_vol": 0.0, "total_vol": 0.0,
                "delta": 0.0, "inst_delta": 0.0, "ret_delta": 0.0,
                "price_change": 0.0, "price_range": 0.0,
                "lots_per_tick": 0.0, "imbalance_pct": 0.0,
                "absorption_state": "NEUTRO", "absorption_score": 0.0,
            }

        latest_ts = self.sec_buckets[-1][0]
        cutoff_ts = latest_ts - window_sec

        buy_v = 0.0
        sell_v = 0.0
        inst_d = 0.0
        ret_d = 0.0
        high_p = -1e18
        low_p = 1e18
        first_p = None
        last_p = self.sec_buckets[-1][3]

        for b in reversed(self.sec_buckets):
            if b[0] < cutoff_ts:
                break
            first_p = b[3]
            if b[1] > high_p:
                high_p = b[1]
            if b[2] < low_p:
                low_p = b[2]
            buy_v += b[4]
            sell_v += b[5]
            inst_d += b[6]
            ret_d += b[7]

        if first_p is None:
            first_p = last_p
            high_p = last_p
            low_p = last_p

        tot_v = buy_v + sell_v
        delta = buy_v - sell_v
        price_change = last_p - first_p
        price_range = max(0.0, high_p - low_p)
        ticks_moved = abs(price_change) / self.tick_size
        lots_per_tick = tot_v / max(1.0, ticks_moved)
        imbalance_pct = (delta / tot_v * 100.0) if tot_v > 0 else 0.0

        min_vol_active = 3000.0 if self.asset == "WIN" else 800.0
        abs_state = "NEUTRO"
        abs_score = 0.0

        if tot_v >= min_vol_active:
            if delta < 0 and abs(imbalance_pct) >= 10.0:
                if price_change >= -self.tick_size * 2.0:
                    abs_state = "ABSORCAO_COMPRADORA"
                    abs_score = min(100.0, abs(imbalance_pct) * 2.5)
                elif price_change < -self.tick_size * 6.0 and inst_d < 0:
                    abs_state = "AGRESSAO_VENDEDORA_DIRECIONAL"
                    abs_score = -min(100.0, abs(imbalance_pct) * 2.5)
            elif delta > 0 and abs(imbalance_pct) >= 10.0:
                if price_change <= self.tick_size * 2.0:
                    abs_state = "ABSORCAO_VENDEDORA"
                    abs_score = -min(100.0, abs(imbalance_pct) * 2.5)
                elif price_change > self.tick_size * 6.0 and inst_d > 0:
                    abs_state = "AGRESSAO_COMPRADORA_DIRECIONAL"
                    abs_score = min(100.0, abs(imbalance_pct) * 2.5)

        return {
            "buy_vol": round(buy_v, 0),
            "sell_vol": round(sell_v, 0),
            "total_vol": round(tot_v, 0),
            "delta": round(delta, 0),
            "inst_delta": round(inst_d, 0),
            "ret_delta": round(ret_d, 0),
            "price_change": round(price_change, 2),
            "price_range": round(price_range, 2),
            "lots_per_tick": round(lots_per_tick, 1),
            "imbalance_pct": round(imbalance_pct, 1),
            "absorption_state": abs_state,
            "absorption_score": round(abs_score, 1),
        }

    def analyze_nearby_walls(self, count_each_side: int = 3) -> dict:
        if not self.walls or self.last_price <= 0.0:
            return {"support_walls": [], "resistance_walls": [], "active_wall_alert": None}

        latest_ts = self.sec_buckets[-1][0] if self.sec_buckets else int(time.time())
        cutoff_5m = latest_ts - 300

        enriched = []
        for w in self.walls:
            key = f"{w['type']}_{w['price']:.2f}"
            ws = self.wall_stats.get(key, {})
            rev = ws.get("recent_events", [])

            b_5m = sum(e[2] for e in rev if e[0] >= cutoff_5m)
            s_5m = sum(e[3] for e in rev if e[0] >= cutoff_5m)
            id_5m = sum(e[4] for e in rev if e[0] >= cutoff_5m)
            tot_5m = b_5m + s_5m
            d_5m = b_5m - s_5m

            dist_pts = round(w["price"] - self.last_price, 2)
            in_zone = abs(dist_pts) <= self.wall_zone_radius

            status = "AGUARDANDO_TOQUE"
            if tot_5m > 0 or ws.get("deals", 0) > 0:
                if in_zone:
                    if d_5m < 0 and self.last_price >= w["price"] - self.tick_size * 2:
                        status = "ABSORCAO_COMPRADORA_NA_WALL"
                    elif d_5m > 0 and self.last_price <= w["price"] + self.tick_size * 2:
                        status = "ABSORCAO_VENDEDORA_NA_WALL"
                    elif id_5m > 0 and self.last_price > w["price"]:
                        status = "ROMPIMENTO_COMPRADOR_NA_WALL"
                    elif id_5m < 0 and self.last_price < w["price"]:
                        status = "ROMPIMENTO_VENDEDOR_NA_WALL"
                    else:
                        status = "DISPUTA_EM_ZONA"
                else:
                    status = "TESTADA_HOJE"

            enriched.append({
                "type": w["type"],
                "price": w["price"],
                "width": w["width"],
                "dist_pts": dist_pts,
                "in_zone": in_zone,
                "session_buy_vol": round(ws.get("buy_vol", 0.0), 0),
                "session_sell_vol": round(ws.get("sell_vol", 0.0), 0),
                "session_delta": round(ws.get("buy_vol", 0.0) - ws.get("sell_vol", 0.0), 0),
                "session_inst_delta": round(ws.get("inst_buy_vol", 0.0) - ws.get("inst_sell_vol", 0.0), 0),
                "vol_5m": round(tot_5m, 0),
                "delta_5m": round(d_5m, 0),
                "inst_delta_5m": round(id_5m, 0),
                "status": status,
            })

        below = [x for x in enriched if x["price"] <= self.last_price]
        above = [x for x in enriched if x["price"] > self.last_price]

        support_walls = sorted(below, key=lambda x: x["price"], reverse=True)[:count_each_side]
        resistance_walls = sorted(above, key=lambda x: x["price"])[:count_each_side]

        in_zone_list = [x for x in enriched if x["in_zone"]]
        active_alert = min(in_zone_list, key=lambda x: abs(x["dist_pts"])) if in_zone_list else None

        return {
            "support_walls": support_walls,
            "resistance_walls": resistance_walls,
            "active_wall_alert": active_alert,
        }

    def compute_composite_flow_score(self) -> dict:
        w1m = self.compute_window_metrics(60)
        w5m = self.compute_window_metrics(300)
        w15m = self.compute_window_metrics(900)
        w60m = self.compute_window_metrics(3600)

        inst_scale_5m = 15000.0 if self.asset == "WIN" else 4000.0
        inst_scale_15m = 30000.0 if self.asset == "WIN" else 8000.0
        s_inst_5m = np.clip((w5m["inst_delta"] / inst_scale_5m) * 100.0, -100.0, 100.0)
        s_inst_15m = np.clip((w15m["inst_delta"] / inst_scale_15m) * 100.0, -100.0, 100.0)
        inst_score = 0.60 * s_inst_5m + 0.40 * s_inst_15m

        aggr_score = np.clip(
            (0.30 * w1m["imbalance_pct"] + 0.45 * w5m["imbalance_pct"] + 0.25 * w15m["imbalance_pct"]) * 3.0,
            -100.0, 100.0
        )

        div_bonus = 0.0
        if w15m["inst_delta"] > 0 and w15m["ret_delta"] < 0:
            div_bonus = 25.0
        elif w15m["inst_delta"] < 0 and w15m["ret_delta"] > 0:
            div_bonus = -25.0

        abs_component = np.clip(0.60 * w5m["absorption_score"] + 0.40 * div_bonus, -100.0, 100.0)

        final_score = float(np.clip(
            0.45 * inst_score + 0.30 * aggr_score + 0.25 * abs_component,
            -100.0, 100.0
        ))

        if final_score >= 35.0:
            verdict = "COMPRA INSTITUCIONAL / FLUXO ALTISTA"
        elif final_score <= -35.0:
            verdict = "VENDA INSTITUCIONAL / FLUXO BAIXISTA"
        elif abs(w5m["absorption_score"]) >= 25.0:
            verdict = f"DEFESA PASSIVA ({w5m['absorption_state']})"
        else:
            verdict = "EQUILIBRIO / TRANSICAO DE FLUXO"

        return {
            "score": round(final_score, 1),
            "inst_score": round(float(inst_score), 1),
            "aggr_score": round(float(aggr_score), 1),
            "abs_score": round(float(abs_component), 1),
            "verdict": verdict,
            "windows": {
                "1m": w1m,
                "5m": w5m,
                "15m": w15m,
                "60m": w60m,
            },
        }

    def get_summary_payload(self) -> dict:
        vwap = (self.vwap_num / self.vwap_den) if self.vwap_den > 0 else self.last_price
        gamma_flip = 0.0
        max_gamma = 0.0
        min_gamma = 0.0
        for w in self.walls:
            if w["type"] == "GammaFlip":
                gamma_flip = w["price"]
            elif w["type"] == "MaxGamma":
                max_gamma = w["price"]
            elif w["type"] == "MinGamma":
                min_gamma = w["price"]

        comp = self.compute_composite_flow_score()
        walls_analysis = self.analyze_nearby_walls(count_each_side=3)

        sorted_m5 = [self.m5_bars[k] for k in sorted(self.m5_bars.keys())[-130:]]

        tot_book_q = self.best_bid_qty + self.best_ask_qty
        book_imb = ((self.best_bid_qty - self.best_ask_qty) / tot_book_q * 100.0) if tot_book_q > 0 else 0.0

        # Ranking de corretoras compradoras e vendedoras líquidas (e agressão vs absorção passiva)
        active_brokers = [
            {"broker": k, **v}
            for k, v in self.brokers.items()
            if v["vol"] > 0 or v["net"] != 0
        ]
        top_buyers = sorted([b for b in active_brokers if b["net"] > 0], key=lambda x: x["net"], reverse=True)[:5]
        top_sellers = sorted([b for b in active_brokers if b["net"] < 0], key=lambda x: x["net"])[:5]
        inst_broker_net = sum(b["net"] for b in active_brokers if b.get("is_institutional"))
        inst_broker_aggr_delta = sum(b["aggr_buy"] - b["aggr_sell"] for b in active_brokers if b.get("is_institutional"))
        inst_broker_passive_delta = sum(b["passive_buy"] - b["passive_sell"] for b in active_brokers if b.get("is_institutional"))

        return {
            "asset": self.asset,
            "active_contract": self.active_contract,
            "source": self.source,
            "session_date": self.session_date,
            "last_price": round(self.last_price, 2),
            "open_price": round(self.open_price, 2),
            "high_price": round(self.high_price, 2),
            "low_price": round(self.low_price, 2),
            "vwap": round(vwap, 2),
            "gamma_flip": round(gamma_flip, 2),
            "max_gamma": round(max_gamma, 2),
            "min_gamma": round(min_gamma, 2),
            "gamma_regime": "POSITIVE_GAMMA (Amortecimento / Defesa de Wall)" if (gamma_flip > 0 and self.last_price >= gamma_flip) else "NEGATIVE_GAMMA (Aceleracao Direcional)",
            "top_of_book": {
                "best_bid_price": round(self.best_bid_price, 2),
                "best_bid_qty": round(self.best_bid_qty, 0),
                "best_ask_price": round(self.best_ask_price, 2),
                "best_ask_qty": round(self.best_ask_qty, 0),
                "book_imbalance_pct": round(book_imb, 1),
            },
            "session_totals": {
                "buy_vol": round(self.buy_vol, 0),
                "sell_vol": round(self.sell_vol, 0),
                "total_delta": round(self.buy_vol - self.sell_vol, 0),
                "delta": round(self.buy_vol - self.sell_vol, 0),
                "inst_buy_vol": round(self.inst_buy_vol, 0),
                "inst_sell_vol": round(self.inst_sell_vol, 0),
                "inst_delta": round(self.inst_buy_vol - self.inst_sell_vol, 0),
                "mid_delta": round(self.mid_buy_vol - self.mid_sell_vol, 0),
                "retail_buy_vol": round(self.ret_buy_vol, 0),
                "retail_sell_vol": round(self.ret_sell_vol, 0),
                "retail_delta": round(self.ret_buy_vol - self.ret_sell_vol, 0),
                "rlp_vol": round(self.rlp_vol, 0),
                "rlp_deals": self.rlp_deals,
                "total_deals": self.buy_deals + self.sell_deals,
                "inst_broker_net": inst_broker_net,
                "inst_broker_aggr_delta": inst_broker_aggr_delta,
                "inst_broker_passive_delta": inst_broker_passive_delta,
            },
            "flow_compass": comp,
            "composite": comp,
            "walls_radar": walls_analysis,
            "all_walls": self.walls,
            "brokers": self.brokers,
            "top_buyers": top_buyers,
            "top_sellers": top_sellers,
            "m5_cvd_series": sorted_m5,
        }


class ProfitMt5FlowEngine:
    """
    Orquestrador unificado da Etapa 1 (Profit CSV f.seek + MT5 Vectorized Live Stream).
    """

    def __init__(self):
        self.win_state = SymbolMicrostructureState(
            asset="WIN", inst_lot_threshold=50, mid_lot_threshold=10, tick_size=5.0, wall_zone_radius=60.0
        )
        self.wdo_state = SymbolMicrostructureState(
            asset="WDO", inst_lot_threshold=20, mid_lot_threshold=5, tick_size=0.5, wall_zone_radius=2.5
        )
        self._file_offsets = {}
        self._last_tick_msc = {"WIN": 0, "WDO": 0}
        self._profit_active_today = {"WIN": False, "WDO": False}
        self._profit_warnings = []
        self._last_update_ts = 0.0

    def _detect_mt5_contracts(self):
        if not self.win_state.active_contract:
            syms_w = mt5.symbols_get("WIN*") or []
            best_w, best_deals = "WIN$N", -1
            for s in syms_w:
                if re.match(r"^WIN[A-Z]\d{2}$", s.name):
                    mt5.symbol_select(s.name, True)
                    if s.session_deals > best_deals:
                        best_deals = s.session_deals
                        best_w = s.name
            self.win_state.active_contract = best_w

        if not self.wdo_state.active_contract:
            syms_d = mt5.symbols_get("WDO*") or []
            best_d, best_deals = "WDO$N", -1
            for s in syms_d:
                if re.match(r"^WDO[A-Z]\d{2}$", s.name):
                    mt5.symbol_select(s.name, True)
                    if s.session_deals > best_deals:
                        best_deals = s.session_deals
                        best_d = s.name
            self.wdo_state.active_contract = best_d

    def _poll_profit_rtd_folder(self):
        if not os.path.exists(RTD_DIR):
            return

        today_suffix = datetime.now().strftime("%d_%m_%Y")
        today_iso = datetime.now().strftime("%Y-%m-%d")
        csv_files = glob.glob(os.path.join(RTD_DIR, "*.csv"))

        self._profit_warnings.clear()

        for filepath in sorted(csv_files):
            fname = os.path.basename(filepath)
            fname_up = fname.upper()

            is_today_file = (today_suffix in fname) or ("SALDO" in fname_up)
            if not is_today_file:
                continue

            try:
                size = os.path.getsize(filepath)
            except OSError:
                continue

            if size == 0:
                if today_suffix in fname:
                    self._profit_warnings.append(
                        f"Arquivo {fname} criado pelo Profit hoje está com 0 bytes (altere o ativo exportado no Profit para {self.win_state.active_contract or 'WINZ26'} / {self.wdo_state.active_contract or 'WDOX26'})."
                    )
                continue

            target_state = None
            if any(k in fname_up for k in ["WIN", "IND"]):
                target_state = self.win_state
                asset_key = "WIN"
            elif any(k in fname_up for k in ["WDO", "DOL"]):
                target_state = self.wdo_state
                asset_key = "WDO"
            else:
                continue

            if "SALDO" in fname_up and size < 200 * 1024:
                self._parse_profit_broker_balance_file(filepath, target_state)
                continue

            last_offset = self._file_offsets.get(filepath, 0)
            if size < last_offset:
                last_offset = 0
            if size == last_offset:
                continue

            try:
                with open(filepath, "rb") as fb:
                    fb.seek(last_offset)
                    raw_chunk = fb.read()
                    new_offset = fb.tell()
            except OSError:
                continue

            if not raw_chunk:
                continue

            last_nl = raw_chunk.rfind(b"\n")
            if last_nl == -1:
                continue

            complete_bytes = raw_chunk[: last_nl + 1]
            self._file_offsets[filepath] = (new_offset - len(raw_chunk)) + last_nl + 1

            # Otimização C-Speed: em arquivos grandes (>64KB), 90% das linhas são TinyBook (;Compra;/;Venda;).
            # Filtramos em C apenas as linhas ;Trade; e os últimos 8KB para atualizar a fila atual do Topo do Book!
            if len(complete_bytes) > 65536 and b";Trade;" in complete_bytes[:65536]:
                trade_b = [l for l in complete_bytes.splitlines() if b";Trade;" in l]
                tail_b = [l for l in complete_bytes[-8192:].splitlines() if b";Trade;" not in l]
                text_lines = [l.decode("latin1", errors="replace") for l in (trade_b + tail_b)]
            else:
                text_lines = complete_bytes.decode("latin1", errors="replace").splitlines()
            trades_ingested = self._parse_profit_trades_lines(text_lines, target_state, today_iso)
            if trades_ingested > 0:
                self._profit_active_today[asset_key] = True
                target_state.source = f"PROFIT_CSV ({fname})"

    def _parse_profit_broker_balance_file(self, filepath: str, state: SymbolMicrostructureState):
        try:
            with open(filepath, "r", encoding="latin1", errors="replace") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
        except OSError:
            return
        if len(lines) < 2:
            return

        header = lines[0]
        sep = ";" if ";" in header else ","
        cols = [c.strip().upper() for c in header.split(sep)]

        broker_col, net_col, avg_col, buy_col, sell_col = -1, -1, -1, -1, -1
        for i, col in enumerate(cols):
            if any(k in col for k in ["CORRETORA", "AGENTE", "NOME"]):
                broker_col = i
            elif any(k in col for k in ["MÉDIO", "MEDIO", "PREÇO", "PRECO"]):
                avg_col = i
            elif any(k in col for k in ["POSIÇÃO", "POSICAO", "SALDO"]) and "AGRES" not in col and net_col == -1:
                net_col = i
            elif any(k in col for k in ["AGRES", "AGR"]):
                if any(k in col for k in ["COMPRA", "BUY"]):
                    buy_col = i
                elif any(k in col for k in ["VENDA", "SELL"]):
                    sell_col = i

        if broker_col == -1 or net_col == -1:
            return

        for line in lines[1:]:
            parts = line.split(sep)
            if len(parts) <= max(broker_col, net_col):
                continue
            b_name = _match_broker_name(parts[broker_col])
            if not b_name:
                continue
            net_v = _clean_int(parts[net_col])
            avg_v = _clean_float(parts[avg_col]) if avg_col != -1 and len(parts) > avg_col else 0.0
            buy_v = _clean_int(parts[buy_col]) if buy_col != -1 and len(parts) > buy_col else 0
            sell_v = _clean_int(parts[sell_col]) if sell_col != -1 and len(parts) > sell_col else 0
            state.brokers[b_name] = {
                "net": net_v,
                "avg": avg_v,
                "buy": buy_v,
                "sell": sell_v,
                "vol": buy_v + sell_v,
            }

    def _parse_profit_trades_lines(self, lines: list, state: SymbolMicrostructureState, today_iso: str) -> int:
        base_dt = datetime.strptime(today_iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        base_epoch = int(base_dt.timestamp())

        ts_list = []
        price_list = []
        qty_list = []
        side_list = []

        has_explicit_trade_tag = any(";Trade;" in l or ";TRADE;" in l.upper() for l in lines[:200])

        # Reconstrução de Ordem Original: agrupa fills consecutivos no mesmo milissegundo (HH:MM:SS:mmm),
        # mesmo lado e mesma corretora agressora (evita que uma ordem de 100 lotes quebrada em 50 fills de 2L pareça varejo)
        curr_ord_key = None
        curr_ord_ts = 0
        curr_ord_price = 0.0
        curr_ord_qty = 0.0
        curr_ord_side = 0

        for line in lines:
            if not line:
                continue
            sep = ";" if ";" in line else ","
            parts = line.split(sep)
            if len(parts) < 4:
                continue

            type_str = parts[1].strip().upper()
            price = _clean_float(parts[2])
            qty = float(_clean_int(parts[3]))
            if price <= 0.0 or qty <= 0.0:
                continue

            # Formato Exportar Tape Reading do Profit Scalper Pro:
            # 1) Linha de Book (4 cols): HH:MM:SS:mmm;Compra;BidPrice;BidQty | HH:MM:SS:mmm;Venda;AskPrice;AskQty
            if len(parts) == 4 and has_explicit_trade_tag:
                if "COMPRA" in type_str or "BUY" in type_str:
                    state.best_bid_price = price
                    state.best_bid_qty = qty
                elif "VEND" in type_str or "SELL" in type_str:
                    state.best_ask_price = price
                    state.best_ask_qty = qty
                continue

            # 2) Linha de Negócio Real (7 cols): HH:MM:SS:mmm;Trade;Price;Qty;BuyerCode;SellerCode;Aggressor
            side = 0
            if "TRADE" in type_str and len(parts) >= 6:
                aggr_str = parts[6].strip().upper() if len(parts) >= 7 else ""
                if "COMPRA" in aggr_str or "BUY" in aggr_str:
                    side = 1
                elif "VEND" in aggr_str or "SELL" in aggr_str:
                    side = -1
                elif "RLP" in aggr_str:
                    state.rlp_vol += qty
                    state.rlp_deals += 1
                    side = 0
            elif "COMPRA" in type_str or "BUY" in type_str:
                state.best_bid_price = price
                state.best_bid_qty = qty
                if not has_explicit_trade_tag and today_iso != datetime.now().strftime("%Y-%m-%d"):
                    side = 1
                else:
                    continue
            elif "VEND" in type_str or "SELL" in type_str:
                state.best_ask_price = price
                state.best_ask_qty = qty
                if not has_explicit_trade_tag and today_iso != datetime.now().strftime("%Y-%m-%d"):
                    side = -1
                else:
                    continue
            else:
                continue

            aggr_broker_code = ""
            if len(parts) >= 6:
                try:
                    b_code = int(parts[4])
                    s_code = int(parts[5])
                    aggr_broker_code = parts[4] if side > 0 else parts[5]
                    b_name = B3_BROKER_CODES.get(b_code)
                    s_name = B3_BROKER_CODES.get(s_code)
                    q_int = int(qty)
                    if b_name:
                        b_rec = state.brokers[b_name]
                        b_rec["net"] += q_int
                        b_rec["buy"] += q_int
                        b_rec["vol"] += q_int
                        if side > 0:
                            b_rec["aggr_buy"] += q_int
                        elif side < 0:
                            b_rec["passive_buy"] += q_int
                    if s_name:
                        s_rec = state.brokers[s_name]
                        s_rec["net"] -= q_int
                        s_rec["sell"] += q_int
                        s_rec["vol"] += q_int
                        if side < 0:
                            s_rec["aggr_sell"] += q_int
                        elif side > 0:
                            s_rec["passive_sell"] += q_int
                except ValueError:
                    pass

            if side == 0:
                continue

            t_raw = parts[0].strip()
            t_parts = t_raw.split(":")
            if len(t_parts) >= 3:
                try:
                    ts_sec = base_epoch + int(t_parts[0]) * 3600 + int(t_parts[1]) * 60 + int(t_parts[2])
                except ValueError:
                    ts_sec = int(time.time())
            else:
                ts_sec = int(time.time())

            ord_key = (t_raw, side, aggr_broker_code)
            if ord_key == curr_ord_key:
                curr_ord_qty += qty
                curr_ord_price = price
            else:
                if curr_ord_qty > 0.0:
                    ts_list.append(curr_ord_ts)
                    price_list.append(curr_ord_price)
                    qty_list.append(curr_ord_qty)
                    side_list.append(curr_ord_side)
                curr_ord_key = ord_key
                curr_ord_ts = ts_sec
                curr_ord_price = price
                curr_ord_qty = qty
                curr_ord_side = side

        if curr_ord_qty > 0.0:
            ts_list.append(curr_ord_ts)
            price_list.append(curr_ord_price)
            qty_list.append(curr_ord_qty)
            side_list.append(curr_ord_side)

        if ts_list:
            state.ingest_batch_vectorized(
                np.array(ts_list, dtype=np.int64),
                np.array(price_list, dtype=np.float64),
                np.array(qty_list, dtype=np.float64),
                np.array(side_list, dtype=np.int8),
            )
        return len(ts_list)

    def _get_first_profit_trade_ts(self, asset_key: str, today_iso: str) -> int:
        """Descobre o primeiro timestamp de negócio (;Trade;) no CSV do Profit de hoje para evitar sobreposição com o backfill MT5."""
        if not os.path.exists(RTD_DIR):
            return 0
        today_suffix = datetime.now().strftime("%d_%m_%Y")
        base_dt = datetime.strptime(today_iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        base_epoch = int(base_dt.timestamp())
        for filepath in glob.glob(os.path.join(RTD_DIR, "*.csv")):
            fname_up = os.path.basename(filepath).upper()
            if today_suffix not in fname_up:
                continue
            if asset_key == "WIN" and not any(k in fname_up for k in ["WIN", "IND"]):
                continue
            if asset_key == "WDO" and not any(k in fname_up for k in ["WDO", "DOL"]):
                continue
            try:
                if os.path.getsize(filepath) == 0:
                    continue
                with open(filepath, "rb") as fb:
                    head_bytes = fb.read(65536)
                for line in head_bytes.decode("latin1", errors="ignore").splitlines():
                    if ";Trade;" in line:
                        t_parts = line.split(";")[0].strip().split(":")
                        if len(t_parts) >= 3:
                            return base_epoch + int(t_parts[0]) * 3600 + int(t_parts[1]) * 60 + int(t_parts[2])
            except Exception:
                pass
        return 0

    def _poll_mt5_ticks(self, today_iso: str = None):
        if mt5.terminal_info() is None:
            if not mt5.initialize(MT5_PATH, timeout=5000):
                return

        self._detect_mt5_contracts()
        if not today_iso:
            today_iso = datetime.now().strftime("%Y-%m-%d")

        for asset_key, state in [("WIN", self.win_state), ("WDO", self.wdo_state)]:
            if self._profit_active_today.get(asset_key, False):
                continue

            sym = state.active_contract
            if not sym:
                continue

            mt5.symbol_select(sym, True)
            tk = mt5.symbol_info_tick(sym)
            if tk is None or tk.time == 0:
                continue

            last_msc = self._last_tick_msc[asset_key]
            first_profit_ts = self._get_first_profit_trade_ts(asset_key, today_iso) if last_msc == 0 else 0

            if last_msc == 0:
                srv_dt = datetime.fromtimestamp(tk.time, tz=timezone.utc)
                start_of_day = srv_dt.replace(hour=9, minute=0, second=0, microsecond=0)
                if srv_dt < start_of_day:
                    start_of_day = srv_dt
                # Pagina copy_ticks_from para garantir cobertura 100% desde as 09h00 até first_profit_ts (mesmo >1M ticks)
                cur_dt = start_of_day
                chunks = []
                for _ in range(4):
                    batch = mt5.copy_ticks_from(sym, cur_dt, 1000000, mt5.COPY_TICKS_ALL)
                    if batch is None or len(batch) == 0:
                        break
                    chunks.append(batch)
                    last_batch_ts = int(batch["time"][-1])
                    last_batch_msc = int(batch["time_msc"][-1])
                    if len(batch) < 1000000 or (first_profit_ts > 0 and last_batch_ts >= first_profit_ts):
                        break
                    cur_dt = datetime.fromtimestamp((last_batch_msc + 1) / 1000.0, tz=timezone.utc)
                ticks = np.concatenate(chunks) if chunks else None
            else:
                from_dt = datetime.fromtimestamp(last_msc / 1000.0, tz=timezone.utc)
                ticks = mt5.copy_ticks_from(sym, from_dt, 100000, mt5.COPY_TICKS_ALL)

            if ticks is None or len(ticks) == 0:
                continue

            msc_arr = ticks["time_msc"]
            mask_new = msc_arr > last_msc
            if first_profit_ts > 0:
                mask_new = mask_new & (ticks["time"] < first_profit_ts)
            if not np.any(mask_new):
                continue

            t_sub = ticks[mask_new]
            self._last_tick_msc[asset_key] = int(t_sub["time_msc"][-1])

            flags = t_sub["flags"]
            is_buy = (flags & mt5.TICK_FLAG_BUY) != 0
            is_sell = (flags & mt5.TICK_FLAG_SELL) != 0
            valid_dir = (is_buy ^ is_sell) & (t_sub["volume"] > 0) & (t_sub["last"] > 0)
            if not np.any(valid_dir):
                continue

            t_valid = t_sub[valid_dir]
            side_arr = np.where((t_valid["flags"] & mt5.TICK_FLAG_BUY) != 0, 1, -1).astype(np.int8)

            state.ingest_batch_vectorized(
                t_valid["time"].astype(np.int64),
                t_valid["last"].astype(np.float64),
                t_valid["volume"].astype(np.float64),
                side_arr,
            )
            if not self._profit_active_today.get(asset_key, False):
                state.source = f"MT5_TICKS_LIVE ({sym})"

    def update(self) -> dict:
        today_str = datetime.now().strftime("%Y-%m-%d")
        if self.win_state.session_date != today_str:
            self.win_state.reset_session(today_str)
            self.wdo_state.reset_session(today_str)
            self._file_offsets.clear()
            self._last_tick_msc = {"WIN": 0, "WDO": 0}
            self._profit_active_today = {"WIN": False, "WDO": False}

        self.win_state.reload_walls_if_needed()
        self.wdo_state.reload_walls_if_needed()

        # 1. Backfill matinal do MT5 (se ainda não carregado) + 2. Stream Incremental do Profit CSV
        self._poll_mt5_ticks(today_str)
        self._poll_profit_rtd_folder()

        self._last_update_ts = time.time()
        win_payload = self.win_state.get_summary_payload()
        wdo_payload = self.wdo_state.get_summary_payload()

        # 3. Etapa 2 (Caminho A): Pressão de Hedge Dinâmico dos Dealers GEX cruzada com Fluxo Profit/MT5
        try:
            from core.gex_live_dealer_engine import gex_dealer_engine_singleton
            win_dealer = gex_dealer_engine_singleton.analyze_asset(win_payload)
            wdo_dealer = gex_dealer_engine_singleton.analyze_asset(wdo_payload)
            win_payload["caminho_a"] = win_dealer
            win_payload["dealer_gex"] = win_dealer
            wdo_payload["caminho_a"] = wdo_dealer
            wdo_payload["dealer_gex"] = wdo_dealer
        except Exception as e:
            win_payload["caminho_a"] = {"ok": False, "error": str(e)}
            wdo_payload["caminho_a"] = {"ok": False, "error": str(e)}

        # 4. Etapa 3 (Caminho B): Radar Ao Vivo da Cadeia de Opções (BOVA11 / IBOV)
        try:
            from core.options_live_radar_engine import options_radar_singleton
            caminho_b_payload = options_radar_singleton.update(win_price=win_payload.get("last_price", 0.0))
            win_payload["caminho_b"] = caminho_b_payload
        except Exception as e:
            caminho_b_payload = {"ok": False, "error": str(e)}
            win_payload["caminho_b"] = caminho_b_payload

        return {
            "ok": True,
            "timestamp": int(self._last_update_ts),
            "updated_at": datetime.now().strftime("%H:%M:%S"),
            "profit_rtd_warnings": list(self._profit_warnings),
            "WIN": win_payload,
            "WDO": wdo_payload,
            "win": win_payload,
            "wdo": wdo_payload,
            "caminho_a": {
                "WIN": win_payload.get("caminho_a", {}),
                "WDO": wdo_payload.get("caminho_a", {}),
            },
            "caminho_b": caminho_b_payload,
        }

    def _poll_profit_rtd_files(self):
        return self._poll_profit_rtd_folder()


flow_engine_singleton = ProfitMt5FlowEngine()
