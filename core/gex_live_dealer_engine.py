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
        if self._prev_day_closes_cache is None:
            self._prev_day_closes_cache = {"WIN": {}, "WDO": {}, "dates": []}
            hist_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
                "processed",
                "gex_historical_sessions_v1",
            )
            if os.path.isdir(hist_dir):
                fnames = sorted(f[:-5] for f in os.listdir(hist_dir) if f.endswith(".json"))
                self._prev_day_closes_cache["dates"] = fnames
                for d_k in fnames:
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

        max_inst_wall_vol = max(
            [float(w.get("inst_total_vol", 0.0)) for w in all_walls_list if w.get("type") in ("Wall", "MidWall")]
            + [5000.0 if asset == "WIN" else 1000.0]
        )
        max_abs_gex = float(np.max(np.abs(model.strike_gex))) if len(model.strike_gex) > 0 else 1.0
        if max_abs_gex <= 0:
            max_abs_gex = 1.0

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

            is_res = wp > spot
            inst_b = float(w.get("inst_buy_vol", 0.0))
            inst_s = float(w.get("inst_sell_vol", 0.0))
            inst_tot = float(w.get("inst_total_vol", inst_b + inst_s))
            def_lots = inst_s if is_res else inst_b
            w["defense_lots"] = int(round(def_lots, 0))
            w["inst_total_vol"] = int(round(inst_tot, 0))

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
                    w["wall_power_pct"] = int(ref_w.get("wall_power_pct", 25))
                    w["wall_tier"] = ref_w.get("wall_tier", "MODERADA")
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

        # Calibração Campeã Conjunta da Janela de Fluxo A.S.G (124 pregões auditados):
        # - WIN: Fast=5, Slow=18, wCVD=0.85, Smooth=0.45, Flip=11.0 (100% meses positivos no WIN Rejeição + Ret/DD 24.20x no Combo WIN)
        # - WDO: Fast=4, Slow=22, wCVD=0.85, Smooth=0.60, Flip=11.0 (100% meses positivos no WDO Pullback + Ret/DD 11.38x)
        fast_period = 5.0 if is_win else 4.0
        slow_period = 18.0 if is_win else 22.0
        w_cvd_weight = 0.85
        w_price_weight = 0.15
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
        ema_cvd_f = first_cvd
        ema_cvd_s = first_cvd
        ema_cvd_step = max(abs(float(first_b.get("inst_delta_bar", 0.0))), 2500.0 if is_win else 500.0)
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
            if idx == first_today_idx and idx > 0:
                ema_p_high = round(h, 2)
                ema_p_low = round(l, 2)
                ema_atr = max(round(h, 2) - round(l, 2), 40.0 if is_win else 1.5)
                ema_cvd_f = cvd
                ema_cvd_s = cvd
                ema_cvd_step = max(abs(inst_5m), 2500.0 if is_win else 500.0)
                ema_hist = 0.0
                cum_dealer_hedge = 0.0
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

            # ── 1º PASSO: ATUALIZA JANELA DE FLUXO A.S.G DESTA BARRA ─────────────
            prev_cvd = m5_enriched[idx - 1]["cvd_inst"] if rel_idx > 0 else (cvd - round(inst_5m, 0))

            rng_bar = max(round(h, 2) - round(l, 2), 15.0 if is_win else 0.5)
            ema_atr = alpha_band * rng_bar + (1.0 - alpha_band) * ema_atr
            ema_p_high = alpha_band * round(h, 2) + (1.0 - alpha_band) * ema_p_high
            ema_p_low = alpha_band * round(l, 2) + (1.0 - alpha_band) * ema_p_low

            p_upper_trava = round(ema_p_high + 0.35 * ema_atr, 2)
            p_lower_trava = round(ema_p_low - 0.35 * ema_atr, 2)
            p_mid_trava = round(0.5 * (p_upper_trava + p_lower_trava), 2)

            ema_cvd_f = alpha_fast * cvd + (1.0 - alpha_fast) * ema_cvd_f
            ema_cvd_s = alpha_slow * cvd + (1.0 - alpha_slow) * ema_cvd_s
            ema_cvd_step = alpha_band * max(abs(cvd - prev_cvd), 500.0 if is_win else 100.0) + (1.0 - alpha_band) * ema_cvd_step

            flow_upper_trava = round(max(cvd, prev_cvd, ema_cvd_f) + 0.8 * ema_cvd_step, 0)
            flow_lower_trava = round(min(cvd, prev_cvd, ema_cvd_f) - 0.8 * ema_cvd_step, 0)

            raw_cvd_osc = (ema_cvd_f - ema_cvd_s) / max(1.0, ema_cvd_step * 1.4)
            raw_price_osc = (round(c, 2) - p_mid_trava) / max(1.0, ema_atr * 0.9)
            raw_score = float(np.clip((w_cvd_weight * raw_cvd_osc + w_price_weight * raw_price_osc) * 55.0, -100.0, 100.0))
            ema_hist = hist_smooth_alpha * raw_score + (1.0 - hist_smooth_alpha) * ema_hist
            hist_val = round(float(np.clip(ema_hist, -100.0, 100.0)), 1)

            # Virada de Janela A.S.G SÓ ocorre em barra FECHADA (não repinta intra-barra)
            if active_win_dir == 0:
                if hist_val >= 4.0 or (cvd >= prev_cvd and round(c, 2) >= round(o, 2)):
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
                "delta_bar": round(delta_5m, 0),
                "cvd_inst": cvd,
                "cvd_retail": round(float(b["cvd_retail"]), 0),
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

        # ── 3º PASSO: MODO CAMPEÃO 6 ESTRATÉGIAS C/ FILTRO DE FLUXO (WIN: EST_01 + EST_07 + EST_13 | WDO: WDO_09 + WDO_11 + WDO_S2) ──
        if use_champion_mode:
            today_closed_bars = [
                (i, eb) for i, eb in enumerate(m5_enriched[:closed_end])
                if not eb.get("is_prev_day", False) and eb.get("is_bar_closed", True)
            ]
            cached_bt_trades = self._get_portfolio_6_cached_trades(str(sess_date or ""), asset.upper())
            strat_short_names = {
                "EST_01": "WIN Rejeição",
                "EST_07": "WIN Rompimento",
                "EST_13": "WIN Next Wall",
                "WDO_09": "WDO Pullback",
                "WDO_11": "WDO Next Wall",
                "WDO_S2": "WDO Lunch",
            }
            if cached_bt_trades:
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
                    xpx = float(tr.get("exit_price") or (epx + s_dir * pts))
                    sl_px = float(tr.get("stop_price") or (epx - s_dir * (240.0 if is_win else 10.0)))
                    tp_px = float(tr.get("tp_price") or (epx + s_dir * (350.0 if is_win else 15.0)))
                    lbl = str(tr.get("label", ""))
                    is_val = pts > 0
                    val_st = "VALIDO_ALVO" if ("ALVO" in lbl and is_val) else ("VALIDO_FAVORAVEL" if is_val else "INVALIDO_STOP")
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
                        "tp_price": round(tp_px, 2),
                        "tp_tag": "TP",
                        "be_triggered": "PROTEÇÃO" in lbl or "ESCUDO" in lbl or "REDUZIDO" in lbl,
                        "be_bar_index": min(ex_idx, b_idx + 1),
                        "be_time": m5_enriched[min(ex_idx, b_idx + 1)].get("time", t_in),
                        "be_trigger_price": None,
                        "be_stop_price": round(epx, 2),
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
                        "validation_status": val_st,
                        "validation_label": lbl,
                        "is_valid": is_val,
                        "is_prev_day": False,
                        "closed_bar_confirmed": True,
                    }
                    signals_log.append(sig_obj)
                    m5_enriched[b_idx]["signal"] = sig_obj
                signals_log.sort(key=lambda s: s["bar_index"])
            elif is_win:
                # Live / Out-of-cache WIN: Avalia EST_01 (6_COMBO_SMART), EST_07 (3_FLUXO_INST) e EST_13 (4_FLUXO_ABSORCAO)
                signals_log = []
                for eb in m5_enriched:
                    eb["signal"] = None
                busy_by_slot = {"EST_01": -1, "EST_07": -1, "EST_13": -1}
                ops_by_slot = {"EST_01": 0, "EST_07": 0, "EST_13": 0}
                for pos_k, (b_idx, eb) in enumerate(today_closed_bars):
                    if pos_k < 2:
                        continue
                    t_str = eb["time"]
                    c = float(eb["close"])
                    o = float(eb["open"])
                    h = float(eb["high"])
                    l = float(eb["low"])
                    rng = float(eb.get("rng", max(h - l, 5.0)))
                    lower_wick = float(eb.get("lower_wick", min(o, c) - l))
                    upper_wick = float(eb.get("upper_wick", h - max(o, c)))
                    inst_5m = float(eb.get("inst_delta_bar", 0.0))
                    delta_5m = float(eb.get("delta_bar", 0.0))
                    pos_nwe = float(eb.get("nwe_pos_band", 0.0))
                    slp_nwe = float(eb.get("nwe_slope", 0.0))
                    w_dir = int(eb.get("window_dir", 0))
                    f_hist = float(eb.get("flow_hist", 0.0))
                    sup_w = eb.get("sup_w")
                    res_w = eb.get("res_w")

                    # Filtros do Dashboard para WIN
                    b_abs = (inst_5m >= 0 or delta_5m >= 0 or lower_wick >= 0.22 * rng or c >= o) and (inst_5m >= -12000.0)
                    s_abs = (inst_5m <= 0 or delta_5m <= 0 or upper_wick >= 0.22 * rng or c <= o) and (inst_5m <= 12000.0)
                    b_combo = (w_dir == 1 or f_hist >= -14.0) and b_abs
                    s_combo = (w_dir == -1 or f_hist <= 14.0) and s_abs
                    b_inst = (inst_5m >= 0)
                    s_inst = (inst_5m <= 0)

                    cands = []
                    # 1. EST_01: Scalper Híbrido NY (10:00–16:30) c/ 6_COMBO_SMART
                    if "10:00" <= t_str <= "16:30" and b_idx > busy_by_slot["EST_01"] and ops_by_slot["EST_01"] < 4:
                        if sup_w is not None and pos_nwe <= -0.35 and c > o and b_combo:
                            cands.append(("EST_01", 1, 350.0, 240.0, 150.0, 25.0, 16, sup_w))
                        elif res_w is not None and pos_nwe >= 0.35 and c < o and s_combo:
                            cands.append(("EST_01", -1, 350.0, 240.0, 150.0, 25.0, 16, res_w))

                    # 2. EST_07: Breakout Momentum NY (10:00–16:00) c/ 3_FLUXO_INST
                    if "10:00" <= t_str <= "16:00" and b_idx > busy_by_slot["EST_07"] and ops_by_slot["EST_07"] < 3:
                        if sup_w is not None and (c - o) >= 55.0 and slp_nwe >= 4.0 and b_inst:
                            cands.append(("EST_07", 1, 500.0, 240.0, 150.0, 20.0, 16, sup_w))
                        elif res_w is not None and (o - c) >= 55.0 and slp_nwe <= -4.0 and s_inst:
                            cands.append(("EST_07", -1, 500.0, 240.0, 150.0, 20.0, 16, res_w))

                    # 3. EST_13: SmartGrid CrossWDO+NextWall (09:05–16:15) c/ 4_FLUXO_ABSORCAO
                    if "09:05" <= t_str <= "16:15" and b_idx > busy_by_slot["EST_13"] and ops_by_slot["EST_13"] < 3:
                        if sup_w is not None and pos_nwe <= -0.15 and c > o and b_abs:
                            cands.append(("EST_13", 1, 220.0, 320.0, 130.0, 20.0, 18, sup_w))
                        elif res_w is not None and pos_nwe >= 0.15 and c < o and s_abs:
                            cands.append(("EST_13", -1, 220.0, 320.0, 130.0, 20.0, 18, res_w))

                    for sid, sig_dir, tr_tp, tr_sl, tr_be_trig, tr_be_lock, tr_max_b, nearest_w in cands:
                        future_slice = today_closed_bars[pos_k + 1 : min(len(today_closed_bars), pos_k + 1 + tr_max_b)]
                        be_armed = False
                        be_armed_idx = None
                        be_armed_time = None
                        mfe_w, mae_w, realized_w = 0.0, 0.0, 0.0
                        exit_reason = ""
                        closed_trade = False
                        win_exit_idx = future_slice[-1][0] if future_slice else b_idx
                        for f_b_idx, fb in future_slice:
                            fh, fl, fc = float(fb["high"]), float(fb["low"]), float(fb["close"])
                            fav = (fh - c) if sig_dir > 0 else (c - fl)
                            adv = (fl - c) if sig_dir > 0 else (c - fh)
                            if fav > mfe_w:
                                mfe_w = fav
                            if adv < mae_w:
                                mae_w = adv
                            eff_sl = -tr_be_lock if be_armed else tr_sl
                            if adv <= -eff_sl:
                                realized_w = -eff_sl
                                exit_reason = "BE" if eff_sl < 0 else "SL"
                                closed_trade = True
                                win_exit_idx = f_b_idx
                                break
                            elif fav >= tr_tp:
                                realized_w = tr_tp
                                exit_reason = "TP"
                                closed_trade = True
                                win_exit_idx = f_b_idx
                                break
                            if not be_armed and fav >= tr_be_trig:
                                be_armed = True
                                be_armed_idx = f_b_idx
                                be_armed_time = fb.get("time", "")
                        busy_by_slot[sid] = max(busy_by_slot[sid], win_exit_idx)
                        ops_by_slot[sid] += 1
                        if not closed_trade:
                            if is_live_session and len(future_slice) < tr_max_b:
                                val_status, val_label, is_valid, realized_w, exit_reason = "EM_ANDAMENTO", "⏳ EM ABERTO (Barra Fechada)", None, 0.0, "ABERTA"
                            else:
                                last_fc = float(future_slice[-1][1]["close"]) if future_slice else c
                                realized_w = round(sig_dir * (last_fc - c), 1)
                                is_valid = realized_w > 0
                                exit_reason = "TEMPO"
                                val_status = "VALIDO_FAVORAVEL" if is_valid else "INVALIDO_CONTRA"
                                val_label = f"{'✅' if is_valid else '❌'} TEMPO ({realized_w:+.0f} pts)"
                        else:
                            is_valid = realized_w > 0
                            val_status = "VALIDO_ALVO" if exit_reason == "TP" else ("VALIDO_FAVORAVEL" if exit_reason == "BE" else "INVALIDO_STOP")
                            val_label = f"✅ ALVO (+{tr_tp:.0f} pts)" if exit_reason == "TP" else (f"✅ PROTEÇÃO BE (+{realized_w:.0f} pts)" if exit_reason == "BE" else f"❌ STOP (-{tr_sl:.0f} pts)")
                        win_ex_eb = m5_enriched[min(len(m5_enriched) - 1, win_exit_idx)]
                        win_ex_px = round(float(m5_enriched[-1]["close"]), 2) if val_status == "EM_ANDAMENTO" else round(c + sig_dir * realized_w, 2)
                        short_nm = strat_short_names.get(sid, sid)
                        win_sig_obj = {
                            "id": f"{asset}_{t_str}_{sid}_{'BUY' if sig_dir > 0 else 'SELL'}",
                            "strategy_id": sid,
                            "strategy_short": short_nm,
                            "bar_index": b_idx,
                            "timestamp": eb["timestamp"],
                            "time": t_str,
                            "direction": "COMPRA" if sig_dir > 0 else "VENDA",
                            "dir_num": sig_dir,
                            "type": f"{short_nm} · {'COMPRA' if sig_dir > 0 else 'VENDA'}",
                            "entry_price": round(c, 2),
                            "exit_bar_index": win_exit_idx,
                            "exit_time": win_ex_eb.get("time", t_str),
                            "exit_price": win_ex_px,
                            "exit_reason": exit_reason,
                            "stop_price": round(c - sig_dir * tr_sl, 2),
                            "tp_price": round(c + sig_dir * tr_tp, 2),
                            "tp_tag": "TP",
                            "be_triggered": bool(be_armed),
                            "be_bar_index": be_armed_idx,
                            "be_time": be_armed_time,
                            "be_trigger_price": round(c + sig_dir * tr_be_trig, 2),
                            "be_stop_price": round(c + sig_dir * tr_be_lock, 2),
                            "wall_price": round(nearest_w["price"], 2) if nearest_w else None,
                            "wall_type": nearest_w["type"] if nearest_w else short_nm,
                            "inst_delta_5m": eb["inst_delta_bar"],
                            "dealer_hedge_5m": eb["dealer_hedge_bar"],
                            "reason": f"{short_nm} ({sid}) c/ Fluxo · {val_label}",
                            "pnl_5m": round(realized_w, 1),
                            "pnl_15m": round(realized_w, 1),
                            "pnl_30m": round(realized_w, 1),
                            "mfe_30m": round(mfe_w, 1),
                            "mae_30m": round(mae_w, 1),
                            "realized_pts": round(realized_w, 1),
                            "validation_status": val_status,
                            "validation_label": val_label,
                            "is_valid": is_valid,
                            "is_prev_day": False,
                            "closed_bar_confirmed": True,
                        }
                        signals_log.append(win_sig_obj)
                        m5_enriched[b_idx]["signal"] = win_sig_obj
                signals_log.sort(key=lambda s: s["bar_index"])
            else:
                # Live / Out-of-cache WDO: Avalia WDO_09 (1_JANELA_ASG), WDO_11 (4_FLUXO_ABSORCAO) e WDO_S2 (12:00-14:30 Reversão NWE c/ Fluxo)
                signals_log = []
                for eb in m5_enriched:
                    eb["signal"] = None
                busy_by_slot = {"WDO_09": -1, "WDO_11": -1, "WDO_S2": -1}
                ops_by_slot = {"WDO_09": 0, "WDO_11": 0, "WDO_S2": 0}
                last_s2_pos = -99
                for pos_k, (b_idx, eb) in enumerate(today_closed_bars):
                    if pos_k < 1:
                        continue
                    t_str = eb["time"]
                    c = float(eb["close"])
                    o = float(eb["open"])
                    h = float(eb["high"])
                    l = float(eb["low"])
                    rng = float(eb.get("rng", max(h - l, 0.5)))
                    lower_wick = float(eb.get("lower_wick", min(o, c) - l))
                    upper_wick = float(eb.get("upper_wick", h - max(o, c)))
                    inst_5m = float(eb.get("inst_delta_bar", 0.0))
                    delta_5m = float(eb.get("delta_bar", 0.0))
                    pos_nwe = float(eb.get("nwe_pos_band", 0.0))
                    w_dir = int(eb.get("window_dir", 0))
                    sup_w = eb.get("sup_w")
                    res_w = eb.get("res_w")

                    b_abs = (inst_5m >= 0 or delta_5m >= 0 or lower_wick >= 0.22 * rng or c >= o) and (inst_5m >= -800.0)
                    s_abs = (inst_5m <= 0 or delta_5m <= 0 or upper_wick >= 0.22 * rng or c <= o) and (inst_5m <= 800.0)

                    cands = []
                    # 1. WDO_09: Cluster NWE30+50 Wall (NO_LUNCH) c/ 1_JANELA_ASG
                    if ("09:05" <= t_str <= "12:15" or "13:30" <= t_str <= "16:15") and b_idx > busy_by_slot["WDO_09"] and ops_by_slot["WDO_09"] < 2:
                        if sup_w is not None and pos_nwe <= -0.35 and w_dir == 1:
                            cands.append(("WDO_09", 1, 14.0, 11.5, 6.5, 2.0, 16, sup_w))
                        elif res_w is not None and pos_nwe >= 0.35 and w_dir == -1:
                            cands.append(("WDO_09", -1, 14.0, 11.5, 6.5, 2.0, 16, res_w))

                    # 2. WDO_11: SmartGrid GF+NextWall (09:05–16:15) c/ 4_FLUXO_ABSORCAO
                    if "09:05" <= t_str <= "16:15" and b_idx > busy_by_slot["WDO_11"] and ops_by_slot["WDO_11"] < 2:
                        if sup_w is not None and pos_nwe <= -0.20 and c > o and b_abs:
                            cands.append(("WDO_11", 1, 12.0, 18.0, 6.0, 1.5, 20, sup_w))
                        elif res_w is not None and pos_nwe >= 0.20 and c < o and s_abs:
                            cands.append(("WDO_11", -1, 12.0, 18.0, 6.0, 1.5, 20, res_w))

                    # 3. WDO_S2: Reversão Banda Extrema NWE (12:00–14:30) c/ Fluxo
                    if ("12:00" <= t_str <= "14:30") and b_idx > busy_by_slot["WDO_S2"] and (pos_k - last_s2_pos) >= 3 and ops_by_slot["WDO_S2"] < 2:
                        if pos_nwe <= -0.75 and c >= l + 0.50 * rng and (lower_wick >= 0.25 * rng or c > o) and (inst_5m > 0 or delta_5m < 0):
                            candle_sl_d = min(10.0, round(max(1.5, (c - l) + 1.5), 2))
                            cands.append(("WDO_S2", 1, 15.0, 10.0, 5.0, -candle_sl_d, 24, sup_w))
                            last_s2_pos = pos_k
                        elif pos_nwe >= 0.75 and c <= h - 0.50 * rng and (upper_wick >= 0.25 * rng or c < o) and (inst_5m < 0 or delta_5m > 0):
                            candle_sl_d = min(10.0, round(max(1.5, (h - c) + 1.5), 2))
                            cands.append(("WDO_S2", -1, 15.0, 10.0, 5.0, -candle_sl_d, 24, res_w))
                            last_s2_pos = pos_k

                    for sid, sig_dir, tr_tp, tr_sl, tr_be_trig, tr_be_lock, tr_max_b, nearest_w in cands:
                        future_slice = today_closed_bars[pos_k + 1 : min(len(today_closed_bars), pos_k + 1 + tr_max_b)]
                        be_armed = False
                        be_armed_idx = None
                        be_armed_time = None
                        mfe_w, mae_w, realized_w = 0.0, 0.0, 0.0
                        exit_reason = ""
                        closed_trade = False
                        wdo_exit_idx = future_slice[-1][0] if future_slice else b_idx
                        for f_b_idx, fb in future_slice:
                            fh, fl, fc = float(fb["high"]), float(fb["low"]), float(fb["close"])
                            fav = (fh - c) if sig_dir > 0 else (c - fl)
                            adv = (fl - c) if sig_dir > 0 else (c - fh)
                            if fav > mfe_w:
                                mfe_w = fav
                            if adv < mae_w:
                                mae_w = adv
                            eff_sl = -tr_be_lock if be_armed else tr_sl
                            if adv <= -eff_sl:
                                realized_w = -eff_sl
                                exit_reason = "BE" if eff_sl < 0 else "SL"
                                closed_trade = True
                                wdo_exit_idx = f_b_idx
                                break
                            elif fav >= tr_tp:
                                realized_w = tr_tp
                                exit_reason = "TP"
                                closed_trade = True
                                wdo_exit_idx = f_b_idx
                                break
                            if not be_armed and fav >= tr_be_trig:
                                be_armed = True
                                be_armed_idx = f_b_idx
                                be_armed_time = fb.get("time", "")
                        busy_by_slot[sid] = max(busy_by_slot[sid], wdo_exit_idx)
                        ops_by_slot[sid] += 1
                        if not closed_trade:
                            if is_live_session and len(future_slice) < tr_max_b:
                                val_status, val_label, is_valid, realized_w, exit_reason = "EM_ANDAMENTO", "⏳ EM ABERTO (Barra Fechada)", None, 0.0, "ABERTA"
                            else:
                                last_fc = float(future_slice[-1][1]["close"]) if future_slice else c
                                realized_w = round(sig_dir * (last_fc - c), 1)
                                is_valid = realized_w > 0
                                exit_reason = "TEMPO"
                                val_status = "VALIDO_FAVORAVEL" if is_valid else "INVALIDO_CONTRA"
                                val_label = f"{'✅' if is_valid else '❌'} TEMPO ({realized_w:+.1f} pts)"
                        else:
                            is_valid = realized_w > 0
                            val_status = "VALIDO_ALVO" if exit_reason == "TP" else ("VALIDO_FAVORAVEL" if exit_reason == "BE" else "INVALIDO_STOP")
                            val_label = f"✅ ALVO (+{tr_tp:.1f} pts)" if exit_reason == "TP" else (f"✅ PROTEÇÃO BE (+{realized_w:.1f} pts)" if exit_reason == "BE" else f"❌ STOP ({realized_w:.1f} pts)")
                        wdo_ex_eb = m5_enriched[min(len(m5_enriched) - 1, wdo_exit_idx)]
                        wdo_ex_px = round(float(m5_enriched[-1]["close"]), 2) if val_status == "EM_ANDAMENTO" else round(c + sig_dir * realized_w, 2)
                        short_nm = strat_short_names.get(sid, sid)
                        wdo_sig_obj = {
                            "id": f"{asset}_{t_str}_{sid}_{'BUY' if sig_dir > 0 else 'SELL'}",
                            "strategy_id": sid,
                            "strategy_short": short_nm,
                            "bar_index": b_idx,
                            "timestamp": eb["timestamp"],
                            "time": t_str,
                            "direction": "COMPRA" if sig_dir > 0 else "VENDA",
                            "dir_num": sig_dir,
                            "type": f"{short_nm} · {'COMPRA' if sig_dir > 0 else 'VENDA'}",
                            "entry_price": round(c, 2),
                            "exit_bar_index": wdo_exit_idx,
                            "exit_time": wdo_ex_eb.get("time", t_str),
                            "exit_price": wdo_ex_px,
                            "exit_reason": exit_reason,
                            "stop_price": round(c - sig_dir * tr_sl, 2),
                            "tp_price": round(c + sig_dir * tr_tp, 2),
                            "tp_tag": "TP",
                            "be_triggered": bool(be_armed),
                            "be_bar_index": be_armed_idx,
                            "be_time": be_armed_time,
                            "be_trigger_price": round(c + sig_dir * tr_be_trig, 2),
                            "be_stop_price": round(c + sig_dir * tr_be_lock, 2),
                            "wall_price": round(nearest_w["price"], 2) if nearest_w else None,
                            "wall_type": nearest_w["type"] if nearest_w else short_nm,
                            "inst_delta_5m": eb["inst_delta_bar"],
                            "dealer_hedge_5m": eb["dealer_hedge_bar"],
                            "reason": f"{short_nm} ({sid}) c/ Fluxo · {val_label}",
                            "pnl_5m": round(realized_w, 1),
                            "pnl_15m": round(realized_w, 1),
                            "pnl_30m": round(realized_w, 1),
                            "mfe_30m": round(mfe_w, 1),
                            "mae_30m": round(mae_w, 1),
                            "realized_pts": round(realized_w, 1),
                            "validation_status": val_status,
                            "validation_label": val_label,
                            "is_valid": is_valid,
                            "is_prev_day": False,
                            "closed_bar_confirmed": True,
                        }
                        signals_log.append(wdo_sig_obj)
                        m5_enriched[b_idx]["signal"] = wdo_sig_obj
                signals_log.sort(key=lambda s: s["bar_index"])

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

        # Usa a última barra FECHADA quando em pregão ao vivo para não oscilar o comando intra-barra
        if is_live_session and len(m5_enriched) >= 2:
            last_bar = m5_enriched[-2]
        else:
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
                    strat_ids = ["EST_01", "EST_07", "EST_13", "WDO_09", "WDO_11", "WDO_S2"]
                    stats_acc = {
                        k: {"wins": 0, "ops": 0, "gross_win_1c": 0.0, "gross_loss_1c": 0.0}
                        for k in strat_ids
                    }
                    compact_days = []
                    raw_days = raw.get("days", [])
                    total_days = len(raw_days)
                    for idx_d, d in enumerate(raw_days):
                        d_date = str(d.get("date", ""))
                        d_trades = d.get("trades", []) or []
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
                        dc = {
                            "date": d_date,
                            "month": d.get("month", d_date[:7]),
                            "is_live": False,
                            "EST_01_pts": float(d.get("EST_01_pts", 0.0)),
                            "EST_07_pts": float(d.get("EST_07_pts", 0.0)),
                            "EST_13_pts": float(d.get("EST_13_pts", 0.0)),
                            "WDO_09_pts": float(d.get("WDO_09_pts", 0.0)),
                            "WDO_11_pts": float(d.get("WDO_11_pts", 0.0)),
                            "WDO_S2_pts": float(d.get("WDO_S2_pts", 0.0)),
                            "EST_01_ops": int(d.get("EST_01_ops", 0)),
                            "EST_07_ops": int(d.get("EST_07_ops", 0)),
                            "EST_13_ops": int(d.get("EST_13_ops", 0)),
                            "WDO_09_ops": int(d.get("WDO_09_ops", 0)),
                            "WDO_11_ops": int(d.get("WDO_11_ops", 0)),
                            "WDO_S2_ops": int(d.get("WDO_S2_ops", 0)),
                            "WIN_S1_pts": float(d.get("WIN_S1_pts", 0.0)),
                            "WIN_S2_pts": float(d.get("WIN_S2_pts", 0.0)),
                            "WDO_S1_pts": float(d.get("WDO_S1_pts", 0.0)),
                            "WIN_S1_ops": int(d.get("WIN_S1_ops", 0)),
                            "WIN_S2_ops": int(d.get("WIN_S2_ops", 0)),
                            "WDO_S1_ops": int(d.get("WDO_S1_ops", 0)),
                            "trades": d_trades,
                        }
                        compact_days.append(dc)

                    for k, st in stats_acc.items():
                        if k in summary_1c:
                            summary_1c[k]["wins"] = st["wins"]
                            summary_1c[k]["gross_win_1c"] = round(st["gross_win_1c"], 2)
                            summary_1c[k]["gross_loss_1c"] = round(st["gross_loss_1c"], 2)

                    self._portfolio_4_base = {
                        "version": raw.get("version", "2.0-6strats-flow"),
                        "start_date": raw.get("start_date", "2026-05-07"),
                        "last_bt_date": raw.get("last_bt_date", "2026-10-30"),
                        "total_bt_sessions": raw.get("total_bt_sessions", len(compact_days)),
                        "summary_1c": summary_1c,
                        "bt_days": compact_days,
                    }
                else:
                    self._portfolio_4_base = None
            except Exception:
                self._portfolio_4_base = None

    def _get_portfolio_6_cached_trades(self, sess_date: str, asset: str) -> list:
        """Retorna os trades auditados das 6 estratégias c/ filtro de fluxo para uma data e ativo."""
        self._ensure_portfolio_6_cache_loaded()
        trades_map = getattr(self, "_portfolio_6_trades_by_date", {}) or {}
        day_trades = trades_map.get(str(sess_date), []) or []
        asset_up = str(asset or "").upper()
        return [t for t in day_trades if str(t.get("asset", "")).upper() == asset_up]

    def build_portfolio_4_sistematicas_payload(self, snap: dict) -> dict:
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
        strat_ids = ("EST_01", "EST_07", "EST_13", "WDO_09", "WDO_11", "WDO_S2")

        # Limpa registros legados (pré-6 estratégias ou <= last_bt_date)
        for k_old in list(self._live_days_map.keys()):
            if k_old <= last_bt_date or "EST_01_pts" not in self._live_days_map[k_old]:
                del self._live_days_map[k_old]

        # Se o snapshot atual é de um pregão real pós-backtest (> last_bt_date), atualiza os sinais live desse dia
        if sel_date > last_bt_date:
            day_rec = {
                "date": sel_date,
                "month": sel_date[:7],
                "is_live": True,
                "EST_01_pts": 0.0,
                "EST_07_pts": 0.0,
                "EST_13_pts": 0.0,
                "WDO_09_pts": 0.0,
                "WDO_11_pts": 0.0,
                "WDO_S2_pts": 0.0,
                "EST_01_ops": 0,
                "EST_07_ops": 0,
                "EST_13_ops": 0,
                "WDO_09_ops": 0,
                "WDO_11_ops": 0,
                "WDO_S2_ops": 0,
                "WIN_S1_pts": 0.0,
                "WIN_S2_pts": 0.0,
                "WDO_S1_pts": 0.0,
                "WIN_S1_ops": 0,
                "WIN_S2_ops": 0,
                "WDO_S1_ops": 0,
                "trades": [],
                "open_trades": [],
            }
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
                            "pts": round(pts, 2),
                            "brl_1c": round(pts * mult_1c, 2),
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
                            "pts": round(unr, 2),
                            "brl_1c": round(unr * mult_1c, 2),
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

        days_out = list(self._portfolio_4_base["bt_days"])

        return {
            "ok": True,
            "version": self._portfolio_4_base["version"],
            "start_date": self._portfolio_4_base["start_date"],
            "last_bt_date": last_bt_date,
            "live_start_date": live_days_sorted[0]["date"] if live_days_sorted else last_bt_date,
            "total_bt_sessions": self._portfolio_4_base["total_bt_sessions"],
            "total_live_sessions": len(live_days_sorted),
            "selected_date": sel_date,
            "is_historical_view": is_hist,
            "summary_1c": self._portfolio_4_base["summary_1c"],
            "days": days_out + live_days_sorted,
            "live_days": live_days_sorted,
        }


gex_dealer_engine_singleton = GexLiveDealerEngine()
