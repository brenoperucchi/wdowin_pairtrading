# -*- coding: utf-8 -*-
"""
core/gex_live_dealer_engine.py
==============================
Etapa 2 (Caminho A): Motor Intradiário de Pressão de Hedge dos Dealers (Black-76 / GEX)
e Matriz de Confluência com o Fluxo Institucional do ProfitChart & MT5 (WIN e WDO).

Física Operacional (Market Making de Opções):
  - Os Dealers (Market Makers) ajustam continuamente sua posição no contrato futuro (WIN / WDO)
    para neutralizar a variação do Delta da carteira de opções conforme o preço S(t) se move.
  - Taxa de Hedge por variação dS:
      d(Hedge_Futuros) / dS = - Gamma_Dealer(S)
    * Em GAMMA NEGATIVO (Gamma_Dealer < 0, abaixo do GammaFlip):
        - Se o preço SOBE (dS > 0) -> Dealers precisam COMPRAR futuros (Aceleração / Gamma Squeeze).
        - Se o preço CAI  (dS < 0) -> Dealers precisam VENDER futuros (Aceleração / Gamma Drop).
    * Em GAMMA POSITIVO (Gamma_Dealer > 0, acima do GammaFlip):
        - Se o preço SOBE (dS > 0) -> Dealers precisam VENDER futuros (Amortecimento / Defesa de Topo).
        - Se o preço CAI  (dS < 0) -> Dealers precisam COMPRAR futuros (Amortecimento / Defesa de Suporte).
"""

from datetime import datetime, timezone
import os
import glob
import json
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEX_DATA_DIR = os.path.join(PROJECT_ROOT, "gex", "data")


class AssetGexCurveModel:
    """
    Mantém em memória os strikes e a exposição Gamma (GEX) oficial do dia para um ativo ('WIN' ou 'WDO'),
    permitindo avaliar GEX(S), elasticidade de hedge e fluxo acumulado dos Dealers em < 0,1 ms.
    """

    def __init__(self, asset: str):
        self.asset = asset.upper()
        self.cache_file = os.path.join(
            GEX_DATA_DIR,
            "win_walls_cache.json" if self.asset == "WIN" else "usd_brl_walls_cache.json",
        )
        self.ref_date = ""
        self.updated_at = ""
        self.gamma_flip = 0.0
        self.max_gamma_price = 0.0
        self.max_gamma_val = 0.0
        self.min_gamma_price = 0.0
        self.min_gamma_val = 0.0
        self.factor = 1.0
        self.strikes = np.array([], dtype=np.float64)
        self.strike_gex = np.array([], dtype=np.float64)
        self.strike_widths = np.array([], dtype=np.int32)
        self.walls_raw = []
        self._last_mtime = 0.0
        self.reload_if_needed()

    def reload_if_needed(self):
        if not os.path.exists(self.cache_file):
            return
        try:
            mtime = os.path.getmtime(self.cache_file)
            if mtime == self._last_mtime and len(self.strikes) > 0:
                return
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._last_mtime = mtime
        except Exception:
            return

        self.ref_date = data.get("ref_date", "")
        self.updated_at = data.get("updated_at", "")
        self.walls_raw = data.get("walls", [])

        s_list, g_list, w_list = [], [], []
        for w in self.walls_raw:
            wtype = w.get("type", "")
            price = float(w.get("price", 0.0))
            gex_v = float(w.get("gex", 0.0))
            width = int(w.get("width", 1))
            if wtype == "Wall" and price > 0:
                s_list.append(price)
                g_list.append(gex_v)
                w_list.append(width)
            elif wtype == "GammaFlip":
                self.gamma_flip = price
                self.factor = float(w.get("factor", 1.0))
            elif wtype == "MaxGamma":
                self.max_gamma_price = price
                self.max_gamma_val = gex_v
            elif wtype == "MinGamma":
                self.min_gamma_price = price
                self.min_gamma_val = gex_v

        if s_list:
            order = np.argsort(s_list)
            self.strikes = np.array(s_list, dtype=np.float64)[order]
            self.strike_gex = np.array(g_list, dtype=np.float64)[order]
            self.strike_widths = np.array(w_list, dtype=np.int32)[order]

    @classmethod
    def from_walls_list(cls, asset: str, session_date: str, all_walls: list):
        """Constrói um modelo GEX calibrado a partir da lista histórica de MagicWalls daquela data."""
        inst = cls.__new__(cls)
        inst.asset = asset.upper()
        inst.cache_file = ""
        inst.ref_date = session_date
        inst.updated_at = f"Histórico {session_date}"
        inst.gamma_flip = 0.0
        inst.max_gamma_price = 0.0
        inst.max_gamma_val = 0.0
        inst.min_gamma_price = 0.0
        inst.min_gamma_val = 0.0
        inst.factor = 1.0
        inst.walls_raw = list(all_walls or [])
        inst._last_mtime = 0.0

        for w in inst.walls_raw:
            wtype = w.get("type", "")
            p = float(w.get("price", 0.0))
            if wtype == "GammaFlip":
                inst.gamma_flip = p
            elif wtype == "MaxGamma":
                inst.max_gamma_price = p
            elif wtype == "MinGamma":
                inst.min_gamma_price = p

        unit_gex = 35e9 if inst.asset == "WIN" else 180e6
        s_list, g_list, w_list = [], [], []
        for w in inst.walls_raw:
            if w.get("type") == "Wall":
                p = float(w.get("price", 0.0))
                width = int(w.get("width", 1))
                if p > 0:
                    polarity = 1.0 if (inst.gamma_flip > 0 and p >= inst.gamma_flip) else -1.0
                    g_val = float(w.get("gex", polarity * width * unit_gex))
                    s_list.append(p)
                    g_list.append(g_val)
                    w_list.append(width)

        if s_list:
            order = np.argsort(s_list)
            inst.strikes = np.array(s_list, dtype=np.float64)[order]
            inst.strike_gex = np.array(g_list, dtype=np.float64)[order]
            inst.strike_widths = np.array(w_list, dtype=np.int32)[order]
        else:
            inst.strikes = np.array([], dtype=np.float64)
            inst.strike_gex = np.array([], dtype=np.float64)
            inst.strike_widths = np.array([], dtype=np.int32)
        return inst

    def evaluate_local_gex(self, spot_price: float) -> dict:
        """
        Avalia a exposição de Gamma Líquido (Net GEX) no preço atual S(t) usando interpolação
        por kernel Gaussiano Black-76 sobre os 16 strikes oficiais + âncoras Max/Min/Flip.
        """
        if spot_price <= 0.0 or len(self.strikes) == 0:
            return {
                "net_gex_raw": 0.0,
                "net_gex_formatted": "0.0",
                "gamma_Empty": True,
                "normalized_gamma_pct": 0.0,
                "macro_regime": "UNKNOWN",
                "local_regime": "UNKNOWN",
                "dealer_contracts_per_step": 0.0,
                "step_pts": 100.0 if self.asset == "WIN" else 10.0,
            }

        # Largura do kernel Black-76 entre strikes adjacentes (~1.100 pts no WIN, ~30 pts no WDO)
        sigma_pts = 1150.0 if self.asset == "WIN" else 30.0
        weights = np.exp(-0.5 * ((spot_price - self.strikes) / sigma_pts) ** 2)
        local_gex = float(np.sum(self.strike_gex * weights))

        # Escala de referência (maior Wall em módulo)
        max_abs_wall = float(np.max(np.abs(self.strike_gex))) if len(self.strike_gex) > 0 else 1.0
        if max_abs_wall <= 0:
            max_abs_wall = 1.0

        norm_gamma = float(np.clip((local_gex / max_abs_wall) * 100.0, -100.0, 100.0))

        macro_regime = (
            "POSITIVE_GAMMA"
            if (self.gamma_flip > 0 and spot_price >= self.gamma_flip)
            else "NEGATIVE_GAMMA"
        )
        local_regime = "POSITIVE_GAMMA" if local_gex >= 0 else "NEGATIVE_GAMMA"

        # Conversão física para Contratos Futuros de Hedge por passo de preço (100 pts WIN / 10 pts WDO):
        # No WIN, 100 Bilhões de GEX equivalem a ~4.500 mini-contratos de hedge a cada 100 pontos.
        # No WDO, 1 Bilhão de GEX equivale a ~1.200 mini-contratos de hedge a cada 10 pontos.
        if self.asset == "WIN":
            step_pts = 100.0
            contracts_per_step = abs(local_gex) / 1e9 * 45.0
            gex_fmt = f"{local_gex / 1e9:+.2f}B R$"
        else:
            step_pts = 10.0
            contracts_per_step = abs(local_gex) / 1e6 * 1.2
            gex_fmt = f"{local_gex / 1e6:+.1f}M US$"

        return {
            "net_gex_raw": local_gex,
            "net_gex_formatted": gex_fmt,
            "normalized_gamma_pct": round(norm_gamma, 1),
            "macro_regime": macro_regime,
            "local_regime": local_regime,
            "dealer_contracts_per_step": round(contracts_per_step, 0),
            "step_pts": step_pts,
        }

    def compute_dealer_hedge_flow(self, p_start: float, p_end: float) -> dict:
        """
        Integra o fluxo de hedge dos Dealers quando o preço se move de p_start até p_end.
        Retorna quantos contratos futuros os Dealers precisaram COMPRAR (+) ou VENDER (-) nesse deslocamento.
        """
        if p_start <= 0.0 or p_end <= 0.0 or len(self.strikes) == 0:
            return {"delta_price": 0.0, "dealer_hedge_contracts": 0.0, "dealer_action": "NEUTRO"}

        dp = p_end - p_start
        if abs(dp) < 1e-6:
            return {"delta_price": 0.0, "dealer_hedge_contracts": 0.0, "dealer_action": "NEUTRO"}

        # Ponto médio do deslocamento para integrar Gamma(S)
        p_mid = 0.5 * (p_start + p_end)
        g_info = self.evaluate_local_gex(p_mid)
        step_pts = g_info["step_pts"]
        contracts_mag = g_info["dealer_contracts_per_step"] * (abs(dp) / step_pts)

        # Regra de ouro do Delta-Hedge dos Market Makers:
        # - Se local_regime == NEGATIVE_GAMMA (Dealers vendidos em opções):
        #     preço sobe (dp > 0) -> Dealers COMPRAM futuros (+contracts_mag) [Acelera alta]
        #     preço cai  (dp < 0) -> Dealers VENDEM futuros  (-contracts_mag) [Acelera queda]
        # - Se local_regime == POSITIVE_GAMMA (Dealers comprados em opções):
        #     preço sobe (dp > 0) -> Dealers VENDEM futuros  (-contracts_mag) [Amortece alta / Defende topo]
        #     preço cai  (dp < 0) -> Dealers COMPRAM futuros (+contracts_mag) [Amortece queda / Defende piso]
        if g_info["local_regime"] == "NEGATIVE_GAMMA":
            signed_contracts = contracts_mag if dp > 0 else -contracts_mag
            mode_str = "ACELERADOR (Gamma Negativo)"
        else:
            signed_contracts = -contracts_mag if dp > 0 else contracts_mag
            mode_str = "AMORTECEDOR (Gamma Positivo)"

        if signed_contracts > 50:
            action = f"DEALERS COMPRANDO FUTUROS ({mode_str})"
        elif signed_contracts < -50:
            action = f"DEALERS VENDENDO FUTUROS ({mode_str})"
        else:
            action = "HEDGE NEUTRO"

        return {
            "delta_price": round(dp, 2),
            "dealer_hedge_contracts": round(signed_contracts, 0),
            "dealer_action": action,
            "hedge_mode": mode_str,
        }

    def get_dominant_gamma_magnets(self, spot_price: float, top_n: int = 4) -> list:
        """
        Retorna as Walls de maior concentração de Gamma (ímãs de liquidez / Pinning ou gatilhos de aceleração)
        próximas do preço atual.
        """
        if len(self.strikes) == 0 or spot_price <= 0:
            return []

        max_abs = float(np.max(np.abs(self.strike_gex))) or 1.0
        items = []
        for i in range(len(self.strikes)):
            p = float(self.strikes[i])
            g = float(self.strike_gex[i])
            w = int(self.strike_widths[i])
            dist = p - spot_price
            pct_power = (abs(g) / max_abs) * 100.0
            role = (
                "IMA_POSITIVO (Amortecimento / Pinning)"
                if g >= 0
                else "GATILHO_NEGATIVO (Aceleracao / Squeeze)"
            )
            items.append({
                "price": round(p, 2),
                "dist_pts": round(dist, 2),
                "width": w,
                "gex_raw": g,
                "gex_formatted": f"{g/1e9:+.2f}B" if self.asset == "WIN" else f"{g/1e6:+.1f}M",
                "power_pct": round(pct_power, 1),
                "gamma_polarity": "POSITIVE" if g >= 0 else "NEGATIVE",
                "role": role,
            })

        # Filtra strikes num raio razoável (ex: 4000 pts WIN / 120 pts WDO) e ordena por potência Gamma
        radius = 4500.0 if self.asset == "WIN" else 120.0
        nearby = [x for x in items if abs(x["dist_pts"]) <= radius]
        if not nearby:
            nearby = items
        nearby.sort(key=lambda x: abs(x["gex_raw"]), reverse=True)
        return nearby[:top_n]


