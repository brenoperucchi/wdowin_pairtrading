# -*- coding: utf-8 -*-
"""
core/options_live_radar_engine.py
=================================
Etapa 3 (Caminho B): Radar Ao Vivo da Cadeia de Opções (BOVA11 & IBOV) via MT5 + Profit RTD.

Física Operacional (Caminho B — Microestrutura Direta das Opções):
  1. Monitora em tempo real as séries ATM/OTM mais líquidas de Calls e Puts de BOVA11 (ex: BOVAK* / BOVAW*)
     e IBOV (IBOVK* / IBOVW*) diretamente via MetaTrader 5 (tick-by-tick com flags de agressão Buy/Sell)
     e arquivos CSV do ProfitChart na pasta RTD/ (quando exportados).
  2. Decompõe o fluxo de opções nos 4 Quadrantes Direcionais Reais (evitando a armadilha do volume bruto):
       - COMPRA AGRESSIVA DE CALL (+Call Buy)  -> Fluxo Altista  (Delta > 0)
       - VENDA AGRESSIVA DE PUT   (-Put Sell)  -> Fluxo Altista  (Delta > 0)
       - VENDA AGRESSIVA DE CALL  (-Call Sell) -> Fluxo Baixista (Delta < 0)
       - COMPRA AGRESSIVA DE PUT  (+Put Buy)   -> Fluxo Baixista (Delta < 0)
  3. Calcula em tempo real (Black-Scholes com taxa Selic e dias úteis até o vencimento):
       - Volatilidade Implícita (IV%) de cada strike (usando o Mid-Price do Book Ao Vivo: (Bid+Ask)/2).
       - IV ATM (Volatilidade Implícita no Dinheiro).
       - Skew de Volatilidade Implícita 25-Delta (IV_Put_OTM - IV_Call_OTM): mede se o institucional
         está encarecendo proteção de queda (Skew Positivo Alto) ou pagando caro por Calls (Call Squeeze).
       - Fluxo Equivalente em Delta (Delta-Adjusted Net Option Flow) para 5m, 15m, 60m e Sessão.
"""

import os
import glob
import math
import time
from datetime import datetime, timezone
import numpy as np
import MetaTrader5 as mt5

from core.config import MT5_PATH

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RTD_DIR = os.path.join(PROJECT_ROOT, "RTD")

# Taxa livre de risco anualizada (Selic / DI curto) para Black-Scholes de BOVA11
RISK_FREE_RATE = 0.1125


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_price_and_greeks(spot: float, strike: float, t_years: float, r: float, sigma: float, is_call: bool) -> tuple:
    """
    Retorna (price, delta, gamma, vega) via Black-Scholes para uma opção europeia/B3.
    """
    if spot <= 0.0 or strike <= 0.0 or t_years <= 1e-5 or sigma <= 1e-4:
        intrinsic = max(0.0, (spot - strike) if is_call else (strike - spot))
        delta = (1.0 if spot > strike else 0.0) if is_call else (-1.0 if spot < strike else 0.0)
        return intrinsic, delta, 0.0, 0.0

    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t

    nd1 = _norm_cdf(d1)
    nd2 = _norm_cdf(d2)
    npd1 = _norm_pdf(d1)
    disc = math.exp(-r * t_years)

    if is_call:
        price = spot * nd1 - strike * disc * nd2
        delta = nd1
    else:
        price = strike * disc * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
        delta = nd1 - 1.0

    gamma = npd1 / (spot * sigma * sqrt_t)
    vega = spot * npd1 * sqrt_t
    return price, delta, gamma, vega


