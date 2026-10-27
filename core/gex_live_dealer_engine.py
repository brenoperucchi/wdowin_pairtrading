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

    def analyze_asset(self, symbol_payload: dict) -> dict:
        asset = symbol_payload.get("asset", "WIN").upper()
        model = self.win_model if asset == "WIN" else self.wdo_model
        model.reload_if_needed()

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

        # Enriquecer cada Wall próxima com o seu GEX e o comportamento esperado do Dealer naquela linha
        gex_by_price = {round(float(model.strikes[i]), 1): float(model.strike_gex[i]) for i in range(len(model.strikes))}
        for w_list in (sup_walls, res_walls):
            for w in w_list:
                wp = round(float(w["price"]), 1)
                wgex = gex_by_price.get(wp, 0.0)
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

        # Série histórica M5 enriquecida com o fluxo de hedge dos Dealers barra a barra + Sinais Marcados no Tempo
        all_walls = symbol_payload.get("all_walls") or model.walls_raw
        signals_result = self._evaluate_intraday_signals_and_scorecard(
            asset=asset,
            m5_series=m5_series,
            model=model,
            all_walls=all_walls,
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
            "signals_log": signals_result["signals_log"],
            "signals_scorecard": signals_result["scorecard"],
        }

    def _evaluate_intraday_signals_and_scorecard(
        self, asset: str, m5_series: list, model: AssetGexCurveModel, all_walls: list
    ) -> dict:
        """
        Percorre todas as barras M5 do pregão (09h00 até agora), marca no tempo cada Sinal Oficial
        da Bússola (Pullback/Absorção na Wall ou Confluência de Fluxo + Dealer) e valida objetivamente
        se o sinal foi compatível com o movimento subsequente do preço (+5m, +15m, +30m, MFE e MAE).
        """
        is_win = asset.upper() == "WIN"
        p_fmt = ".0f" if is_win else ".1f"
        wall_radius = 85.0 if is_win else 2.5
        inst_thresh_5m = 3200.0 if is_win else 650.0
        target_pts = 150.0 if is_win else 5.0
        stop_pts = 130.0 if is_win else 4.5

        walls_clean = [
            {"type": w.get("type", "Wall"), "price": float(w.get("price", 0.0)), "gex": float(w.get("gex", 0.0))}
            for w in (all_walls or [])
            if float(w.get("price", 0.0)) > 0
        ]

        m5_enriched = []
        signals_log = []
        cum_dealer_hedge = 0.0
        last_sig_idx_by_dir = {1: -99, -1: -99}
        last_any_sig_idx = -99

        n = len(m5_series)
        for idx, b in enumerate(m5_series):
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
            p0 = float(m5_series[idx - 1]["close"]) if idx > 0 else o
            prev_l = float(m5_series[idx - 1].get("low", p0)) if idx > 0 else l
            prev_h = float(m5_series[idx - 1].get("high", p0)) if idx > 0 else h
            p_15m_ago = float(m5_series[max(0, idx - 3)]["close"]) if idx >= 2 else o
            move_15m = c - p_15m_ago

            hf = model.compute_dealer_hedge_flow(p0, c)
            cum_dealer_hedge += hf["dealer_hedge_contracts"]

            inst_5m = float(b.get("inst_delta_bar", 0.0))
            inst_15m = sum(float(m5_series[k].get("inst_delta_bar", 0.0)) for k in range(max(0, idx - 2), idx + 1))
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
                and (c - w["price"]) <= target_pts * 0.95
                and move_15m <= target_pts * 0.5  # Veio testando de cima ou lateral (não esticado em alta)
            ]
            res_candidates = [
                w for w in walls_clean
                if (max(o, p0) - wall_radius * 0.4) <= w["price"] <= (max_2bar + wall_radius)
                and c <= w["price"] + wall_radius * 0.25
                and (w["price"] - c) <= target_pts * 0.95
                and move_15m >= -target_pts * 0.5  # Veio testando de baixo ou lateral (não esticado em queda)
            ]
            sup_w = min(sup_candidates, key=lambda w: abs(min_2bar - w["price"])) if sup_candidates else None
            res_w = min(res_candidates, key=lambda w: abs(max_2bar - w["price"])) if res_candidates else None

            loc_g = model.evaluate_local_gex(c)
            is_neg_g = loc_g["local_regime"] == "NEGATIVE_GAMMA"

            sig_dir = 0
            sig_type = ""
            sig_reason = ""
            nearest_w = None

            if idx >= 1:
                # 1. COMPRA POR ABSORÇÃO / DEFESA DE SUPORTE NA WALL
                if (
                    sup_w is not None
                    and c >= l + 0.50 * rng
                    and (
                        # Caso A: Absorção passiva (venda bateu na mínima e deixou pavio de defesa)
                        (lower_wick >= 0.32 * rng and (delta_5m < 0 or inst_5m > 0))
                        # Caso B: Reversão institucional na parede (institucional comprou defendendo o piso)
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
                        # Caso A: Absorção passiva no teto (compra bateu na máxima e deixou pavio superior)
                        (upper_wick >= 0.32 * rng and (delta_5m > 0 or inst_5m < 0))
                        # Caso B: Rejeição institucional na parede (institucional vendeu defendendo o teto)
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

                # 3. COMPRA POR FLUXO INSTITUCIONAL + DEALER
                elif (
                    inst_5m >= inst_thresh_5m
                    and inst_15m >= inst_thresh_5m * (0.8 if is_neg_g else 1.35)
                    and imb_5m >= 9.0
                    and c > o
                    and (
                        is_neg_g  # Em Gamma-, acompanha aceleração
                        or (move_15m <= target_pts * 0.35 and body <= target_pts * 0.95)  # Em Gamma+, só compra retomada na base sem vela exausta
                    )
                ):
                    sig_dir = 1
                    sig_type = "COMPRA · FLUXO INSTITUCIONAL" + (" + SQUEEZE" if is_neg_g else "")
                    sig_reason = (
                        f"Agressão Institucional Forte (+{inst_5m:.0f}L em 5m / +{inst_15m:.0f}L em 15m) "
                        f"+ Desequilíbrio +{imb_5m:.1f}% ({'Gamma− Acelerador' if is_neg_g else 'Retomada na Base'})"
                    )

                # 4. VENDA POR FLUXO INSTITUCIONAL + DEALER
                elif (
                    inst_5m <= -inst_thresh_5m
                    and inst_15m <= -inst_thresh_5m * (0.8 if is_neg_g else 1.35)
                    and imb_5m <= -9.0
                    and c < o
                    and (
                        is_neg_g  # Em Gamma-, acompanha aceleração
                        or (move_15m >= -target_pts * 0.35 and body <= target_pts * 0.95)  # Em Gamma+, só vende rejeição no topo sem vela exausta
                    )
                ):
                    sig_dir = -1
                    sig_type = "VENDA · FLUXO INSTITUCIONAL" + (" + DROP" if is_neg_g else "")
                    sig_reason = (
                        f"Venda Institucional Forte ({inst_5m:.0f}L em 5m / {inst_15m:.0f}L em 15m) "
                        f"+ Desequilíbrio {imb_5m:.1f}% ({'Gamma− Acelerador' if is_neg_g else 'Pressão Vendedora'})"
                    )

            # Cooldown de 5 barras (25 min) para mesma direção e 3 barras (15 min) geral para sinais limpos
            sig_obj = None
            if sig_dir != 0 and (idx - last_sig_idx_by_dir[sig_dir]) >= 5 and (idx - last_any_sig_idx) >= 3:
                last_sig_idx_by_dir[sig_dir] = idx
                last_any_sig_idx = idx

                # Validação para frente (Forward Price Path nos próximos 30 minutos = 6 barras M5)
                future_bars = m5_series[idx + 1 : min(n, idx + 7)]
                pnl_5m = (
                    sig_dir * (float(m5_series[idx + 1]["close"]) - c)
                    if (idx + 1) < n
                    else None
                )
                pnl_15m = (
                    sig_dir * (float(m5_series[idx + 3]["close"]) - c)
                    if (idx + 3) < n
                    else None
                )
                pnl_30m = (
                    sig_dir * (float(m5_series[idx + 6]["close"]) - c)
                    if (idx + 6) < n
                    else None
                )

                mfe_30m = 0.0
                mae_30m = 0.0
                hit_target_first = False
                hit_stop_first = False

                for fb in future_bars:
                    fh = float(fb.get("high", fb["close"]))
                    fl = float(fb.get("low", fb["close"]))
                    fav = (fh - c) if sig_dir > 0 else (c - fl)
                    adv = (fl - c) if sig_dir > 0 else (c - fh)  # <= 0 quando anda contra
                    if fav > mfe_30m:
                        mfe_30m = fav
                    if adv < mae_30m:
                        mae_30m = adv
                    if not hit_target_first and not hit_stop_first:
                        if fav >= target_pts:
                            hit_target_first = True
                        elif adv <= -stop_pts:
                            hit_stop_first = True

                # Classificação da validade do sinal
                if hit_target_first:
                    val_status = "VALIDO_ALVO"
                    val_label = f"✅ VÁLIDO (+{mfe_30m:{p_fmt}} pts)"
                    is_valid = True
                elif hit_stop_first and (pnl_15m is None or pnl_15m < 0):
                    val_status = "INVALIDO_STOP"
                    val_label = f"❌ STOP ({mae_30m:{p_fmt}} pts)"
                    is_valid = False
                elif len(future_bars) < 2:
                    val_status = "EM_ANDAMENTO"
                    val_label = "⏳ EM ABERTO"
                    is_valid = None
                elif mfe_30m >= target_pts * 0.65 or (pnl_15m is not None and pnl_15m > 0) or (pnl_5m is not None and pnl_5m > 0):
                    val_status = "VALIDO_FAVORAVEL"
                    val_label = f"✅ A FAVOR (+{mfe_30m:{p_fmt}} pts)"
                    is_valid = True
                else:
                    val_status = "INVALIDO_CONTRA"
                    val_label = f"❌ CONTRA ({mae_30m:{p_fmt}} pts)"
                    is_valid = False

                sig_obj = {
                    "id": f"{asset}_{time_str}_{ 'BUY' if sig_dir > 0 else 'SELL' }",
                    "bar_index": idx,
                    "timestamp": ts_raw,
                    "time": time_str,
                    "direction": "COMPRA" if sig_dir > 0 else "VENDA",
                    "dir_num": sig_dir,
                    "type": sig_type,
                    "entry_price": round(c, 2),
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
                    "validation_status": val_status,
                    "validation_label": val_label,
                    "is_valid": is_valid,
                }
                signals_log.append(sig_obj)

            m5_enriched.append({
                "timestamp": ts_raw,
                "time": time_str,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "cvd_inst": b["cvd_inst"],
                "cvd_retail": b["cvd_retail"],
                "dealer_hedge_bar": hf["dealer_hedge_contracts"],
                "cum_dealer_hedge": round(cum_dealer_hedge, 0),
                "signal": sig_obj,
            })

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

        return {
            "m5_enriched_series": m5_enriched[-120:],
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
            },
        }


gex_dealer_engine_singleton = GexLiveDealerEngine()