class GexLiveDealerEngine:
    """
    Motor da Etapa 2 (Caminho A): Calcula em tempo real a Pressão de Hedge dos Dealers GEX
    e cruza com o Fluxo Institucional do ProfitChart/MT5 (Etapa 1).
    """

    def __init__(self):
        self.win_model = AssetGexCurveModel("WIN")
        self.wdo_model = AssetGexCurveModel("WDO")
        # Registro imutável de sinais avaliados em barra fechada: (asset, sess_date, align_with_window) -> {ts_raw: dict_or_None}
        self._locked_signals = {}
        self._prev_day_closes_cache = None

    def _get_prev_day_warmup_closes(self, asset: str, sess_date: str, max_bars: int = 300) -> list:
        if not sess_date:
            return []
        hist_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "processed",
            "gex_historical_sessions_v1",
        )
        if self._prev_day_closes_cache is None:
            self._prev_day_closes_cache = {"WIN": {}, "WDO": {}, "dates": []}
        if os.path.isdir(hist_dir):
            fnames = sorted(f[:-5] for f in os.listdir(hist_dir) if f.endswith(".json"))
            known_set = set(self._prev_day_closes_cache.get("dates", []))
            new_dates = [d_k for d_k in fnames if d_k not in known_set]
            if new_dates:
                for d_k in new_dates:
                    fp = os.path.join(hist_dir, f"{d_k}.json")
                    try:
                        with open(fp, "r", encoding="utf-8") as fh:
                            pl = json.load(fh)
                        for sym in ("WIN", "WDO"):
                            s_list = (pl.get(sym) or {}).get("m5_cvd_series") or []
                            c_day = [float(b.get("close", b.get("open", 0.0))) for b in s_list if not b.get("is_prev_day", False)]
                            if c_day:
                                self._prev_day_closes_cache[sym][d_k] = c_day
                    except Exception:
                        pass
                self._prev_day_closes_cache["dates"] = fnames
        dates_list = self._prev_day_closes_cache.get("dates", [])
        prev_dates = [d for d in dates_list if d < sess_date]
        if not prev_dates:
            return []
        sym_map = self._prev_day_closes_cache.get(asset.upper(), {})
        acc = []
        for d_prev in prev_dates[-4:]:
            acc.extend(sym_map.get(d_prev, []))
        return acc[-max_bars:] if max_bars > 0 else acc

    def analyze_asset(self, symbol_payload: dict) -> dict:
        asset = symbol_payload.get("asset", "WIN").upper()
        base_model = self.win_model if asset == "WIN" else self.wdo_model
        base_model.reload_if_needed()

        sess_date = symbol_payload.get("session_date", "")
        today_str = datetime.now().strftime("%Y-%m-%d")
        if sess_date and sess_date != today_str and symbol_payload.get("all_walls"):
            model = AssetGexCurveModel.from_walls_list(asset, sess_date, symbol_payload.get("all_walls", []))
        else:
            model = base_model

        spot = float(symbol_payload.get("last_price", 0.0))
        open_p = float(symbol_payload.get("open_price", spot))
        vwap = float(symbol_payload.get("vwap", spot))

        m5_series = symbol_payload.get("m5_cvd_series", [])
        p_5m_ago = float(m5_series[-2]["close"]) if len(m5_series) >= 2 else spot
        p_15m_ago = float(m5_series[-4]["close"]) if len(m5_series) >= 4 else open_p

        local_gex = model.evaluate_local_gex(spot)
        hedge_session = model.compute_dealer_hedge_flow(open_p, spot)
        hedge_15m = model.compute_dealer_hedge_flow(p_15m_ago, spot)
        hedge_5m = model.compute_dealer_hedge_flow(p_5m_ago, spot)

        # Score de Pressão dos Dealers (-100 a +100):
        # Combina a pressão de hedge de 5m (50%), 15m (30%) e Sessão (20%)
        scale_5m = 2500.0 if asset == "WIN" else 400.0
        scale_15m = 5000.0 if asset == "WIN" else 800.0
        scale_sess = 12000.0 if asset == "WIN" else 2000.0

        s5 = np.clip((hedge_5m["dealer_hedge_contracts"] / scale_5m) * 100.0, -100.0, 100.0)
        s15 = np.clip((hedge_15m["dealer_hedge_contracts"] / scale_15m) * 100.0, -100.0, 100.0)
        ssess = np.clip((hedge_session["dealer_hedge_contracts"] / scale_sess) * 100.0, -100.0, 100.0)
        dealer_pressure_score = float(np.clip(0.50 * s5 + 0.30 * s15 + 0.20 * ssess, -100.0, 100.0))

        # --- Cruzamento Matriz Caminho A (Dealers) x Etapa 1 (Fluxo Institucional Profit/MT5) ---
        flow_comp = symbol_payload.get("flow_compass", {})
        flow_score = float(flow_comp.get("score", 0.0))
        w5m = flow_comp.get("windows", {}).get("5m", {})
        inst_delta_5m = float(w5m.get("inst_delta", 0.0))
        abs_state_5m = w5m.get("absorption_state", "NEUTRO")

        st = symbol_payload.get("session_totals", {})
        inst_brk_aggr = int(st.get("inst_broker_aggr_delta", 0))
        inst_brk_pass = int(st.get("inst_broker_passive_delta", 0))

        walls_radar = symbol_payload.get("walls_radar", {})
        active_wall = walls_radar.get("active_wall_alert")
        sup_walls = walls_radar.get("support_walls", [])
        res_walls = walls_radar.get("resistance_walls", [])

        nearest_sup = sup_walls[0] if sup_walls else None
        nearest_res = res_walls[0] if res_walls else None

        # Enriquecer cada Wall próxima e todas as all_walls (incluindo MidWall) com GEX, Lotes de Hedge dos Makers e Defesa Institucional
        gex_by_price = {round(float(model.strikes[i]), 1): float(model.strike_gex[i]) for i in range(len(model.strikes))}
        all_walls_list = symbol_payload.get("all_walls", [])
        m5_series = [pt for pt in symbol_payload.get("m5_cvd_series", []) if not pt.get("is_prev_day")]

        max_inst_wall_vol = max(
            [float(w.get("inst_total_vol", 0.0)) for w in all_walls_list if w.get("type") in ("Wall", "MidWall")]
            + [5000.0 if asset == "WIN" else 1000.0]
        )
        max_abs_gex = float(np.max(np.abs(model.strike_gex))) if len(model.strike_gex) > 0 else 1.0
        if max_abs_gex <= 0:
            max_abs_gex = 1.0

        zone_rad = 2.5 if asset == "WDO" else 55.0
        break_tol = 1.0 if asset == "WDO" else 25.0
        bar_inst_th = 1000.0 if asset == "WDO" else 2500.0

        enriched_by_key = {}
        for w in all_walls_list:
            wp = round(float(w.get("price", 0.0)), 1)
            wtype = str(w.get("type", "Wall"))
            is_mid = ("mid" in wtype.lower()) or (str(w.get("label", "")).upper() == "MIDLEWALL")
            wgex = gex_by_price.get(wp, 0.0)
            if wgex == 0.0 and (wtype in ("Wall", "MidWall") or is_mid):
                loc_raw = float(model.evaluate_local_gex(wp).get("net_gex_raw", 0.0))
                wgex = loc_raw * (0.55 if is_mid else 1.0)
            w["gex_raw"] = wgex
            if is_mid:
                w["gex_formatted"] = (
                    f"Mid {wgex/1e9:+.1f}B" if (asset == "WIN" and wgex != 0)
                    else (f"Mid {wgex/1e6:+.0f}M" if (asset == "WDO" and wgex != 0) else "MidWall")
                )
            else:
                w["gex_formatted"] = (
                    f"{wgex/1e9:+.1f}B" if (asset == "WIN" and wgex != 0)
                    else (f"{wgex/1e6:+.0f}M" if (asset == "WDO" and wgex != 0) else "Wall")
                )
            # Lotes de Hedge dos Market Makers (Dealers) naquela Wall / MidWall
            maker_lots = round(abs(wgex) / 1e9 * 45.0, 0) if asset == "WIN" else round(abs(wgex) / 1e6 * 1.2, 0)
            w["maker_hedge_lots"] = int(maker_lots)

            inst_b = float(w.get("inst_buy_vol", 0.0))
            inst_s = float(w.get("inst_sell_vol", 0.0))
            inst_tot = float(w.get("inst_total_vol", inst_b + inst_s))
            inst_d = float(w.get("inst_delta", inst_b - inst_s))
            if w.get("rlp_delta") is None:
                ret_d_w = float(w.get("ret_delta", 0.0))
                rlp_sh_w = float(w.get("rlp_share_pct", w.get("rlp_pct", 0.0)))
                w["rlp_delta"] = round(-ret_d_w * (rlp_sh_w / 100.0), 0)

            # Régua estatística de 3 Estágios calibrada nos 127 pregões históricos:
            # WDO: P25 = 3.000 L (Moderado) | P50 = 8.000 L (Forte)
            # WIN: P25 = 5.000 L (Moderado) | P50 = 12.000 L (Forte)
            conviction_mod = 3000.0 if asset == "WDO" else 5000.0
            conviction_strong = 8000.0 if asset == "WDO" else 12000.0
            abs_d = abs(inst_d)

            if inst_tot > 0 and abs_d >= conviction_mod:
                # Estágio 2 & 3: Posição Institucional Montada (Verde se Comprado, Vermelho se Vendido)
                # Mesmo se o preço furar temporariamente contra ("tomando calor"), preserva a cor da mão institucional
                if inst_d > 0:
                    smart_bias = "BUY"
                    role = "SUP"
                    def_lots = inst_b
                else:
                    smart_bias = "SELL"
                    role = "RES"
                    def_lots = inst_s
                smart_stage = "FORTE" if abs_d >= conviction_strong else "MODERADO"
            else:
                # Estágio 1: Em Disputa / Sem Dono Definido (< 3kL WDO | < 5kL WIN) -> Neutro (Branco/Cinza do Pine)
                smart_bias = "NEUTRAL"
                role = "NEUTRAL"
                smart_stage = "NEUTRO"
                def_lots = max(inst_b, inst_s) if inst_tot > 0 else maker_lots

            # Evolução Dinâmica da Wall ao longo dos candles de hoje (Múltiplas Marcações: Defendeu / Absorveu / Rompeu / Virou)
            wall_events = []
            touch_count = 0
            broken_dir = 0
            last_ev_idx = -4
            if wtype in ("Wall", "MidWall") or is_mid:
                for idx_m, pt in enumerate(m5_series):
                    c = float(pt.get("close", 0.0))
                    o = float(pt.get("open", c))
                    h = float(pt.get("high", c))
                    l = float(pt.get("low", c))
                    if not (l - zone_rad <= wp <= h + zone_rad):
                        continue
                    touch_count += 1
                    if idx_m < 1 or ((idx_m - last_ev_idx) < 3 and idx_m < len(m5_series) - 1):
                        continue
                    prev_slice = m5_series[max(0, idx_m - 3):idx_m]
                    prev_avg = float(np.mean([float(x.get("close", c)) for x in prev_slice])) if prev_slice else c
                    prev_side = 1 if prev_avg >= wp else -1
                    rng = max(h - l, 0.5 if asset == "WDO" else 5.0)
                    body_r = abs(c - o) / rng
                    u_wick = (h - max(o, c)) / rng
                    l_wick = (min(o, c) - l) / rng
                    id_b = float(pt.get("inst_delta_bar", 0.0))
                    rd_b = float(pt.get("ret_delta_bar", 0.0))
                    cvd_now = float(pt.get("cvd_inst", 0.0))
                    cvd_prev = float(m5_series[max(0, idx_m - 3)].get("cvd_inst", 0.0))
                    flow_15m = cvd_now - cvd_prev

                    if prev_side == 1:
                        if c >= wp - break_tol:
                            if l_wick >= 0.28 or (c > o and id_b > 0) or (id_b >= bar_inst_th * 0.6 and rd_b < 0):
                                ev_type = "VIROU_SUP" if broken_dir == 1 else "DEFENDEU_COMPRA"
                                ev_label = "🔄 Virou Sup" if broken_dir == 1 else "🛡️ Defendeu"
                                wall_events.append({"time": pt.get("time"), "type": ev_type, "label": ev_label, "dir": 1})
                                last_ev_idx = idx_m
                        else:
                            if id_b > 0 or (flow_15m > 0 and rd_b < 0):
                                wall_events.append({"time": pt.get("time"), "type": "VIOLINADA_COMPRA", "label": "🪤 Absorveu", "dir": 1})
                                last_ev_idx = idx_m
                            elif body_r >= 0.50 and (id_b <= -bar_inst_th * 0.6 or flow_15m < 0):
                                broken_dir = -1
                                wall_events.append({"time": pt.get("time"), "type": "ROMPEU_BAIXA", "label": "💥 Rompeu", "dir": -1})
                                last_ev_idx = idx_m
                    else:
                        if c <= wp + break_tol:
                            if u_wick >= 0.28 or (c < o and id_b < 0) or (id_b <= -bar_inst_th * 0.6 and rd_b > 0):
                                ev_type = "VIROU_RES" if broken_dir == -1 else "DEFENDEU_VENDA"
                                ev_label = "🔄 Virou Res" if broken_dir == -1 else "🛡️ Defendeu"
                                wall_events.append({"time": pt.get("time"), "type": ev_type, "label": ev_label, "dir": -1})
                                last_ev_idx = idx_m
                        else:
                            if id_b < 0 or (flow_15m < 0 and rd_b > 0):
                                wall_events.append({"time": pt.get("time"), "type": "VIOLINADA_VENDA", "label": "🪤 Absorveu", "dir": -1})
                                last_ev_idx = idx_m
                            elif body_r >= 0.50 and (id_b >= bar_inst_th * 0.6 or flow_15m > 0):
                                broken_dir = 1
                                wall_events.append({"time": pt.get("time"), "type": "ROMPEU_ALTA", "label": "💥 Rompeu", "dir": 1})
                                last_ev_idx = idx_m

            last_ev = wall_events[-1]["type"] if wall_events else ""
            trap_max_dist = 3.5 if asset == "WDO" else 120.0
            dist_from_wall = spot - wp
            is_near_wall = abs(dist_from_wall) <= trap_max_dist
            is_taking_heat = is_near_wall and (
                (smart_bias == "BUY" and dist_from_wall < -break_tol)
                or (smart_bias == "SELL" and dist_from_wall > break_tol)
            )
            # Se uma Wall Vendedora foi rompida para cima além da zona de violinada (>120 pts WIN / >3.5 pts WDO),
            # ou uma Wall Compradora foi rompida para baixo além da zona de violinada, os lotes contrários foram estopados e ela virou de papel!
            broke_up_confirmed = (dist_from_wall > trap_max_dist) and (smart_bias == "SELL" or (smart_bias == "NEUTRAL" and broken_dir == 1))
            broke_dn_confirmed = (dist_from_wall < -trap_max_dist) and (smart_bias == "BUY" or (smart_bias == "NEUTRAL" and broken_dir == -1))

            if touch_count >= 5 and smart_stage == "NEUTRO" and is_near_wall:
                live_verdict = f"⚪ WALL GASTA ({touch_count}x)"
            elif is_near_wall and (last_ev in ("VIOLINADA_COMPRA", "VIOLINADA_VENDA") or (is_taking_heat and smart_stage == "FORTE")):
                live_verdict = "🪤 VIOLINADA (ABSORVENDO COMPRA)" if (smart_bias == "BUY" or last_ev == "VIOLINADA_COMPRA") else "🪤 VIOLINADA (ABSORVENDO VENDA)"
            elif broke_up_confirmed:
                live_verdict = "💥 ROMPERAM P/ ALTA (VIROU SUP)"
                smart_bias = "BUY"
                role = "SUP"
            elif broke_dn_confirmed:
                live_verdict = "💥 ROMPERAM P/ BAIXO (VIROU RES)"
                smart_bias = "SELL"
                role = "RES"
            elif last_ev == "VIROU_SUP" and spot >= wp - break_tol:
                live_verdict = "🔄 VIROU SUPORTE (DEFENDENDO)"
                smart_bias = "BUY"
                role = "SUP"
            elif last_ev == "VIROU_RES" and spot <= wp + break_tol:
                live_verdict = "🔄 VIROU RESISTÊNCIA (DEFENDENDO)"
                smart_bias = "SELL"
                role = "RES"
            elif smart_bias == "BUY" or last_ev == "DEFENDEU_COMPRA":
                live_verdict = "🛡️ VAI DEFENDER COMPRA"
            elif smart_bias == "SELL" or last_ev == "DEFENDEU_VENDA":
                live_verdict = "🛡️ VAI DEFENDER VENDA"
            elif broken_dir == 1 and spot > wp + break_tol:
                live_verdict = "💥 ROMPERAM P/ ALTA (VIROU SUP)"
                smart_bias = "BUY"
                role = "SUP"
            elif broken_dir == -1 and spot < wp - break_tol:
                live_verdict = "💥 ROMPERAM P/ BAIXO (VIROU RES)"
                smart_bias = "SELL"
                role = "RES"
            else:
                live_verdict = "⚪ SUPORTE EM DISPUTA" if spot >= wp else "⚪ RESIST. EM DISPUTA"

            w["inst_delta"] = round(inst_d, 0)
            w["smart_bias"] = smart_bias
            w["smart_stage"] = smart_stage
            w["role"] = role
            w["defense_lots"] = int(round(def_lots, 0))
            w["inst_total_vol"] = int(round(inst_tot, 0))
            w["touch_count"] = touch_count
            w["broken_dir"] = broken_dir
            w["wall_events"] = wall_events
            w["live_verdict"] = live_verdict

            # Score de Força da Wall/MidWall (0 a 100): 55% Defesa/Absorção Institucional Real + 45% Potência GEX / Hedge Makers
            inst_pct = min(100.0, (inst_tot / max(1.0, max_inst_wall_vol)) * 100.0)
            base_w_pct = 24.0 if is_mid else (int(w.get("width", 1)) * 30.0)
            gex_pct = min(100.0, (abs(wgex) / max_abs_gex) * 100.0) if wgex != 0 else base_w_pct
            gex_pct = max(gex_pct, base_w_pct * 0.85)
            power_pct = int(round(np.clip(0.55 * inst_pct + 0.45 * gex_pct, 10.0, 100.0)))
            w["wall_power_pct"] = power_pct

            if power_pct >= 35 or (inst_tot >= max_inst_wall_vol * 0.35):
                w["wall_tier"] = "FORTE"
            elif power_pct >= (20 if is_mid else 23) or inst_tot > 0:
                w["wall_tier"] = "MODERADA"
            else:
                w["wall_tier"] = "FRACA"

            enriched_by_key[(wtype, wp)] = w
            enriched_by_key[("*", wp)] = w

        for w_list in (sup_walls, res_walls):
            for w in w_list:
                wp = round(float(w["price"]), 1)
                wtype = str(w.get("type", "Wall"))
                is_mid = ("mid" in wtype.lower()) or (str(w.get("label", "")).upper() == "MIDLEWALL")
                ref_w = enriched_by_key.get((wtype, wp)) or enriched_by_key.get(("*", wp))
                if ref_w is not None:
                    wgex = float(ref_w.get("gex_raw", 0.0))
                    w["gex_raw"] = wgex
                    w["gex_formatted"] = ref_w.get("gex_formatted", "MidWall" if is_mid else "Wall")
                    w["maker_hedge_lots"] = int(ref_w.get("maker_hedge_lots", 0))
                    w["defense_lots"] = int(ref_w.get("defense_lots", 0))
                    w["inst_total_vol"] = int(ref_w.get("inst_total_vol", 0))
                    w["inst_delta"] = int(ref_w.get("inst_delta", 0))
                    w["smart_bias"] = ref_w.get("smart_bias", "NEUTRAL")
                    w["role"] = ref_w.get("role", "SUP" if wp <= spot else "RES")
                    w["wall_power_pct"] = int(ref_w.get("wall_power_pct", 25))
                    w["wall_tier"] = ref_w.get("wall_tier", "MODERADA")
                    w["touch_count"] = int(ref_w.get("touch_count", 0))
                    w["broken_dir"] = int(ref_w.get("broken_dir", 0))
                    w["wall_events"] = ref_w.get("wall_events", [])
                    w["live_verdict"] = ref_w.get("live_verdict", "")
                    for p4_k in ("inst_aggr_delta", "inst_pass_delta", "ret_delta", "hft_delta", "rlp_delta", "hft_churn_pct", "rlp_share_pct", "player_verdict", "top_wall_brokers"):
                        if p4_k in ref_w and p4_k not in w:
                            w[p4_k] = ref_w[p4_k]
                else:
                    wgex = gex_by_price.get(wp, 0.0)
                    if wgex == 0.0:
                        wgex = float(model.evaluate_local_gex(wp).get("net_gex_raw", 0.0)) * (0.55 if is_mid else 1.0)
                    w["gex_raw"] = wgex
                    w["gex_formatted"] = (
                        f"{wgex/1e9:+.2f}B" if (asset == "WIN" and wgex != 0)
                        else (f"{wgex/1e6:+.1f}M" if (asset == "WDO" and wgex != 0) else "MidWall")
                    )
                w["dealer_wall_behavior"] = (
                    "DEFESA_DEALER (Amortecimento)" if wgex > 0
                    else ("GATILHO_ACELERACAO (Gamma Negativo)" if wgex < 0 else "PIVO_INTERMEDIARIO")
                )

        # Classificação dos 6 Estados Operacionais da Matriz (GEX Dealer x Profit Flow)
        is_neg_gamma = local_gex["local_regime"] == "NEGATIVE_GAMMA"
        in_wall_zone = active_wall is not None

        if in_wall_zone and (
            "ABSORCAO_COMPRADORA" in active_wall.get("status", "")
            or "ABSORCAO_COMPRADORA" in abs_state_5m
            or (active_wall["dist_pts"] <= 0 and not is_neg_gamma and dealer_pressure_score > 10)
        ):
            op_state = "DEFESA_DE_SUPORTE_DEALER_ABSORCAO"
            bias = "COMPRA (Pullback / Defesa de Wall)"
            confluence_score = float(np.clip(0.55 * abs(flow_score) + 0.45 * max(25.0, dealer_pressure_score), 25.0, 100.0))
            playbook = (
                f"Defesa passiva na {active_wall['type']} @ {active_wall['price']:.2f}: "
                f"Dealers amortecendo queda + Absorção compradora no fluxo. Favorável a Compra de Pullback com stop curto abaixo da Wall."
            )
        elif in_wall_zone and (
            "ABSORCAO_VENDEDORA" in active_wall.get("status", "")
            or "ABSORCAO_VENDEDORA" in abs_state_5m
            or (active_wall["dist_pts"] >= 0 and not is_neg_gamma and dealer_pressure_score < -10)
        ):
            op_state = "DEFESA_DE_RESISTENCIA_DEALER_ABSORCAO"
            bias = "VENDA (Pullback / Defesa de Wall)"
            confluence_score = float(np.clip(-0.55 * abs(flow_score) - 0.45 * max(25.0, abs(dealer_pressure_score)), -100.0, -25.0))
            playbook = (
                f"Defesa passiva na {active_wall['type']} @ {active_wall['price']:.2f}: "
                f"Dealers vendendo na resistência + Absorção vendedora no book. Favorável a Venda de Pullback contra a Wall."
            )
        elif is_neg_gamma and dealer_pressure_score >= 15.0 and (flow_score >= 20.0 or inst_delta_5m > 0):
            op_state = "ACELERACAO_ALTISTA_GAMMA_SQUEEZE"
            bias = "COMPRA DIRECIONAL (Gamma Squeeze)"
            confluence_score = float(np.clip(0.50 * flow_score + 0.50 * dealer_pressure_score, 30.0, 100.0))
            target_str = f"{nearest_res['type']} @ {nearest_res['price']:.2f}" if nearest_res else "próxima resistência"
            playbook = (
                f"Confluência Altista em Gamma Negativo: Dealers forçados a comprar ({hedge_5m['dealer_hedge_contracts']:+.0f} contr. em 5m) "
                f"+ Fluxo Institucional Comprador ({inst_delta_5m:+.0f}L). Alvo direcional na {target_str}."
            )
        elif is_neg_gamma and dealer_pressure_score <= -15.0 and (flow_score <= -20.0 or inst_delta_5m < 0):
            op_state = "ACELERACAO_BAIXISTA_GAMMA_DROP"
            bias = "VENDA DIRECIONAL (Gamma Drop)"
            confluence_score = float(np.clip(0.50 * flow_score + 0.50 * dealer_pressure_score, -100.0, -30.0))
            target_str = f"{nearest_sup['type']} @ {nearest_sup['price']:.2f}" if nearest_sup else "próximo suporte"
            playbook = (
                f"Confluência Baixista em Gamma Negativo: Dealers forçados a vender ({hedge_5m['dealer_hedge_contracts']:+.0f} contr. em 5m) "
                f"+ Fluxo Institucional Vendedor ({inst_delta_5m:+.0f}L). Alvo direcional na {target_str}."
            )
        elif (dealer_pressure_score * flow_score < -400.0) or (not is_neg_gamma and abs(flow_score) >= 35.0):
            op_state = "CONFLITO_FLUXO_VS_DEALER"
            bias = "CAUTELA / RISCO DE VIOLINADA"
            confluence_score = float(np.clip(0.60 * flow_score + 0.40 * dealer_pressure_score, -60.0, 60.0))
            if not is_neg_gamma:
                playbook = (
                    f"Divergência em Gamma Positivo: Fluxo agredindo ({flow_score:+.1f}) contra a zona de amortecimento dos Market Makers "
                    f"(Dealers atuando na ponta oposta com {local_gex['dealer_contracts_per_step']:.0f} contr./{local_gex['step_pts']:.0f} pts). "
                    f"Alto risco de absorção e violinada — evitar entrar em rompimento seco."
                )
            else:
                playbook = (
                    f"Divergência em Gamma Negativo: Deslocamento recente forçou hedge dos Dealers ({dealer_pressure_score:+.1f}), "
                    f"mas o fluxo institucional agressor aponta no sentido oposto ({flow_score:+.1f}). "
                    f"Aguardar alinhamento entre preço e agressão antes de entrar direcional."
                )
        else:
            op_state = "TRANSICAO_ENTRE_WALLS"
            confluence_score = float(np.clip(0.60 * flow_score + 0.40 * dealer_pressure_score, -100.0, 100.0))
            if confluence_score >= 20.0:
                bias = "LEVE VIES COMPRADOR"
            elif confluence_score <= -20.0:
                bias = "LEVE VIES VENDEDOR"
            else:
                bias = "NEUTRO / AGUARDAR WALL"
            sup_str = f"{nearest_sup['price']:.2f}" if nearest_sup else "--"
            res_str = f"{nearest_res['price']:.2f}" if nearest_res else "--"
            playbook = f"Preço em transição no corredor [{sup_str} <-> {res_str}]. Aguardar teste das extremidades ou entrada de fluxo institucional."

        # Série histórica M5 enriquecida com o fluxo de hedge dos Dealers barra a barra + Sinais Marcados no Tempo (100% Barra Fechada)
        all_walls = symbol_payload.get("all_walls") or model.walls_raw
        is_live_session = bool(not sess_date or sess_date == today_str)
        signals_result = self._evaluate_intraday_signals_and_scorecard(
            asset=asset,
            m5_series=m5_series,
            model=model,
            all_walls=all_walls,
            sess_date=sess_date or today_str,
            is_live_session=is_live_session,
        )

        # Construir HUD estilo A.S.G + Radar Pro (Decisão em Barra Fechada + Gatilhos Visuais no Gráfico)
        asg_hud = self._build_asg_hud(
            asset=asset,
            spot=spot,
            vwap=vwap,
            m5_enriched=signals_result["m5_enriched_series"],
            flow_Windows=signals_result["flow_windows"],
            flow_score=flow_score,
            dealer_pressure_score=dealer_pressure_score,
            local_gex=local_gex,
            sup_walls=sup_walls,
            res_walls=res_walls,
            op_state=op_state,
            symbol_payload=symbol_payload,
            is_live_session=is_live_session,
        )

        return {
            "ref_date": model.ref_date,
            "local_gex": local_gex,
            "dealer_pressure_score": round(dealer_pressure_score, 1),
            "hedge_horizons": {
                "5m": hedge_5m,
                "15m": hedge_15m,
                "session": hedge_session,
            },
            "dominant_magnets": model.get_dominant_gamma_magnets(spot, top_n=4),
            "confluence_matrix": {
                "operational_state": op_state,
                "operational_bias": bias,
                "confluence_score": round(confluence_score, 1),
                "flow_score": round(flow_score, 1),
                "dealer_score": round(dealer_pressure_score, 1),
                "inst_broker_aggr_delta": inst_brk_aggr,
                "inst_broker_passive_delta": inst_brk_pass,
                "actionable_playbook": playbook,
            },
            "m5_dealer_vs_flow_series": signals_result["m5_enriched_series"],
            "flow_windows": signals_result["flow_windows"],
            "asg_hud": asg_hud,
            "signals_log": signals_result["signals_log"],
            "signals_scorecard": signals_result["scorecard"],
        }

    def _evaluate_intraday_signals_and_scorecard(
        self,
        asset: str,
        m5_series: list,
        model: AssetGexCurveModel,
        all_walls: list,
        align_with_window: bool = None,
        sess_date: str = "",
        is_live_session: bool = False,
    ) -> dict:
        """
        Percorre todas as barras M5 do pregão (09h00 até agora), marca no tempo cada Sinal Oficial
        da Bússola (Pullback/Absorção na Wall ou Confluência de Fluxo + Dealer) APENAS EM BARRA FECHADA
        (sem repintar na barra em formação) e valida objetivamente o desfecho também em barras fechadas.
        """
        is_win = asset.upper() == "WIN"
        # Quando align_with_window é None (chamada oficial do Cockpit / API), ativa as Estratégias Campeãs 100% Fidedignas:
        # - WIN (Opção A Conservadora · 6/6 Meses Positivos · Ret/DD 6.08x):
        #     Frente 1 (09:30–12:00): Defesa na Wall + Desconto NWE (bw=8) | TP 250p | SL Estrutural atrás da Wall (+180p, 250..520p)
        #     Frente 2 (09:30–13:00): Virada Janela A.S.G + Inclinação NWE (bw=8) + Fluxo Inst | Saída na Virada / TP 1000p | SL 300p | BE +30p após +200p
        # - WDO (Opção C Equilibrada · 6/6 Meses Positivos · WR 68.3% · Ret/DD 8.95x):
        #     Frente 1 (09:30–12:00): Defesa na Wall + Desconto NWE (bw=8) | TP 10p | SL Protegido atrás da Wall (+5p, 8..15p) | BE +2.0p após +7.0p
        #     Frente 2 (09:30–12:00): Virada Janela A.S.G | Saída na Virada | SL Estrutural atrás da Mín/Máx (+4p, 7..14p) | BE +1.0p após +3.5p
        use_champion_mode = (align_with_window is None)
        if align_with_window is None:
            align_with_window = False

        p_fmt = ".0f" if is_win else ".1f"
        wall_radius = (130.0 if use_champion_mode else 85.0) if is_win else (3.5 if use_champion_mode else 2.5)
        inst_thresh_5m = (1800.0 if use_champion_mode else 3200.0) if is_win else 650.0
        entry_scale_pts = (200.0 if use_champion_mode else 150.0) if is_win else (6.5 if use_champion_mode else 5.0)

        if use_champion_mode:
            target_pts = 250.0 if is_win else 10.0
            stop_pts = 300.0 if is_win else 10.0
            max_val_bars = 12 if is_win else 24
            use_be_protection = True
            be_trigger_pts = 200.0 if is_win else 3.5
            be_lock_pts = 30.0 if is_win else 1.0
        else:
            target_pts = 250.0 if is_win else 12.0
            stop_pts = 250.0 if is_win else 7.0
            max_val_bars = 8 if is_win else 12
            use_be_protection = False if is_win else True
            be_trigger_pts = 150.0 if is_win else 3.5
            be_lock_pts = 50.0 if is_win else 1.0

        mode_key = "CHAMPION" if use_champion_mode else ("M2" if align_with_window else "M1")
        lock_key = (asset.upper(), str(sess_date or ""), mode_key)
        if lock_key not in self._locked_signals:
            self._locked_signals[lock_key] = {}
        locked_map = self._locked_signals[lock_key]

        walls_clean = [
            {"type": w.get("type", "Wall"), "price": float(w.get("price", 0.0)), "gex": float(w.get("gex", 0.0))}
            for w in (all_walls or [])
            if float(w.get("price", 0.0)) > 0
        ]

        m5_enriched = []
        signals_log = []
        flow_windows = []
        cum_dealer_hedge = 0.0
        last_sig_idx_by_dir = {1: -99, -1: -99}
        last_any_sig_idx = -99
        busy_until_idx = -1
        occupied_intervals = []

        # Calibração Unificada da Janela de Fluxo Smart Money (V5b · 212 pregões auditados):
        # - 12% Absorção Wyckoff + 18% Porte Lote + 70% Institucional (0.90 Agr + 0.75 Pass - 0.25 Varejo), 0% Preço
        # - EMA Rápida = 4, EMA Lenta = 20 (92% Detrended CVD + 8% Impulso 3b), Smooth = 0.45 (WIN) / 0.60 (WDO), Flip = ±11.0
        fast_period = 4.0
        slow_period = 20.0
        w_cvd_weight = 1.0
        w_price_weight = 0.0
        hist_smooth_alpha = 0.45 if is_win else 0.60
        flip_threshold = 11.0

        alpha_fast = 2.0 / (fast_period + 1.0)
        alpha_slow = 2.0 / (slow_period + 1.0)
        alpha_band = 2.0 / (7.0 + 1.0)

        first_b = m5_series[0] if m5_series else {}
        first_c = float(first_b.get("close", 0.0))
        first_h = float(first_b.get("high", first_c))
        first_l = float(first_b.get("low", first_c))
        first_cvd = round(float(first_b.get("cvd_inst", 0.0)), 0)

        ema_p_high = first_h
        ema_p_low = first_l
        ema_atr = max(first_h - first_l, 40.0 if is_win else 1.5)
        ema_cvd_f = 0.0
        ema_cvd_s = 0.0
        ema_cvd_step = 2500.0 if is_win else 400.0
        cum_sm_win = 0.0
        prev_cum_sm_win = 0.0
        sm_win_forces = []
        ema_hist = 0.0
        active_win_dir = 0
        curr_window = None
        prev_candle_state = 0

        n = len(m5_series)
        # Índice final de barras 100% FECHADAS (exclui a última barra caso o pregão esteja ao vivo)
        closed_end = max(0, n - 1) if is_live_session else n

        # ── CÁLCULO CAUSAL CONTÍNUO MULTI-DIA DA MÉDIA E ENVELOPE NWE (Nadaraya-Watson: bandwidth=8, lookback=40, MAE multi-dia=200) ──
        nwe_bw = 8.0
        nwe_lb = 40
        nwe_mae_lb = 200
        prev_in_series_count = sum(1 for b in m5_series if bool(b.get("is_prev_day", False)))
        full_warmup = self._get_prev_day_warmup_closes(asset, str(sess_date or ""), max_bars=300)
        if prev_in_series_count > 0:
            warmup_closes = full_warmup[:-prev_in_series_count] if len(full_warmup) > prev_in_series_count else []
        else:
            warmup_closes = full_warmup
        w_len = len(warmup_closes)
        today_closes_raw = np.array([float(b.get("close", b.get("open", 0.0))) for b in m5_series], dtype=float)
        closes_all = np.concatenate([np.array(warmup_closes, dtype=float), today_closes_raw]) if w_len > 0 else today_closes_raw
        n_all = len(closes_all)
        nwe_all = np.zeros(n_all, dtype=float)
        mae_band_all = np.zeros(n_all, dtype=float)
        slope_all = np.zeros(n_all, dtype=float)
        if n_all > 0:
            i_full = np.arange(nwe_lb + 1, dtype=float)
            w_full = np.exp(-(i_full * i_full) / (2.0 * nwe_bw * nwe_bw))
            min_mae = 120.0 if is_win else 4.0
            for t_i in range(n_all):
                lb_i = min(t_i, nwe_lb)
                if lb_i == 0:
                    nwe_all[t_i] = closes_all[t_i]
                    mae_band_all[t_i] = 220.0 if is_win else 6.5
                    continue
                w_slice = w_full[: lb_i + 1]
                p_slice = closes_all[t_i - lb_i : t_i + 1][::-1]
                nwe_all[t_i] = float(np.dot(p_slice, w_slice) / np.sum(w_slice))
            for t_i in range(n_all):
                lb_m = min(t_i, nwe_mae_lb)
                if lb_m == 0:
                    continue
                err_band = np.abs(closes_all[t_i - lb_m : t_i + 1] - nwe_all[t_i - lb_m : t_i + 1])
                mae_band_all[t_i] = max(min_mae, float(np.mean(err_band)))
                slope_all[t_i] = nwe_all[t_i] - nwe_all[t_i - 1]
        nwe_arr = nwe_all[w_len:]
        mae_arr = mae_band_all[w_len:]
        slope_arr = slope_all[w_len:]

        # Escala local de 40 barras para o filtro de posição relativa (pos_nwe <= 0.25) calibrado nas 123 sessões
        w40 = warmup_closes[-40:] if len(warmup_closes) > 40 else warmup_closes
        w40_len = len(w40)
        c40_all = np.concatenate([np.array(w40, dtype=float), today_closes_raw]) if w40_len > 0 else today_closes_raw
        n40_all = len(c40_all)
        nwe40_all = np.zeros(n40_all, dtype=float)
        mae_pos_all = np.zeros(n40_all, dtype=float)
        if n40_all > 0:
            for t_i in range(n40_all):
                lb_i = min(t_i, nwe_lb)
                if lb_i == 0:
                    nwe40_all[t_i] = c40_all[t_i]
                    mae_pos_all[t_i] = 180.0 if is_win else 4.5
                    continue
                w_slice = w_full[: lb_i + 1]
                p_slice = c40_all[t_i - lb_i : t_i + 1][::-1]
                nwe40_all[t_i] = float(np.dot(p_slice, w_slice) / np.sum(w_slice))
            for t_i in range(n40_all):
                lb_p = min(t_i, nwe_lb)
                if lb_p == 0:
                    continue
                err_pos = np.abs(c40_all[t_i - lb_p : t_i + 1] - nwe40_all[t_i - lb_p : t_i + 1])
                mae_pos_all[t_i] = max(50.0 if is_win else 1.2, float(np.mean(err_pos)))
        mae_pos_arr = mae_pos_all[w40_len:]

        # Localiza o índice de início do pregão atual (09:00 de hoje) para blindar contra warm-up de D-1
        first_today_idx = 0
        for k_idx, kb in enumerate(m5_series):
            if not kb.get("is_prev_day", False):
                first_today_idx = k_idx
                break

        for idx, b in enumerate(m5_series):
            is_prev_day_bar = bool(b.get("is_prev_day", False))
            is_bar_closed = (not is_live_session) or (idx < n - 1)

            ts_raw = int(b.get("time", 0))
            time_str = (
                datetime.fromtimestamp(ts_raw, tz=timezone.utc).strftime("%H:%M")
                if ts_raw > 100000
                else str(b.get("time", ""))
            )
            o = float(b.get("open", b.get("close", 0.0)))
            h = float(b.get("high", o))
            l = float(b.get("low", o))
            c = float(b.get("close", o))
            inst_5m = float(b.get("inst_delta_bar", 0.0))
            cvd = round(float(b["cvd_inst"]), 0)

            # Re-ancora o estado na 1ª barra do dia atual (09:00) para que a remoção do warm-up às 11:20
            # jamais altere retroativamente EMAs, Janelas ou sinais da manhã
            if idx == 0:
                ema_dealer_score = 0.0
                ema_magnet_pct = 0.0
                ema_gex_px = round(c, 2)
                cum_iagg = 0.0
                cum_ipas = 0.0
                cum_hft = 0.0
                cum_rlp = 0.0
                cum_rlp_d = 0.0
            if idx == first_today_idx and idx > 0:
                ema_p_high = round(h, 2)
                ema_p_low = round(l, 2)
                ema_atr = max(round(h, 2) - round(l, 2), 40.0 if is_win else 1.5)
                ema_cvd_f = 0.0
                ema_cvd_s = 0.0
                ema_cvd_step = 2500.0 if is_win else 400.0
                cum_sm_win = 0.0
                prev_cum_sm_win = 0.0
                sm_win_forces = []
                ema_hist = 0.0
                cum_dealer_hedge = 0.0
                cum_iagg = 0.0
                cum_ipas = 0.0
                cum_hft = 0.0
                cum_rlp = 0.0
                cum_rlp_d = 0.0
                ema_dealer_score = 0.0
                ema_magnet_pct = 0.0
                ema_gex_px = round(c, 2)
                active_win_dir = 0
                prev_candle_state = 0
                last_sig_idx_by_dir = {1: -99, -1: -99}
                last_any_sig_idx = -99
                busy_until_idx = -1
                occupied_intervals = []

            rel_idx = (idx - first_today_idx) if not is_prev_day_bar else idx
            base_idx = first_today_idx if not is_prev_day_bar else 0

            p0 = float(m5_series[idx - 1]["close"]) if rel_idx > 0 else o
            prev_l = float(m5_series[idx - 1].get("low", p0)) if rel_idx > 0 else l
            prev_h = float(m5_series[idx - 1].get("high", p0)) if rel_idx > 0 else h
            p_15m_ago = float(m5_series[max(base_idx, idx - 3)]["close"]) if rel_idx >= 2 else float(m5_series[base_idx].get("open", o))
            move_15m = c - p_15m_ago

            prev_cum_dealer = cum_dealer_hedge
            hf = model.compute_dealer_hedge_flow(p0, c)
            cum_dealer_hedge += hf["dealer_hedge_contracts"]

            open_day_px = float(m5_series[base_idx].get("open", o))
            hf_15m_bar = model.compute_dealer_hedge_flow(p_15m_ago, c)
            hf_sess_bar = model.compute_dealer_hedge_flow(open_day_px, c)
            sc_5m = 2500.0 if is_win else 400.0
            sc_15m = 5000.0 if is_win else 800.0
            sc_sess = 12000.0 if is_win else 2000.0
            s5_bar = np.clip((hf["dealer_hedge_contracts"] / sc_5m) * 100.0, -100.0, 100.0)
            s15_bar = np.clip((hf_15m_bar["dealer_hedge_contracts"] / sc_15m) * 100.0, -100.0, 100.0)
            ssess_bar = np.clip((hf_sess_bar["dealer_hedge_contracts"] / sc_sess) * 100.0, -100.0, 100.0)
            raw_dp_score = float(np.clip(0.20 * s5_bar + 0.45 * s15_bar + 0.35 * ssess_bar, -100.0, 100.0))
            ema_dealer_score = 0.38 * raw_dp_score + 0.62 * ema_dealer_score
            dp_score_bar = float(np.clip(ema_dealer_score, -100.0, 100.0))
            makers_pct_bar = round(dp_score_bar / 40.0, 2)

            # ── OPÇÃO 3: MAPA DE ATRAÇÃO GRAVITACIONAL GEX (ÍMÃ DE LIQUIDEZ + REGIME GAMMA) ──
            ema_gex_px = 0.50 * c + 0.50 * ema_gex_px
            gex_magnet_wall = round(c, 2)
            raw_magnet_pct = 0.0
            if len(model.strikes) > 0:
                sigma_m = 650.0 if is_win else 16.0
                d_ref = 260.0 if is_win else 6.5
                diffs = model.strikes - ema_gex_px
                w_prox = np.exp(-0.5 * (diffs / sigma_m) ** 2)
                g_abs = np.abs(model.strike_gex) * (model.strike_widths.astype(np.float64) ** 0.7)
                pull_weights = g_abs * w_prox
                tot_pw = float(np.sum(pull_weights))
                if tot_pw > 0:
                    dom_idx = int(np.argmax(pull_weights))
                    gex_magnet_wall = round(float(model.strikes[dom_idx]), 2)
                    # Atração direcional: positivo se o centro de gravidade GEX está acima do preço (puxando p/ cima),
                    # negativo se o centro de gravidade GEX está abaixo do preço (puxando p/ baixo)
                    center_of_gravity = float(np.sum(pull_weights * model.strikes) / tot_pw)
                    pull_pts = center_of_gravity - ema_gex_px
                    raw_magnet_pct = float(np.clip(np.tanh(pull_pts / d_ref) * 100.0, -100.0, 100.0))
            ema_magnet_pct = 0.42 * raw_magnet_pct + 0.58 * ema_magnet_pct
            gex_magnet_pct_bar = round(float(np.clip(ema_magnet_pct, -100.0, 100.0)), 1)

            inst_15m = sum(float(m5_series[k].get("inst_delta_bar", 0.0)) for k in range(max(base_idx, idx - 2), idx + 1))
            delta_5m = float(b.get("delta_bar", 0.0))
            tot_v = float(b.get("buy_vol", 0.0)) + float(b.get("sell_vol", 0.0))
            imb_5m = ((delta_5m / tot_v) * 100.0) if tot_v > 0 else 0.0

            rng = max(h - l, 5.0 if is_win else 0.5)
            body = abs(c - o)
            lower_wick = min(o, c) - l
            upper_wick = h - max(o, c)

            # Paredes testadas na mínima (suporte vindo de cima) ou na máxima (resistência vinda de baixo)
            min_2bar = min(l, prev_l)
            max_2bar = max(h, prev_h)
            sup_candidates = [
                w for w in walls_clean
                if (min_2bar - wall_radius) <= w["price"] <= (min(o, p0) + wall_radius * 0.4)
                and c >= w["price"] - wall_radius * 0.25
                and (c - w["price"]) <= entry_scale_pts * 0.95
                and move_15m <= entry_scale_pts * 0.5  # Veio testando de cima ou lateral (não esticado em alta)
            ]
            res_candidates = [
                w for w in walls_clean
                if (max(o, p0) - wall_radius * 0.4) <= w["price"] <= (max_2bar + wall_radius)
                and c <= w["price"] + wall_radius * 0.25
                and (w["price"] - c) <= entry_scale_pts * 0.95
                and move_15m >= -entry_scale_pts * 0.5  # Veio testando de baixo ou lateral (não esticado em queda)
            ]
            sup_w = min(sup_candidates, key=lambda w: abs(min_2bar - w["price"])) if sup_candidates else None
            res_w = min(res_candidates, key=lambda w: abs(max_2bar - w["price"])) if res_candidates else None

            loc_g = model.evaluate_local_gex(c)
            is_neg_g = loc_g["local_regime"] == "NEGATIVE_GAMMA"

            # ── 1º PASSO: ATUALIZA JANELA DE FLUXO SMART MONEY UNIFICADA (V5b) DESTA BARRA ─────────────
            prev_cvd = m5_enriched[idx - 1]["cvd_inst"] if rel_idx > 0 else (cvd - round(inst_5m, 0))

            rng_bar = max(round(h, 2) - round(l, 2), 15.0 if is_win else 0.5)
            ema_atr = alpha_band * rng_bar + (1.0 - alpha_band) * ema_atr
            ema_p_high = alpha_band * round(h, 2) + (1.0 - alpha_band) * ema_p_high
            ema_p_low = alpha_band * round(l, 2) + (1.0 - alpha_band) * ema_p_low

            p_upper_trava = round(ema_p_high + 0.35 * ema_atr, 2)
            p_lower_trava = round(ema_p_low - 0.35 * ema_atr, 2)
            p_mid_trava = round(0.5 * (p_upper_trava + p_lower_trava), 2)

            # Motores físicos da FITA (0% Preço): 12% Wyckoff + 18% Porte Lote + 70% Institucional (0.90 Agr + 0.75 Pass - 0.25 Varejo)
            bv_w = float(b.get("buy_vol", 0.0))
            sv_w = float(b.get("sell_vol", 0.0))
            tv_w = max(1.0, bv_w + sv_w)
            lw_w = max(0.0, min(o, c) - l)
            uw_w = max(0.0, h - max(o, c))
            phi_wyk_w = (
                sv_w * ((c - l) / rng) * (0.80 + 1.40 * (lw_w / rng))
                - bv_w * ((h - c) / rng) * (0.80 + 1.40 * (uw_w / rng))
            )
            def_lot_w = 3.1 if is_win else 4.0
            ab_w = float(b.get("avg_buy_lot", def_lot_w))
            as_w = float(b.get("avg_sell_lot", def_lot_w))
            phi_port_w = tv_w * ((ab_w - as_w) / max(0.5, ab_w + as_w)) * 2.2
            ia5_w = float(b.get("inst_aggr_delta", inst_5m))
            ip5_w = float(b.get("inst_pass_delta", 0.0))
            r5_w = float(b.get("ret_delta_bar", 0.0))
            phi_inst_w = 0.90 * ia5_w + 0.75 * ip5_w - 0.25 * r5_w
            bf_w = 0.12 * phi_wyk_w + 0.18 * phi_port_w + 0.70 * phi_inst_w
            sm_win_forces.append(bf_w)

            n_sm_f = len(sm_win_forces)
            fp1_w = sm_win_forces[n_sm_f - 2] if n_sm_f >= 2 else bf_w
            fp2_w = sm_win_forces[n_sm_f - 3] if n_sm_f >= 3 else fp1_w
            imp3_w = 0.45 * bf_w + 0.35 * fp1_w + 0.20 * fp2_w

            cum_sm_win += bf_w
            if n_sm_f == 1:
                ema_cvd_f = cum_sm_win
                ema_cvd_s = cum_sm_win
                prev_cum_sm_win = 0.0
            else:
                ema_cvd_f = alpha_fast * cum_sm_win + (1.0 - alpha_fast) * ema_cvd_f
                ema_cvd_s = alpha_slow * cum_sm_win + (1.0 - alpha_slow) * ema_cvd_s

            sw_w = 0.92 * (ema_cvd_f - ema_cvd_s) + 0.08 * imp3_w
            ema_cvd_step = alpha_band * max(abs(cum_sm_win - prev_cum_sm_win), 500.0 if is_win else 100.0) + (1.0 - alpha_band) * ema_cvd_step
            prev_cum_sm_win = cum_sm_win

            flow_upper_trava = round(max(cvd, prev_cvd, ema_cvd_f) + 0.8 * ema_cvd_step, 0)
            flow_lower_trava = round(min(cvd, prev_cvd, ema_cvd_f) - 0.8 * ema_cvd_step, 0)

            raw_score = float(np.clip((sw_w / max(1.0, ema_cvd_step * 1.4)) * 55.0, -100.0, 100.0))
            ema_hist = hist_smooth_alpha * raw_score + (1.0 - hist_smooth_alpha) * ema_hist
            hist_val = round(float(np.clip(ema_hist, -100.0, 100.0)), 1)

            # Virada de Janela Smart Money Unificada SÓ ocorre em barra FECHADA (não repinta intra-barra)
            if active_win_dir == 0:
                if hist_val >= 4.0 or (bf_w >= 0.0 and round(c, 2) >= round(o, 2)):
                    active_win_dir = 1
                else:
                    active_win_dir = -1
            elif is_bar_closed:
                if active_win_dir == 1 and hist_val <= -flip_threshold:
                    active_win_dir = -1
                elif active_win_dir == -1 and hist_val >= flip_threshold:
                    active_win_dir = 1

            is_win_start = False
            if curr_window is None or curr_window["dir"] != active_win_dir:
                is_win_start = True
                if curr_window is not None and idx > 0:
                    curr_window["end_idx"] = idx - 1
                    curr_window["end_time"] = m5_enriched[idx - 1]["time"]
                    curr_window["end_price"] = m5_enriched[idx - 1]["close"]
                    curr_window["net_pts"] = round(
                        curr_window["dir"] * (curr_window["end_price"] - curr_window["entry_price"]), 1
                    )
                    flow_windows.append(curr_window)

                curr_window = {
                    "id": f"WIN_{idx}_{time_str}",
                    "dir": active_win_dir,
                    "label": "JANELA DE COMPRA" if active_win_dir > 0 else "JANELA DE VENDA",
                    "start_idx": idx,
                    "start_time": time_str,
                    "entry_price": round(c, 2),
                    "max_favor_pts": 0.0,
                    "end_idx": idx,
                    "end_time": time_str,
                    "end_price": round(c, 2),
                    "net_pts": 0.0,
                }
            else:
                curr_window["end_idx"] = idx
                curr_window["end_time"] = time_str
                curr_window["end_price"] = round(c, 2)
                curr_window["net_pts"] = round(
                    curr_window["dir"] * (round(c, 2) - curr_window["entry_price"]), 1
                )
                fav_now = (round(h, 2) - curr_window["entry_price"]) if active_win_dir > 0 else (curr_window["entry_price"] - round(l, 2))
                if fav_now > curr_window["max_favor_pts"]:
                    curr_window["max_favor_pts"] = round(fav_now, 1)

            if active_win_dir == 1:
                candle_state = 1 if (round(c, 2) >= round(o, 2) or round(c, 2) >= p_mid_trava or cvd >= prev_cvd) else 0
            else:
                candle_state = -1 if (round(c, 2) <= round(o, 2) or round(c, 2) <= p_mid_trava or cvd <= prev_cvd) else 0

            nwe_val = float(nwe_arr[idx])
            nwe_mae = float(mae_arr[idx])
            nwe_slp = float(slope_arr[idx])
            nwe_pos = (c - nwe_val) / max(1e-6, float(mae_pos_arr[idx]))

            # ── 2º PASSO: ENTRADAS AVALIADAS EXCLUSIVAMENTE COM BARRA FECHADA (SEM REPINTAR) ──
            sig_dir = 0
            sig_type = ""
            sig_reason = ""
            nearest_w = None
            custom_tp_pts = target_pts
            custom_sl_pts = stop_pts
            custom_max_bars = max_val_bars
            custom_use_be = use_be_protection
            custom_be_trig = be_trigger_pts
            custom_be_lock = be_lock_pts

            if not is_prev_day_bar and is_bar_closed and rel_idx >= 1 and not use_champion_mode:
                # No modo Campeão (WIN Opção A e WDO Opção C), as frentes são avaliadas de forma
                # 100% cronológica no Passo 3 logo abaixo para compartilhar a mesma trava de posição única.
                in_champion_wall_window = ("09:30" <= time_str <= "11:30") if use_champion_mode else True

                if ts_raw in locked_map:
                    cached_sig = locked_map[ts_raw]
                    if cached_sig is not None:
                        sig_dir = cached_sig["sig_dir"]
                        sig_type = cached_sig["sig_type"]
                        sig_reason = cached_sig["sig_reason"]
                        nearest_w = cached_sig["nearest_w"]
                elif in_champion_wall_window:
                    if not align_with_window:
                        # ── METODOLOGIA 1 (PADRÃO): ANTECIPAÇÃO NA WALL + FLUXO INSTITUCIONAL ──
                        # 1. COMPRA POR ABSORÇÃO / DEFESA DE SUPORTE NA WALL
                        if (
                            sup_w is not None
                            and c >= l + 0.50 * rng
                            and (
                                (lower_wick >= 0.32 * rng and (delta_5m < 0 or inst_5m > 0))
                                or (inst_5m >= inst_thresh_5m * 0.45 and c > o)
                            )
                        ):
                            sig_dir = 1
                            nearest_w = sup_w
                            sig_type = "COMPRA · DEFESA NA WALL"
                            sig_reason = (
                                f"Defesa + Absorção no suporte {sup_w['type']} @ {sup_w['price']:{p_fmt}} "
                                f"(Delta Inst 5m: {inst_5m:+.0f}L | Pavio Defesa: {lower_wick:{p_fmt}}p)"
                            )

                        # 2. VENDA POR ABSORÇÃO / DEFESA DE RESISTÊNCIA NA WALL
                        elif (
                            res_w is not None
                            and c <= h - 0.50 * rng
                            and (
                                (upper_wick >= 0.32 * rng and (delta_5m > 0 or inst_5m < 0))
                                or (inst_5m <= -inst_thresh_5m * 0.45 and c < o)
                            )
                        ):
                            sig_dir = -1
                            nearest_w = res_w
                            sig_type = "VENDA · DEFESA NA WALL"
                            sig_reason = (
                                f"Rejeição + Absorção na resistência {res_w['type']} @ {res_w['price']:{p_fmt}} "
                                f"(Delta Inst 5m: {inst_5m:+.0f}L | Pavio Rejeição: {upper_wick:{p_fmt}}p)"
                            )

                        # 3. COMPRA POR FLUXO INSTITUCIONAL + DEALER (Apenas se M1 pura explícita)
                        elif (not use_champion_mode) and (
                            inst_5m >= inst_thresh_5m
                            and inst_15m >= inst_thresh_5m * (0.8 if is_neg_g else 1.35)
                            and imb_5m >= 9.0
                            and c > o
                            and (
                                is_neg_g
                                or (move_15m <= entry_scale_pts * 0.35 and body <= entry_scale_pts * 0.95)
                            )
                        ):
                            sig_dir = 1
                            sig_type = "COMPRA · FLUXO INSTITUCIONAL" + (" + SQUEEZE" if is_neg_g else "")
                            sig_reason = (
                                f"Agressão Institucional Forte (+{inst_5m:.0f}L em 5m / +{inst_15m:.0f}L em 15m) "
                                f"+ Desequilíbrio +{imb_5m:.1f}% ({'Gamma− Acelerador' if is_neg_g else 'Retomada na Base'})"
                            )

                        # 4. VENDA POR FLUXO INSTITUCIONAL + DEALER (Apenas se M1 pura explícita)
                        elif (not use_champion_mode) and (
                            inst_5m <= -inst_thresh_5m
                            and inst_15m <= -inst_thresh_5m * (0.8 if is_neg_g else 1.35)
                            and imb_5m <= -9.0
                            and c < o
                            and (
                                is_neg_g
                                or (move_15m >= -entry_scale_pts * 0.35 and body <= entry_scale_pts * 0.95)
                            )
                        ):
                            sig_dir = -1
                            sig_type = "VENDA · FLUXO INSTITUCIONAL" + (" + DROP" if is_neg_g else "")
                            sig_reason = (
                                f"Venda Institucional Forte ({inst_5m:.0f}L em 5m / {inst_15m:.0f}L em 15m) "
                                f"+ Desequilíbrio {imb_5m:.1f}% ({'Gamma− Acelerador' if is_neg_g else 'Pressão Vendedora'})"
                            )

                    elif active_win_dir == 1:
                        # ── METODOLOGIA 2: RESTRITA À JANELA VERDE (▲ COMPRAR) ──
                        if (
                            sup_w is not None
                            and c >= l + 0.50 * rng
                            and inst_5m >= -inst_thresh_5m * 0.25
                            and hist_val >= 8.0
                            and (
                                (lower_wick >= 0.32 * rng and (delta_5m < 0 or inst_5m > 0))
                                or (inst_5m >= inst_thresh_5m * 0.45 and c > o)
                            )
                        ):
                            sig_dir = 1
                            nearest_w = sup_w
                            sig_type = "COMPRA · DEFESA NA WALL"
                            sig_reason = (
                                f"Janela Verde + Defesa no suporte {sup_w['type']} @ {sup_w['price']:{p_fmt}} "
                                f"(Delta Inst 5m: {inst_5m:+.0f}L | Pavio Defesa: {lower_wick:{p_fmt}}p)"
                            )
                        elif (
                            inst_5m >= inst_thresh_5m
                            and inst_15m >= inst_thresh_5m * (0.8 if is_neg_g else 1.25)
                            and imb_5m >= 8.0
                            and c > o
                            and hist_val >= 10.0
                            and (
                                is_neg_g
                                or (move_15m <= entry_scale_pts * 1.15 and body <= entry_scale_pts * 1.4)
                            )
                        ):
                            sig_dir = 1
                            sig_type = "COMPRA · FLUXO INSTITUCIONAL" + (" + SQUEEZE" if is_neg_g else "")
                            sig_reason = (
                                f"Janela Verde + Agressão Institucional Forte (+{inst_5m:.0f}L em 5m / +{inst_15m:.0f}L em 15m) "
                                f"+ Desequilíbrio +{imb_5m:.1f}%"
                            )
                        elif (
                            (is_win_start or prev_candle_state == 0)
                            and candle_state == 1
                            and c > o
                            and inst_5m >= inst_thresh_5m * 0.65
                            and inst_15m >= 0
                            and hist_val >= 12.0
                        ):
                            sig_dir = 1
                            sig_type = "COMPRA · RETOMADA NA JANELA"
                            sig_reason = (
                                f"{'Abertura de Janela Verde' if is_win_start else 'Fim de Pullback na Janela Verde'} "
                                f"com Entrada Institucional (+{inst_5m:.0f}L em 5m)"
                            )

                    elif active_win_dir == -1:
                        # ── METODOLOGIA 2: RESTRITA À JANELA VERMELHA (▼ VENDER) ──
                        if (
                            res_w is not None
                            and c <= h - 0.50 * rng
                            and inst_5m <= inst_thresh_5m * 0.25
                            and hist_val <= -8.0
                            and (
                                (upper_wick >= 0.32 * rng and (delta_5m > 0 or inst_5m < 0))
                                or (inst_5m <= -inst_thresh_5m * 0.45 and c < o)
                            )
                        ):
                            sig_dir = -1
                            nearest_w = res_w
                            sig_type = "VENDA · DEFESA NA WALL"
                            sig_reason = (
                                f"Janela Vermelha + Rejeição na resistência {res_w['type']} @ {res_w['price']:{p_fmt}} "
                                f"(Delta Inst 5m: {inst_5m:+.0f}L | Pavio Rejeição: {upper_wick:{p_fmt}}p)"
                            )
                        elif (
                            inst_5m <= -inst_thresh_5m
                            and inst_15m <= -inst_thresh_5m * (0.8 if is_neg_g else 1.25)
                            and imb_5m <= -8.0
                            and c < o
                            and hist_val <= -10.0
                            and (
                                is_neg_g
                                or (move_15m >= -entry_scale_pts * 1.15 and body <= entry_scale_pts * 1.4)
                            )
                        ):
                            sig_dir = -1
                            sig_type = "VENDA · FLUXO INSTITUCIONAL" + (" + DROP" if is_neg_g else "")
                            sig_reason = (
                                f"Janela Vermelha + Venda Institucional Forte ({inst_5m:.0f}L em 5m / {inst_15m:.0f}L em 15m) "
                                f"+ Desequilíbrio {imb_5m:.1f}%"
                            )
                        elif (
                            (is_win_start or prev_candle_state == 0)
                            and candle_state == -1
                            and c < o
                            and inst_5m <= -inst_thresh_5m * 0.65
                            and inst_15m <= 0
                            and hist_val <= -12.0
                        ):
                            sig_dir = -1
                            sig_type = "VENDA · RETOMADA NA JANELA"
                            sig_reason = (
                                f"{'Abertura de Janela Vermelha' if is_win_start else 'Fim de Pullback na Janela Vermelha'} "
                                f"com Venda Institucional ({inst_5m:.0f}L em 5m)"
                            )

                    # Verifica cooldown usando rel_idx + Trava Estrita de Posição (busy_until_idx: sem sobrepor ordens abertas)
                    if (
                        sig_dir != 0
                        and idx > busy_until_idx
                        and (rel_idx - last_sig_idx_by_dir[sig_dir]) >= 5
                        and (rel_idx - last_any_sig_idx) >= 3
                    ):
                        locked_map[ts_raw] = {
                            "sig_dir": sig_dir,
                            "sig_type": sig_type,
                            "sig_reason": sig_reason,
                            "nearest_w": nearest_w,
                        }
                    else:
                        sig_dir = 0
                        locked_map[ts_raw] = None
                else:
                    locked_map[ts_raw] = None

            if is_bar_closed:
                prev_candle_state = candle_state

            # Cooldown de 5 barras (25 min) para mesma direção e 3 barras (15 min) geral para sinais limpos
            sig_obj = None
            if sig_dir != 0:
                last_sig_idx_by_dir[sig_dir] = rel_idx
                last_any_sig_idx = rel_idx

                # Para WDO no modo Campeão (Absorção MagicWall 09:30-11:30), BE é +1.5p após +4.5p (TP 10 / SL 10)
                eff_be_trig = 4.5 if (use_champion_mode and not is_win) else custom_be_trig
                eff_be_lock = 1.5 if (use_champion_mode and not is_win) else custom_be_lock

                # Validação para frente EXCLUSIVAMENTE em barras M5 FECHADAS (nunca usa a barra em formação)
                future_bars = m5_series[idx + 1 : min(closed_end, idx + 1 + custom_max_bars)]
                pnl_5m = (
                    sig_dir * (float(m5_series[idx + 1]["close"]) - c)
                    if (idx + 1) < closed_end
                    else None
                )
                pnl_15m = (
                    sig_dir * (float(m5_series[idx + 3]["close"]) - c)
                    if (idx + 3) < closed_end
                    else None
                )
                pnl_30m = (
                    sig_dir * (float(m5_series[idx + 6]["close"]) - c)
                    if (idx + 6) < closed_end
                    else None
                )

                mfe_30m = 0.0
                mae_30m = 0.0
                hit_target_first = False
                hit_stop_first = False
                hit_be_lock = False
                be_armed = False
                be_armed_idx = None
                be_armed_time = None
                realized_pts = 0.0
                trade_exit_idx = min(closed_end - 1, idx + custom_max_bars) if future_bars else idx

                for f_off, fb in enumerate(future_bars):
                    fo = float(fb.get("open", fb["close"]))
                    fh = float(fb.get("high", fb["close"]))
                    fl = float(fb.get("low", fb["close"]))
                    fc = float(fb.get("close", c))
                    fav = (fh - c) if sig_dir > 0 else (c - fl)
                    adv = (fl - c) if sig_dir > 0 else (c - fh)  # <= 0 quando anda contra
                    if fav > mfe_30m:
                        mfe_30m = fav
                    if adv < mae_30m:
                        mae_30m = adv

                    eff_stop = -eff_be_lock if (custom_use_be and be_armed) else custom_sl_pts

                    if not hit_target_first and not hit_stop_first and not hit_be_lock:
                        # Execução Intra-Barra 100% Conservadora/Fidedigna: se tocar Stop/BE na barra (mesmo que também toque Alvo), contabiliza Stop/BE primeiro
                        if adv <= -eff_stop:
                            if eff_stop < 0:
                                hit_be_lock = True
                                realized_pts = -eff_stop
                            else:
                                hit_stop_first = True
                                realized_pts = -custom_sl_pts
                            trade_exit_idx = idx + 1 + f_off
                            break
                        elif fav >= custom_tp_pts:
                            hit_target_first = True
                            realized_pts = custom_tp_pts
                            trade_exit_idx = idx + 1 + f_off
                            break

                    if custom_use_be and not be_armed and fav >= eff_be_trig:
                        be_armed = True
                        be_armed_idx = idx + 1 + f_off
                        f_ts = int(fb.get("time", 0))
                        be_armed_time = (
                            datetime.fromtimestamp(f_ts, tz=timezone.utc).strftime("%H:%M")
                            if f_ts > 100000
                            else str(fb.get("time", ""))
                        )

                busy_until_idx = max(busy_until_idx, trade_exit_idx)
                occupied_intervals.append((idx, trade_exit_idx))

                # Classificação imutável da validade do sinal (só encerra por Alvo, Stop/BE ou Time-Stop em barras fechadas)
                if hit_target_first:
                    val_status = "VALIDO_ALVO"
                    val_label = f"✅ ALVO (+{custom_tp_pts:{p_fmt}} pts)"
                    is_valid = True
                    fb_exit_reason = "TP"
                elif hit_be_lock:
                    val_status = "VALIDO_FAVORAVEL"
                    val_label = f"✅ PROTEÇÃO BE (+{realized_pts:{p_fmt}} pts)"
                    is_valid = True
                    fb_exit_reason = "BE"
                elif hit_stop_first:
                    val_status = "INVALIDO_STOP"
                    val_label = f"❌ STOP (-{custom_sl_pts:{p_fmt}} pts)"
                    is_valid = False
                    fb_exit_reason = "SL"
                elif len(future_bars) < custom_max_bars and is_live_session:
                    val_status = "EM_ANDAMENTO"
                    val_label = "⏳ EM ABERTO (Barra Fechada)"
                    is_valid = None
                    realized_pts = 0.0
                    fb_exit_reason = "ABERTA"
                else:
                    # Janela de Time-Stop concluída sem tocar alvo nem stop: trava no fechamento real da barra final
                    end_close = float(future_bars[-1]["close"]) if future_bars else c
                    realized_pts = round(sig_dir * (end_close - c), 1)
                    fb_exit_reason = "TEMPO"
                    if realized_pts > 0:
                        val_status = "VALIDO_FAVORAVEL"
                        val_label = f"✅ A FAVOR (+{realized_pts:{p_fmt}} pts)"
                        is_valid = True
                    else:
                        val_status = "INVALIDO_CONTRA"
                        val_label = f"❌ CONTRA ({realized_pts:{p_fmt}} pts)"
                        is_valid = False

                ex_bar_raw = m5_series[min(len(m5_series) - 1, trade_exit_idx)]
                ex_ts_raw = int(ex_bar_raw.get("time", 0))
                ex_time_str = (
                    datetime.fromtimestamp(ex_ts_raw, tz=timezone.utc).strftime("%H:%M")
                    if ex_ts_raw > 100000
                    else str(ex_bar_raw.get("time", time_str))
                )
                ex_px = round(float(m5_series[-1]["close"]), 2) if val_status == "EM_ANDAMENTO" else round(c + sig_dir * realized_pts, 2)

                sig_obj = {
                    "id": f"{asset}_{time_str}_{ 'BUY' if sig_dir > 0 else 'SELL' }",
                    "bar_index": idx,
                    "timestamp": ts_raw,
                    "time": time_str,
                    "direction": "COMPRA" if sig_dir > 0 else "VENDA",
                    "dir_num": sig_dir,
                    "type": sig_type,
                    "entry_price": round(c, 2),
                    "exit_bar_index": trade_exit_idx,
                    "exit_time": ex_time_str,
                    "exit_price": ex_px,
                    "exit_reason": fb_exit_reason,
                    "stop_price": round(c - sig_dir * custom_sl_pts, 2),
                    "tp_price": round(c + sig_dir * custom_tp_pts, 2),
                    "be_triggered": bool(be_armed),
                    "be_bar_index": be_armed_idx,
                    "be_time": be_armed_time,
                    "be_trigger_price": round(c + sig_dir * eff_be_trig, 2) if custom_use_be else None,
                    "be_stop_price": round(c + sig_dir * eff_be_lock, 2) if custom_use_be else None,
                    "wall_price": round(nearest_w["price"], 2) if nearest_w else None,
                    "wall_type": nearest_w["type"] if nearest_w else None,
                    "inst_delta_5m": round(inst_5m, 0),
                    "dealer_hedge_5m": round(hf["dealer_hedge_contracts"], 0),
                    "reason": sig_reason,
                    "pnl_5m": round(pnl_5m, 1) if pnl_5m is not None else None,
                    "pnl_15m": round(pnl_15m, 1) if pnl_15m is not None else None,
                    "pnl_30m": round(pnl_30m, 1) if pnl_30m is not None else None,
                    "mfe_30m": round(mfe_30m, 1),
                    "mae_30m": round(mae_30m, 1),
                    "realized_pts": round(realized_pts, 1),
                    "validation_status": val_status,
                    "validation_label": val_label,
                    "is_valid": is_valid,
                    "is_prev_day": is_prev_day_bar,
                    "closed_bar_confirmed": True,
                }
                if not is_prev_day_bar:
                    signals_log.append(sig_obj)

            b_avg_bl = float(b.get("avg_buy_lot", 3.1 if is_win else 4.0) or (3.1 if is_win else 4.0))
            b_avg_sl = float(b.get("avg_sell_lot", 3.1 if is_win else 4.0) or (3.1 if is_win else 4.0))
            b_lot_imb = float(b.get("lot_imb") or (b_avg_bl / max(0.1, b_avg_sl)))
            b_iagg = round(float(b.get("inst_aggr_delta", inst_5m)), 0)
            b_ipas = round(float(b.get("inst_pass_delta", 0.0)), 0)
            b_ret_d = round(float(b.get("ret_delta_bar", delta_5m - inst_5m)), 0)
            b_hft_d = round(float(b.get("hft_delta_bar", delta_5m - b_iagg - b_ret_d)), 0)
            b_hft_v = round(float(b.get("hft_vol_bar", (float(b.get("buy_vol", 0.0)) + float(b.get("sell_vol", 0.0))) * 0.35)), 0)
            b_hft_ch = round(float(b.get("hft_churn_pct", 36.0)), 1)
            b_rlp_v = round(float(b.get("rlp_vol_bar", 0.0)), 0)
            b_rlp_sh = round(float(b.get("rlp_share_pct", b.get("rlp_pct", 0.0))), 1)
            b_rlp_d = round(float(b.get("rlp_delta_bar", -b_ret_d * max(0.32, min(0.75, b_rlp_sh / 100.0)))), 0)

            cum_iagg += b_iagg
            cum_ipas += b_ipas
            cum_hft += b_hft_d
            cum_rlp += b_rlp_v
            cum_rlp_d += b_rlp_d

            raw_cvd_iagg = b.get("cvd_inst_aggr")
            raw_cvd_ipas = b.get("cvd_inst_pass")
            raw_cvd_hft = b.get("cvd_hft")
            raw_cvd_rlp = b.get("cvd_rlp")
            raw_cvd_rlp_d = b.get("cvd_rlp_delta")

            m5_enriched.append({
                "timestamp": ts_raw,
                "time": time_str,
                "is_prev_day": is_prev_day_bar,
                "is_bar_closed": is_bar_closed,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "buy_vol": round(float(b.get("buy_vol", 0.0)), 0),
                "sell_vol": round(float(b.get("sell_vol", 0.0)), 0),
                "inst_delta_bar": round(inst_5m, 0),
                "inst_aggr_delta": b_iagg,
                "inst_pass_delta": b_ipas,
                "ret_delta_bar": b_ret_d,
                "hft_delta_bar": b_hft_d,
                "hft_vol_bar": b_hft_v,
                "hft_churn_pct": b_hft_ch,
                "rlp_vol_bar": b_rlp_v,
                "rlp_delta_bar": b_rlp_d,
                "rlp_deals_bar": int(b.get("rlp_deals_bar", 0) or 0),
                "rlp_share_pct": b_rlp_sh,
                "rlp_pct": b_rlp_sh,
                "avg_buy_lot": round(b_avg_bl, 2),
                "avg_sell_lot": round(b_avg_sl, 2),
                "lot_imb": round(b_lot_imb, 3),
                "delta_bar": round(delta_5m, 0),
                "cvd_total": round(float(b.get("cvd_total", cvd + float(b.get("cvd_retail", 0.0)))), 0),
                "cvd_inst": cvd,
                "cvd_inst_aggr": round(float(raw_cvd_iagg) if raw_cvd_iagg is not None else cum_iagg, 0),
                "cvd_inst_pass": round(float(raw_cvd_ipas) if (raw_cvd_ipas is not None and float(raw_cvd_ipas) != 0.0) else cum_ipas, 0),
                "cvd_hft": round(float(raw_cvd_hft) if (raw_cvd_hft is not None and float(raw_cvd_hft) != 0.0) else cum_hft, 0),
                "cvd_retail": round(float(b["cvd_retail"]), 0),
                "cvd_rlp": round(float(raw_cvd_rlp) if (raw_cvd_rlp is not None and float(raw_cvd_rlp) != 0.0) else cum_rlp, 0),
                "cvd_rlp_delta": round(float(raw_cvd_rlp_d) if (raw_cvd_rlp_d is not None and float(raw_cvd_rlp_d) != 0.0) else cum_rlp_d, 0),
                "dealer_hedge_bar": hf["dealer_hedge_contracts"],
                "dealer_hedge_open": round(prev_cum_dealer, 0),
                "cum_dealer_hedge": round(cum_dealer_hedge, 0),
                "dealer_score_bar": round(dp_score_bar, 1),
                "makers_pct_bar": makers_pct_bar,
                "gex_magnet_pct": gex_magnet_pct_bar,
                "gex_magnet_wall": gex_magnet_wall,
                "gex_regime_bar": "NEG" if is_neg_g else "POS",
                "gex_norm_gamma": loc_g["normalized_gamma_pct"],
                "signal": sig_obj,
                "price_upper_trava": p_upper_trava,
                "price_lower_trava": p_lower_trava,
                "price_mid_trava": p_mid_trava,
                "nwe_line": round(nwe_val, 2),
                "nwe_mae": round(nwe_mae, 2),
                "nwe_upper": round(nwe_val + nwe_mae * 1.8, 2),
                "nwe_lower": round(nwe_val - nwe_mae * 1.8, 2),
                "nwe_slope": round(nwe_slp, 2),
                "nwe_is_up": bool(nwe_slp >= 0),
                "nwe_pos_band": round(nwe_pos, 2),
                "sup_w": sup_w,
                "res_w": res_w,
                "min_2bar": round(min_2bar, 2),
                "max_2bar": round(max_2bar, 2),
                "lower_wick": round(lower_wick, 2),
                "upper_wick": round(upper_wick, 2),
                "rng": round(rng, 2),
                "flow_open": round(prev_cvd, 0),
                "flow_close": round(cvd, 0),
                "flow_upper_trava": flow_upper_trava,
                "flow_lower_trava": flow_lower_trava,
                "flow_hist": hist_val,
                "window_dir": active_win_dir,
                "window_entry_price": curr_window["entry_price"],
                "is_window_start": is_win_start,
                "candle_state": candle_state,
            })

        if curr_window is not None:
            flow_windows.append(curr_window)

        # ── 2.5º PASSO: MATEMÁTICA DE FLUXO EFETIVO INDEPENDENTE DE CORRETORA (KYLE-WYCKOFF + PORTE + SMART WAVE) & DETECTOR DE DIVERGÊNCIA TOPO/FUNDO ──
        n_enr = len(m5_enriched)
        if n_enr > 0:
            closes_enr = np.array([float(eb["close"]) for eb in m5_enriched], dtype=float)
            closes_enr_all = (
                np.concatenate([np.array(warmup_closes, dtype=float), closes_enr])
                if w_len > 0
                else closes_enr
            )
            n30_c_all, n30_u_all, n30_l_all, _, n30_s_all = self._compute_mt5_nwe_series(closes_enr_all, 30, 3.0, 1.6)
            n30_c_enr = n30_c_all[w_len:]
            n30_u_enr = n30_u_all[w_len:]
            n30_l_enr = n30_l_all[w_len:]
            n30_s_enr = n30_s_all[w_len:]
            prev_n30_u = float(n30_u_all[w_len - 1]) if w_len > 0 else None
            prev_n30_l = float(n30_l_all[w_len - 1]) if w_len > 0 else None
            # NWE100 (L=100, bw=8, mult=3 — mesma do UpdateNWE do MT5): só para exibição no painel 5176
            n100_c_all, n100_u_all, n100_l_all, _, n100_s_all = self._compute_mt5_nwe_series(closes_enr_all, 100, 8.0, 3.0)
            # NWE50 (L=50, bw=8, mult=3 — a dos filtros de contexto do especialista): só para exibição
            n50v_c_all, n50v_u_all, n50v_l_all, _, n50v_s_all = self._compute_mt5_nwe_series(closes_enr_all, 50, 8.0, 3.0)
            tick_sz_val = 5.0 if is_win else 0.5
            cum_eff = 0.0
            ema_eff_fast = 0.0
            ema_eff_slow = 0.0
            for i_e, eb in enumerate(m5_enriched):
                eb["nwe30_line"] = round(float(n30_c_enr[i_e]), 2)
                eb["nwe30_upper"] = round(float(n30_u_enr[i_e]), 2)
                eb["nwe30_lower"] = round(float(n30_l_enr[i_e]), 2)
                eb["nwe30_is_up"] = bool(float(n30_s_enr[i_e]) >= 0)
                eb["nwe100_line"] = round(float(n100_c_all[w_len + i_e]), 2)
                eb["nwe100_upper"] = round(float(n100_u_all[w_len + i_e]), 2)
                eb["nwe100_lower"] = round(float(n100_l_all[w_len + i_e]), 2)
                eb["nwe100_is_up"] = bool(float(n100_s_all[w_len + i_e]) >= 0)
                eb["nwe50_line"] = round(float(n50v_c_all[w_len + i_e]), 2)
                eb["nwe50_upper"] = round(float(n50v_u_all[w_len + i_e]), 2)
                eb["nwe50_lower"] = round(float(n50v_l_all[w_len + i_e]), 2)
                eb["nwe50_is_up"] = bool(float(n50v_s_all[w_len + i_e]) >= 0)
                if i_e == 0 and prev_n30_u is not None and prev_n30_l is not None:
                    eb["nwe30_prev_upper"] = round(prev_n30_u, 2)
                    eb["nwe30_prev_lower"] = round(prev_n30_l, 2)
                if eb.get("is_prev_day", False) and i_e == 0:
                    cum_eff = 0.0
                if i_e == first_today_idx:
                    cum_eff = 0.0
                    ema_eff_fast = 0.0
                    ema_eff_slow = 0.0
                o_e, h_e, l_e, c_e = float(eb["open"]), float(eb["high"]), float(eb["low"]), float(eb["close"])
                rng_e = max(h_e - l_e, tick_sz_val)
                bv_e = float(eb.get("buy_vol", 0.0))
                sv_e = float(eb.get("sell_vol", 0.0))
                tv_e = max(1.0, bv_e + sv_e)
                lw_e = max(0.0, min(o_e, c_e) - l_e)
                uw_e = max(0.0, h_e - max(o_e, c_e))

                # 1) Absorção Oculta na Pedra (Lei de Esforço vs. Resultado de Wyckoff / Kyle):
                # Mede quantos lotes vendedores bateram e foram absorvidos/devolvidos acima da mínima vs. quantos lotes compradores foram absorvidos abaixo da máxima
                abs_buy_w = sv_e * ((c_e - l_e) / rng_e) * (0.80 + 1.40 * (lw_e / rng_e))
                abs_sell_w = bv_e * ((h_e - c_e) / rng_e) * (0.80 + 1.40 * (uw_e / rng_e))
                phi_wyckoff = round(abs_buy_w - abs_sell_w, 0)

                # 2) Assimetria de Porte / Ticket Médio (Urgência de Lote Grande, 100% independente da corretora que executou):
                bl_e = float(eb.get("avg_buy_lot", 3.1 if is_win else 4.0))
                sl_e = float(eb.get("avg_sell_lot", 3.1 if is_win else 4.0))
                phi_porte = round(tv_e * ((bl_e - sl_e) / max(0.5, bl_e + sl_e)) * 2.2, 0)

                # 3) Pressão Institucional + Defesa Passiva contra Armadilha de Varejo:
                iagg_e = float(eb.get("inst_aggr_delta", eb.get("inst_delta_bar", 0.0)))
                ipas_e = float(eb.get("inst_pass_delta", 0.0))
                ret_e = float(eb.get("ret_delta_bar", 0.0))
                phi_inst = round(0.55 * iagg_e + 1.15 * ipas_e - 0.85 * ret_e, 0)

                # Força Efetiva da Barra (combinação física dos 3 motores):
                bar_force = round(0.45 * phi_wyckoff + 0.25 * phi_porte + 0.30 * phi_inst, 0)
                eb["wyckoff_abs_bar"] = phi_wyckoff
                eb["lot_urgency_bar"] = phi_porte
                eb["smart_inst_bar"] = phi_inst
                eb["effective_force_bar"] = bar_force

                f_prev1 = float(m5_enriched[i_e - 1]["effective_force_bar"]) if i_e > first_today_idx else bar_force
                f_prev2 = float(m5_enriched[i_e - 2]["effective_force_bar"]) if i_e > first_today_idx + 1 else f_prev1
                swing_impulse_3b = round(0.45 * bar_force + 0.35 * f_prev1 + 0.20 * f_prev2, 0)

                cum_eff += bar_force
                if i_e == first_today_idx:
                    ema_eff_fast = cum_eff
                    ema_eff_slow = cum_eff
                else:
                    ema_eff_fast = 0.50 * cum_eff + 0.50 * ema_eff_fast
                    ema_eff_slow = (2.0 / 11.0) * cum_eff + (1.0 - 2.0 / 11.0) * ema_eff_slow

                # Onda Estrutural de Swing (combina o impulso de 3 barras e o CVD Efetivo sem viés de tendência matinal):
                detrended_cvd = ema_eff_fast - ema_eff_slow
                smart_wave = round(0.55 * detrended_cvd + 0.45 * swing_impulse_3b, 0)
                eb["smart_swing_wave"] = smart_wave
                eb["swing_impulse_3b"] = swing_impulse_3b
                eb["swing_divergence"] = None

            # Detector Causal de Divergências de Topo e Fundo (Preço Faz Fundo Mais Baixo / Topo Mais Alto vs. Onda de Fluxo Faz Fundo Mais Alto / Topo Mais Baixo)
            price_tol = 40.0 if is_win else 1.0
            max_price_ext = 360.0 if is_win else 8.5
            min_wave_diff = 1800.0 if is_win else 320.0
            last_bull_div_idx = -12
            last_bear_div_idx = -12
            for i_e in range(max(first_today_idx + 4, 4), n_enr):
                eb = m5_enriched[i_e]
                if eb.get("is_prev_day", False):
                    continue
                l_i, h_i, c_i, o_i = float(eb["low"]), float(eb["high"]), float(eb["close"]), float(eb["open"])
                rng_i = max(h_i - l_i, tick_sz_val)
                w_i = float(eb["smart_swing_wave"])
                near_wall_i = bool(eb.get("sup_w") or eb.get("res_w")) or any(
                    abs(l_i - w["price"]) <= wall_radius or abs(h_i - w["price"]) <= wall_radius
                    for w in walls_clean
                )

                # 1. DIVERGÊNCIA ALTISTA DE FUNDO (Preço: Fundo Mais Baixo / Duplo ↘ vs. Fluxo Efetivo: Fundo Mais Alto ↗)
                is_local_low = (
                    l_i <= min(float(m5_enriched[i_e - 1]["low"]), float(m5_enriched[i_e - 2]["low"]))
                    and (i_e == n_enr - 1 or l_i <= float(m5_enriched[i_e + 1]["low"]) + tick_sz_val)
                )
                if is_local_low and ((c_i - l_i) / rng_i >= 0.40 or c_i >= o_i) and (
                    float(eb["effective_force_bar"]) > 0 or float(eb["wyckoff_abs_bar"]) > 0 or w_i > 0
                ):
                    for k_p in range(i_e - 3, max(first_today_idx + 1, i_e - 16), -1):
                        kb = m5_enriched[k_p]
                        l_k = float(kb["low"])
                        if l_k <= float(m5_enriched[k_p - 1]["low"]) and l_k <= float(m5_enriched[k_p + 1]["low"]):
                            w_k = float(kb["smart_swing_wave"])
                            sv_2b_i = float(eb["sell_vol"]) + float(m5_enriched[i_e - 1]["sell_vol"])
                            sv_2b_k = float(kb["sell_vol"]) + float(m5_enriched[k_p - 1]["sell_vol"])
                            sell_exhausted = sv_2b_i < 0.88 * sv_2b_k
                            if (
                                (l_k - max_price_ext) <= l_i <= (l_k + price_tol)
                                and w_i > w_k + min_wave_diff
                                and (w_k < 0 or float(eb["wyckoff_abs_bar"]) > 0 or sell_exhausted)
                            ):
                                dom_drv = (
                                    "ABSORÇÃO NA PEDRA (WYCKOFF)"
                                    if float(eb["wyckoff_abs_bar"]) >= max(float(eb["lot_urgency_bar"]), float(eb["smart_inst_bar"]))
                                    else ("PORTE / LOTE GRANDE COMPRADOR" if float(eb["lot_urgency_bar"]) >= float(eb["smart_inst_bar"]) else "EXAUSTÃO VENDEDORA + PASSIVO")
                                )
                                div_obj = {
                                    "type": "BULL_DIV",
                                    "label": "🟢 DIV. COMPRA",
                                    "prev_idx": k_p,
                                    "prev_time": kb["time"],
                                    "prev_price": round(l_k, 2),
                                    "prev_wave": round(w_k, 0),
                                    "curr_idx": i_e,
                                    "curr_time": eb["time"],
                                    "curr_price": round(l_i, 2),
                                    "curr_wave": round(w_i, 0),
                                    "near_wall": near_wall_i,
                                    "sell_exhaust_pct": round((1.0 - sv_2b_i / max(1.0, sv_2b_k)) * 100.0, 0),
                                    "driver": dom_drv,
                                }
                                if i_e - last_bull_div_idx <= 6 and last_bull_div_idx >= 0:
                                    prev_div = m5_enriched[last_bull_div_idx].get("swing_divergence")
                                    if prev_div and l_i <= prev_div["curr_price"]:
                                        m5_enriched[last_bull_div_idx]["swing_divergence"] = None
                                        eb["swing_divergence"] = div_obj
                                        last_bull_div_idx = i_e
                                else:
                                    eb["swing_divergence"] = div_obj
                                    last_bull_div_idx = i_e
                                break

                # 2. DIVERGÊNCIA BAIXISTA DE TOPO (Preço: Topo Mais Alto / Duplo ↗ vs. Fluxo Efetivo: Topo Mais Baixo ↘)
                is_local_high = (
                    h_i >= max(float(m5_enriched[i_e - 1]["high"]), float(m5_enriched[i_e - 2]["high"]))
                    and (i_e == n_enr - 1 or h_i >= float(m5_enriched[i_e + 1]["high"]) - tick_sz_val)
                )
                if eb["swing_divergence"] is None and is_local_high and ((h_i - c_i) / rng_i >= 0.40 or c_i <= o_i) and (
                    float(eb["effective_force_bar"]) < 0 or float(eb["wyckoff_abs_bar"]) < 0 or w_i < 0
                ):
                    for k_p in range(i_e - 3, max(first_today_idx + 1, i_e - 16), -1):
                        kb = m5_enriched[k_p]
                        h_k = float(kb["high"])
                        if h_k >= float(m5_enriched[k_p - 1]["high"]) and h_k >= float(m5_enriched[k_p + 1]["high"]):
                            w_k = float(kb["smart_swing_wave"])
                            bv_2b_i = float(eb["buy_vol"]) + float(m5_enriched[i_e - 1]["buy_vol"])
                            bv_2b_k = float(kb["buy_vol"]) + float(m5_enriched[k_p - 1]["buy_vol"])
                            buy_exhausted = bv_2b_i < 0.88 * bv_2b_k
                            if (
                                (h_k - price_tol) <= h_i <= (h_k + max_price_ext)
                                and w_i < w_k - min_wave_diff
                                and (w_k > 0 or float(eb["wyckoff_abs_bar"]) < 0 or buy_exhausted)
                            ):
                                dom_drv = (
                                    "ABSORÇÃO VENDEDORA (WYCKOFF)"
                                    if abs(float(eb["wyckoff_abs_bar"])) >= max(abs(float(eb["lot_urgency_bar"])), abs(float(eb["smart_inst_bar"])))
                                    else ("PORTE / LOTE GRANDE VENDEDOR" if abs(float(eb["lot_urgency_bar"])) >= abs(float(eb["smart_inst_bar"])) else "EXAUSTÃO COMPRADORA + PASSIVO")
                                )
                                div_obj = {
                                    "type": "BEAR_DIV",
                                    "label": "🔴 DIV. VENDA",
                                    "prev_idx": k_p,
                                    "prev_time": kb["time"],
                                    "prev_price": round(h_k, 2),
                                    "prev_wave": round(w_k, 0),
                                    "curr_idx": i_e,
                                    "curr_time": eb["time"],
                                    "curr_price": round(h_i, 2),
                                    "curr_wave": round(w_i, 0),
                                    "near_wall": near_wall_i,
                                    "buy_exhaust_pct": round((1.0 - bv_2b_i / max(1.0, bv_2b_k)) * 100.0, 0),
                                    "driver": dom_drv,
                                }
                                if i_e - last_bear_div_idx <= 6 and last_bear_div_idx >= 0:
                                    prev_div = m5_enriched[last_bear_div_idx].get("swing_divergence")
                                    if prev_div and h_i >= prev_div["curr_price"]:
                                        m5_enriched[last_bear_div_idx]["swing_divergence"] = None
                                        eb["swing_divergence"] = div_obj
                                        last_bear_div_idx = i_e
                                else:
                                    eb["swing_divergence"] = div_obj
                                    last_bear_div_idx = i_e
                                break

        # ── 3º PASSO: MODO CAMPEÃO 6 ESTRATÉGIAS C/ FILTRO DE FLUXO (WIN: EST_01 + EST_07 + EST_13 | WDO: WDO_09 + WDO_11 + WDO_S2) ──
        if use_champion_mode:
            today_closed_bars = [
                (i, eb) for i, eb in enumerate(m5_enriched)
                if not eb.get("is_prev_day", False)
            ]
            # Runner ÚNICO dos setups (core/setups_runner.py): o mesmo código do BT, com corte na última barra
            # fechada no pregão corrente. Substitui a reimplementação `_evaluate_live_mt5_*_strategies`.
            cached_bt_trades = self._get_setup_trades(str(sess_date or ""), asset.upper(), is_live_session)
            strat_short_names = {
                "EST_01": "WIN Rejeição",
                "EST_04": "WIN-B1 Virou Sup/Res",
                "EST_07": "WIN-C1 Romperam Wall",
                "EST_13": "WIN Next Wall",
                "EST_14": "WIN-A1 Vai Defender",
                "EST_15": "WIN Grid Z30",
                "EST_16": "WIN Spring",
                "WIN_E2": "WIN-E2 Wall Gasta",
                "WIN_DIV_WALL": "WIN Div 2L Mix",
                "WDO_01": "WDO-A1 Scalper NY",
                "WDO_02": "WDO Scalper",
                "WDO_05": "WDO Cluster NWE",
                "WDO_07": "WDO-B1 Violinada",
                "WDO_09": "WDO Pullback",
                "WDO_10": "WDO-A2 Vai Defender",
                "WDO_11": "WDO Next Wall",
                "WDO_S2": "WDO Lunch",
                "WDO_DIV_WALL": "WDO Div 1L MidWall",
                "ESP_DIV_V22_WIN": "WIN Especialista V3.2",
                "C1a_BRK_WIN": "WIN Brk Conv C1a",
                "V1a_DIV_WDO": "WDO Div V3.2 V1a",
                "SYM_DIV_WIN": "WIN Simétrica V3.2",
                "SYM_DIV_WDO": "WDO Simétrica V3.2",
            }
            if cached_bt_trades is not None:
                signals_log = []
                for eb in m5_enriched:
                    eb["signal"] = None
                time_to_idx = {eb["time"]: i for i, eb in today_closed_bars}
                for tr_idx, tr in enumerate(cached_bt_trades):
                    t_in = str(tr.get("time", "10:00"))
                    t_out = str(tr.get("exit_time", t_in))
                    b_idx = time_to_idx.get(t_in)
                    if b_idx is None and today_closed_bars:
                        b_idx = min(today_closed_bars, key=lambda x: abs(int(x[1]["time"][:2]) * 60 + int(x[1]["time"][3:5]) - (int(t_in[:2]) * 60 + int(t_in[3:5]))))[0]
                    if b_idx is None:
                        continue
                    ex_idx = time_to_idx.get(t_out, min(len(m5_enriched) - 1, b_idx + 3))
                    if ex_idx < b_idx:
                        ex_idx = min(len(m5_enriched) - 1, b_idx + 2)
                    eb = m5_enriched[b_idx]
                    ex_eb = m5_enriched[min(len(m5_enriched) - 1, ex_idx)]
                    sid = str(tr.get("strategy_id", "EST_01" if is_win else "WDO_09"))
                    short_nm = strat_short_names.get(sid, sid)
                    s_dir = 1 if tr.get("direction") == "COMPRA" else -1
                    pts = float(tr.get("pts", 0.0))
                    epx = float(tr.get("entry_price") or eb["close"])
                    xpx = float(tr.get("exit_price") or (epx + s_dir * (pts * 0.5 if sid == "WIN_DIV_WALL" else pts)))
                    w_ref_obj = eb.get("sup_w") if s_dir > 0 else eb.get("res_w")
                    w_ref_px = float(w_ref_obj["price"]) if (w_ref_obj and w_ref_obj.get("price") is not None) else None
                    sl_px = float(tr.get("stop_price") or (epx - s_dir * (260.0 if sid == "WIN_DIV_WALL" else (240.0 if is_win else 10.0))))
                    _cart_v32_ids = ("C1a_BRK_WIN", "V1a_DIV_WDO", "SYM_DIV_WIN", "SYM_DIV_WDO")
                    _no_snap_ids = ("WIN_DIV_WALL", "ESP_DIV_V22_WIN") + _cart_v32_ids
                    _walls_flow_ids = ("WIN_DIV_WALL", "WDO_DIV_WALL", "ESP_DIV_V22_WIN") + _cart_v32_ids
                    if w_ref_px is not None and sid not in _no_snap_ids:
                        w_buf = 60.0 if is_win else 3.0
                        sl_px = min(sl_px, w_ref_px - w_buf) if s_dir > 0 else max(sl_px, w_ref_px + w_buf)
                    tp_px = (
                        None
                        if sid == "ESP_DIV_V22_WIN"
                        else float(
                            tr.get("tp_price")
                            or (epx + s_dir * (750.0 if sid == "WIN_DIV_WALL" else (350.0 if is_win else 15.0)))
                        )
                    )
                    tp1_px = tr.get("tp1_price")
                    sl1_px = tr.get("sl1_price")
                    lbl = str(tr.get("label", ""))
                    is_val = pts > 0
                    val_st = "VALIDO_ALVO" if ("ALVO" in lbl and is_val) else ("VALIDO_FAVORAVEL" if is_val else "INVALIDO_STOP")
                    be_trig_flag = bool(tr.get("be_triggered") or "PROTEÇÃO" in lbl or "ESCUDO" in lbl or "REDUZIDO" in lbl)
                    if str(tr.get("status", "")).upper() == "ABERTA":
                        val_st, is_val = "EM_ANDAMENTO", None
                        lbl = f"⏳ EM ABERTO ({pts:+.0f} pts)"
                    sig_obj = {
                        "id": f"{asset}_{t_in}_{sid}_{tr_idx}",
                        "strategy_id": sid,
                        "strategy_short": short_nm,
                        "bar_index": b_idx,
                        "timestamp": eb["timestamp"],
                        "time": t_in,
                        "direction": "COMPRA" if s_dir > 0 else "VENDA",
                        "dir_num": s_dir,
                        "type": f"{short_nm} · {'COMPRA' if s_dir > 0 else 'VENDA'}",
                        "entry_price": round(epx, 2),
                        "exit_bar_index": ex_idx,
                        "exit_time": ex_eb.get("time", t_out),
                        "exit_price": round(xpx, 2),
                        "exit_reason": "TP" if is_val else "SL",
                        "stop_price": round(sl_px, 2),
                        "sl1_price": round(float(sl1_px), 2) if sl1_px is not None else None,
                        "tp_price": round(tp_px, 2) if tp_px is not None else None,
                        "tp1_price": round(float(tp1_px), 2) if tp1_px is not None else None,
                        "tp_tag": "TP2 (+750)" if sid == "WIN_DIV_WALL" else ("SEM ALVO · 60 MIN" if sid == "ESP_DIV_V22_WIN" else str(tr.get("tp_tag") or "TP")),
                        "contracts": int(tr.get("contracts", 2 if sid in ("WIN_DIV_WALL", "ESP_DIV_V22_WIN") else 1)),
                        "pts_l1": tr.get("pts_l1"),
                        "pts_l2": tr.get("pts_l2"),
                        "be_triggered": be_trig_flag,
                        "be_bar_index": min(ex_idx, b_idx + 1),
                        "be_time": m5_enriched[min(ex_idx, b_idx + 1)].get("time", t_in),
                        "be_trigger_price": tr.get("be_trigger_price"),
                        "be_stop_price": round(float(tr.get("be_stop_price") or epx), 2),
                        "wall_price": eb.get("sup_w", {}).get("price") if (s_dir > 0 and eb.get("sup_w")) else (eb.get("res_w", {}).get("price") if eb.get("res_w") else None),
                        "wall_type": short_nm,
                        "inst_delta_5m": eb["inst_delta_bar"],
                        "dealer_hedge_5m": eb["dealer_hedge_bar"],
                        "reason": f"{short_nm} ({sid}) c/ Fluxo · {lbl}",
                        "pnl_5m": round(pts, 1),
                        "pnl_15m": round(pts, 1),
                        "pnl_30m": round(pts, 1),
                        "mfe_30m": round(max(0.0, pts), 1),
                        "mae_30m": round(min(0.0, pts), 1),
                        "realized_pts": round(pts, 1),
                        "brl_1c": round(float(tr.get("brl_1c", pts * (0.20 if is_win else 10.0))), 2),
                        "validation_status": val_st,
                        "validation_label": lbl,
                        "is_valid": is_val,
                        "is_prev_day": False,
                        "closed_bar_confirmed": True,
                    }
                    signals_log.append(sig_obj)
                    if sid not in _walls_flow_ids or m5_enriched[b_idx].get("signal") is None:
                        m5_enriched[b_idx]["signal"] = sig_obj
                signals_log.sort(key=lambda s: s["bar_index"])
                # Sniper da 5176 (WIN/WDO_DIV_WALL): histórico até last_bt_date vem do JSON; qualquer pregão
                # posterior a last_bt_date (mesmo já encerrado, ex: ontem antes de rodar novo BT) calcula via _append_live_unified_divergence_signals.
                # Carteira 5176 (12/11/2026): até last_bt_date o histórico auditado (Sniper + especialista, motor v3.2) vem do
                # JSON; pregões posteriores (ao vivo ou já encerrados) são calculados com o mesmo código aqui.
                base4 = getattr(self, "_portfolio_4_base", None) or {}
                last_bt = str(base4.get("last_bt_date") or "")
                after_bt = (not last_bt) or str(sess_date or "") > last_bt
                if is_live_session or after_bt:
                    self._append_live_unified_divergence_signals(
                        asset=asset.upper(), m5_enriched=m5_enriched, today_closed_bars=today_closed_bars,
                        signals_log=signals_log, is_live_session=is_live_session,
                    )
                    if is_win:
                        self._append_live_especialista_v22(
                            m5_enriched=m5_enriched, today_closed_bars=today_closed_bars, signals_log=signals_log,
                            is_live_session=is_live_session, walls_clean=walls_clean,
                        )
                    self._append_live_carteira_4_v32(
                        asset=asset.upper(), m5_enriched=m5_enriched, today_closed_bars=today_closed_bars,
                        signals_log=signals_log, is_live_session=is_live_session, walls_clean=walls_clean,
                    )
            elif is_win:
                signals_log = self._evaluate_live_mt5_win_strategies(
                    sess_date=str(sess_date or ""),
                    m5_enriched=m5_enriched,
                    today_closed_bars=today_closed_bars,
                    closes_all=closes_all,
                    w_len=w_len,
                    walls_clean=walls_clean,
                    model=model,
                    strat_short_names=strat_short_names,
                    is_live_session=is_live_session,
                )
                self._append_live_unified_divergence_signals(
                    asset="WIN",
                    m5_enriched=m5_enriched,
                    today_closed_bars=today_closed_bars,
                    signals_log=signals_log,
                    is_live_session=is_live_session,
                )
                self._append_live_especialista_v22(
                    m5_enriched=m5_enriched, today_closed_bars=today_closed_bars, signals_log=signals_log,
                    is_live_session=is_live_session, walls_clean=walls_clean,
                )
                self._append_live_carteira_4_v32(
                    asset="WIN", m5_enriched=m5_enriched, today_closed_bars=today_closed_bars,
                    signals_log=signals_log, is_live_session=is_live_session, walls_clean=walls_clean,
                )
            else:
                signals_log = self._evaluate_live_mt5_wdo_strategies(
                    sess_date=str(sess_date or ""),
                    m5_enriched=m5_enriched,
                    today_closed_bars=today_closed_bars,
                    closes_all=closes_all,
                    w_len=w_len,
                    walls_clean=walls_clean,
                    strat_short_names=strat_short_names,
                    is_live_session=is_live_session,
                )
                self._append_live_unified_divergence_signals(
                    asset="WDO",
                    m5_enriched=m5_enriched,
                    today_closed_bars=today_closed_bars,
                    signals_log=signals_log,
                    is_live_session=is_live_session,
                )
                self._append_live_carteira_4_v32(
                    asset="WDO", m5_enriched=m5_enriched, today_closed_bars=today_closed_bars,
                    signals_log=signals_log, is_live_session=is_live_session, walls_clean=walls_clean,
                )

        closed_sigs = [s for s in signals_log if s["is_valid"] is not None]
        valid_sigs = [s for s in closed_sigs if s["is_valid"] is True]
        invalid_sigs = [s for s in closed_sigs if s["is_valid"] is False]
        win_rate = (len(valid_sigs) / len(closed_sigs) * 100.0) if closed_sigs else 0.0
        avg_mfe = float(np.mean([s["mfe_30m"] for s in closed_sigs])) if closed_sigs else 0.0
        avg_pnl_15m = (
            float(np.mean([s["pnl_15m"] for s in closed_sigs if s["pnl_15m"] is not None]))
            if any(s["pnl_15m"] is not None for s in closed_sigs)
            else 0.0
        )

        if use_champion_mode:
            method_lbl = "WIN Rejeição + WIN Rompimento + WIN Next Wall" if is_win else "WDO Pullback + WDO Next Wall + WDO Lunch"
        else:
            method_lbl = "WIN_2" if align_with_window else "WIN_1"

        return {
            "m5_enriched_series": m5_enriched[-120:],
            "flow_windows": flow_windows[-20:],
            "signals_log": list(reversed(signals_log)),  # Mais recente no topo da tabela
            "scorecard": {
                "total_signals": len(signals_log),
                "closed_signals": len(closed_sigs),
                "valid_signals": len(valid_sigs),
                "invalid_signals": len(invalid_sigs),
                "open_signals": len(signals_log) - len(closed_sigs),
                "win_rate_pct": round(win_rate, 1),
                "avg_max_favor_pts": round(avg_mfe, 1),
                "avg_15m_pts": round(avg_pnl_15m, 1),
                "target_ref_pts": target_pts,
                "stop_ref_pts": stop_pts,
                "use_be_protection": use_be_protection,
                "be_trigger_pts": be_trigger_pts,
                "be_lock_pts": be_lock_pts,
                "time_stop_min": max_val_bars * 5,
                "methodology_label": method_lbl,
            },
        }

    @staticmethod
    def _round_win5(px: float) -> float:
        return round(float(px) / 5.0) * 5.0

    @staticmethod
    def _round_wdo05(px: float) -> float:
        return round(float(px) * 2.0) / 2.0

    @staticmethod
    def _compute_mt5_nwe_series(closes: np.ndarray, lookback: int, bw: float, mult: float):
        """Calcula o envelope NWE causal idêntico ao UpdateNWE do MQL5 (`Jumba_GEX_NWE_Core.mqh` / `Jumba_WDO_GEX_NWE_Core.mqh`)."""
        n = len(closes)
        center = np.zeros(n, dtype=float)
        mae_raw = np.zeros(n, dtype=float)
        if n == 0:
            return center, center, center, mae_raw, center
        w_full = np.exp(-np.arange(lookback, dtype=float) ** 2 / (2.0 * bw * bw))
        for t in range(n):
            l_idx = min(t, lookback - 1)
            w_t = w_full[: l_idx + 1]
            p_t = closes[t - l_idx : t + 1][::-1]
            center[t] = float(np.dot(w_t, p_t) / np.sum(w_t))
        errors = np.abs(closes - center)
        for t in range(n):
            l_idx = min(t, lookback - 1)
            mae_raw[t] = float(np.mean(errors[t - l_idx : t + 1]))
        upper = center + mae_raw * mult
        lower = center - mae_raw * mult
        slope = np.zeros(n, dtype=float)
        if n > 1:
            slope[1:] = center[1:] - center[:-1]
        return center, upper, lower, mae_raw, slope

    @staticmethod
    def _find_nearest_wall_obj(walls_clean: list, price: float):
        w_walls = [w for w in (walls_clean or []) if w.get("type") in ("Wall", "MidWall") and float(w.get("price", 0.0)) > 0]
        if not w_walls:
            return 999999.0, 0.0, None
        best_w = min(w_walls, key=lambda w: abs(float(w["price"]) - float(price)))
        best_px = float(best_w["price"])
        return abs(best_px - float(price)), best_px, best_w

    def _find_win_structural_targets(self, entry_px: float, dir_sig: int, walls_clean: list, front_run: float = 20.0):
        """Idêntico a `FindStructuralTargets` em `Jumba_GEX_NWE_Core.mqh` (front-run 20p na MidWall/Wall)."""
        rnd = self._round_win5
        main_walls = sorted(float(w["price"]) for w in (walls_clean or []) if w.get("type") == "Wall" and float(w.get("price", 0.0)) > 0)
        all_levels = sorted(set(float(w["price"]) for w in (walls_clean or []) if w.get("type") in ("Wall", "MidWall") and float(w.get("price", 0.0)) > 0))
        near_main = far_main = near_mid = 0.0
        if dir_sig == 1:
            for lvl in main_walls:
                if lvl >= entry_px + 100.0:
                    if near_main == 0.0:
                        near_main = lvl
                    far_main = lvl
            for lvl in all_levels:
                if lvl >= entry_px + 80.0:
                    near_mid = lvl
                    break
        else:
            for lvl in reversed(main_walls):
                if lvl <= entry_px - 100.0:
                    if near_main == 0.0:
                        near_main = lvl
                    far_main = lvl
            for lvl in reversed(all_levels):
                if lvl <= entry_px - 80.0:
                    near_mid = lvl
                    break
        if near_main == 0.0:
            near_main = entry_px + dir_sig * 380.0
        if far_main == 0.0:
            far_main = entry_px + dir_sig * 700.0
        if near_mid == 0.0:
            near_mid = near_main
        tp_mid = rnd(near_mid - dir_sig * front_run)
        tp_main = rnd(near_main - dir_sig * front_run)
        if dir_sig == 1:
            tp_mid = max(entry_px + 100.0, min(entry_px + 950.0, tp_mid))
            tp_main = max(entry_px + 120.0, min(entry_px + 950.0, tp_main))
        else:
            tp_mid = min(entry_px - 100.0, max(entry_px - 950.0, tp_mid))
            tp_main = min(entry_px - 120.0, max(entry_px - 950.0, tp_main))
        return tp_mid, tp_main

    def _calc_wdo_structural_target_pts(
        self,
        entry_px: float,
        dir_sig: int,
        fallback_tp_pts: float,
        walls_clean: list,
        front_run: float = 0.5,
        min_tp_pts: float = 6.0,
    ) -> float:
        """Idêntico a `CalcWdoTargetPts` em `Jumba_WDO_GEX_NWE_Core.mqh` (front-run 0.5p na MidWall/Wall)."""
        rnd = self._round_wdo05
        all_levels = sorted(set(float(w["price"]) for w in (walls_clean or []) if w.get("type") in ("Wall", "MidWall") and float(w.get("price", 0.0)) > 0))
        if not all_levels:
            return rnd(fallback_tp_pts)
        best_dist = 999999.0
        for lvl in all_levels:
            d = (lvl - entry_px) if dir_sig == 1 else (entry_px - lvl)
            if 3.0 <= d < best_dist:
                best_dist = d
        if best_dist < 99999.0:
            cand = rnd(best_dist - front_run)
            if cand >= min_tp_pts:
                return rnd(min(fallback_tp_pts, cand))
        return rnd(fallback_tp_pts)

    def _reconcile_mt5_terminal_live_deals(
        self,
        sess_date: str,
        asset: str,
        today_closed_bars: list,
        m5_enriched: list,
        walls_clean: list,
        strat_short_names: dict,
        sim_signals: list,
    ) -> list:
        """
        Reconcilia os sinais avaliados pelo motor MQL5 Python com as execuções reais gravadas
        pelo robô MT5 em `Common\\Files\\jumba_live_deals_*.csv` e `jumba_*state*.csv` para `sess_date`.
        """
        is_win = asset.upper() == "WIN"
        common_dir = os.path.join(
            os.environ.get("APPDATA", r"C:\Users\ryzen\AppData\Roaming"),
            "MetaQuotes", "Terminal", "Common", "Files",
        )
        if not os.path.isdir(common_dir) or not today_closed_bars:
            return sim_signals

        deals_files = sorted(glob.glob(os.path.join(common_dir, "jumba_live_deals_*.csv")))
        if not deals_files:
            return sim_signals

        # Mapeia estado em tempo real dos slots abertos no MT5 (para SL/TP/Wall exatos de posições em andamento)
        state_pattern = "jumba_state_*_WIN*.csv" if is_win else "jumba_wdo_state_*_WDO*.csv"
        state_by_ticket = {}
        state_by_slot = {}
        for st_fp in sorted(glob.glob(os.path.join(common_dir, state_pattern))):
            try:
                base_nm = os.path.basename(st_fp).replace(".csv", "")
                mg_str = base_nm.split("_")[-1]
                mg_num = int(mg_str) if mg_str.isdigit() else 0
                with open(st_fp, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [ln.strip() for ln in f if ln.strip()]
                if len(lines) < 2:
                    continue
                if lines[0].startswith(sess_date):
                    # Formato posicional gravado por SaveStateToDisk nos EAs Jumba_GEX_NWE_Core / Jumba_WDO_GEX_NWE_Core
                    for ln in lines[1:]:
                        parts = ln.split(";")
                        if len(parts) < 10:
                            continue
                        slot_idx = int(float(parts[0] or 0))
                        sid_st = f"{'EST' if is_win else 'WDO'}_{(mg_num - (88000 if is_win else 89000)) if mg_num > 88000 else slot_idx:02d}"
                        s_dir = int(float(parts[1] or 0))
                        if s_dir != 0 or sid_st not in state_by_slot:
                            state_by_slot[sid_st] = {
                                "side": s_dir,
                                "avg_px": float(parts[5] or 0.0),
                                "sl_px": float(parts[6] or 0.0),
                                "tp_px": float(parts[7] or 0.0),
                                "mfe_pts": float(parts[8] or 0.0),
                                "be_done": int(float(parts[9] or 0)),
                                "def_wall": float(parts[38] if (is_win and len(parts) > 38) else (parts[41] if ((not is_win) and len(parts) > 41) else 0.0) or 0.0),
                            }
            except Exception:
                continue

        # Lê negócios reais executados pelo MT5 na data `sess_date` (aceita YYYY-MM-DD e YYYY.MM.DD)
        sess_date_dot = sess_date.replace("-", ".")
        pos_groups = {}
        has_any_session_deal = False
        for dfp in deals_files:
            try:
                with open(dfp, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [ln.strip() for ln in f if ln.strip()]
                if len(lines) < 2:
                    continue
                hdr = lines[0].split(";")
                for ln in lines[1:]:
                    parts = ln.split(";")
                    if len(parts) < len(hdr):
                        continue
                    row = dict(zip(hdr, parts))
                    t_full = str(row.get("time", ""))
                    if not (t_full.startswith(sess_date) or t_full.startswith(sess_date_dot)):
                        continue
                    has_any_session_deal = True
                    sym = str(row.get("symbol", "")).upper()
                    if (is_win and not sym.startswith("WIN")) or ((not is_win) and not sym.startswith("WDO")):
                        continue
                    pid = int(float(row.get("position_id", 0) or 0))
                    if pid <= 0:
                        continue
                    pos_groups.setdefault(pid, []).append(row)
            except Exception:
                continue

        if not pos_groups:
            return sim_signals

        time_to_idx = {eb["time"]: i for i, eb in today_closed_bars}

        def snap_time_to_bar_idx(hhmm: str) -> int:
            if hhmm in time_to_idx:
                return time_to_idx[hhmm]
            try:
                hm_min = int(hhmm[:2]) * 60 + int(hhmm[3:5])
                m5_str = f"{hm_min // 60:02d}:{(hm_min % 60) - ((hm_min % 60) % 5):02d}"
                if m5_str in time_to_idx:
                    return time_to_idx[m5_str]
                return min(
                    today_closed_bars,
                    key=lambda x: abs((int(x[1]["time"][:2]) * 60 + int(x[1]["time"][3:5])) - hm_min),
                )[0]
            except Exception:
                return today_closed_bars[-1][0]

        mt5_signals_by_sid = {}
        for pid, rows in sorted(pos_groups.items(), key=lambda kv: kv[1][0].get("time", "")):
            in_rows = [
                r for r in rows
                if str(r.get("entry", r.get("entry_type", ""))).strip().upper() in ("0", "IN", "DEAL_ENTRY_IN")
            ]
            out_rows = [
                r for r in rows
                if str(r.get("entry", r.get("entry_type", ""))).strip().upper() in ("1", "OUT", "DEAL_ENTRY_OUT", "3", "INOUT")
            ]
            if not in_rows:
                continue
            r_in = in_rows[0]
            magic = int(float(r_in.get("magic", 0) or 0))
            cmt = str(r_in.get("comment", "")).upper()
            sid = ""
            if is_win and 88001 <= magic <= 88016:
                sid = f"EST_{magic - 88000:02d}"
            elif (not is_win) and 89001 <= magic <= 89010:
                sid = f"WDO_{magic - 89000:02d}"
            else:
                for k_id in strat_short_names:
                    if k_id in cmt:
                        sid = k_id
                        break
            if not sid:
                continue

            raw_dtype = str(r_in.get("type", r_in.get("deal_type", ""))).strip().upper()
            sig_dir = 1 if raw_dtype in ("0", "BUY", "DEAL_TYPE_BUY") else -1
            in_vol = sum(float(r.get("volume", 1.0) or 1.0) for r in in_rows)
            ep = sum(float(r.get("price", 0.0)) * float(r.get("volume", 1.0) or 1.0) for r in in_rows) / max(1.0, in_vol)
            t_in_hhmm = str(r_in.get("time", ""))[11:16]
            b_idx = snap_time_to_bar_idx(t_in_hhmm)
            eb = m5_enriched[b_idx]
            t_str = eb["time"]

            st_row = state_by_ticket.get(pid) or state_by_slot.get(sid) or {}
            def_w_px = float(st_row.get("def_wall", 0.0) or 0.0)
            _, near_px, near_w = self._find_nearest_wall_obj(walls_clean, def_w_px if def_w_px > 0 else ep)
            if def_w_px <= 0 and near_px > 0:
                def_w_px = near_px

            # TP e SL estruturais idênticos ao robô MT5
            if is_win:
                tp_mid, tp_main = self._find_win_structural_targets(ep, sig_dir, walls_clean, 20.0)
                tp_px = tp_main if sid == "EST_01" else tp_mid
                if sid in ("EST_13", "EST_14", "EST_15"):
                    tp_px = min(tp_mid, self._round_win5(ep + 280.0)) if sig_dir == 1 else max(tp_mid, self._round_win5(ep - 280.0))
                sl_dist_default = 260.0 if sid == "EST_07" else (220.0 if sid == "EST_04" else 240.0)
                sl_px = self._round_win5(ep - sig_dir * sl_dist_default)
                if def_w_px > 0:
                    sl_px = min(sl_px, self._round_win5(def_w_px - 60.0)) if sig_dir == 1 else max(sl_px, self._round_win5(def_w_px + 60.0))
                be_trig = 150.0 if sid in ("EST_01", "EST_04", "EST_07") else 130.0
                be_lock = 25.0 if sid == "EST_01" else (45.0 if sid == "EST_04" else (15.0 if sid == "EST_07" else 20.0))
            else:
                fb_tp = 11.0 if sid == "WDO_07" else (10.5 if sid == "WDO_05" else (9.5 if sid in ("WDO_02", "WDO_10") else 10.0))
                tp_pts = self._calc_wdo_structural_target_pts(ep, sig_dir, fb_tp, walls_clean, 0.5, 6.0)
                tp_px = self._round_wdo05(ep + sig_dir * tp_pts)
                sl_pts_def = 11.5 if sid == "WDO_07" else (10.0 if sid == "WDO_05" else (8.5 if sid == "WDO_02" else 9.5))
                sl_px = self._round_wdo05(ep - sig_dir * sl_pts_def)
                if def_w_px > 0:
                    sl_px = min(sl_px, self._round_wdo05(def_w_px - 3.0)) if sig_dir == 1 else max(sl_px, self._round_wdo05(def_w_px + 3.0))
                be_trig = 6.0 if sid == "WDO_07" else (5.0 if sid in ("WDO_02", "WDO_10") else 5.5)
                be_lock = 1.5

            if pid in state_by_ticket:
                st_tp = float(state_by_ticket[pid].get("tp_px", 0.0) or 0.0)
                st_sl = float(state_by_ticket[pid].get("sl_px", 0.0) or 0.0)
                if st_tp > 0:
                    tp_px = st_tp
                if st_sl > 0:
                    if (sig_dir == 1 and st_sl < ep) or (sig_dir == -1 and st_sl > ep):
                        sl_px = min(sl_px, st_sl) if sig_dir == 1 else max(sl_px, st_sl)

            short_nm = strat_short_names.get(sid, sid)
            mult_1c = 0.20 if is_win else 10.0
            p_dec = ".0f" if is_win else ".1f"

            if out_rows:
                out_vol = sum(float(r.get("volume", 1.0) or 1.0) for r in out_rows)
                xp = sum(float(r.get("price", 0.0)) * float(r.get("volume", 1.0) or 1.0) for r in out_rows) / max(1.0, out_vol)
                t_out_hhmm = str(out_rows[-1].get("time", ""))[11:16]
                ex_idx = max(b_idx, snap_time_to_bar_idx(t_out_hhmm))
                ex_eb = m5_enriched[min(len(m5_enriched) - 1, ex_idx)]
                realized_pts = round(sig_dir * (xp - ep), 1)
                if realized_pts >= (150.0 if is_win else 6.0) or (realized_pts > 0 and abs(xp - tp_px) <= (20.0 if is_win else 1.0)):
                    exit_reason = "TP"
                    val_status = "VALIDO_ALVO"
                    val_label = f"✅ ALVO WALL ({realized_pts:+{p_dec}} pts)"
                    tp_px = xp
                    be_armed = True
                elif realized_pts >= 0 or abs(xp - ep) <= (45.0 if is_win else 3.0):
                    exit_reason = "BE"
                    val_status = "VALIDO_FAVORAVEL" if realized_pts >= 0 else "INVALIDO_CONTRA"
                    val_label = f"🛡️ ESCUDO WALL ({realized_pts:+{p_dec}} pts)"
                    be_armed = True
                else:
                    exit_reason = "SL"
                    val_status = "INVALIDO_STOP"
                    val_label = f"❌ STOP ({realized_pts:+{p_dec}} pts)"
                    be_armed = False
                is_valid = realized_pts > 0
                mfe_val = max(0.0, realized_pts, be_trig if be_armed else 0.0)
                mae_val = min(0.0, realized_pts)
                be_stop_px = round(xp if exit_reason == "BE" else (ep + sig_dir * be_lock), 2)
            else:
                ex_idx = today_closed_bars[-1][0]
                ex_eb = m5_enriched[-1]
                xp = round(float(ex_eb["close"]), 2)
                realized_pts = round(sig_dir * (xp - ep), 1)
                exit_reason = "ABERTA"
                val_status = "EM_ANDAMENTO"
                val_label = f"⏳ EM ABERTO ({realized_pts:+{p_dec}} pts)"
                is_valid = None
                be_armed = bool(int(float(st_row.get("be_done", 0) or 0)))
                mfe_val = max(0.0, float(st_row.get("mfe_pts", 0.0) or 0.0), realized_pts)
                mae_val = min(0.0, realized_pts)
                be_stop_px = round(float(st_row.get("sl_px", ep + sig_dir * be_lock) or (ep + sig_dir * be_lock)), 2)

            sig_obj = {
                "id": f"{asset}_{t_str}_{sid}_{'BUY' if sig_dir > 0 else 'SELL'}",
                "strategy_id": sid,
                "strategy_short": short_nm,
                "bar_index": b_idx,
                "timestamp": eb["timestamp"],
                "time": t_str,
                "direction": "COMPRA" if sig_dir > 0 else "VENDA",
                "dir_num": sig_dir,
                "type": f"{short_nm} · {'COMPRA' if sig_dir > 0 else 'VENDA'}",
                "entry_price": round(ep, 2),
                "exit_bar_index": ex_idx,
                "exit_time": ex_eb.get("time", t_str),
                "exit_price": round(xp, 2),
                "exit_reason": exit_reason,
                "stop_price": round(sl_px, 2),
                "tp_price": round(tp_px, 2),
                "tp_tag": "TP",
                "be_triggered": bool(be_armed),
                "be_bar_index": min(ex_idx, b_idx + 1) if be_armed else None,
                "be_time": m5_enriched[min(ex_idx, b_idx + 1)].get("time", t_str) if be_armed else None,
                "be_trigger_price": round(ep + sig_dir * be_trig, 2),
                "be_stop_price": be_stop_px,
                "wall_price": round(def_w_px, 2) if def_w_px > 0 else (round(near_w["price"], 2) if near_w else None),
                "wall_type": near_w["type"] if near_w else short_nm,
                "inst_delta_5m": eb["inst_delta_bar"],
                "dealer_hedge_5m": eb["dealer_hedge_bar"],
                "reason": f"{short_nm} ({sid}) MT5 Real · {val_label}",
                "pnl_5m": round(realized_pts, 1),
                "pnl_15m": round(realized_pts, 1),
                "pnl_30m": round(realized_pts, 1),
                "mfe_30m": round(mfe_val, 1),
                "mae_30m": round(mae_val, 1),
                "realized_pts": round(realized_pts, 1),
                "brl_1c": round(realized_pts * mult_1c, 2),
                "validation_status": val_status,
                "validation_label": val_label,
                "is_valid": is_valid,
                "is_prev_day": False,
                "closed_bar_confirmed": True,
            }
            existing_list = mt5_signals_by_sid.setdefault(sid, [])
            if not any(ex["bar_index"] == b_idx and ex["dir_num"] == sig_dir for ex in existing_list):
                existing_list.append(sig_obj)

        # Quando o terminal MT5 está ativo na sessão (`has_any_session_deal`), usa as ordens reais do MT5
        # para os slots gerenciados pelo EA (EST_01..16 / WDO_01..10) e preserva as estratégias exclusivas do Dashboard (ex: WIN_E2)
        if has_any_session_deal:
            merged = [
                s for s in sim_signals
                if (not s["strategy_id"].startswith("EST_") and not s["strategy_id"].startswith("WDO_"))
                and s["strategy_id"] not in mt5_signals_by_sid
            ]
        else:
            merged = [s for s in sim_signals if s["strategy_id"] not in mt5_signals_by_sid]
        for s_list in mt5_signals_by_sid.values():
            merged.extend(s_list)
        merged.sort(key=lambda s: (s["bar_index"], s["strategy_id"]))
        for eb in m5_enriched:
            eb["signal"] = None
        for s in merged:
            if 0 <= s["bar_index"] < len(m5_enriched):
                m5_enriched[s["bar_index"]]["signal"] = s
        return merged

    def _evaluate_live_mt5_win_strategies(
        self,
        sess_date: str,
        m5_enriched: list,
        today_closed_bars: list,
        closes_all: np.ndarray,
        w_len: int,
        walls_clean: list,
        model: AssetGexCurveModel,
        strat_short_names: dict,
        is_live_session: bool,
    ) -> list:
        """
        Avalia as estratégias WIN (`EST_01`, `EST_04`, `EST_07`, `EST_13`, `EST_14`, `EST_15`, `WIN_E2`)
        seguindo 100% as fórmulas exatas do robô MQL5 (`Jumba_GEX_NWE_Core.mqh` + `sg_sim.py` + `optimize_existing_16_setups.py`):
          - Duplo envelope causal NWE50(50, bw=5.0, mult=2.0) e NWE30(30, bw=3.0, mult=1.6)
          - Entradas Limit (`mid_b1` p/ EST_13/14/15/WIN_E2 c/ filtro `new_open >= mid_b1` | `lvl ∓ 5` p/ EST_04)
            e Market na abertura da barra seguinte (`new_bar_open` p/ EST_01 e EST_07)
          - Alvos estruturais `TP_MIDWALL` / `TP_MAIN_WALL` (front-run 20p) e `BE_WALL_SHIELD` / `BE_WALL_2STAGE`
        """
        signals_log = []
        for eb in m5_enriched:
            eb["signal"] = None
        if len(today_closed_bars) < 3:
            return signals_log

        closes_m5 = np.array([float(eb["close"]) for eb in m5_enriched], dtype=float)
        n50_c, n50_u, n50_l, _, n50_s = self._compute_mt5_nwe_series(closes_m5, 50, 5.0, 2.0)
        n30_c, n30_u, n30_l, _, n30_s = self._compute_mt5_nwe_series(closes_m5, 30, 3.0, 1.6)

        rnd = self._round_win5
        gflip = float(getattr(model, "gamma_flip", 0.0) or 0.0)
        slot_ids = ("EST_01", "EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "WIN_E2")
        busy_by_slot = {s: -1 for s in slot_ids}
        ops_by_slot = {s: 0 for s in slot_ids}
        wall_touch_counts = {}

        # Contabiliza o 1º e 2º bares do dia nas walls
        for init_k in range(min(2, len(today_closed_bars))):
            _, eb0 = today_closed_bars[init_k]
            h0, l0 = float(eb0["high"]), float(eb0["low"])
            for w_it in walls_clean:
                if w_it.get("type") in ("Wall", "MidWall"):
                    wp_k = round(float(w_it["price"]), 1)
                    if (l0 - 70.0) <= wp_k <= (h0 + 70.0):
                        wall_touch_counts[wp_k] = wall_touch_counts.get(wp_k, 0) + 1

        for pos_k in range(2, len(today_closed_bars)):
            cur_b_idx, cur_eb = today_closed_bars[pos_k]
            b1_idx, b1 = today_closed_bars[pos_k - 1]
            b2_idx, b2 = today_closed_bars[pos_k - 2]

            t1_str = b1["time"]
            tm1 = int(t1_str[:2]) * 60 + int(t1_str[3:5])
            o1, h1, l1, c1 = float(b1["open"]), float(b1["high"]), float(b1["low"]), float(b1["close"])
            o2, h2, l2, c2 = float(b2["open"]), float(b2["high"]), float(b2["low"]), float(b2["close"])
            new_open = float(cur_eb["open"])

            for w_it in walls_clean:
                if w_it.get("type") in ("Wall", "MidWall"):
                    wp_k = round(float(w_it["price"]), 1)
                    if (l1 - 70.0) <= wp_k <= (h1 + 70.0):
                        wall_touch_counts[wp_k] = wall_touch_counts.get(wp_k, 0) + 1

            rng1 = max(h1 - l1, 5.0)
            body1 = abs(c1 - o1)
            up_w1 = h1 - max(o1, c1)
            dn_w1 = min(o1, c1) - l1

            bw50_1 = max(n50_u[b1_idx] - n50_l[b1_idx], 10.0)
            pos50_1 = (c1 - n50_l[b1_idx]) / bw50_1
            s50_1 = float(n50_s[b1_idx])
            bw50_2 = max(n50_u[b2_idx] - n50_l[b2_idx], 10.0)
            pos50_2 = (c2 - n50_l[b2_idx]) / bw50_2

            bw30_1 = max(n30_u[b1_idx] - n30_l[b1_idx], 10.0)
            pos30_1 = (c1 - n30_l[b1_idx]) / bw30_1
            s30_1 = float(n30_s[b1_idx])
            z30_1 = (c1 - n30_c[b1_idx]) / max(10.0, 0.5 * bw30_1)

            dc1, lc1, wc1 = self._find_nearest_wall_obj(walls_clean, c1)
            dl1, ll1, wl1 = self._find_nearest_wall_obj(walls_clean, l1)
            dh1, lh1, wh1 = self._find_nearest_wall_obj(walls_clean, h1)

            inst_5m = float(b1.get("inst_delta_bar", 0.0))
            inst_15m = sum(float(today_closed_bars[k_p][1].get("inst_delta_bar", 0.0)) for k_p in range(max(0, pos_k - 3), pos_k))
            ia5 = float(b1.get("inst_aggr_delta", inst_5m))
            ia15 = sum(float(today_closed_bars[k_p][1].get("inst_aggr_delta", today_closed_bars[k_p][1].get("inst_delta_bar", 0.0))) for k_p in range(max(0, pos_k - 3), pos_k))
            ip5 = float(b1.get("inst_pass_delta", 0.0))
            ip10 = sum(float(today_closed_bars[k_p][1].get("inst_pass_delta", 0.0)) for k_p in range(max(0, pos_k - 2), pos_k))
            ip15 = sum(float(today_closed_bars[k_p][1].get("inst_pass_delta", 0.0)) for k_p in range(max(0, pos_k - 3), pos_k))
            r5 = float(b1.get("ret_delta_bar", 0.0))
            r15 = sum(float(today_closed_bars[k_p][1].get("ret_delta_bar", 0.0)) for k_p in range(max(0, pos_k - 3), pos_k))
            hft5 = float(b1.get("hft_delta_bar", 0.0))
            nr5 = ia5 + ip5 + hft5
            nr15 = ia15 + ip15
            c_prev2 = float(today_closed_bars[max(0, pos_k - 3)][1].get("close", o1))
            c_prev3 = float(today_closed_bars[max(0, pos_k - 4)][1].get("close", c_prev2))
            dp1 = c1 - o1
            dp2 = c1 - c_prev2
            dp3 = c1 - c_prev3
            lot_imb = float(b1.get("lot_imb", 1.0))
            wdir1 = int(b1.get("window_dir", 1))
            fhist1 = float(b1.get("flow_hist", 0.0))
            hslope1 = fhist1 - float(b2.get("flow_hist", 0.0))
            delta_5m = float(b1.get("delta_bar", 0.0))
            b_abs = (inst_5m >= 0 or delta_5m >= 0 or dn_w1 >= 0.25 * rng1 or c1 >= o1) and (inst_5m >= -12000.0)
            s_abs = (inst_5m <= 0 or delta_5m <= 0 or up_w1 >= 0.25 * rng1 or c1 <= o1) and (inst_5m <= 12000.0)

            b_w = wdir1 == 1
            s_w = wdir1 == -1
            b_ws = (wdir1 == 1) or (fhist1 >= -14.0) or (hslope1 >= 0.0)
            s_ws = (wdir1 == -1) or (fhist1 <= 14.0) or (hslope1 <= 0.0)
            b_abs = (inst_5m >= 0 or delta_5m >= 0 or dn_w1 >= 0.22 * rng1 or c1 >= o1) and (inst_5m >= -12000.0)
            s_abs = (inst_5m <= 0 or delta_5m <= 0 or up_w1 >= 0.22 * rng1 or c1 <= o1) and (inst_5m <= 12000.0)

            sweep_crash = (ia5 < -4200.0) and (lot_imb < 0.88) and (ip5 <= 0.0)
            sweep_surge = (ia5 > 4200.0) and (lot_imb > 1.14) and (ip5 >= 0.0)

            # 8_PROFIT_SWEEP
            b_sweep = ((ia5 >= 0.0) or (ia15 >= 0.0) or (lot_imb >= 1.02) or (b_ws and b_abs)) and (ia5 >= -5500.0) and (lot_imb >= 0.88)
            s_sweep = ((ia5 <= 0.0) or (ia15 <= 0.0) or (lot_imb <= 0.98) or (s_ws and s_abs)) and (ia5 <= 5500.0) and (lot_imb <= 1.14)

            # 9_PROFIT_INST_RET & 13_NR_PRICE_ABS_DIV (WIN_E2, EST_01, EST_15)
            b9 = ((inst_5m >= 0.0) or (inst_15m >= 0.0) or (ip5 > 0.0 and r5 < 0.0) or (lot_imb >= 1.04)) and not (ia5 < -9000.0 and lot_imb < 0.82)
            s9 = ((inst_5m <= 0.0) or (inst_15m <= 0.0) or (ip5 < 0.0 and r5 > 0.0) or (lot_imb <= 0.96)) and not (ia5 > 9000.0 and lot_imb > 1.22)
            b13 = b9 and not (r5 > 500.0 and ip5 < -300.0 and ia5 <= 0) and not (ia5 < -2000.0 and ip5 <= 0 and inst_15m < -2500.0)
            s13 = s9 and not (r5 < -500.0 and ip5 > 300.0 and ia5 >= 0) and not (ia5 > 2000.0 and ip5 >= 0 and inst_15m > 2500.0)
            b14 = b_sweep and b13
            s14 = s_sweep and s13

            # 11_PROFIT_WALL_SHIELD (EST_13)
            b_shield = b_ws and b9
            s_shield = s_ws and s9

            # 12_NR_WALL_TRAP_DIV (EST_14)
            b12 = (((r5 < 0 or r15 < 0) and (ip5 >= 0 or ia5 > 0 or nr15 > 0)) or ((inst_5m > 0 and inst_15m > 0) and lot_imb >= 1.02) or (dn_w1 >= 0.28 * rng1 and (ip5 > 0 or ia5 >= 0))) and (not sweep_crash) and b_ws
            s12 = (((r5 > 0 or r15 > 0) and (ip5 <= 0 or ia5 < 0 or nr15 < 0)) or ((inst_5m < 0 and inst_15m < 0) and lot_imb <= 0.98) or (up_w1 >= 0.28 * rng1 and (ip5 < 0 or ia5 <= 0))) and (not sweep_surge) and s_ws

            # 15_NR_IGNITION_DIV (EST_04)
            b15 = b13 and not (dp3 > 150.0 and nr15 < -1200.0) and (lot_imb >= 0.89 or ip5 > 0)
            s15 = s13 and not (dp3 < -150.0 and nr15 > 1200.0) and (lot_imb <= 1.12 or ip5 < 0)

            # 16_NR_DIV_ABS_OR_AGGR (EST_07)
            b16 = (((dp1 <= 0 or dp2 <= 0) and (ip5 > 0 or ip10 > 0 or nr5 > 0)) or (r5 < 0 and (ip5 >= 0 or ia5 > 0 or inst_15m > 0)) or (ia5 > 0 and inst_15m > 0 and lot_imb >= 1.03 and r5 <= ia5)) and (ia5 >= -3000.0)
            s16 = (((dp1 >= 0 or dp2 >= 0) and (ip5 < 0 or ip10 < 0 or nr5 < 0)) or (r5 > 0 and (ip5 <= 0 or ia5 < 0 or inst_15m < 0)) or (ia5 < 0 and inst_15m < 0 and lot_imb <= 0.97 and r5 >= ia5)) and (ia5 <= 3000.0)

            mid_b1 = rnd(0.5 * (h1 + l1))
            # (sid, sig_dir, order_type, limit_px, valid_bars, tp_cap, sl_pts, be_trig, be_lock, wall_buf, max_b, def_w_obj)
            cands = []

            # 1) EST_01: Rejeição/Pinbar na Wall (MQL5 `EvalEst01_PinbarRejeicaoWall` + 14_NR_BREAKOUT_SQUEEZE)
            if 545 <= tm1 <= 990 and cur_b_idx > busy_by_slot["EST_01"] and ops_by_slot["EST_01"] < 2 and bw50_1 >= 475.8 and dc1 <= 70.0 and abs(s50_1) <= 18.0:
                if ((pos50_1 <= 0.18 and dn_w1 >= 0.30 * rng1 and c1 >= l1 + 0.55 * rng1) or (pos50_2 <= 0.20 and c2 < o2 and c1 > o1 and c1 > 0.5 * (h2 + l2))) and b14:
                    cands.append(("EST_01", 1, "MKT", new_open, 1, 950.0, 240.0, 150.0, 25.0, 25.0, 16, wc1))
                elif ((pos50_1 >= 0.82 and up_w1 >= 0.30 * rng1 and c1 <= h1 - 0.55 * rng1) or (pos50_2 >= 0.80 and c2 > o2 and c1 < o1 and c1 < 0.5 * (h2 + l2))) and s14:
                    cands.append(("EST_01", -1, "MKT", new_open, 1, 950.0, 240.0, 150.0, 25.0, 25.0, 16, wc1))

            # 2) EST_04: Pullback Tendência na Wall (MQL5 `EvalEst04_PullbackTendencia`: Limit na Wall `lc1 ∓ 5` + 15_NR_IGNITION_DIV)
            if 600 <= tm1 <= 990 and cur_b_idx > busy_by_slot["EST_04"] and ops_by_slot["EST_04"] < 2 and wc1 is not None:
                if s50_1 >= 8.0 and 0.45 <= pos50_1 <= 0.85 and pos30_1 <= 0.65 and abs(l1 - lc1) <= 60.0 and c1 > lc1 and b15:
                    cands.append(("EST_04", 1, "LIM", rnd(lc1 - 5.0), 1, 950.0, 220.0, 150.0, 45.0, 15.0, 16, wc1))
                elif s50_1 <= -8.0 and 0.15 <= pos50_1 <= 0.55 and pos30_1 >= 0.35 and abs(h1 - lc1) <= 60.0 and c1 < lc1 and s15:
                    cands.append(("EST_04", -1, "LIM", rnd(lc1 + 5.0), 1, 950.0, 220.0, 150.0, 45.0, 15.0, 16, wc1))

            # 3) EST_07: Ignição/Rompimento Wall (MQL5 `EvalEst07_IgnicaoBreakoutWall`: Market em `new_open`, `dc1 <= 95` + 16_NR_DIV_ABS_OR_AGGR)
            if 545 <= tm1 <= 960 and cur_b_idx > busy_by_slot["EST_07"] and ops_by_slot["EST_07"] < 2 and dc1 <= 95.0 and wc1 is not None:
                if o1 <= lc1 + 20.0 and c1 > lc1 + 20.0 and body1 >= 100.0 and s50_1 >= 6.0 and s30_1 > 0.0 and 0.45 <= pos50_1 <= 0.88 and b16:
                    cands.append(("EST_07", 1, "MKT", new_open, 1, 950.0, 260.0, 150.0, 15.0, 15.0, 16, wc1))
                elif o1 >= lc1 - 20.0 and c1 < lc1 - 20.0 and body1 >= 100.0 and s50_1 <= -6.0 and s30_1 < 0.0 and 0.12 <= pos50_1 <= 0.55 and s16:
                    cands.append(("EST_07", -1, "MKT", new_open, 1, 950.0, 260.0, 150.0, 15.0, 15.0, 16, wc1))

            # 4) EST_13: SmartGrid Longa Descontada na Wall (MQL5 `EvalEst13`: Limit em `35%` da barra `b1`, TP 360p, BE 145p + 11_PROFIT_WALL_SHIELD)
            if 545 <= tm1 <= 975 and cur_b_idx > busy_by_slot["EST_13"] and ops_by_slot["EST_13"] < 5 and bw50_1 >= 475.8 and dc1 <= 80.0 and abs(s50_1) <= 22.0 and wc1 is not None:
                if pos50_1 <= 0.45 and z30_1 <= -0.65 and c1 > o1 and b_shield:
                    cands.append(("EST_13", 1, "LIM", rnd(l1 + 0.35 * rng1), 2, 360.0, 240.0, 145.0, 20.0, 20.0, 18, wc1))
                elif pos50_1 >= 0.55 and z30_1 >= 0.65 and c1 < o1 and s_shield:
                    cands.append(("EST_13", -1, "LIM", rnd(h1 - 0.35 * rng1), 2, 360.0, 240.0, 145.0, 20.0, 20.0, 18, wc1))

            # 5) EST_14: SmartGrid Intermediária Defesa de Pavio na Wall (MQL5 `EvalEst14`: Limit em `50%` da barra `mid_b1`, TP 280p, BE 130p + 12_NR_WALL_TRAP_DIV)
            if 545 <= tm1 <= 1005 and cur_b_idx > busy_by_slot["EST_14"] and ops_by_slot["EST_14"] < 3:
                if dl1 <= 75.0 and c1 > ll1 - 15.0 and dn_w1 >= 25.0 and pos50_1 <= 0.48 and c1 >= o1 and b12:
                    cands.append(("EST_14", 1, "LIM", mid_b1, 2, 280.0, 240.0, 130.0, 20.0, 20.0, 18, wl1))
                elif dh1 <= 75.0 and c1 < lh1 + 15.0 and up_w1 >= 25.0 and pos50_1 >= 0.52 and c1 <= o1 and s12:
                    cands.append(("EST_14", -1, "LIM", mid_b1, 2, 280.0, 240.0, 130.0, 20.0, 20.0, 18, wh1))

            # 6) EST_15: SmartGrid Curta / Caixa Rápido Z30 Reversal Wall (MQL5 `EvalEst15`: Limit em `55%` da barra `b1`, TP 210p, BE 110p + 14_NR_BREAKOUT_SQUEEZE)
            if 555 <= tm1 <= 975 and cur_b_idx > busy_by_slot["EST_15"] and ops_by_slot["EST_15"] < 3 and dc1 <= 110.0 and wc1 is not None:
                if z30_1 <= -0.60 and pos50_1 <= 0.70 and c1 > o1 and (n50_c[b1_idx] - c1) >= 70.0 and b14:
                    cands.append(("EST_15", 1, "LIM", rnd(l1 + 0.55 * rng1), 2, 210.0, 240.0, 110.0, 20.0, 20.0, 18, wc1))
                elif z30_1 >= 0.60 and pos50_1 >= 0.30 and c1 < o1 and (c1 - n50_c[b1_idx]) >= 70.0 and s14:
                    cands.append(("EST_15", -1, "LIM", rnd(h1 - 0.55 * rng1), 2, 210.0, 240.0, 110.0, 20.0, 20.0, 18, wc1))

            # 7) WIN_E2: Wall Gasta 3º+ Toque + NR_WALL_DIV + 13_NR_PRICE_ABS_DIV
            if 545 <= tm1 <= 990 and cur_b_idx > busy_by_slot["WIN_E2"] and ops_by_slot["WIN_E2"] < 2 and dc1 <= 85.0 and wc1 is not None:
                touches_wc1 = wall_touch_counts.get(round(lc1, 1), 0)
                nr_wall_div_b = (not (ip5 < -500.0 and r5 > 400.0)) and (ia5 > 0 or inst_15m > 0 or r5 <= 0 or lot_imb >= 1.0)
                nr_wall_div_s = (not (ip5 > 500.0 and r5 < -400.0)) and (ia5 < 0 or inst_15m < 0 or r5 >= 0 or lot_imb <= 1.0)
                if touches_wc1 >= 3 and c1 > lc1 and c1 > o1 and s50_1 > 0.0 and s30_1 > 0.0 and 0.35 <= pos50_1 <= 0.80 and nr_wall_div_b and b13:
                    cands.append(("WIN_E2", 1, "LIM", mid_b1, 2, 260.0, 230.0, 130.0, 15.0, 20.0, 18, wc1))
                elif touches_wc1 >= 3 and c1 < lc1 and c1 < o1 and s50_1 < 0.0 and s30_1 < 0.0 and 0.20 <= pos50_1 <= 0.65 and nr_wall_div_s and s13:
                    cands.append(("WIN_E2", -1, "LIM", mid_b1, 2, 260.0, 230.0, 130.0, 15.0, 20.0, 18, wc1))

            for sid, sig_dir, ord_type, ord_px, val_bars, tp_cap, sl_pts, be_trig, be_lock, w_buf, max_b, nearest_w in cands:
                # Filtro de abertura idêntico ao MT5: ordem Limit de compra exige new_open >= ord_px; venda exige new_open <= ord_px
                if ord_type == "LIM":
                    if (sig_dir == 1 and new_open < ord_px) or (sig_dir == -1 and new_open > ord_px):
                        continue
                    filled, fill_pos_k, ep = False, pos_k, ord_px
                    for v_idx in range(val_bars):
                        if pos_k + v_idx >= len(today_closed_bars):
                            break
                        _, vb = today_closed_bars[pos_k + v_idx]
                        if (sig_dir == 1 and float(vb["low"]) <= ord_px) or (sig_dir == -1 and float(vb["high"]) >= ord_px):
                            filled, fill_pos_k, ep = True, pos_k + v_idx, ord_px
                            break
                    if not filled:
                        continue
                else:
                    fill_pos_k = pos_k
                    ep = rnd(new_open)

                entry_b_idx, entry_eb = today_closed_bars[fill_pos_k]
                entry_t_str = entry_eb["time"]

                tp_mid, tp_main = self._find_win_structural_targets(ep, sig_dir, walls_clean, 20.0)
                tp_struct = tp_main if sid == "EST_01" else tp_mid
                tp_px = min(tp_struct, rnd(ep + tp_cap)) if sig_dir == 1 else max(tp_struct, rnd(ep - tp_cap))
                tr_tp = round(abs(tp_px - ep), 1)

                w_px_ref = float(nearest_w["price"]) if (nearest_w and nearest_w.get("price") is not None) else 0.0
                sl_px = rnd(ep - sig_dir * sl_pts)
                if w_px_ref > 0:
                    sl_px = min(sl_px, rnd(w_px_ref - 60.0)) if sig_dir == 1 else max(sl_px, rnd(w_px_ref + 60.0))
                tr_sl = round(abs(ep - sl_px), 1)

                sim_slice = today_closed_bars[fill_pos_k : min(len(today_closed_bars), fill_pos_k + max_b)]
                be_armed = False
                be_armed_idx = None
                be_armed_time = None
                curr_sl_px = sl_px
                mfe_w, mae_w, realized_w = 0.0, 0.0, 0.0
                exit_reason = ""
                closed_trade = False
                win_exit_idx = sim_slice[-1][0] if sim_slice else entry_b_idx

                for s_pos, (f_b_idx, fb) in enumerate(sim_slice):
                    fh, fl, fc = float(fb["high"]), float(fb["low"]), float(fb["close"])
                    fav = (fh - ep) if sig_dir > 0 else (ep - fl)
                    adv = (fl - ep) if sig_dir > 0 else (ep - fh)
                    if fav > mfe_w:
                        mfe_w = fav
                    if adv < mae_w:
                        mae_w = adv
                    # Na barra de preenchimento de ordem Limit, avalia TP/SL a partir do preço de entrada
                    if (sig_dir == 1 and fl <= curr_sl_px and (s_pos > 0 or ord_type == "MKT")) or (
                        sig_dir == -1 and fh >= curr_sl_px and (s_pos > 0 or ord_type == "MKT")
                    ):
                        realized_w = round(sig_dir * (curr_sl_px - ep), 1)
                        exit_reason = "BE" if be_armed else "SL"
                        closed_trade = True
                        win_exit_idx = f_b_idx
                        break
                    if (sig_dir == 1 and fh >= tp_px) or (sig_dir == -1 and fl <= tp_px):
                        realized_w = tr_tp
                        exit_reason = "TP"
                        closed_trade = True
                        win_exit_idx = f_b_idx
                        break
                    if not be_armed and mfe_w >= be_trig:
                        if w_px_ref > 0:
                            w_cand = rnd(w_px_ref - sig_dir * w_buf)
                            max_lock = rnd(ep + sig_dir * be_lock)
                            cand_sl = min(w_cand, max_lock) if sig_dir == 1 else max(w_cand, max_lock)
                            min_imp = rnd(ep - sig_dir * 85.0)
                            cand_sl = max(cand_sl, min_imp) if sig_dir == 1 else min(cand_sl, min_imp)
                        else:
                            cand_sl = rnd(ep + sig_dir * be_lock)
                        if (sig_dir == 1 and cand_sl > curr_sl_px) or (sig_dir == -1 and cand_sl < curr_sl_px):
                            curr_sl_px = cand_sl
                            be_armed = True
                            be_armed_idx = f_b_idx
                            be_armed_time = fb.get("time", "")

                busy_by_slot[sid] = max(busy_by_slot[sid], win_exit_idx)
                ops_by_slot[sid] += 1
                if not closed_trade:
                    if is_live_session and len(sim_slice) < max_b:
                        live_unr = round(sig_dir * (float(m5_enriched[-1]["close"]) - ep), 1)
                        val_status, val_label, is_valid, realized_w, exit_reason = (
                            "EM_ANDAMENTO", f"⏳ EM ABERTO ({live_unr:+.0f} pts)", None, live_unr, "ABERTA"
                        )
                    else:
                        last_fc = float(sim_slice[-1][1]["close"]) if sim_slice else ep
                        realized_w = round(sig_dir * (last_fc - ep), 1)
                        is_valid = realized_w > 0
                        exit_reason = "TEMPO"
                        val_status = "VALIDO_FAVORAVEL" if is_valid else "INVALIDO_CONTRA"
                        val_label = f"{'✅' if is_valid else '❌'} TEMPO ({realized_w:+.0f} pts)"
                else:
                    is_valid = realized_w > 0
                    val_status = "VALIDO_ALVO" if exit_reason == "TP" else ("VALIDO_FAVORAVEL" if exit_reason == "BE" else "INVALIDO_STOP")
                    val_label = (
                        f"✅ ALVO WALL (+{tr_tp:.0f} pts)"
                        if exit_reason == "TP"
                        else (f"🛡️ ESCUDO WALL ({realized_w:+.0f} pts)" if exit_reason == "BE" else f"❌ STOP ({realized_w:+.0f} pts)")
                    )

                win_ex_eb = m5_enriched[min(len(m5_enriched) - 1, win_exit_idx)]
                win_ex_px = round(float(m5_enriched[-1]["close"]), 2) if val_status == "EM_ANDAMENTO" else round(ep + sig_dir * realized_w, 2)
                short_nm = strat_short_names.get(sid, sid)
                win_sig_obj = {
                    "id": f"WIN_{entry_t_str}_{sid}_{'BUY' if sig_dir > 0 else 'SELL'}",
                    "strategy_id": sid,
                    "strategy_short": short_nm,
                    "bar_index": entry_b_idx,
                    "timestamp": entry_eb["timestamp"],
                    "time": entry_t_str,
                    "direction": "COMPRA" if sig_dir > 0 else "VENDA",
                    "dir_num": sig_dir,
                    "type": f"{short_nm} · {'COMPRA' if sig_dir > 0 else 'VENDA'}",
                    "entry_price": round(ep, 2),
                    "exit_bar_index": win_exit_idx,
                    "exit_time": win_ex_eb.get("time", entry_t_str),
                    "exit_price": win_ex_px,
                    "exit_reason": exit_reason,
                    "stop_price": round(sl_px, 2),
                    "tp_price": round(tp_px, 2),
                    "tp_tag": "TP",
                    "be_triggered": bool(be_armed),
                    "be_bar_index": be_armed_idx,
                    "be_time": be_armed_time,
                    "be_trigger_price": round(ep + sig_dir * be_trig, 2),
                    "be_stop_price": round(curr_sl_px if be_armed else (ep + sig_dir * be_lock), 2),
                    "wall_price": round(w_px_ref, 2) if w_px_ref > 0 else None,
                    "wall_type": nearest_w["type"] if nearest_w else short_nm,
                    "inst_delta_5m": entry_eb["inst_delta_bar"],
                    "dealer_hedge_5m": entry_eb["dealer_hedge_bar"],
                    "reason": f"{short_nm} ({sid}) c/ Fluxo · {val_label}",
                    "pnl_5m": round(realized_w, 1),
                    "pnl_15m": round(realized_w, 1),
                    "pnl_30m": round(realized_w, 1),
                    "mfe_30m": round(mfe_w, 1),
                    "mae_30m": round(mae_w, 1),
                    "realized_pts": round(realized_w, 1),
                    "brl_1c": round(realized_w * 0.20, 2),
                    "validation_status": val_status,
                    "validation_label": val_label,
                    "is_valid": is_valid,
                    "is_prev_day": False,
                    "closed_bar_confirmed": True,
                }
                signals_log.append(win_sig_obj)
                m5_enriched[entry_b_idx]["signal"] = win_sig_obj

        signals_log.sort(key=lambda s: s["bar_index"])
        return self._reconcile_mt5_terminal_live_deals(
            sess_date=sess_date,
            asset="WIN",
            today_closed_bars=today_closed_bars,
            m5_enriched=m5_enriched,
            walls_clean=walls_clean,
            strat_short_names=strat_short_names,
            sim_signals=signals_log,
        )

    def _evaluate_live_mt5_wdo_strategies(
        self,
        sess_date: str,
        m5_enriched: list,
        today_closed_bars: list,
        closes_all: np.ndarray,
        w_len: int,
        walls_clean: list,
        strat_short_names: dict,
        is_live_session: bool,
    ) -> list:
        """
        Avalia as estratégias WDO (`WDO_01`, `WDO_02`, `WDO_05`, `WDO_07`, `WDO_10`)
        seguindo 100% as fórmulas exatas do robô MQL5 (`Jumba_WDO_GEX_NWE_Core.mqh` + `wdo_mt5_sim.py`):
          - Duplo envelope causal NWE50(50, bw=5.0, mult=2.0) e NWE30(30, bw=3.0, mult=1.6)
          - Direção FADE correta no micro-rompimento da Wall NY (`WDO_01` Part A, `WDO_05` Part A, `WDO_07`)
          - Entradas Limit (`round05(b1.low+0.5)` / `round05(b1.high-0.5)` p/ `WDO_02` Part B e `WDO_05`)
            e Market na abertura da barra seguinte (`new_bar_open` p/ `WDO_01`, `WDO_02` Part A, `WDO_07`, `WDO_10`)
          - Alvos `TP_MIDWALL` (`CalcWdoTargetPts`) e `BE_WALL_SHIELD`
        """
        signals_log = []
        for eb in m5_enriched:
            eb["signal"] = None
        if len(today_closed_bars) < 3:
            return signals_log

        closes_m5 = np.array([float(eb["close"]) for eb in m5_enriched], dtype=float)
        n50_c, n50_u, n50_l, _, n50_s = self._compute_mt5_nwe_series(closes_m5, 50, 5.0, 2.0)
        n30_c, n30_u, n30_l, _, n30_s = self._compute_mt5_nwe_series(closes_m5, 30, 3.0, 1.6)

        rnd = self._round_wdo05
        slot_ids = ("WDO_01", "WDO_02", "WDO_05", "WDO_07", "WDO_10")
        busy_by_slot = {s: -1 for s in slot_ids}
        ops_by_slot = {s: 0 for s in slot_ids}

        for pos_k in range(2, len(today_closed_bars)):
            cur_b_idx, cur_eb = today_closed_bars[pos_k]
            b1_idx, b1 = today_closed_bars[pos_k - 1]
            b2_idx, b2 = today_closed_bars[pos_k - 2]

            t1_str = b1["time"]
            tm1 = int(t1_str[:2]) * 60 + int(t1_str[3:5])
            o1, h1, l1, c1 = float(b1["open"]), float(b1["high"]), float(b1["low"]), float(b1["close"])
            o2, h2, l2, c2 = float(b2["open"]), float(b2["high"]), float(b2["low"]), float(b2["close"])
            new_open = float(cur_eb["open"])

            rng1 = max(h1 - l1, 0.5)
            body1 = abs(c1 - o1)
            up_w1 = h1 - max(o1, c1)
            dn_w1 = min(o1, c1) - l1

            bw50_1 = max(n50_u[b1_idx] - n50_l[b1_idx], 0.5)
            pos50_1 = (c1 - n50_l[b1_idx]) / bw50_1
            s50_1 = float(n50_s[b1_idx])
            bw50_2 = max(n50_u[b2_idx] - n50_l[b2_idx], 0.5)
            pos50_2 = (c2 - n50_l[b2_idx]) / bw50_2

            bw30_1 = max(n30_u[b1_idx] - n30_l[b1_idx], 0.5)
            pos30_1 = (c1 - n30_l[b1_idx]) / bw30_1
            z30_1 = (c1 - n30_c[b1_idx]) / max(0.5, 0.5 * bw30_1)

            dc1, lc1, wc1 = self._find_nearest_wall_obj(walls_clean, c1)

            inst_5m = float(b1.get("inst_delta_bar", 0.0))
            inst_15m = sum(float(today_closed_bars[k_p][1].get("inst_delta_bar", 0.0)) for k_p in range(max(0, pos_k - 3), pos_k))
            ia5 = float(b1.get("inst_aggr_delta", inst_5m))
            ia15 = sum(float(today_closed_bars[k_p][1].get("inst_aggr_delta", today_closed_bars[k_p][1].get("inst_delta_bar", 0.0))) for k_p in range(max(0, pos_k - 3), pos_k))
            ip5 = float(b1.get("inst_pass_delta", 0.0))
            ip15 = sum(float(today_closed_bars[k_p][1].get("inst_pass_delta", 0.0)) for k_p in range(max(0, pos_k - 3), pos_k))
            r5 = float(b1.get("ret_delta_bar", 0.0))
            r15 = sum(float(today_closed_bars[k_p][1].get("ret_delta_bar", 0.0)) for k_p in range(max(0, pos_k - 3), pos_k))
            nr15 = ia15 + ip15
            c_prev3 = float(today_closed_bars[max(0, pos_k - 4)][1].get("close", o2))
            dp3 = c1 - c_prev3
            lot_imb = float(b1.get("lot_imb", 1.0))
            wdir1 = int(b1.get("window_dir", 1))
            fhist1 = float(b1.get("flow_hist", 0.0))
            hslope1 = fhist1 - float(b2.get("flow_hist", 0.0))
            delta_5m = float(b1.get("delta_bar", 0.0))

            b_ws = (wdir1 == 1) or (fhist1 >= -14.0) or (hslope1 >= 0.0)
            s_ws = (wdir1 == -1) or (fhist1 <= 14.0) or (hslope1 <= 0.0)
            b_abs = (inst_5m >= 0 or delta_5m >= 0 or dn_w1 >= 0.22 * rng1 or c1 >= o1) and (inst_5m >= -800.0)
            s_abs = (inst_5m <= 0 or delta_5m <= 0 or up_w1 >= 0.22 * rng1 or c1 <= o1) and (inst_5m <= 800.0)
            b6_combo = b_ws and b_abs
            s6_combo = s_ws and s_abs

            # 3_FLUXO_INST
            b_inst = (inst_5m >= 0.0) or (inst_15m >= 0.0)
            s_inst = (inst_5m <= 0.0) or (inst_15m <= 0.0)

            # 9_PROFIT_INST_RET & 13_NR_PRICE_ABS_DIV (WDO_01, WDO_05)
            b_inst_ret = (b_inst or (ip5 > 0.0 and r5 < 0.0) or (lot_imb >= 1.04)) and not (ia5 < -650.0 and lot_imb < 0.82)
            s_inst_ret = (s_inst or (ip5 < 0.0 and r5 > 0.0) or (lot_imb <= 0.96)) and not (ia5 > 650.0 and lot_imb > 1.22)
            b13_wdo = b_inst_ret and not (r5 > 70.0 and ip5 < -45.0 and ia5 <= 0) and not (ia5 < -250.0 and ip5 <= 0 and inst_15m < -300.0)
            s13_wdo = s_inst_ret and not (r5 < -70.0 and ip5 > 45.0 and ia5 >= 0) and not (ia5 > 250.0 and ip5 >= 0 and inst_15m > 300.0)

            # 12_NR_WALL_TRAP_DIV (WDO_07)
            sweep_crash_d = (ia5 < -480.0) and (lot_imb < 0.88) and (ip5 <= 0.0)
            sweep_surge_d = (ia5 > 480.0) and (lot_imb > 1.14) and (ip5 >= 0.0)
            b12_wdo = (((r5 < 0 or r15 < 0) and (ip5 >= 0 or ia5 > 0 or nr15 > 0)) or ((inst_5m > 0 and inst_15m > 0) and lot_imb >= 1.02) or (dn_w1 >= 0.28 * rng1 and (ip5 > 0 or ia5 >= 0))) and (not sweep_crash_d) and b_ws
            s12_wdo = (((r5 > 0 or r15 > 0) and (ip5 <= 0 or ia5 < 0 or nr15 < 0)) or ((inst_5m < 0 and inst_15m < 0) and lot_imb <= 0.98) or (up_w1 >= 0.28 * rng1 and (ip5 < 0 or ia5 <= 0))) and (not sweep_surge_d) and s_ws

            # 17_NR_SQUEEZE_CLEAN (WDO_02)
            b17_wdo = (b_inst or (ip5 > 0 and r5 < 0) or (lot_imb >= 1.03)) and not (r5 > 60.0 and (ip5 < -40.0 or ia5 < 0)) and not (dp3 > 3.0 and nr15 < -120.0) and not (ia5 < -250.0 and lot_imb < 0.92)
            s17_wdo = (s_inst or (ip5 < 0 and r5 > 0) or (lot_imb <= 0.97)) and not (r5 < -60.0 and (ip5 > 40.0 or ia5 > 0)) and not (dp3 < -3.0 and nr15 > 120.0) and not (ia5 > 250.0 and lot_imb > 1.08)

            # (sid, sig_dir, order_type, ord_px, fb_tp, sl_pts, be_trig, be_lock, w_buf, max_b, def_w_obj)
            cands = []

            # 1) WDO_01: Scalper Híbrido Wall NY (MQL5 `EvalWdo01_ScalperHibridoNY` + 13_NR_PRICE_ABS_DIV)
            if 600 <= tm1 <= 970 and cur_b_idx > busy_by_slot["WDO_01"] and ops_by_slot["WDO_01"] < 3 and dc1 <= 2.5 and wc1 is not None:
                if o1 <= lc1 + 0.5 and c1 > lc1 + 0.5 and (c1 - lc1) <= 4.5 and body1 >= 2.0 and s50_1 >= 0.15 and 0.45 <= pos50_1 <= 0.88 and s13_wdo:
                    cands.append(("WDO_01", -1, "MKT", new_open, 10.0, 9.5, 5.5, 1.5, 1.0, 18, wc1))
                elif o1 >= lc1 - 0.5 and c1 < lc1 - 0.5 and (lc1 - c1) <= 4.5 and body1 >= 2.0 and s50_1 <= -0.15 and 0.12 <= pos50_1 <= 0.55 and b13_wdo:
                    cands.append(("WDO_01", 1, "MKT", new_open, 10.0, 9.5, 5.5, 1.5, 1.0, 18, wc1))
                elif pos50_2 <= 0.22 and c2 < o2 and c1 > o1 and c1 > 0.5 * (h2 + l2) and abs(s50_1) <= 0.45 and b13_wdo:
                    cands.append(("WDO_01", 1, "MKT", new_open, 10.0, 9.5, 5.5, 1.5, 1.0, 18, wc1))
                elif pos50_2 >= 0.78 and c2 > o2 and c1 < o1 and c1 < 0.5 * (h2 + l2) and abs(s50_1) <= 0.45 and s13_wdo:
                    cands.append(("WDO_01", -1, "MKT", new_open, 10.0, 9.5, 5.5, 1.5, 1.0, 18, wc1))

            # 2) WDO_02: Scalper Híbrido Core (MQL5 `EvalWdo02_ScalperHibridoCore` + 17_NR_SQUEEZE_CLEAN)
            if 545 <= tm1 <= 980 and cur_b_idx > busy_by_slot["WDO_02"] and ops_by_slot["WDO_02"] < 2 and bw50_1 >= 7.15 and dc1 <= 2.0 and wc1 is not None:
                if s50_1 >= 0.12 and 0.42 <= pos50_1 <= 0.82 and pos30_1 <= 0.65 and abs(l1 - lc1) <= 2.0 and c1 > lc1 and c1 > o1 and b17_wdo:
                    cands.append(("WDO_02", 1, "MKT", new_open, 9.5, 8.5, 5.0, 1.5, 1.0, 16, wc1))
                elif s50_1 <= -0.12 and 0.18 <= pos50_1 <= 0.58 and pos30_1 >= 0.35 and abs(h1 - lc1) <= 2.0 and c1 < lc1 and c1 < o1 and s17_wdo:
                    cands.append(("WDO_02", -1, "MKT", new_open, 9.5, 8.5, 5.0, 1.5, 1.0, 16, wc1))
                elif pos50_1 <= 0.20 and dn_w1 >= 0.32 * rng1 and c1 >= l1 + 0.55 * rng1 and abs(s50_1) <= 0.45 and b17_wdo:
                    cands.append(("WDO_02", 1, "LIM", rnd(l1 + 0.5), 9.5, 8.5, 5.0, 1.5, 1.0, 16, wc1))
                elif pos50_1 >= 0.80 and up_w1 >= 0.32 * rng1 and c1 <= h1 - 0.55 * rng1 and abs(s50_1) <= 0.45 and s17_wdo:
                    cands.append(("WDO_02", -1, "LIM", rnd(h1 - 0.5), 9.5, 8.5, 5.0, 1.5, 1.0, 16, wc1))

            # 3) WDO_05: Cluster NWE30+50 Wall (MQL5 `EvalWdo05_ClusterNweWall` + 13_NR_PRICE_ABS_DIV)
            if 550 <= tm1 <= 975 and cur_b_idx > busy_by_slot["WDO_05"] and ops_by_slot["WDO_05"] < 3 and wc1 is not None:
                if dc1 <= 4.5 and o1 <= lc1 + 0.5 and c1 > lc1 + 0.5 and (c1 - lc1) <= 4.5 and body1 >= 2.0 and s50_1 >= 0.15 and 0.45 <= pos50_1 <= 0.88 and s13_wdo:
                    cands.append(("WDO_05", -1, "LIM", rnd(h1 - 0.5), 10.5, 10.0, 5.5, 1.5, 1.0, 18, wc1))
                elif dc1 <= 4.5 and o1 >= lc1 - 0.5 and c1 < lc1 - 0.5 and (lc1 - c1) <= 4.5 and body1 >= 2.0 and s50_1 <= -0.15 and 0.12 <= pos50_1 <= 0.55 and b13_wdo:
                    cands.append(("WDO_05", 1, "LIM", rnd(l1 + 0.5), 10.5, 10.0, 5.5, 1.5, 1.0, 18, wc1))
                elif dc1 <= 2.5 and abs(n50_l[b1_idx] - n30_l[b1_idx]) <= 3.0 and pos50_1 <= 0.22 and pos30_1 <= 0.22 and c1 >= l1 + 0.50 * rng1 and s50_1 >= -0.45 and b13_wdo:
                    cands.append(("WDO_05", 1, "LIM", rnd(l1 + 0.5), 10.5, 10.0, 5.5, 1.5, 1.0, 18, wc1))
                elif dc1 <= 2.5 and abs(n50_u[b1_idx] - n30_u[b1_idx]) <= 3.0 and pos50_1 >= 0.78 and pos30_1 >= 0.78 and c1 <= h1 - 0.50 * rng1 and s50_1 <= 0.45 and s13_wdo:
                    cands.append(("WDO_05", -1, "LIM", rnd(h1 - 0.5), 10.5, 10.0, 5.5, 1.5, 1.0, 18, wc1))

            # 4) WDO_07: Absorção Mkt Wall NY (MQL5 `EvalWdo07_AbsorcaoWallNY` + 12_NR_WALL_TRAP_DIV)
            if 600 <= tm1 <= 960 and cur_b_idx > busy_by_slot["WDO_07"] and ops_by_slot["WDO_07"] < 3 and dc1 <= 4.5 and wc1 is not None:
                if o1 <= lc1 + 0.5 and c1 > lc1 + 0.5 and (c1 - lc1) <= 4.5 and body1 >= 2.0 and s50_1 >= 0.15 and 0.45 <= pos50_1 <= 0.88 and s12_wdo:
                    cands.append(("WDO_07", -1, "MKT", new_open, 11.0, 11.5, 6.0, 1.5, 1.0, 16, wc1))
                elif o1 >= lc1 - 0.5 and c1 < lc1 - 0.5 and (lc1 - c1) <= 4.5 and body1 >= 2.0 and s50_1 <= -0.15 and 0.12 <= pos50_1 <= 0.55 and b12_wdo:
                    cands.append(("WDO_07", 1, "MKT", new_open, 11.0, 11.5, 6.0, 1.5, 1.0, 16, wc1))

            # 5) WDO_10: Lunch Reversão NWE (MQL5 `EvalWdo10_LunchReversaoNwe` + 6_COMBO_SMART)
            if 710 <= tm1 <= 870 and cur_b_idx > busy_by_slot["WDO_10"] and ops_by_slot["WDO_10"] < 1 and bw50_1 >= 7.15 and dc1 <= 2.5 and wc1 is not None:
                if pos50_1 <= 0.25 and z30_1 <= -0.75 and abs(s50_1) <= 0.35 and c1 >= l1 + 0.50 * rng1 and b6_combo:
                    cands.append(("WDO_10", 1, "MKT", new_open, 9.5, 9.5, 5.0, 1.5, 1.5, 14, wc1))
                elif pos50_1 >= 0.75 and z30_1 >= 0.75 and abs(s50_1) <= 0.35 and c1 <= h1 - 0.50 * rng1 and s6_combo:
                    cands.append(("WDO_10", -1, "MKT", new_open, 9.5, 9.5, 5.0, 1.5, 1.5, 14, wc1))

            for sid, sig_dir, ord_type, ord_px, fb_tp, sl_pts, be_trig, be_lock, w_buf, max_b, nearest_w in cands:
                if ord_type == "LIM":
                    if (sig_dir == 1 and new_open < ord_px) or (sig_dir == -1 and new_open > ord_px):
                        continue
                    if (sig_dir == 1 and float(cur_eb["low"]) > ord_px) or (sig_dir == -1 and float(cur_eb["high"]) < ord_px):
                        continue
                    ep = rnd(ord_px)
                else:
                    ep = rnd(new_open)

                entry_b_idx = cur_b_idx
                entry_eb = cur_eb
                entry_t_str = entry_eb["time"]

                tr_tp = self._calc_wdo_structural_target_pts(ep, sig_dir, fb_tp, walls_clean, 0.5, 6.0)
                tp_px = rnd(ep + sig_dir * tr_tp)

                w_px_ref = float(nearest_w["price"]) if (nearest_w and nearest_w.get("price") is not None) else 0.0
                sl_px = rnd(ep - sig_dir * sl_pts)
                if w_px_ref > 0:
                    sl_px = min(sl_px, rnd(w_px_ref - 3.0)) if sig_dir == 1 else max(sl_px, rnd(w_px_ref + 3.0))
                tr_sl = round(abs(ep - sl_px), 1)

                sim_slice = today_closed_bars[pos_k : min(len(today_closed_bars), pos_k + max_b)]
                be_armed = False
                be_armed_idx = None
                be_armed_time = None
                curr_sl_px = sl_px
                mfe_w, mae_w, realized_w = 0.0, 0.0, 0.0
                exit_reason = ""
                closed_trade = False
                wdo_exit_idx = sim_slice[-1][0] if sim_slice else entry_b_idx

                for s_pos, (f_b_idx, fb) in enumerate(sim_slice):
                    fh, fl, fc = float(fb["high"]), float(fb["low"]), float(fb["close"])
                    fav = (fh - ep) if sig_dir > 0 else (ep - fl)
                    adv = (fl - ep) if sig_dir > 0 else (ep - fh)
                    if fav > mfe_w:
                        mfe_w = fav
                    if adv < mae_w:
                        mae_w = adv
                    if (sig_dir == 1 and fl <= curr_sl_px and (s_pos > 0 or ord_type == "MKT")) or (
                        sig_dir == -1 and fh >= curr_sl_px and (s_pos > 0 or ord_type == "MKT")
                    ):
                        realized_w = round(sig_dir * (curr_sl_px - ep), 1)
                        exit_reason = "BE" if be_armed else "SL"
                        closed_trade = True
                        wdo_exit_idx = f_b_idx
                        break
                    if (sig_dir == 1 and fh >= tp_px) or (sig_dir == -1 and fl <= tp_px):
                        realized_w = tr_tp
                        exit_reason = "TP"
                        closed_trade = True
                        wdo_exit_idx = f_b_idx
                        break
                    if not be_armed and mfe_w >= be_trig:
                        if w_px_ref > 0:
                            w_cand = rnd(w_px_ref - sig_dir * w_buf)
                            max_lock = rnd(ep + sig_dir * be_lock)
                            cand_sl = min(w_cand, max_lock) if sig_dir == 1 else max(w_cand, max_lock)
                            min_imp = rnd(ep - sig_dir * 3.0)
                            cand_sl = max(cand_sl, min_imp) if sig_dir == 1 else min(cand_sl, min_imp)
                        else:
                            cand_sl = rnd(ep + sig_dir * be_lock)
                        if (sig_dir == 1 and cand_sl > curr_sl_px) or (sig_dir == -1 and cand_sl < curr_sl_px):
                            curr_sl_px = cand_sl
                            be_armed = True
                            be_armed_idx = f_b_idx
                            be_armed_time = fb.get("time", "")

                busy_by_slot[sid] = max(busy_by_slot[sid], wdo_exit_idx)
                ops_by_slot[sid] += 1
                if not closed_trade:
                    if is_live_session and len(sim_slice) < max_b:
                        live_unr = round(sig_dir * (float(m5_enriched[-1]["close"]) - ep), 1)
                        val_status, val_label, is_valid, realized_w, exit_reason = (
                            "EM_ANDAMENTO", f"⏳ EM ABERTO ({live_unr:+.1f} pts)", None, live_unr, "ABERTA"
                        )
                    else:
                        last_fc = float(sim_slice[-1][1]["close"]) if sim_slice else ep
                        realized_w = round(sig_dir * (last_fc - ep), 1)
                        is_valid = realized_w > 0
                        exit_reason = "TEMPO"
                        val_status = "VALIDO_FAVORAVEL" if is_valid else "INVALIDO_CONTRA"
                        val_label = f"{'✅' if is_valid else '❌'} TEMPO ({realized_w:+.1f} pts)"
                else:
                    is_valid = realized_w > 0
                    val_status = "VALIDO_ALVO" if exit_reason == "TP" else ("VALIDO_FAVORAVEL" if exit_reason == "BE" else "INVALIDO_STOP")
                    val_label = (
                        f"✅ ALVO WALL (+{tr_tp:.1f} pts)"
                        if exit_reason == "TP"
                        else (f"🛡️ ESCUDO WALL ({realized_w:+.1f} pts)" if exit_reason == "BE" else f"❌ STOP ({realized_w:+.1f} pts)")
                    )

                wdo_ex_eb = m5_enriched[min(len(m5_enriched) - 1, wdo_exit_idx)]
                wdo_ex_px = round(float(m5_enriched[-1]["close"]), 2) if val_status == "EM_ANDAMENTO" else round(ep + sig_dir * realized_w, 2)
                short_nm = strat_short_names.get(sid, sid)
                wdo_sig_obj = {
                    "id": f"WDO_{entry_t_str}_{sid}_{'BUY' if sig_dir > 0 else 'SELL'}",
                    "strategy_id": sid,
                    "strategy_short": short_nm,
                    "bar_index": entry_b_idx,
                    "timestamp": entry_eb["timestamp"],
                    "time": entry_t_str,
                    "direction": "COMPRA" if sig_dir > 0 else "VENDA",
                    "dir_num": sig_dir,
                    "type": f"{short_nm} · {'COMPRA' if sig_dir > 0 else 'VENDA'}",
                    "entry_price": round(ep, 2),
                    "exit_bar_index": wdo_exit_idx,
                    "exit_time": wdo_ex_eb.get("time", entry_t_str),
                    "exit_price": wdo_ex_px,
                    "exit_reason": exit_reason,
                    "stop_price": round(sl_px, 2),
                    "tp_price": round(tp_px, 2),
                    "tp_tag": "TP",
                    "be_triggered": bool(be_armed),
                    "be_bar_index": be_armed_idx,
                    "be_time": be_armed_time,
                    "be_trigger_price": round(ep + sig_dir * be_trig, 2),
                    "be_stop_price": round(curr_sl_px if be_armed else (ep + sig_dir * be_lock), 2),
                    "wall_price": round(w_px_ref, 2) if w_px_ref > 0 else None,
                    "wall_type": nearest_w["type"] if nearest_w else short_nm,
                    "inst_delta_5m": entry_eb["inst_delta_bar"],
                    "dealer_hedge_5m": entry_eb["dealer_hedge_bar"],
                    "reason": f"{short_nm} ({sid}) c/ Fluxo · {val_label}",
                    "pnl_5m": round(realized_w, 1),
                    "pnl_15m": round(realized_w, 1),
                    "pnl_30m": round(realized_w, 1),
                    "mfe_30m": round(mfe_w, 1),
                    "mae_30m": round(mae_w, 1),
                    "realized_pts": round(realized_w, 1),
                    "brl_1c": round(realized_w * 10.0, 2),
                    "validation_status": val_status,
                    "validation_label": val_label,
                    "is_valid": is_valid,
                    "is_prev_day": False,
                    "closed_bar_confirmed": True,
                }
                signals_log.append(wdo_sig_obj)
                m5_enriched[entry_b_idx]["signal"] = wdo_sig_obj

        signals_log.sort(key=lambda s: s["bar_index"])
        return self._reconcile_mt5_terminal_live_deals(
            sess_date=sess_date,
            asset="WDO",
            today_closed_bars=today_closed_bars,
            m5_enriched=m5_enriched,
            walls_clean=walls_clean,
            strat_short_names=strat_short_names,
            sim_signals=signals_log,
        )

    @staticmethod
    def _detect_causal_visual_swing_divs(today_bars: list, is_win: bool) -> list:
        """
        Detector 100% causal idêntico ao `swingDivergences` (`F1➔F2` / `T1➔T2`) desenhado no `FluxoRealAsgChart`.
        Retorna lista de `(pos_idx, dir_num)` sobre `today_bars`.
        """
        p_tol = 50.0 if is_win else 1.5
        max_ext = 360.0 if is_win else 8.5
        sigs = []
        last_bull = -12
        last_bear = -12

        for i in range(4, len(today_bars)):
            b = today_bars[i]
            pb = today_bars[i - 1]
            p2b = today_bars[i - 2]
            p3b = today_bars[i - 3]

            h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
            ph, pl, pc = float(pb["high"]), float(pb["low"]), float(pb["close"])
            p2h, p2l = float(p2b["high"]), float(p2b["low"])
            p3h, p3l = float(p3b["high"]), float(p3b["low"])

            w_i = float(b.get("smart_swing_wave", 0.0))
            w_p1 = float(pb.get("smart_swing_wave", 0.0))
            w_p2 = float(p2b.get("smart_swing_wave", 0.0))
            wyk = float(b.get("wyckoff_abs_bar", 0.0))
            eff = float(b.get("effective_force_bar", 0.0))
            sv = float(b.get("sell_vol", 0.0))
            bv = float(b.get("buy_vol", 0.0))
            abl = float(b.get("avg_buy_lot", 3.1 if is_win else 4.0))
            asl = float(b.get("avg_sell_lot", 3.1 if is_win else 4.0))

            l2 = min(l, pl)
            h2 = max(h, ph)
            w_low2 = min(w_i, w_p1, w_p2)
            w_high2 = max(w_i, w_p1, w_p2)

            is_local_bottom = (
                l2 <= min(p2l, p3l) + (20.0 if is_win else 0.5)
                and (c >= l + (h - l) * 0.35 or c >= pc or wyk > 0)
                and (eff > 0 or wyk > 0 or w_i > 0)
            )
            is_local_top = (
                h2 >= max(p2h, p3h) - (20.0 if is_win else 0.5)
                and (c <= h - (h - l) * 0.35 or c <= pc or wyk < 0)
                and (eff < 0 or wyk < 0 or w_i < 0)
            )

            if is_local_bottom:
                best_p1 = None
                for j in range(max(1, i - 16), i - 2):
                    lj = float(today_bars[j]["low"])
                    l_prev = float(today_bars[max(0, j - 1)]["low"])
                    l_next = float(today_bars[min(i - 1, j + 1)]["low"])
                    if lj <= l_prev and lj <= l_next:
                        wj = min(
                            float(today_bars[j].get("smart_swing_wave", 0.0)),
                            float(today_bars[max(0, j - 1)].get("smart_swing_wave", 0.0)),
                            float(today_bars[min(i - 1, j + 1)].get("smart_swing_wave", 0.0)),
                        )
                        if best_p1 is None or lj < best_p1["price"]:
                            best_p1 = {"idx": j, "price": lj, "wave": wj, "sv": float(today_bars[j].get("sell_vol", 0.0))}
                if best_p1 is not None:
                    price_ok = (best_p1["price"] - max_ext) <= l2 <= (best_p1["price"] + p_tol)
                    wave_ok = (w_low2 > best_p1["wave"] + max(1500.0 if is_win else 180.0, abs(best_p1["wave"]) * 0.18)) or (best_p1["wave"] < 0 and w_i > 0)
                    sv_ok = (sv < best_p1["sv"] * 0.90) or (wyk > 0) or (abl >= asl)
                    if price_ok and wave_ok and sv_ok and (i - last_bull > 6):
                        sigs.append((i, 1))
                        last_bull = i

            if is_local_top:
                best_t1 = None
                for j in range(max(1, i - 16), i - 2):
                    hj = float(today_bars[j]["high"])
                    h_prev = float(today_bars[max(0, j - 1)]["high"])
                    h_next = float(today_bars[min(i - 1, j + 1)]["high"])
                    if hj >= h_prev and hj >= h_next:
                        wj = max(
                            float(today_bars[j].get("smart_swing_wave", 0.0)),
                            float(today_bars[max(0, j - 1)].get("smart_swing_wave", 0.0)),
                            float(today_bars[min(i - 1, j + 1)].get("smart_swing_wave", 0.0)),
                        )
                        if best_t1 is None or hj > best_t1["price"]:
                            best_t1 = {"idx": j, "price": hj, "wave": wj, "bv": float(today_bars[j].get("buy_vol", 0.0))}
                if best_t1 is not None:
                    price_ok = (best_t1["price"] - p_tol) <= h2 <= (best_t1["price"] + max_ext)
                    wave_ok = (w_high2 < best_t1["wave"] - max(1500.0 if is_win else 180.0, abs(best_t1["wave"]) * 0.18)) or (best_t1["wave"] > 0 and w_i < 0)
                    bv_ok = (bv < best_t1["bv"] * 0.90) or (wyk < 0) or (asl >= abl)
                    if price_ok and wave_ok and bv_ok and (i - last_bear > 6):
                        sigs.append((i, -1))
                        last_bear = i

        return sigs

    def _append_live_especialista_v22(
        self,
        m5_enriched: list,
        today_closed_bars: list,
        signals_log: list,
        is_live_session: bool,
        walls_clean: list,
    ) -> None:
        """
        Especialista ESP_DIV_V22_WIN (WIN, 2 ct) do painel 5176, pela regra única de `core/especialista_v22.py`
        (a mesma que gerou o histórico). Sinal só em barras fechadas; a barra em formação entra apenas com a abertura.
        """
        if not today_closed_bars:
            return
        from core import especialista_v22 as esp

        idx_list = [b_i for b_i, _ in today_closed_bars]
        bars = [eb for _, eb in today_closed_bars]
        sig_bars = bars[:-1] if (is_live_session and len(bars) > 1) else bars
        try:
            trades = esp.run(sig_bars, walls_clean or [], exec_bars=bars, is_live=is_live_session)
        except Exception as exc:  # noqa: BLE001
            print(f"[especialista_v22] {exc!r}")
            return
        for k_t, t in enumerate(trades):
            b_idx = idx_list[t["entry_idx"]]
            ex_idx = idx_list[t["exit_idx"]]
            eb = m5_enriched[b_idx]
            d = int(t["dir_num"])
            pts = float(t["pts"])
            if t["is_open"]:
                val_st, is_val = "EM_ANDAMENTO", None
                lbl = f"⏳ EM ABERTO 2L ({pts:+.0f}p · R$ {t['brl_1c']:+.0f})"
            else:
                is_val = pts > 0
                val_st = "VALIDO_FAVORAVEL" if is_val else "INVALIDO_STOP"
                why = {"STOP": "❌ STOP 200", "BE": "🛡️ BE +20", "TEMPO": "⏱️ SAÍDA 60 MIN", "17:25": "⏱️ SAÍDA 17:25"}.get(t["exit_reason"], t["exit_reason"])
                lbl = f"{why} ({pts:+.0f}p · R$ {t['brl_1c']:+.0f})"
            sig = {
                "id": f"WIN_{t['time']}_{esp.STRATEGY_ID}_{k_t}",
                "strategy_id": esp.STRATEGY_ID,
                "strategy_short": "WIN Especialista V3.2",
                "bar_index": b_idx,
                "timestamp": eb.get("timestamp"),
                "time": t["time"],
                "direction": t["direction"],
                "dir_num": d,
                "type": f"WIN Especialista V3.2 · {t['direction']}",
                "entry_price": t["entry_price"],
                "exit_bar_index": ex_idx,
                "exit_time": t["exit_time"],
                "exit_price": t["exit_price"],
                "exit_reason": "ABERTA" if t["is_open"] else t["exit_reason"],
                "stop_price": t["stop_price"],
                "tp_price": None,
                "tp1_price": None,
                "tp_tag": "SEM ALVO · 60 MIN",
                "contracts": 2,
                "be_triggered": t["be_triggered"],
                "be_trigger_price": t["be_trigger_price"],
                "be_stop_price": t["be_stop_price"],
                "time_limit": t["time_limit"],
                "reason": (f"Especialista V3.2 · div {t['f1_time']}→{t['f2_time']} · {t['anchor']} {t['trigger_kind']} "
                           f"gatilho {t['trigger_time']} · SL 200 · BE 180→20 · 12 barras · {lbl}"),
                "pnl_5m": pts, "pnl_15m": pts, "pnl_30m": pts,
                "mfe_30m": max(0.0, pts), "mae_30m": min(0.0, pts),
                "realized_pts": pts,
                "unrealized_pts": pts if t["is_open"] else None,
                "brl_1c": t["brl_1c"],
                "validation_status": val_st,
                "validation_label": lbl,
                "is_valid": is_val,
                "is_prev_day": False,
                "closed_bar_confirmed": True,
            }
            signals_log.append(sig)
        signals_log.sort(key=lambda x: x["bar_index"])

    def _append_live_carteira_4_v32(
        self,
        asset: str,
        m5_enriched: list,
        today_closed_bars: list,
        signals_log: list,
        is_live_session: bool,
        walls_clean: list,
    ) -> None:
        """
        Adiciona de forma independente (Opção A — sem compartilhamento de bloqueio entre estratégias)
        as 4 estratégias auditadas V3.2 do painel 5176 (`core/carteira_v32_estrategias.py`):
          WIN: C1a_BRK_WIN, SYM_DIV_WIN | WDO: V1a_DIV_WDO, SYM_DIV_WDO
        """
        if not today_closed_bars:
            return
        from core import carteira_v32_estrategias as C32

        a = asset.upper()
        idx_list = [b_i for b_i, _ in today_closed_bars]
        bars = [dict(eb) for _, eb in today_closed_bars]
        if idx_list[0] > 0:
            bars[0]["nwe50_prev_line"] = m5_enriched[idx_list[0] - 1].get("nwe50_line")
        sig_bars = bars[:-1] if (is_live_session and len(bars) > 1) else bars
        try:
            trades = C32.run_all_for_asset(a, sig_bars, walls_clean or [], exec_bars=bars, is_live=is_live_session)
        except Exception as exc:  # noqa: BLE001
            print(f"[carteira_v32_4s] {exc!r}")
            return
        is_win = a == "WIN"
        for k_t, t in enumerate(trades):
            sid = t["strategy_id"]
            cfg = C32.STRAT_CFGS[sid]
            short_nm = cfg["short"]
            b_idx = idx_list[t["entry_idx"]]
            ex_idx = idx_list[t["exit_idx"]]
            eb = m5_enriched[b_idx]
            d = int(t["dir_num"])
            pts = float(t["pts"])
            fmt_p = ".0f" if is_win else ".1f"
            if t["is_open"]:
                val_st, is_val = "EM_ANDAMENTO", None
                lbl = f"⏳ EM ABERTO ({pts:+{fmt_p}}p · R$ {t['brl_1c']:+.0f})"
            else:
                is_val = pts > 0
                val_st = "VALIDO_ALVO" if (t["exit_reason"] == "ALVO" and is_val) else ("VALIDO_FAVORAVEL" if is_val else "INVALIDO_STOP")
                why = {
                    "STOP": "❌ STOP",
                    "ALVO": "🎯 ALVO",
                    "TEMPO": f"⏱️ SAÍDA {cfg['tmax'] * 5}M",
                    "17:25": "⏱️ SAÍDA 17:25",
                }.get(t["exit_reason"], t["exit_reason"])
                lbl = f"{why} ({pts:+{fmt_p}}p · R$ {t['brl_1c']:+.0f})"
            tp_pts_val = t.get("tp_pts")
            tp_tag = f"TP {tp_pts_val:{fmt_p}}p" if tp_pts_val is not None else cfg["tp_tag_fmt"]
            sig = {
                "id": f"{a}_{t['time']}_{sid}_{k_t}",
                "strategy_id": sid,
                "strategy_short": short_nm,
                "bar_index": b_idx,
                "timestamp": eb.get("timestamp"),
                "time": t["time"],
                "direction": t["direction"],
                "dir_num": d,
                "type": f"{short_nm} · {t['direction']}",
                "entry_price": t["entry_price"],
                "exit_bar_index": ex_idx,
                "exit_time": t["exit_time"],
                "exit_price": t["exit_price"],
                "exit_reason": "ABERTA" if t["is_open"] else t["exit_reason"],
                "stop_price": t["stop_price"],
                "tp_price": t["tp_price"],
                "tp1_price": None,
                "tp_tag": tp_tag,
                "contracts": int(t.get("contracts", 1)),
                "be_triggered": False,
                "be_trigger_price": None,
                "be_stop_price": None,
                "time_limit": t["time_limit"],
                "reason": f"{t.get('reason_detail', short_nm)} · {lbl}",
                "pnl_5m": pts,
                "pnl_15m": pts,
                "pnl_30m": pts,
                "mfe_30m": max(0.0, pts),
                "mae_30m": min(0.0, pts),
                "realized_pts": pts,
                "unrealized_pts": pts if t["is_open"] else None,
                "brl_1c": t["brl_1c"],
                "validation_status": val_st,
                "validation_label": lbl,
                "is_valid": is_val,
                "is_prev_day": False,
                "closed_bar_confirmed": True,
            }
            signals_log.append(sig)
        signals_log.sort(key=lambda x: (x["bar_index"], str(x.get("strategy_id", ""))))

    def _append_live_unified_divergence_signals(
        self,
        asset: str,
        m5_enriched: list,
        today_closed_bars: list,
        signals_log: list,
        is_live_session: bool,
    ) -> None:
        """
        Anexa de forma aditiva (sem alterar os sinais EST_*/WDO_* do localhost:5174)
        as operações Sniper F1➔F2 / T1➔T2 da Opção 2 para o localhost:5176 em pregões live (> last_bt_date):
          - WIN_DIV_WALL (2 ct): Sniper F1➔F2/T1➔T2 (tol=2b, c/ sobreposição) + 09:05–16:45 (s/ 12h) + Meta Diária >= +R$ 180
          - WDO_DIV_WALL (1 ct): Sniper F1➔F2/T1➔T2 (tol=2b, c/ sobreposição) + 09:00–17:00 (s/ 11h NY/PTAX) + Meta Diária >= +R$ 120
        """
        if not signals_log or not today_closed_bars:
            return
        is_win = asset.upper() == "WIN"
        seen_keys = set()
        today_only_bars = [eb for _, eb in today_closed_bars]
        bar_idx_to_pos = {b_i: pos for pos, (b_i, _) in enumerate(today_closed_bars)}
        # Motor de divergência unificado (12/11/2026): v3.2 sem módulo de abertura, o mesmo do especialista ESP_DIV_V22_WIN.
        # Substitui o detector "visual" B (`_detect_causal_visual_swing_divs`, mantido só como referência).
        from core.div_engines_view import sniper_divs
        sig_bars = today_only_bars[:-1] if (is_live_session and len(today_only_bars) > 1) else today_only_bars
        vis_divs = sniper_divs(asset.upper(), sig_bars)   # só barras fechadas (a última ao vivo ainda está formando)

        if not is_win:
            allowed_wdo = {"WDO_01", "WDO_05", "WDO_07", "WDO_10"}
            added = []
            for idx_s, s in enumerate(sorted(signals_log, key=lambda x: x["bar_index"])):
                if s.get("strategy_id") not in allowed_wdo or s.get("is_prev_day"):
                    continue
                t_str = str(s.get("time") or "")
                if t_str < "09:00" or t_str > "17:00" or ("11:00" <= t_str <= "11:55"):
                    continue
                key = (t_str, s.get("direction"))
                if key in seen_keys:
                    continue
                pos_in = bar_idx_to_pos.get(int(s["bar_index"]))
                if pos_in is None:
                    continue
                s_dir = 1 if s.get("direction") == "COMPRA" else -1
                # Versão B (auditoria 11/11/2026): entrada no fechamento da barra do sinal ⇒ divergência até essa barra,
                # mesma janela do histórico (3 barras: entrada−3 … entrada−1).
                if not any(sd == s_dir and (pos_in - 2) <= si <= pos_in for (si, sd) in vis_divs):
                    continue
                # Meta Causal de Gain Diário WDO (1 ct): >= +R$ 120,00 já encerrados até t_str
                realized_wdo = sum(
                    float(prev.get("brl_1c") or 0.0)
                    for prev in added
                    if prev.get("is_valid") is not None and str(prev.get("exit_time") or "23:59") < t_str
                )
                if realized_wdo >= 120.0:
                    continue

                seen_keys.add(key)
                sc = dict(s)
                is_closed = sc.get("is_valid") is not None and str(sc.get("validation_status", "")).upper() not in ("EM_ANDAMENTO", "ABERTA")
                raw_pts = float(sc.get("realized_pts") or 0.0)
                net_pts = round(raw_pts - (0.5 if is_closed else 0.0), 1)
                sc["id"] = f"WDO_{t_str}_WDO_DIV_WALL_{idx_s}"
                sc["strategy_id"] = "WDO_DIV_WALL"
                sc["strategy_short"] = "WDO Div 1L MidWall"
                sc["type"] = f"WDO Div 1L MidWall · {sc.get('direction')}"
                sc["contracts"] = 1
                sc["realized_pts"] = net_pts
                sc["brl_1c"] = round(net_pts * 10.0, 2)
                if is_closed:
                    sc["is_valid"] = net_pts > 0
                added.append(sc)
            signals_log.extend(added)
            signals_log.sort(key=lambda x: x["bar_index"])
            return

        # WIN_DIV_WALL: Sniper F1➔F2/T1➔T2 (tol=2b, c/ sobreposição) + Horário s/ 12h + Meta Diária >= +R$ 180 + 2 Lotes Mix
        allowed_win = {"EST_01", "EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "EST_16", "WIN_E2"}
        rnd5 = self._round_win5

        def check_bar_3motor(b_idx_chk: int, s_dir_chk: int) -> bool:
            if b_idx_chk < 0 or b_idx_chk >= len(m5_enriched):
                return False
            eb_c = m5_enriched[b_idx_chk]
            o_i, h_i, l_i, c_i = float(eb_c["open"]), float(eb_c["high"]), float(eb_c["low"]), float(eb_c["close"])
            wyk_i = float(eb_c.get("wyckoff_abs_bar", 0.0))
            urg_i = float(eb_c.get("lot_urgency_bar", 0.0))
            eff_i = float(eb_c.get("effective_force_bar", 0.0))
            imp3_i = float(eb_c.get("swing_impulse_3b", 0.0))
            w_i = float(eb_c.get("smart_swing_wave", 0.0))
            bull_sw = bool((eb_c.get("swing_divergence") or {}).get("type") == "BULL_DIV")
            bear_sw = bool((eb_c.get("swing_divergence") or {}).get("type") == "BEAR_DIV")
            if b_idx_chk >= 3:
                l_2b = min(l_i, float(m5_enriched[b_idx_chk - 1]["low"]))
                h_2b = max(h_i, float(m5_enriched[b_idx_chk - 1]["high"]))
                w_low_2 = min(w_i, float(m5_enriched[b_idx_chk - 1].get("smart_swing_wave", w_i)))
                w_high_2 = max(w_i, float(m5_enriched[b_idx_chk - 1].get("smart_swing_wave", w_i)))
                for k_b in range(b_idx_chk - 2, max(0, b_idx_chk - 16), -1):
                    kb = m5_enriched[k_b]
                    if kb.get("is_prev_day"):
                        continue
                    l_k, h_k = float(kb["low"]), float(kb["high"])
                    w_k = float(kb.get("smart_swing_wave", 0.0))
                    sv_i = float(eb_c.get("sell_vol", 0.0)) + float(m5_enriched[b_idx_chk - 1].get("sell_vol", 0.0))
                    sv_k = float(kb.get("sell_vol", 0.0)) + float(m5_enriched[max(0, k_b - 1)].get("sell_vol", 0.0))
                    bv_i = float(eb_c.get("buy_vol", 0.0)) + float(m5_enriched[b_idx_chk - 1].get("buy_vol", 0.0))
                    bv_k = float(kb.get("buy_vol", 0.0)) + float(m5_enriched[max(0, k_b - 1)].get("buy_vol", 0.0))
                    if (-380.0 <= (l_2b - l_k) <= 50.0) and (max(w_i, w_low_2) > w_k + 1200 or sv_i < 0.85 * sv_k or wyk_i > 0):
                        bull_sw = True
                    if (-50.0 <= (h_2b - h_k) <= 380.0) and (min(w_i, w_high_2) < w_k - 1200 or bv_i < 0.85 * bv_k or wyk_i < 0):
                        bear_sw = True
            dp3 = c_i - float(m5_enriched[max(0, b_idx_chk - 3)]["close"])
            if s_dir_chk > 0:
                return (
                    (bull_sw and (eff_i > 0 or wyk_i > 0 or imp3_i > 0 or urg_i > 0))
                    or ((dp3 <= 30.0 or c_i <= o_i) and (wyk_i > 0 or eff_i > 0 or imp3_i > 0))
                    or (eff_i > 0 and imp3_i > 0 and wyk_i >= -800)
                )
            return (
                (bear_sw and (eff_i < 0 or wyk_i < 0 or imp3_i < 0 or urg_i < 0))
                or ((dp3 >= -30.0 or c_i >= o_i) and (wyk_i < 0 or eff_i < 0 or imp3_i < 0))
                or (eff_i < 0 and imp3_i < 0 and wyk_i <= 800)
            )

        def causal_nwe30_tp1(ep_v: float, s_dir_v: int, bar_i: int) -> float:
            if bar_i <= 0 and m5_enriched:
                eb0 = m5_enriched[0]
                prev_k = "nwe30_prev_upper" if s_dir_v > 0 else "nwe30_prev_lower"
                cur_k = "nwe30_upper" if s_dir_v > 0 else "nwe30_lower"
                opp30 = float(eb0.get(prev_k, eb0.get(cur_k, ep_v + s_dir_v * 400.0)))
            else:
                ref_i = max(0, bar_i - 1)
                eb_r = m5_enriched[ref_i]
                opp30 = float(eb_r.get("nwe30_upper" if s_dir_v > 0 else "nwe30_lower", ep_v + s_dir_v * 400.0))
            raw_p = opp30 - s_dir_v * 15.0
            clip_p = np.clip(raw_p, ep_v + 260.0, ep_v + 750.0) if s_dir_v > 0 else np.clip(raw_p, ep_v - 750.0, ep_v - 260.0)
            return rnd5(float(clip_p))

        added_win = []
        for idx_s, s in enumerate(sorted(signals_log, key=lambda x: x["bar_index"])):
            if s.get("strategy_id") not in allowed_win or s.get("is_prev_day"):
                continue
            t_str = str(s.get("time") or "")
            if t_str < "09:05" or t_str > "16:45" or ("12:00" <= t_str <= "12:55"):
                continue
            key = (t_str, s.get("direction"))
            if key in seen_keys:
                continue
            b_idx = int(s["bar_index"])
            pos_in = bar_idx_to_pos.get(b_idx)
            if pos_in is None:
                continue
            s_dir = 1 if s.get("direction") == "COMPRA" else -1
            # Versão B (auditoria 11/11/2026): 3 motores só na barra do sinal (= barra anterior à entrada) e
            # divergência na mesma janela do histórico (entrada−3 … entrada−1).
            if not check_bar_3motor(b_idx, s_dir):
                continue
            if not any(sd == s_dir and (pos_in - 2) <= si <= pos_in for (si, sd) in vis_divs):
                continue
            # Meta Causal de Gain Diário WIN (2 ct): >= +R$ 180,00 já encerrados até t_str
            realized_win = sum(
                float(prev.get("brl_1c") or 0.0)
                for prev in added_win
                if prev.get("is_valid") is not None and str(prev.get("exit_time") or "23:59") < t_str
            )
            if realized_win >= 180.0:
                continue
            seen_keys.add(key)

            ep = float(s.get("entry_price") or m5_enriched[b_idx]["close"])
            tp1_px = causal_nwe30_tp1(ep, s_dir, b_idx)
            tp2_px = rnd5(ep + s_dir * 750.0)
            sl1_init = rnd5(ep - s_dir * 240.0)
            sl2_init = rnd5(ep - s_dir * 260.0)
            sl1_px, sl2_px = sl1_init, sl2_init

            leg1_open, leg2_open = True, True
            be1_on, be2_on = False, False
            mfe = 0.0
            xp1, xp2 = ep, ep
            ex_idx = b_idx
            rsn1, rsn2 = "ABERTA", "ABERTA"

            for step_k, (f_idx, fb) in enumerate(today_closed_bars[pos_in + 1 :], start=1):
                bh, bl, bc, bo = float(fb["high"]), float(fb["low"]), float(fb["close"]), float(fb["open"])
                if fb["time"] >= "17:25":
                    if leg1_open:
                        xp1, leg1_open, rsn1 = bo, False, "EOD"
                    if leg2_open:
                        xp2, leg2_open, rsn2 = bo, False, "EOD"
                    ex_idx = f_idx
                    break

                if leg1_open:
                    tp1_px = causal_nwe30_tp1(ep, s_dir, f_idx)
                    if (s_dir == 1 and bl <= sl1_px) or (s_dir == -1 and bh >= sl1_px):
                        xp1, leg1_open, rsn1, ex_idx = sl1_px, False, ("BE" if be1_on else "SL"), f_idx
                    elif s_dir == 1 and bh >= tp1_px:
                        xp1, leg1_open, rsn1, ex_idx = (bo if bo >= tp1_px else tp1_px), False, "TP1", f_idx
                    elif s_dir == -1 and bl <= tp1_px:
                        xp1, leg1_open, rsn1, ex_idx = (bo if bo <= tp1_px else tp1_px), False, "TP1", f_idx

                if leg2_open:
                    if (s_dir == 1 and bl <= sl2_px) or (s_dir == -1 and bh >= sl2_px):
                        xp2, leg2_open, rsn2, ex_idx = sl2_px, False, ("BE" if be2_on else "SL"), f_idx
                    elif (s_dir == 1 and bh >= tp2_px) or (s_dir == -1 and bl <= tp2_px):
                        xp2, leg2_open, rsn2, ex_idx = tp2_px, False, "TP2", f_idx

                fav = (bh - ep) if s_dir == 1 else (ep - bl)
                if fav > mfe:
                    mfe = fav

                next_pos = pos_in + 1 + step_k
                if mfe >= 180.0 and next_pos < len(today_closed_bars):
                    no = float(today_closed_bars[next_pos][1]["open"])
                    cand = ep + s_dir * 20.0
                    if leg1_open and not be1_on and ((s_dir == 1 and cand > sl1_px and no > cand) or (s_dir == -1 and cand < sl1_px and no < cand)):
                        sl1_px, be1_on = cand, True
                    if leg2_open and not be2_on and ((s_dir == 1 and cand > sl2_px and no > cand) or (s_dir == -1 and cand < sl2_px and no < cand)):
                        sl2_px, be2_on = cand, True

                if step_k >= 24:
                    if leg1_open:
                        xp1, leg1_open, rsn1 = bc, False, "TEMPO"
                    if leg2_open:
                        xp2, leg2_open, rsn2 = bc, False, "TEMPO"
                    ex_idx = f_idx
                    break
                if not leg1_open and not leg2_open:
                    break

            last_c = float(m5_enriched[-1]["close"])
            if (leg1_open or leg2_open) and is_live_session:
                cur_xp1 = last_c if leg1_open else xp1
                cur_xp2 = last_c if leg2_open else xp2
                pts1 = round((cur_xp1 - ep) * s_dir - (0.0 if leg1_open else 10.0), 1)
                pts2 = round((cur_xp2 - ep) * s_dir - (0.0 if leg2_open else 10.0), 1)
                tot_pts = round(pts1 + pts2, 1)
                tot_brl = round(tot_pts * 0.20, 2)
                val_st = "EM_ANDAMENTO"
                is_val = None
                ex_idx = today_closed_bars[-1][0]
                lbl = f"⏳ EM ABERTO 2L ({tot_pts:+.0f}p · R$ {tot_brl:+.0f})"
                ex_px = round(0.5 * (cur_xp1 + cur_xp2), 1)
            else:
                if leg1_open:
                    xp1 = float(today_closed_bars[-1][1]["close"])
                if leg2_open:
                    xp2 = float(today_closed_bars[-1][1]["close"])
                pts1 = round((xp1 - ep) * s_dir - 10.0, 1)
                pts2 = round((xp2 - ep) * s_dir - 10.0, 1)
                tot_pts = round(pts1 + pts2, 1)
                tot_brl = round(tot_pts * 0.20, 2)
                is_val = tot_pts > 0
                val_st = "VALIDO_ALVO" if (rsn1 == "TP1" and is_val) else ("VALIDO_FAVORAVEL" if is_val else "INVALIDO_STOP")
                if rsn1 == "TP1" and rsn2 == "TP2":
                    lbl = f"✅ ALVO DUPLO NWE30+750 ({tot_pts:+.0f}p · R$ {tot_brl:+.0f})"
                elif rsn1 == "TP1" and is_val:
                    lbl = f"✅ ALVO TP1 NWE30 + {rsn2} ({tot_pts:+.0f}p · R$ {tot_brl:+.0f})"
                elif is_val and (be1_on or be2_on):
                    lbl = f"🛡️ PROTEÇÃO BE ZERO ({tot_pts:+.0f}p · R$ {tot_brl:+.0f})"
                elif is_val:
                    lbl = f"✅ A FAVOR ({tot_pts:+.0f}p · R$ {tot_brl:+.0f})"
                else:
                    lbl = f"❌ STOP ({tot_pts:+.0f}p · R$ {tot_brl:+.0f})"
                ex_px = round(0.5 * (xp1 + xp2), 1)

            sc = dict(s)
            sc.update({
                "id": f"WIN_{s.get('time')}_WIN_DIV_WALL_{idx_s}",
                "strategy_id": "WIN_DIV_WALL",
                "strategy_short": "WIN Div 2L Mix",
                "type": f"WIN Div 2L Mix · {s.get('direction')}",
                "entry_price": round(ep, 2),
                "exit_bar_index": ex_idx,
                "exit_time": m5_enriched[min(len(m5_enriched) - 1, ex_idx)].get("time", s.get("time")),
                "exit_price": ex_px,
                "exit_reason": "ABERTA" if val_st == "EM_ANDAMENTO" else ("TP" if is_val else "SL"),
                "stop_price": round(sl2_init, 2),
                "sl1_price": round(sl1_init, 2),
                "tp_price": round(tp2_px, 2),
                "tp1_price": round(tp1_px, 2),
                "tp_tag": "TP2 (+750)",
                "contracts": 2,
                "pts_l1": pts1,
                "pts_l2": pts2,
                "be_triggered": bool(be1_on or be2_on),
                "be_trigger_price": round(ep + s_dir * 180.0, 2),
                "be_stop_price": round(ep + s_dir * 20.0, 2),
                "reason": f"WIN Div 2L Mix (NWE30 Din + 750p) · {lbl}",
                "pnl_5m": tot_pts,
                "pnl_15m": tot_pts,
                "pnl_30m": tot_pts,
                "realized_pts": tot_pts,
                "brl_1c": tot_brl,
                "validation_status": val_st,
                "validation_label": lbl,
                "is_valid": is_val,
            })
            added_win.append(sc)

        signals_log.extend(added_win)
        signals_log.sort(key=lambda x: x["bar_index"])

    def _build_asg_hud(
        self,
        asset: str,
        spot: float,
        vwap: float,
        m5_enriched: list,
        flow_Windows: list,
        flow_score: float,
        dealer_pressure_score: float,
        local_gex: dict,
        sup_walls: list,
        res_walls: list,
        op_state: str,
        symbol_payload: dict,
        is_live_session: bool = False,
    ) -> dict:
        """
        Constrói o payload completo para o HUD estilo A.S.G + Radar Pro:
          - Comando visual imediato: 'COMPRA', 'VENDA' ou 'NEUTRALIZADO' (baseado na última barra FECHADA)
          - Vela 3D Neon: MICRO (0-100%), MACRO (0-100%), MAKERS (% pressão GEX)
          - Gatilhos desenhados direto no gráfico: 'Precisa Romper 👉' e 'Zona Stop / Pullback'
          - Dominância Compradores % vs Vendedores %
          - Escada de Alvos 1 -> 2 -> 3
        """
        is_win = asset.upper() == "WIN"
        step_default = 150.0 if is_win else 5.0

        # Usa a barra atual em tempo real para refletir imediatamente a leitura do fluxo minuto a minuto
        last_bar = m5_enriched[-1] if m5_enriched else {}
        win_dir = int(last_bar.get("window_dir", 0))
        hist_val = float(last_bar.get("flow_hist", 0.0))
        p_up = float(last_bar.get("price_upper_trava", spot + step_default * 0.5))
        p_dn = float(last_bar.get("price_lower_trava", spot - step_default * 0.5))
        p_mid = float(last_bar.get("price_mid_trava", spot))
        win_entry = float(last_bar.get("window_entry_price", spot))

        # Dominância Compradores vs Vendedores (últimos 15m combinados com fluxo institucional)
        w15 = symbol_payload.get("flow_compass", {}).get("windows", {}).get("15m", {})
        b_vol = float(w15.get("buy_vol", 0.0))
        s_vol = float(w15.get("sell_vol", 0.0))
        if (b_vol + s_vol) > 0:
            buyers_pct = int(round(np.clip((b_vol / (b_vol + s_vol)) * 100.0, 5.0, 95.0)))
        else:
            buyers_pct = int(round(np.clip(50.0 + hist_val * 0.4, 10.0, 90.0)))
        sellers_pct = 100 - buyers_pct

        # MICRO (0 a 100): força imediata na janela atual
        micro_raw = 0.55 * abs(hist_val) + 0.45 * abs(flow_score)
        micro_pct = int(round(np.clip(35.0 + micro_raw * 0.65, 15.0, 99.0)))

        # MACRO (0 a 100): tendência estrutural da sessão (CVD Institucional + VWAP + Dealers)
        cvd_now = float(last_bar.get("cvd_inst", 0.0))
        macro_dir = 1 if (cvd_now > 0 and spot >= vwap) else (-1 if (cvd_now < 0 and spot <= vwap) else win_dir)
        macro_pct = int(round(np.clip(45.0 + 0.45 * abs(hist_val) + (15.0 if macro_dir == win_dir else -10.0), 20.0, 98.0)))

        # MAKERS (%): pressão dos Market Makers GEX
        makers_pct = round(dealer_pressure_score / 40.0, 2)

        # Decisão do Semáforo Central A.S.G: COMPRA, VENDA ou NEUTRALIZADO
        nearest_sup = sup_walls[0] if sup_walls else None
        nearest_res = res_walls[0] if res_walls else None

        # Verifica se está num ponto de conflito forte (ex: tentando comprar colado no teto com rejeição ou hist fraco)
        is_conflict = (
            abs(hist_val) < 7.0
            or (win_dir > 0 and flow_score < -25.0)
            or (win_dir < 0 and flow_score > 25.0)
        )

        if is_conflict:
            command = "NEUTRALIZADO"
            command_sub = "REGIÃO DE TRANSIÇÃO · AGUARDAR DEFINIÇÃO DO FLUXO"
            command_color = "#00d4ff"
        elif win_dir > 0:
            command = "COMPRA"
            command_sub = "SIGA O FLUXO COMPRADOR · JANELA VERDE ATIVA"
            command_color = "#00e87a"
        else:
            command = "VENDA"
            command_sub = "SIGA O FLUXO VENDEDOR · JANELA VERMELHA ATIVA"
            command_color = "#ff3860"

        # Linhas operacionais desenhadas direto no gráfico ("Precisa Romper 👉" e "Zona Stop / Pullback")
        if win_dir >= 0:
            precisa_romper = round(max(p_up, last_bar.get("high", spot)), 2)
            zona_stop = round(min(p_dn, last_bar.get("low", spot) - (35.0 if is_win else 1.5)), 2)
            raw_targets = [w["price"] for w in res_walls if w["price"] > spot]
            while len(raw_targets) < 3:
                prev_t = raw_targets[-1] if raw_targets else spot
                raw_targets.append(round(prev_t + step_default, 2))
        else:
            precisa_romper = round(min(p_dn, last_bar.get("low", spot)), 2)
            zona_stop = round(max(p_up, last_bar.get("high", spot) + (35.0 if is_win else 1.5)), 2)
            raw_targets = [w["price"] for w in sup_walls if w["price"] < spot]
            while len(raw_targets) < 3:
                prev_t = raw_targets[-1] if raw_targets else spot
                raw_targets.append(round(prev_t - step_default, 2))

        active_win = flow_Windows[-1] if flow_Windows else None

        return {
            "command": command,
            "command_sub": command_sub,
            "command_color": command_color,
            "window_dir": win_dir,
            "window_label": "AMBIENTE COMPRADO" if win_dir > 0 else "AMBIENTE VENDIDO",
            "window_start_time": active_win["start_time"] if active_win else "",
            "window_entry_price": round(win_entry, 2),
            "window_net_pts": active_win["net_pts"] if active_win else 0.0,
            "window_max_favor_pts": active_win["max_favor_pts"] if active_win else 0.0,
            "micro_pct": micro_pct,
            "macro_pct": macro_pct,
            "makers_pct": makers_pct,
            "buyers_pct": buyers_pct,
            "sellers_pct": sellers_pct,
            "precisa_romper": precisa_romper,
            "zona_stop": zona_stop,
            "p_mid_trava": p_mid,
            "targets": [round(t, 2) for t in raw_targets[:3]],
            "buy_zone": {
                "price_top": round(
                    nearest_sup["price"] + ((35.0 if is_win else 1.2) if "mid" in str(nearest_sup.get("type", "")).lower() else (45.0 if is_win else 1.5)),
                    2,
                ) if nearest_sup else round(p_dn, 2),
                "price_bot": round(
                    nearest_sup["price"] - ((35.0 if is_win else 1.2) if "mid" in str(nearest_sup.get("type", "")).lower() else (45.0 if is_win else 1.5)),
                    2,
                ) if nearest_sup else round(p_dn - step_default * 0.4, 2),
                "label": f"Região de Compra ({nearest_sup['type']})" if nearest_sup else "Região de Compra",
                "ref_price": round(nearest_sup["price"], 2) if nearest_sup else round(p_dn, 2),
                "wall_type": nearest_sup.get("type", "Wall") if nearest_sup else "Trava",
                "defense_lots": int(nearest_sup.get("defense_lots", 0)) if nearest_sup else 0,
                "maker_hedge_lots": int(nearest_sup.get("maker_hedge_lots", 0)) if nearest_sup else 0,
            },
            "sell_zone": {
                "price_top": round(
                    nearest_res["price"] + ((35.0 if is_win else 1.2) if "mid" in str(nearest_res.get("type", "")).lower() else (45.0 if is_win else 1.5)),
                    2,
                ) if nearest_res else round(p_up + step_default * 0.4, 2),
                "price_bot": round(
                    nearest_res["price"] - ((35.0 if is_win else 1.2) if "mid" in str(nearest_res.get("type", "")).lower() else (45.0 if is_win else 1.5)),
                    2,
                ) if nearest_res else round(p_up, 2),
                "label": f"Região de Venda ({nearest_res['type']})" if nearest_res else "Região de Venda",
                "ref_price": round(nearest_res["price"], 2) if nearest_res else round(p_up, 2),
                "wall_type": nearest_res.get("type", "Wall") if nearest_res else "Trava",
                "defense_lots": int(nearest_res.get("defense_lots", 0)) if nearest_res else 0,
                "maker_hedge_lots": int(nearest_res.get("maker_hedge_lots", 0)) if nearest_res else 0,
            },
        }

    def _ensure_portfolio_6_cache_loaded(self) -> None:
        cache_path = os.path.join(PROJECT_ROOT, "data", "processed", "portfolio_4_sistematicas_equity_v1.json")
        curr_mtime = os.path.getmtime(cache_path) if os.path.exists(cache_path) else 0
        if (
            not hasattr(self, "_portfolio_4_base")
            or self._portfolio_4_base is None
            or getattr(self, "_portfolio_4_mtime", 0) != curr_mtime
        ):
            self._portfolio_4_mtime = curr_mtime
            self._portfolio_6_trades_by_date = {}
            try:
                if os.path.exists(cache_path):
                    with open(cache_path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    summary_1c = raw.get("summary_1c", {})
                    strat_ids = [
                        "EST_01", "EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "EST_16", "WIN_E2", "WIN_DIV_WALL",
                        "WDO_01", "WDO_02", "WDO_05", "WDO_07", "WDO_09", "WDO_10", "WDO_11", "WDO_S2", "WDO_DIV_WALL",
                        "ESP_DIV_V22_WIN", "C1a_BRK_WIN", "V1a_DIV_WDO", "SYM_DIV_WIN", "SYM_DIV_WDO",
                    ]
                    stats_acc = {
                        k: {"wins": 0, "ops": 0, "gross_win_1c": 0.0, "gross_loss_1c": 0.0}
                        for k in strat_ids
                    }
                    compact_days = []
                    raw_days = raw.get("days", [])
                    for d in raw_days:
                        d_date = str(d.get("date", ""))
                        d_trades = [t for t in (d.get("trades", []) or []) if t.get("in_base", True)]
                        self._portfolio_6_trades_by_date[d_date] = d_trades
                        for t in d_trades:
                            sid = t.get("strategy_id")
                            if sid in stats_acc:
                                brl = float(t.get("brl_1c", 0.0))
                                stats_acc[sid]["ops"] += 1
                                if brl > 0:
                                    stats_acc[sid]["wins"] += 1
                                    stats_acc[sid]["gross_win_1c"] += brl
                                elif brl < 0:
                                    stats_acc[sid]["gross_loss_1c"] += abs(brl)
                        dc = dict(d)
                        dc["date"] = d_date
                        dc["month"] = d.get("month", d_date[:7])
                        dc["is_live"] = False
                        slim_trades = []
                        for tr in (d.get("trades", []) or []):
                            slim_trades.append({
                                "date": tr.get("date", d_date),
                                "time": tr.get("time", ""),
                                "exit_time": tr.get("exit_time", ""),
                                "asset": tr.get("asset", ""),
                                "strategy_id": tr.get("strategy_id", ""),
                                "direction": tr.get("direction", ""),
                                "entry_price": tr.get("entry_price", 0),
                                "exit_price": tr.get("exit_price", 0),
                                "tp_price": tr.get("tp_price"),
                                "tp1_price": tr.get("tp1_price"),
                                "stop_price": tr.get("stop_price"),
                                "pts": tr.get("pts", 0),
                                "pts_l1": tr.get("pts_l1"),
                                "pts_l2": tr.get("pts_l2"),
                                "brl_1c": tr.get("brl_1c", 0),
                                "contracts": tr.get("contracts", 1),
                                "label": tr.get("label", ""),
                                "status": tr.get("status", "FECHADA"),
                                "in_base": tr.get("in_base", True),
                            })
                        dc["trades"] = slim_trades
                        compact_days.append(dc)

                    for k, st in stats_acc.items():
                        if k in summary_1c and st["ops"] > 0:
                            summary_1c[k]["wins"] = st["wins"]
                            summary_1c[k]["gross_win_1c"] = round(st["gross_win_1c"], 2)
                            summary_1c[k]["gross_loss_1c"] = round(st["gross_loss_1c"], 2)

                    self._portfolio_4_base = {
                        "version": raw.get("version", "4.0_11_STRATEGIES_NWE_WALLS_FLOW"),
                        "start_date": raw.get("start_date", "2026-05-11"),
                        "last_bt_date": raw.get("last_bt_date", "2026-11-04"),
                        "total_bt_sessions": raw.get("total_bt_sessions", len(compact_days)),
                        "all_11_comparison": raw.get("all_11_comparison", []),
                        "summary_1c": summary_1c,
                        "bt_days": compact_days,
                    }
                else:
                    self._portfolio_4_base = None
            except Exception:
                self._portfolio_4_base = None

    def _get_setup_trades(self, sess_date: str, asset: str, is_live_session: bool) -> list:
        """
        Trades dos setups registrados pelo runner único (`core/setups_live.py` → `core/setups_runner.py`).
        Dias passados: idêntico ao BT. Pregão corrente: mesmo código com corte na última barra M5 fechada.
        Em erro, devolve lista vazia (nunca cai na reimplementação antiga) e registra em `setups_live.LAST_STATUS`.
        O Sniper legado (WIN/WDO_DIV_WALL) dos dias passados continua vindo do JSON auditado.
        """
        from core import setups_live

        try:
            trades = setups_live.trades_for(str(sess_date), asset, is_live_session)
        except Exception as exc:  # noqa: BLE001
            setups_live.LAST_STATUS["error"] = f"{sess_date} {asset}: {exc!r}"
            print(f"[setups_live] {sess_date} {asset}: {exc!r}")
            trades = []
        if not is_live_session:
            legacy_ids = (
                "WIN_DIV_WALL",
                "WDO_DIV_WALL",
                "ESP_DIV_V22_WIN",
                "C1a_BRK_WIN",
                "V1a_DIV_WDO",
                "SYM_DIV_WIN",
                "SYM_DIV_WDO",
            )
            legacy = [t for t in self._get_portfolio_6_cached_trades(sess_date, asset)
                      if t.get("strategy_id") in legacy_ids]
            trades = trades + legacy
        return trades

    def _get_portfolio_6_cached_trades(self, sess_date: str, asset: str) -> list:
        """Retorna os trades auditados das 6 estratégias c/ filtro de fluxo para uma data e ativo."""
        self._ensure_portfolio_6_cache_loaded()
        trades_map = getattr(self, "_portfolio_6_trades_by_date", {}) or {}
        day_trades = trades_map.get(str(sess_date), []) or []
        asset_up = str(asset or "").upper()
        return [t for t in day_trades if str(t.get("asset", "")).upper() == asset_up]

    def build_portfolio_4_sistematicas_payload(self, snap: dict, lite: bool = False) -> dict:
        """
        Retorna a série histórica auditada (desde 07/05/2026) das 6 estratégias
        (EST_01, EST_07, EST_13, WDO_09, WDO_11, WDO_S2) + Portfólio Combinado, anexando dinamicamente
        o acompanhamento de Live Trading a partir de hoje (pregões > last_bt_date).
        """
        live_store_path = os.path.join(PROJECT_ROOT, "data", "processed", "portfolio_4_live_days.json")
        self._ensure_portfolio_6_cache_loaded()

        if not hasattr(self, "_live_days_map"):
            self._live_days_map = {}
            try:
                if os.path.exists(live_store_path):
                    with open(live_store_path, "r", encoding="utf-8") as f:
                        loaded_live = json.load(f)
                        if isinstance(loaded_live, dict):
                            self._live_days_map = loaded_live
            except Exception:
                self._live_days_map = {}

        if not self._portfolio_4_base:
            return {"ok": False, "error": "Cache portfolio_4_sistematicas não encontrado"}

        last_bt_date = self._portfolio_4_base["last_bt_date"]
        today_str = datetime.now().strftime("%Y-%m-%d")
        avail_dates = snap.get("available_dates") or []
        latest_sess_date = str(avail_dates[0]) if avail_dates else last_bt_date
        sel_date = str(snap.get("selected_date") or latest_sess_date)
        is_hist = bool(snap.get("is_historical", False))
        strat_ids = (
            "EST_01", "EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "EST_16", "WIN_E2", "WIN_DIV_WALL",
            "WDO_01", "WDO_02", "WDO_05", "WDO_07", "WDO_09", "WDO_10", "WDO_11", "WDO_S2", "WDO_DIV_WALL",
            "ESP_DIV_V22_WIN", "C1a_BRK_WIN", "V1a_DIV_WDO", "SYM_DIV_WIN", "SYM_DIV_WDO",
        )

        # Limpa registros legados (pré-Sniper v2, sem WIN_DIV_WALL, pré-carteira 4s V3.2 ou <= last_bt_date)
        for k_old in list(self._live_days_map.keys()):
            if (
                k_old <= last_bt_date
                or "EST_01_pts" not in self._live_days_map[k_old]
                or "WIN_DIV_WALL_pts" not in self._live_days_map[k_old]
                or not self._live_days_map[k_old].get("sniper_v32")
                or not self._live_days_map[k_old].get("carteira_v32_4s")
            ):
                del self._live_days_map[k_old]

        # Se o snapshot atual é de um pregão real pós-backtest (> last_bt_date), atualiza os sinais live desse dia
        if sel_date > last_bt_date:
            day_rec = {
                "date": sel_date,
                "month": sel_date[:7],
                "is_live": True,
                "sniper_v32": True,
                "carteira_v32_4s": True,
                "trades": [],
                "open_trades": [],
            }
            for sid_k in strat_ids:
                day_rec[f"{sid_k}_pts"] = 0.0
                day_rec[f"{sid_k}_ops"] = 0
            for asset_k, mult_1c in [("WIN", 0.20), ("WDO", 10.0)]:
                sigs = snap.get(asset_k, {}).get("caminho_a", {}).get("signals_log", []) or []
                for s in reversed(sigs):
                    if s.get("is_prev_day"):
                        continue
                    sid = s.get("strategy_id")
                    if sid not in strat_ids:
                        t_str = str(s.get("type", "")).upper()
                        if asset_k == "WIN":
                            sid = "EST_13" if "13" in t_str or "GRID" in t_str else ("EST_07" if "07" in t_str or "CLIMAX" in t_str or "BREAKOUT" in t_str else "EST_01")
                        else:
                            sid = "WDO_11" if "11" in t_str or "PINNED" in t_str or "GRID" in t_str else ("WDO_09" if "09" in t_str or "TREND" in t_str or "CLUSTER" in t_str else "WDO_S2")
                    val_st = str(s.get("validation_status") or s.get("status") or "").upper()
                    if val_st and val_st not in ("EM_ANDAMENTO", "ABERTA") and s.get("realized_pts") is not None:
                        pts = float(s["realized_pts"])
                        day_rec[f"{sid}_pts"] = round(day_rec[f"{sid}_pts"] + pts, 2)
                        day_rec[f"{sid}_ops"] += 1
                        day_rec["trades"].append({
                            "date": sel_date,
                            "month": sel_date[:7],
                            "time": s.get("time", ""),
                            "exit_time": s.get("exit_time", ""),
                            "asset": asset_k,
                            "strategy_id": sid,
                            "direction": s.get("direction", ""),
                            "type": s.get("type", ""),
                            "entry_price": s.get("entry_price", 0.0),
                            "exit_price": s.get("exit_price", 0.0),
                            "tp_price": s.get("tp_price"),
                            "tp1_price": s.get("tp1_price"),
                            "stop_price": s.get("stop_price"),
                            "pts": round(pts, 2),
                            "pts_l1": s.get("pts_l1"),
                            "pts_l2": s.get("pts_l2"),
                            "brl_1c": round(float(s.get("brl_1c", pts * mult_1c)), 2),
                            "contracts": int(s.get("contracts", 2 if sid in ("WIN_DIV_WALL", "ESP_DIV_V22_WIN") else 1)),
                            "label": s.get("validation_label") or s.get("outcome_label", ""),
                            "status": "FECHADA",
                        })
                    elif val_st in ("EM_ANDAMENTO", "ABERTA"):
                        unr = float(s.get("unrealized_pts") or s.get("pnl_30m") or s.get("pnl_15m") or s.get("pnl_5m") or 0.0)
                        day_rec["open_trades"].append({
                            "date": sel_date,
                            "time": s.get("time", ""),
                            "asset": asset_k,
                            "strategy_id": sid,
                            "direction": s.get("direction", ""),
                            "type": s.get("type", ""),
                            "entry_price": s.get("entry_price", 0.0),
                            "stop_price": s.get("stop_price", 0.0),
                            "tp_price": s.get("tp_price", 0.0),
                            "tp1_price": s.get("tp1_price"),
                            "pts": round(unr, 2),
                            "brl_1c": round(float(s.get("brl_1c", unr * mult_1c)), 2),
                            "contracts": int(s.get("contracts", 2 if sid in ("WIN_DIV_WALL", "ESP_DIV_V22_WIN") else 1)),
                            "label": s.get("validation_label") or s.get("outcome_label", "⏳ EM ABERTO"),
                            "status": "ABERTA",
                        })
            self._live_days_map[sel_date] = day_rec
            if day_rec["trades"]:
                try:
                    with open(live_store_path, "w", encoding="utf-8") as f:
                        json.dump(self._live_days_map, f, ensure_ascii=False)
                except Exception:
                    pass

        live_days_sorted = [
            self._live_days_map[d]
            for d in sorted(self._live_days_map.keys())
            if d > last_bt_date
        ]

        days_out = [] if lite else list(self._portfolio_4_base["bt_days"])

        return {
            "ok": True,
            "is_lite": bool(lite),
            "version": self._portfolio_4_base["version"],
            "start_date": self._portfolio_4_base["start_date"],
            "last_bt_date": last_bt_date,
            "live_start_date": live_days_sorted[0]["date"] if live_days_sorted else last_bt_date,
            "total_bt_sessions": self._portfolio_4_base["total_bt_sessions"],
            "total_live_sessions": len(live_days_sorted),
            "selected_date": sel_date,
            "is_historical_view": is_hist,
            "all_11_comparison": [] if lite else self._portfolio_4_base.get("all_11_comparison", []),
            "summary_1c": self._portfolio_4_base["summary_1c"],
            "days": days_out + live_days_sorted,
            "live_days": live_days_sorted,
        }

    def build_m1_asset_series(self, asset: str, sess_date: str = None) -> dict:
        """
        Reconstrói e enriquece a série intradiária de 1 Minuto (M1) para `WIN` ou `WDO`
        usando o índice nativo `.min` M1 do Profit (`decompose_min_bars`) com fallback para MT5 M1,
        incluindo:
          - Envelope NWE causal com warm-up do dia anterior (D-1)
          - Janela de Fluxo Smart Money Unificada (V5b · 0% Preço)
          - Onda de Fluxo Smart Money 3-Motores (`smart_swing_wave`) para divergências F1➔F2 / T1➔T2 em M1
        """
        if not hasattr(self, "_m1_series_cache"):
            self._m1_series_cache = {}

        is_win = asset.upper() == "WIN"
        asset_up = "WIN" if is_win else "WDO"
        today_str = datetime.now().strftime("%Y-%m-%d")

        from core.profit_wall_players_engine import _load_profit_min_index
        from core.profit_min_decomp import decompose_min_bars

        idx_map = _load_profit_min_index(asset_up)
        m1_dates = sorted(d for d, r in idx_map.items() if r.get("m1") is not None)

        target_date = (sess_date or "").strip()
        explicit_date = bool(target_date)
        if not target_date:
            target_date = today_str

        is_live_day = (target_date == today_str)
        cache_key = (asset_up, target_date)
        if not is_live_day and cache_key in self._m1_series_cache:
            return self._m1_series_cache[cache_key]

        raw_bars = []
        rec = idx_map.get(target_date)
        if rec is not None and rec.get("m1") is not None:
            try:
                raw_bars = decompose_min_bars(rec["m1"], asset_up, target_date)
            except Exception:
                raw_bars = []

        # Fallback MT5 M1 para sessão ao vivo ou data ainda não consolidada no .min
        if len(raw_bars) < 10:
            try:
                import MetaTrader5 as mt5
                from core.mt5_client import mt5_lock, connect_mt5
                dt_base = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                dt_start = dt_base.replace(hour=9, minute=0, second=0, microsecond=0)
                dt_end = dt_base.replace(hour=18, minute=35, second=0, microsecond=0)
                cont_sym = "WIN$N" if is_win else "WDO$N"
                with mt5_lock:
                    connect_mt5()
                    if mt5.terminal_info() is not None:
                        mt5.symbol_select(cont_sym, True)
                        rates = mt5.copy_rates_range(cont_sym, mt5.TIMEFRAME_M1, dt_start, dt_end)
                    else:
                        rates = None
                if rates is not None and len(rates) > 0:
                    tick_sz = 5.0 if is_win else 0.5
                    def_lot = 3.1 if is_win else 4.0
                    for r in rates:
                        rt = int(r["time"])
                        ro, rh, rl, rc = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
                        rv = float(r["real_volume"]) if r["real_volume"] > 0 else float(r["tick_volume"]) * (15.0 if is_win else 6.0)
                        rng_r = max(rh - rl, tick_sz)
                        buy_frac = max(0.15, min(0.85, 0.5 + 0.42 * ((rc - ro) / rng_r)))
                        bq_r = max(1.0, round(rv * buy_frac))
                        sq_r = max(1.0, round(rv * (1.0 - buy_frac)))
                        lwr = max(0.0, min(ro, rc) - rl) / rng_r
                        uwr = max(0.0, rh - max(ro, rc)) / rng_r
                        ia_r = (bq_r - sq_r) * (0.52 if is_win else 0.64)
                        ip_r = (sq_r * (0.28 + 0.42 * lwr) - bq_r * (0.28 + 0.42 * uwr)) * 0.24
                        rd_r = (bq_r - sq_r) * (0.16 if is_win else 0.12)
                        raw_bars.append({
                            "ts": rt,
                            "time": datetime.fromtimestamp(rt, tz=timezone.utc).strftime("%H:%M"),
                            "open": ro, "high": rh, "low": rl, "close": rc,
                            "buy_vol": bq_r, "sell_vol": sq_r,
                            "avg_buy_lot": def_lot, "avg_sell_lot": def_lot,
                            "inst_aggr_delta": ia_r, "inst_pass_delta": ip_r, "ret_delta_bar": rd_r,
                        })
            except Exception:
                pass

        if not raw_bars and is_live_day and hasattr(self, "_m1_live_last_good") and cache_key in self._m1_live_last_good:
            return self._m1_live_last_good[cache_key]

        if not raw_bars and not explicit_date and m1_dates:
            target_date = m1_dates[-1]
            rec = idx_map.get(target_date)
            if rec is not None and rec.get("m1") is not None:
                raw_bars = decompose_min_bars(rec["m1"], asset_up, target_date)

        if not raw_bars:
            return {"ok": False, "date": target_date, "m1_series": [], "flow_windows": []}

        # Warm-up de barras M1 do pregão anterior (D-1) do mesmo contrato para NWE causal desde 09:00
        prev_dates = [d for d in m1_dates if d < target_date]
        warmup_closes = []
        if prev_dates:
            prev_rec = idx_map.get(prev_dates[-1])
            if prev_rec is not None and prev_rec.get("m1") is not None:
                try:
                    prev_bars = decompose_min_bars(prev_rec["m1"], asset_up, prev_dates[-1])
                    if prev_bars and abs(float(prev_bars[-1]["close"]) - float(raw_bars[0]["open"])) <= (3500.0 if is_win else 80.0):
                        warmup_closes = [float(pb["close"]) for pb in prev_bars[-200:]]
                except Exception:
                    warmup_closes = []

        w_len = len(warmup_closes)
        today_closes = np.array([float(b["close"]) for b in raw_bars], dtype=float)
        closes_all = np.concatenate([np.array(warmup_closes, dtype=float), today_closes]) if w_len > 0 else today_closes

        # NWE principal (5174) e NWE30 (5176) calibradas para M1
        nwe_c_all, nwe_u_all, nwe_l_all, nwe_mae_all, nwe_s_all = self._compute_mt5_nwe_series(closes_all, 100, 8.0, 1.8)
        n30_c_all, n30_u_all, n30_l_all, _, n30_s_all = self._compute_mt5_nwe_series(closes_all, 90, 5.0, 1.6)
        nwe_c = nwe_c_all[w_len:]
        nwe_u = nwe_u_all[w_len:]
        nwe_l = nwe_l_all[w_len:]
        nwe_mae = nwe_mae_all[w_len:]
        nwe_s = nwe_s_all[w_len:]
        n30_c = n30_c_all[w_len:]
        n30_u = n30_u_all[w_len:]
        n30_l = n30_l_all[w_len:]
        n30_s = n30_s_all[w_len:]

        # Parâmetros da Fórmula Unificada Smart Money (V5b) em M1:
        fast_p = 12.0
        slow_p = 60.0
        alpha_fast = 2.0 / (fast_p + 1.0)
        alpha_slow = 2.0 / (slow_p + 1.0)
        alpha_band = 2.0 / (21.0 + 1.0)
        smooth_a = 0.35 if is_win else 0.45
        flip_thr = 11.0
        tick_sz = 5.0 if is_win else 0.5
        def_lot = 3.1 if is_win else 4.0

        cum_iagg = 0.0
        cum_ipas = 0.0
        cum_ret = 0.0
        cum_sm_win = 0.0
        prev_cum_sm_win = 0.0
        ema_cvd_f = 0.0
        ema_cvd_s = 0.0
        ema_cvd_step = 800.0 if is_win else 130.0
        ema_hist = 0.0
        active_win_dir = 0
        curr_window = None
        sm_win_forces = []

        # Onda 3-Motores (5176) em M1 calibrada no mesmo horizonte temporal do M5 (15m rápido / 50m lento)
        cum_eff_3m = 0.0
        ema_eff_f3 = 0.0
        ema_eff_s3 = 0.0
        alpha_f3 = 2.0 / (15.0 + 1.0)
        alpha_s3 = 2.0 / (50.0 + 1.0)
        forces_3m = []

        m1_enriched = []
        flow_windows = []

        for idx, b in enumerate(raw_bars):
            t_str = str(b.get("time", ""))
            o = float(b["open"])
            h = float(b["high"])
            l = float(b["low"])
            c = float(b["close"])
            rng = max(h - l, tick_sz)
            bv = float(b.get("buy_vol", 0.0))
            sv = float(b.get("sell_vol", 0.0))
            tv = max(1.0, bv + sv)
            ab = float(b.get("avg_buy_lot", def_lot))
            as_l = float(b.get("avg_sell_lot", def_lot))
            ia = float(b.get("inst_aggr_delta", 0.0))
            ip = float(b.get("inst_pass_delta", 0.0))
            rd = float(b.get("ret_delta_bar", 0.0))
            delta_b = bv - sv

            prev_cvd = round(cum_iagg, 0)
            cum_iagg += ia
            cum_ipas += ip
            cum_ret += rd
            cvd = round(cum_iagg, 0)

            lw = max(0.0, min(o, c) - l)
            uw = max(0.0, h - max(o, c))
            phi_wyk = (
                sv * ((c - l) / rng) * (0.80 + 1.40 * (lw / rng))
                - bv * ((h - c) / rng) * (0.80 + 1.40 * (uw / rng))
            )
            phi_port = tv * ((ab - as_l) / max(0.5, ab + as_l)) * 2.2

            # 1) Janela de Fluxo Smart Money Unificada (V5b)
            phi_inst_v5 = 0.90 * ia + 0.75 * ip - 0.25 * rd
            bf_v5 = 0.12 * phi_wyk + 0.18 * phi_port + 0.70 * phi_inst_v5
            sm_win_forces.append(bf_v5)
            n_f = len(sm_win_forces)
            fp1 = sm_win_forces[n_f - 2] if n_f >= 2 else bf_v5
            fp2 = sm_win_forces[n_f - 3] if n_f >= 3 else fp1
            imp3_v5 = 0.45 * bf_v5 + 0.35 * fp1 + 0.20 * fp2

            cum_sm_win += bf_v5
            if idx == 0:
                ema_cvd_f = cum_sm_win
                ema_cvd_s = cum_sm_win
                prev_cum_sm_win = 0.0
            else:
                ema_cvd_f = alpha_fast * cum_sm_win + (1.0 - alpha_fast) * ema_cvd_f
                ema_cvd_s = alpha_slow * cum_sm_win + (1.0 - alpha_slow) * ema_cvd_s

            sw_v5 = 0.92 * (ema_cvd_f - ema_cvd_s) + 0.08 * imp3_v5
            ema_cvd_step = alpha_band * max(abs(cum_sm_win - prev_cum_sm_win), 180.0 if is_win else 35.0) + (1.0 - alpha_band) * ema_cvd_step
            prev_cum_sm_win = cum_sm_win

            raw_score = float(np.clip((sw_v5 / max(1.0, ema_cvd_step * 2.2)) * 55.0, -100.0, 100.0))
            ema_hist = smooth_a * raw_score + (1.0 - smooth_a) * ema_hist
            hist_val = round(float(np.clip(ema_hist, -100.0, 100.0)), 1)

            if active_win_dir == 0:
                active_win_dir = 1 if (hist_val >= 4.0 or (bf_v5 >= 0.0 and c >= o)) else -1
            elif active_win_dir == 1 and hist_val <= -flip_thr:
                active_win_dir = -1
            elif active_win_dir == -1 and hist_val >= flip_thr:
                active_win_dir = 1

            is_win_start = False
            if curr_window is None or curr_window["dir"] != active_win_dir:
                is_win_start = True
                if curr_window is not None and idx > 0:
                    curr_window["end_idx"] = idx - 1
                    curr_window["end_time"] = m1_enriched[idx - 1]["time"]
                    curr_window["end_price"] = m1_enriched[idx - 1]["close"]
                    curr_window["net_pts"] = round(
                        curr_window["dir"] * (curr_window["end_price"] - curr_window["entry_price"]), 1
                    )
                    flow_windows.append(curr_window)
                curr_window = {
                    "id": f"M1_WIN_{idx}_{t_str}",
                    "dir": active_win_dir,
                    "label": "JANELA DE COMPRA" if active_win_dir > 0 else "JANELA DE VENDA",
                    "start_idx": idx,
                    "start_time": t_str,
                    "entry_price": round(c, 2),
                    "max_favor_pts": 0.0,
                    "end_idx": idx,
                    "end_time": t_str,
                    "end_price": round(c, 2),
                    "net_pts": 0.0,
                }
            else:
                curr_window["end_idx"] = idx
                curr_window["end_time"] = t_str
                curr_window["end_price"] = round(c, 2)
                curr_window["net_pts"] = round(
                    curr_window["dir"] * (round(c, 2) - curr_window["entry_price"]), 1
                )
                fav_now = (round(h, 2) - curr_window["entry_price"]) if active_win_dir > 0 else (curr_window["entry_price"] - round(l, 2))
                if fav_now > curr_window["max_favor_pts"]:
                    curr_window["max_favor_pts"] = round(fav_now, 1)

            # 2) Onda Smart Money 3-Motores (5176) em M1 alinhada à escala de 15m (3 barras M5)
            phi_inst_3m = round(0.55 * ia + 1.15 * ip - 0.85 * rd, 0)
            bf_3m = round(0.45 * phi_wyk + 0.25 * phi_port + 0.30 * phi_inst_3m, 0)
            forces_3m.append(bf_3m)
            sum5_0 = sum(forces_3m[max(0, idx - 4): idx + 1])
            sum5_1 = sum(forces_3m[max(0, idx - 9): max(0, idx - 4)]) if idx >= 5 else sum5_0
            sum5_2 = sum(forces_3m[max(0, idx - 14): max(0, idx - 9)]) if idx >= 10 else sum5_1
            imp3_3m = round(0.45 * sum5_0 + 0.35 * sum5_1 + 0.20 * sum5_2, 0)
            cum_eff_3m += bf_3m
            if idx == 0:
                ema_eff_f3 = cum_eff_3m
                ema_eff_s3 = cum_eff_3m
            else:
                ema_eff_f3 = alpha_f3 * cum_eff_3m + (1.0 - alpha_f3) * ema_eff_f3
                ema_eff_s3 = alpha_s3 * cum_eff_3m + (1.0 - alpha_s3) * ema_eff_s3
            smart_wave_m1 = round((0.68 * (ema_eff_f3 - ema_eff_s3) + 0.32 * imp3_3m) * 2.2, 0)

            candle_state = (1 if c >= o else 0) if active_win_dir == 1 else (-1 if c <= o else 0)

            m1_enriched.append({
                "time": t_str,
                "ts": int(b.get("ts", 0)),
                "is_prev_day": False,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "buy_vol": round(bv, 0),
                "sell_vol": round(sv, 0),
                "avg_buy_lot": round(ab, 2),
                "avg_sell_lot": round(as_l, 2),
                "lot_imb": round(ab / max(0.1, as_l), 2),
                "delta_bar": round(delta_b, 0),
                "inst_delta_bar": round(ia, 0),
                "inst_aggr_delta": round(ia, 0),
                "inst_pass_delta": round(ip, 0),
                "ret_delta_bar": round(rd, 0),
                "hft_delta_bar": 0.0,
                "rlp_delta_bar": round(-rd * 0.42, 0),
                "cvd_total": round(cum_iagg + cum_ret, 0),
                "cvd_inst": cvd,
                "cvd_inst_aggr": cvd,
                "cvd_inst_pass": round(cum_ipas, 0),
                "cvd_retail": round(cum_ret, 0),
                "cvd_hft": 0.0,
                "cvd_rlp_delta": round(-cum_ret * 0.42, 0),
                "flow_open": prev_cvd,
                "flow_close": cvd,
                "flow_hist": hist_val,
                "window_dir": active_win_dir,
                "window_entry_price": curr_window["entry_price"],
                "is_window_start": is_win_start,
                "candle_state": candle_state,
                "nwe_line": round(float(nwe_c[idx]), 2),
                "nwe_mae": round(float(nwe_mae[idx]), 2),
                "nwe_upper": round(float(nwe_u[idx]), 2),
                "nwe_lower": round(float(nwe_l[idx]), 2),
                "nwe_is_up": bool(float(nwe_s[idx]) >= 0),
                "nwe100_line": round(float(nwe_c[idx]), 2),
                "nwe100_mae": round(float(nwe_mae[idx]), 2),
                "nwe100_upper": round(float(nwe_u[idx]), 2),
                "nwe100_lower": round(float(nwe_l[idx]), 2),
                "nwe100_is_up": bool(float(nwe_s[idx]) >= 0),
                "nwe30_line": round(float(n30_c[idx]), 2),
                "nwe30_upper": round(float(n30_u[idx]), 2),
                "nwe30_lower": round(float(n30_l[idx]), 2),
                "nwe30_is_up": bool(float(n30_s[idx]) >= 0),
                "wyckoff_abs_bar": round(phi_wyk, 0),
                "lot_urgency_bar": round(phi_port, 0),
                "smart_inst_bar": phi_inst_3m,
                "effective_force_bar": bf_3m,
                "swing_impulse_3b": imp3_3m,
                "smart_swing_wave": smart_wave_m1,
            })

        if curr_window is not None:
            flow_windows.append(curr_window)

        res = {
            "ok": True,
            "asset": asset_up,
            "date": target_date,
            "bars_count": len(m1_enriched),
            "m1_series": m1_enriched,
            "flow_windows": flow_windows,
        }
        if is_live_day and len(m1_enriched) > 0:
            if not hasattr(self, "_m1_live_last_good"):
                self._m1_live_last_good = {}
            self._m1_live_last_good[cache_key] = res
        elif not is_live_day and len(m1_enriched) >= 200:
            self._m1_series_cache[cache_key] = res
        return res

    def get_m1_chart_payload(self, sess_date: str = None) -> dict:
        win_m1 = self.build_m1_asset_series("WIN", sess_date)
        wdo_m1 = self.build_m1_asset_series("WDO", win_m1.get("date") or sess_date)
        has_bars = bool((win_m1.get("m1_series") or []) or (wdo_m1.get("m1_series") or []))
        return {
            "ok": has_bars,
            "date": win_m1.get("date") or wdo_m1.get("date") or sess_date,
            "WIN": win_m1,
            "WDO": wdo_m1,
        }


gex_dealer_engine_singleton = GexLiveDealerEngine()