def implied_vol_bs(target_price: float, spot: float, strike: float, t_years: float, r: float, is_call: bool) -> tuple:
    """
    Inverte Black-Scholes por Newton-Raphson + Bisseção híbrida em < 0,03 ms.
    Retorna (iv_decimal, delta, gamma).
    """
    if target_price <= 0.0 or spot <= 0.0 or strike <= 0.0 or t_years <= 1e-4:
        _, d, g, _ = bs_price_and_greeks(spot, strike, max(t_years, 1e-4), r, 0.22, is_call)
        return 0.0, d, g

    disc = math.exp(-r * t_years)
    intrinsic = max(0.0, (spot - strike * disc) if is_call else (strike * disc - spot))
    if target_price <= intrinsic + 0.005:
        _, d, g, _ = bs_price_and_greeks(spot, strike, t_years, r, 0.18, is_call)
        return 0.0, d, g

    low_vol, high_vol = 0.04, 1.50
    sigma = 0.24

    for _ in range(14):
        p, d, g, vega = bs_price_and_greeks(spot, strike, t_years, r, sigma, is_call)
        diff = p - target_price
        if abs(diff) < 1e-4:
            return sigma, d, g
        if diff > 0:
            high_vol = sigma
        else:
            low_vol = sigma

        if vega > 1e-5:
            cand = sigma - diff / vega
            if low_vol < cand < high_vol:
                sigma = cand
            else:
                sigma = 0.5 * (low_vol + high_vol)
        else:
            sigma = 0.5 * (low_vol + high_vol)

    _, d, g, _ = bs_price_and_greeks(spot, strike, t_years, r, sigma, is_call)
    return sigma, d, g


class OptionTickerState:
    """Estado incremental de uma série de opção individual (ex: BOVAK176 ou BOVAW170)."""

    def __init__(self, symbol: str, is_call: bool, strike: float, exp_ts: int, underlying: str = "BOVA11"):
        self.symbol = symbol
        self.is_call = is_call
        self.option_type = "CALL" if is_call else "PUT"
        self.strike = strike
        self.exp_ts = exp_ts
        self.underlying = underlying

        self.bid = 0.0
        self.ask = 0.0
        self.last = 0.0
        self.session_deals_mt5 = 0
        self.iv_pct = 0.0
        self.delta = 0.5 if is_call else -0.5
        self.gamma = 0.0

        self.buy_vol = 0.0
        self.sell_vol = 0.0
        self.buy_notional = 0.0
        self.sell_notional = 0.0
        self.buy_deals = 0
        self.sell_deals = 0
        self.last_tick_msc = 0

        # Histórico compacto de negócios para cálculo de janelas (5m, 15m, 60m) e barras M5:
        # Armazenado como listas que são convertidas/filtradas rapidamente
        self.ts_arr = np.empty(0, dtype=np.int64)
        self.vol_arr = np.empty(0, dtype=np.float64)
        self.side_arr = np.empty(0, dtype=np.int8)
        self.price_arr = np.empty(0, dtype=np.float64)

    def ingest_ticks(self, ts_new: np.ndarray, price_new: np.ndarray, vol_new: np.ndarray, side_new: np.ndarray):
        if len(ts_new) == 0:
            return
        is_b = side_new > 0
        is_s = side_new < 0

        self.buy_vol += float(np.sum(vol_new[is_b]))
        self.sell_vol += float(np.sum(vol_new[is_s]))
        self.buy_notional += float(np.sum(vol_new[is_b] * price_new[is_b]))
        self.sell_notional += float(np.sum(vol_new[is_s] * price_new[is_s]))
        self.buy_deals += int(np.sum(is_b))
        self.sell_deals += int(np.sum(is_s))
        self.last = float(price_new[-1])

        self.ts_arr = np.concatenate([self.ts_arr, ts_new])
        self.vol_arr = np.concatenate([self.vol_arr, vol_new])
        self.side_arr = np.concatenate([self.side_arr, side_new])
        self.price_arr = np.concatenate([self.price_arr, price_new])


class OptionsLiveRadarEngine:
    """
    Motor da Etapa 3 (Caminho B): Monitora em tempo real a grade de opções de BOVA11 e IBOV,
    extraindo Pressão Call vs. Put, Fluxo Ajustado por Delta e Skew de Volatilidade Implícita.
    """

    def __init__(self):
        self.session_date = ""
        self.bova_spot = 0.0
        self.bova_open = 0.0
        self.bova_vwap = 0.0
        self.win_ibov_ratio = 1025.0  # Fator de conversão aproximado Strike BOVA11 -> WIN
        self.options: dict[str, OptionTickerState] = {}
        self._discovery_done_ts = 0.0
        self._profit_file_offsets = {}
        self._last_update_ts = 0.0
        self._cached_payload = None

    def reset_session(self, new_date: str):
        self.session_date = new_date
        self.options.clear()
        self._discovery_done_ts = 0.0
        self._profit_file_offsets.clear()
        self._cached_payload = None

    def _update_bova11_spot(self):
        mt5.symbol_select("BOVA11", True)
        tk = mt5.symbol_info_tick("BOVA11")
        info = mt5.symbol_info("BOVA11")
        if tk and tk.last > 0:
            self.bova_spot = float(tk.last)
        elif info and info.last > 0:
            self.bova_spot = float(info.last)
        elif self.bova_spot <= 0:
            self.bova_spot = 174.20

        if info and info.session_open > 0:
            self.bova_open = float(info.session_open)
        elif self.bova_open <= 0:
            self.bova_open = self.bova_spot

        if info and info.session_aw > 0:
            self.bova_vwap = float(info.session_aw)
        else:
            self.bova_vwap = self.bova_spot

    def _discover_liquid_options(self):
        """
        Descobre e habilita no Market Watch do MT5 as opções mais líquidas de BOVA11 ao redor do Spot
        (Calls e Puts com strikes entre -8% e +8% do Spot), além das séries ativas de IBOV.
        Reexecuta a cada 180 segundos para capturar novas séries que ganhem liquidez no dia.
        """
        now = time.time()
        if self.options and (now - self._discovery_done_ts) < 180.0:
            return

        self._update_bova11_spot()
        spot = self.bova_spot
        min_k = spot * 0.91
        max_k = spot * 1.09

        syms = mt5.symbols_get("BOVA*") or []
        now_epoch = int(now)

        # Filtra opções de BOVA11 não vencidas na faixa de strike relevante
        candidates = []
        for s in syms:
            if s.name == "BOVA11":
                continue
            k = float(s.option_strike)
            if min_k <= k <= max_k and s.expiration_time > now_epoch:
                # Prioriza o vencimento mensal principal (entre 2 e 38 dias corridos) e strikes inteiros
                days_to_exp = (s.expiration_time - now_epoch) / 86400.0
                if 2.0 <= days_to_exp <= 38.0 and abs(k - round(k)) < 0.05:
                    candidates.append(s)

        # Habilita no Market Watch as candidatas mais próximas do dinheiro (±11 reais do spot)
        near_atm = [s for s in candidates if abs(float(s.option_strike) - spot) <= 11.5]
        for s in near_atm:
            if not s.select:
                mt5.symbol_select(s.name, True)

        # Aguarda breve sincronismo caso símbolos novos tenham acabado de ser selecionados
        refreshed = []
        for s in near_atm:
            info = mt5.symbol_info(s.name)
            if info and (info.session_deals > 0 or (info.bid > 0 and info.ask > 0)):
                refreshed.append(info)

        # Separa Calls (option_right == 0) e Puts (option_right == 1) e escolhe as Top 14 de cada lado por liquidez
        calls = [x for x in refreshed if x.option_right == 0]
        puts = [x for x in refreshed if x.option_right == 1]

        calls.sort(key=lambda x: (x.session_deals, x.session_volume), reverse=True)
        puts.sort(key=lambda x: (x.session_deals, x.session_volume), reverse=True)

        selected_infos = calls[:14] + puts[:14]
        for info in selected_infos:
            if info.name not in self.options:
                self.options[info.name] = OptionTickerState(
                    symbol=info.name,
                    is_call=(info.option_right == 0),
                    strike=float(info.option_strike),
                    exp_ts=int(info.expiration_time),
                    underlying="BOVA11",
                )

        self._discovery_done_ts = now

    def _poll_mt5_option_ticks(self, today_iso: str):
        base_dt = datetime.strptime(today_iso, "%Y-%m-%d").replace(hour=9, minute=0, second=0, tzinfo=timezone.utc)
        now_epoch = time.time()

        for sym, st in self.options.items():
            info = mt5.symbol_info(sym)
            prev_deals_mt5 = st.session_deals_mt5
            if info is not None:
                st.bid = float(info.bid)
                st.ask = float(info.ask)
                if info.last > 0:
                    st.last = float(info.last)
                st.session_deals_mt5 = int(info.session_deals)

            # Calcula Volatilidade Implícita e Gregas usando o Mid-Price do Book (ou Last se book fechado)
            mid_price = 0.5 * (st.bid + st.ask) if (st.bid > 0 and st.ask > 0 and st.ask >= st.bid) else st.last
            t_years = max((st.exp_ts - now_epoch) / (365.25 * 86400.0), 1.0 / 365.25)
            iv_dec, delta, gamma = implied_vol_bs(
                target_price=mid_price,
                spot=self.bova_spot,
                strike=st.strike,
                t_years=t_years,
                r=RISK_FREE_RATE,
                is_call=st.is_call,
            )
            if iv_dec > 0:
                st.iv_pct = round(iv_dec * 100.0, 2)
            st.delta = round(delta, 4)
            st.gamma = round(gamma, 4)

            # Otimização: após o backfill inicial (last_tick_msc > 0), só chama copy_ticks_from se houve novo negócio!
            if st.last_tick_msc > 0 and st.session_deals_mt5 == prev_deals_mt5:
                continue

            # Busca novos ticks desde last_tick_msc
            if st.last_tick_msc == 0:
                ticks = mt5.copy_ticks_from(sym, base_dt, 100000, mt5.COPY_TICKS_ALL)
            else:
                from_dt = datetime.fromtimestamp(st.last_tick_msc / 1000.0, tz=timezone.utc)
                ticks = mt5.copy_ticks_from(sym, from_dt, 50000, mt5.COPY_TICKS_ALL)

            if ticks is None or len(ticks) == 0:
                continue

            msc_arr = ticks["time_msc"]
            mask_new = msc_arr > st.last_tick_msc
            if not np.any(mask_new):
                continue

            t_sub = ticks[mask_new]
            st.last_tick_msc = int(t_sub["time_msc"][-1])

            flags = t_sub["flags"]
            is_buy = (flags & mt5.TICK_FLAG_BUY) != 0
            is_sell = (flags & mt5.TICK_FLAG_SELL) != 0
            valid = (is_buy ^ is_sell) & (t_sub["volume"] > 0) & (t_sub["last"] > 0)
            if not np.any(valid):
                continue

            t_val = t_sub[valid]
            side_arr = np.where((t_val["flags"] & mt5.TICK_FLAG_BUY) != 0, 1, -1).astype(np.int8)
            st.ingest_ticks(
                t_val["time"].astype(np.int64),
                t_val["last"].astype(np.float64),
                t_val["volume"].astype(np.float64),
                side_arr,
            )

    def _compute_window_option_flow(self, cutoff_ts: int) -> dict:
        """
        Calcula o fluxo dos 4 quadrantes (Call Buy/Sell, Put Buy/Sell) e o Fluxo Equivalente em Delta
        para todos os negócios ocorridos desde `cutoff_ts` (0 = sessão inteira).
        """
        call_buy_vol = 0.0
        call_sell_vol = 0.0
        put_buy_vol = 0.0
        put_sell_vol = 0.0

        call_buy_fin = 0.0
        call_sell_fin = 0.0
        put_buy_fin = 0.0
        put_sell_fin = 0.0

        net_delta_equiv_shares = 0.0

        for st in self.options.values():
            if len(st.ts_arr) == 0:
                continue
            if cutoff_ts <= 0:
                vols = st.vol_arr
                sides = st.side_arr
                prices = st.price_arr
            else:
                idx = np.searchsorted(st.ts_arr, cutoff_ts, side="left")
                if idx >= len(st.ts_arr):
                    continue
                vols = st.vol_arr[idx:]
                sides = st.side_arr[idx:]
                prices = st.price_arr[idx:]

            is_b = sides > 0
            is_s = sides < 0
            b_v = float(np.sum(vols[is_b]))
            s_v = float(np.sum(vols[is_s]))
            b_f = float(np.sum(vols[is_b] * prices[is_b]))
            s_f = float(np.sum(vols[is_s] * prices[is_s]))

            net_opt = b_v - s_v
            # Delta equivalente: se compram Call (delta > 0), fluxo é +net_opt * delta.
            # Se compram Put (delta < 0), fluxo é +net_opt * delta (negativo = baixista!).
            net_delta_equiv_shares += net_opt * st.delta

            if st.is_call:
                call_buy_vol += b_v
                call_sell_vol += s_v
                call_buy_fin += b_f
                call_sell_fin += s_f
            else:
                put_buy_vol += b_v
                put_sell_vol += s_v
                put_buy_fin += b_f
                put_sell_fin += s_f

        call_net_vol = call_buy_vol - call_sell_vol
        put_net_vol = put_buy_vol - put_sell_vol

        # Fluxo Altista em Opções = Compra Agressiva de Call + Venda Agressiva de Put
        bullish_opt_vol = call_buy_vol + put_sell_vol
        # Fluxo Baixista em Opções = Compra Agressiva de Put + Venda Agressiva de Call
        bearish_opt_vol = put_buy_vol + call_sell_vol
        tot_opt_vol = bullish_opt_vol + bearish_opt_vol

        bull_bear_imbalance_pct = (
            ((bullish_opt_vol - bearish_opt_vol) / tot_opt_vol) * 100.0 if tot_opt_vol > 0 else 0.0
        )

        return {
            "call_buy_vol": round(call_buy_vol, 0),
            "call_sell_vol": round(call_sell_vol, 0),
            "call_net_delta": round(call_net_vol, 0),
            "put_buy_vol": round(put_buy_vol, 0),
            "put_sell_vol": round(put_sell_vol, 0),
            "put_net_delta": round(put_net_vol, 0),
            "call_net_notional_brl": round(call_buy_fin - call_sell_fin, 2),
            "put_net_notional_brl": round(put_buy_fin - put_sell_fin, 2),
            "bullish_option_vol": round(bullish_opt_vol, 0),
            "bearish_option_vol": round(bearish_opt_vol, 0),
            "net_directional_vol": round(bullish_opt_vol - bearish_opt_vol, 0),
            "bull_bear_imbalance_pct": round(bull_bear_imbalance_pct, 1),
            "net_delta_equivalent": round(net_delta_equiv_shares, 0),
        }

    def _compute_volatility_surface_metrics(self) -> dict:
        """
        Extrai da cadeia ao vivo:
          - IV ATM (média ponderada das opções com |Delta| entre 0.40 e 0.60)
          - IV Put 25-Delta (Puts OTM com Delta entre -0.38 e -0.15)
          - IV Call 25-Delta (Calls OTM com Delta entre +0.15 e +0.38)
          - Skew 25-Delta = IV_Put_25D - IV_Call_25D
        """
        atm_ivs = []
        call_25d_ivs = []
        put_25d_ivs = []

        for st in self.options.values():
            if st.iv_pct <= 2.0 or st.iv_pct >= 120.0:
                continue
            abs_d = abs(st.delta)
            w = max(1.0, float(st.session_deals_mt5))
            if 0.38 <= abs_d <= 0.62:
                atm_ivs.append((st.iv_pct, w))
            elif st.is_call and 0.14 <= st.delta < 0.38:
                call_25d_ivs.append((st.iv_pct, w))
            elif (not st.is_call) and -0.38 < st.delta <= -0.14:
                put_25d_ivs.append((st.iv_pct, w))

        def _wavg(pairs):
            if not pairs:
                return 0.0
            num = sum(v * w for v, w in pairs)
            den = sum(w for _, w in pairs)
            return num / den if den > 0 else 0.0

        atm_iv = _wavg(atm_ivs)
        call_25d = _wavg(call_25d_ivs) or atm_iv
        put_25d = _wavg(put_25d_ivs) or atm_iv
        skew_25d = (put_25d - call_25d) if (put_25d > 0 and call_25d > 0) else 0.0

        if skew_25d >= 2.5:
            skew_regime = "PROTECAO_CARA_BAIXISTA (Puts OTM com premio elevado)"
        elif skew_25d <= -1.0:
            skew_regime = "APETITE_CALL_ALTISTA (Calls OTM mais caras que Puts)"
        else:
            skew_regime = "SKEW_NEUTRO_NORMAL"

        return {
            "atm_iv_pct": round(atm_iv, 2),
            "put_25d_iv_pct": round(put_25d, 2),
            "call_25d_iv_pct": round(call_25d, 2),
            "skew_25d_pct": round(skew_25d, 2),
            "skew_regime": skew_regime,
        }

    def _build_m5_options_series(self, today_iso: str) -> list:
        """
        Constrói a série histórica M5 intradiária do fluxo de opções (Call Net Delta, Put Net Delta
        e Saldo Direcional Equivalente Acumulado).
        """
        all_ts = []
        all_SignedBull = []
        all_CallNet = []
        all_PutNet = []

        for st in self.options.values():
            if len(st.ts_arr) == 0:
                continue
            signed_vol = st.vol_arr * st.side_arr.astype(np.float64)
            all_ts.append(st.ts_arr)
            if st.is_call:
                all_CallNet.append(signed_vol)
                all_PutNet.append(np.zeros_like(signed_vol))
                all_SignedBull.append(signed_vol * abs(st.delta))
            else:
                all_CallNet.append(np.zeros_like(signed_vol))
                all_PutNet.append(signed_vol)
                # Compra de Put (+signed_vol) é Baixista (-), Venda de Put (-signed_vol) é Altista (+)
                all_SignedBull.append(-signed_vol * abs(st.delta))

        if not all_ts:
            return []

        ts_cat = np.concatenate(all_ts)
        c_cat = np.concatenate(all_CallNet)
        p_cat = np.concatenate(all_PutNet)
        b_cat = np.concatenate(all_SignedBull)

        order = np.argsort(ts_cat, kind="mergesort")
        ts_cat = ts_cat[order]
        c_cat = c_cat[order]
        p_cat = p_cat[order]
        b_cat = b_cat[order]

        m5_keys = (ts_cat // 300) * 300
        uniq_m5, idx_start = np.unique(m5_keys, return_index=True)

        c_bar = np.add.reduceat(c_cat, idx_start)
        p_bar = np.add.reduceat(p_cat, idx_start)
        b_bar = np.add.reduceat(b_cat, idx_start)

        cum_c = 0.0
        cum_p = 0.0
        cum_b = 0.0
        series = []
        for i in range(len(uniq_m5)):
            m5_ts = int(uniq_m5[i])
            cum_c += float(c_bar[i])
            cum_p += float(p_bar[i])
            cum_b += float(b_bar[i])
            dt_str = datetime.fromtimestamp(m5_ts, tz=timezone.utc).strftime("%H:%M")
            series.append({
                "timestamp": m5_ts,
                "time": dt_str,
                "call_net_bar": round(float(c_bar[i]), 0),
                "put_net_bar": round(float(p_bar[i]), 0),
                "cum_call_net": round(cum_c, 0),
                "cum_put_net": round(cum_p, 0),
                "cum_delta_equivalent": round(cum_b, 0),
            })
        return series[-60:]

    def update(self, win_price: float = 0.0) -> dict:
        if mt5.terminal_info() is None:
            mt5.initialize(MT5_PATH, timeout=5000)

        today_iso = datetime.now().strftime("%Y-%m-%d")
        if self.session_date != today_iso:
            self.reset_session(today_iso)

        self._discover_liquid_options()
        self._update_bova11_spot()
        if win_price > 0 and self.bova_spot > 0:
            self.win_ibov_ratio = win_price / self.bova_spot

        self._poll_mt5_option_ticks(today_iso)

        # Timestamp mais recente observado nas opções
        latest_ts = max((int(st.ts_arr[-1]) for st in self.options.values() if len(st.ts_arr) > 0), default=0)

        flow_session = self._compute_window_option_flow(0)
        flow_5m = self._compute_window_option_flow(latest_ts - 300 if latest_ts > 0 else 0)
        flow_15m = self._compute_window_option_flow(latest_ts - 900 if latest_ts > 0 else 0)
        flow_60m = self._compute_window_option_flow(latest_ts - 3600 if latest_ts > 0 else 0)

        vol_surf = self._compute_volatility_surface_metrics()

        # Put/Call Ratios
        tot_call_vol = flow_session["call_buy_vol"] + flow_session["call_sell_vol"]
        tot_put_vol = flow_session["put_buy_vol"] + flow_session["put_sell_vol"]
        pcr_total = (tot_put_vol / tot_call_vol) if tot_call_vol > 0 else 0.0
        pcr_aggr_buy = (
            (flow_session["put_buy_vol"] / flow_session["call_buy_vol"])
            if flow_session["call_buy_vol"] > 0
            else 0.0
        )

        # Score Composto Caminho B (-100 a +100):
        # 1. Desequilíbrio Direcional 5m (30%), 15m (35%) e Sessão (20%)
        # 2. Penalidade/Bônus de Skew IV (15%)
        s_5m = np.clip(flow_5m["bull_bear_imbalance_pct"] * 2.2, -100.0, 100.0)
        s_15m = np.clip(flow_15m["bull_bear_imbalance_pct"] * 2.2, -100.0, 100.0)
        s_sess = np.clip(flow_session["bull_bear_imbalance_pct"] * 2.2, -100.0, 100.0)
        s_skew = np.clip(-vol_surf["skew_25d_pct"] * 12.0, -100.0, 100.0)

        options_pressure_score = float(np.clip(
            0.30 * s_5m + 0.35 * s_15m + 0.20 * s_sess + 0.15 * s_skew,
            -100.0, 100.0
        ))

        if options_pressure_score >= 25.0:
            verdict = "FLUXO DE OPCOES ALTISTA (Compra de Call / Venda de Put)"
        elif options_pressure_score <= -25.0:
            verdict = "FLUXO DE OPCOES BAIXISTA (Venda de Call / Compra de Put)"
        else:
            verdict = "OPCOES EM EQUILIBRIO / TRAVA DE VOLATILIDADE"

        # Ranking das séries mais ativas para exibição na grade do terminal
        chain_rows = []
        for st in self.options.values():
            tot_v = st.buy_vol + st.sell_vol
            net_v = st.buy_vol - st.sell_vol
            imb = ((net_v / tot_v) * 100.0) if tot_v > 0 else 0.0
            # Impacto direcional no índice: +1 se fluxo líquida nessa série empurra o índice para cima, -1 para baixo
            dir_impact = net_v * st.delta
            chain_rows.append({
                "symbol": st.symbol,
                "type": st.option_type,
                "strike_bova": st.strike,
                "equiv_win_strike": round(st.strike * self.win_ibov_ratio, 0),
                "bid": round(st.bid, 2),
                "ask": round(st.ask, 2),
                "last": round(st.last, 2),
                "iv_pct": st.iv_pct,
                "delta": st.delta,
                "gamma": st.gamma,
                "deals": st.buy_deals + st.sell_deals,
                "buy_vol": round(st.buy_vol, 0),
                "sell_vol": round(st.sell_vol, 0),
                "net_aggr_vol": round(net_v, 0),
                "imbalance_pct": round(imb, 1),
                "delta_equiv_flow": round(dir_impact, 0),
                "directional_role": (
                    "PRESSAO_ALTISTA" if dir_impact > 5000
                    else ("PRESSAO_BAIXISTA" if dir_impact < -5000 else "NEUTRO")
                ),
            })

        chain_rows.sort(key=lambda x: x["deals"], reverse=True)

        self._last_update_ts = time.time()
        self._cached_payload = {
            "ok": True,
            "session_date": self.session_date,
            "updated_at": datetime.now().strftime("%H:%M:%S"),
            "bova11": {
                "spot": round(self.bova_spot, 2),
                "open": round(self.bova_open, 2),
                "vwap": round(self.bova_vwap, 2),
                "change_pct": round(((self.bova_spot - self.bova_open) / self.bova_open) * 100.0, 2) if self.bova_open > 0 else 0.0,
                "win_ibov_ratio": round(self.win_ibov_ratio, 2),
            },
            "options_compass": {
                "score": round(options_pressure_score, 1),
                "verdict": verdict,
                "pcr_total_volume": round(pcr_total, 2),
                "pcr_aggressive_buy": round(pcr_aggr_buy, 2),
                "monitored_series_count": len(self.options),
            },
            "volatility_surface": vol_surf,
            "windows": {
                "5m": flow_5m,
                "15m": flow_15m,
                "60m": flow_60m,
                "session": flow_session,
            },
            "most_active_options": chain_rows[:16],
            "m5_options_series": self._build_m5_options_series(today_iso),
        }
        return self._cached_payload


options_radar_singleton = OptionsLiveRadarEngine()
