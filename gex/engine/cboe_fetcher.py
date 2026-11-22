"""
cboe_fetcher.py — Cliente institucional direto para a API pública de Opções da CBOE.

Vantagens sobre o yfinance:
1. Open Interest (OI) 100% preservado durante a madrugada/manhã (sem o bug de OI=0 do Yahoo Finance).
2. Acesso direto às opções de índice oficial (_SPX, _NDX, _RUT, _DJX) além dos ETFs (SPY, QQQ, IWM, DIA, GLD, FXE, FXB, FXY, EWG, EWJ, FXI, UUP, IBIT).
3. Gregas oficiais da CBOE (gamma, delta, iv, vega, theta) já calculadas na resposta.
4. Suporte nativo a agregação Multi-Vencimento (Total GEX — 0DTE + Semanais + Mensais OPEX).
"""

import datetime
import re
import time
import numpy as np
import pandas as pd
import requests

import os

try:
    from gex.engine.chain_archive import archive_payload, list_archived, load_archived_payload
except ImportError:  # execução direta do módulo
    from chain_archive import archive_payload, list_archived, load_archived_payload

CBOE_BASE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json"

# Cloudflare passou a exigir um Referer de cboe.com (confirmado em 2026-11-22).
# Sem Referer a API devolve 403 HTML; com Referer: https://www.cboe.com/ retorna JSON.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.cboe.com",
    "Referer": "https://www.cboe.com/",
}

_SESSION = None


def _session():
    """Sessão HTTP com retry exponencial (3 tentativas) para 429/5xx e falhas de conexão."""
    global _SESSION
    if _SESSION is None:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        s = requests.Session()
        retry = Retry(total=3, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",), raise_on_status=False)
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.headers.update(HEADERS)
        _SESSION = s
    return _SESSION


def _is_cloudflare_block(resp):
    """403 ou página HTML de desafio da Cloudflare em vez de JSON."""
    if resp is None:
        return False
    if resp.status_code == 403:
        return True
    ctype = (resp.headers.get("content-type") or "").lower()
    if "text/html" in ctype and "cloudflare" in (resp.text or "").lower():
        return True
    return False


def _download_cboe_json(ticker, url, attempts=3):
    """GET com backoff em 403/Cloudflare e em erros transitórios de rede."""
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            resp = _session().get(url, timeout=20)
            if _is_cloudflare_block(resp):
                last_err = f"HTTP {resp.status_code} Cloudflare/Forbidden for url: {resp.url}"
                print(f"      [CBOE] {ticker} bloqueado ({last_err}) — tentativa {attempt}/{attempts}.")
                if attempt < attempts:
                    time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            ctype = (resp.headers.get("content-type") or "").lower()
            if "json" not in ctype:
                last_err = f"resposta não-JSON ({ctype or 'sem content-type'}) status={resp.status_code}"
                print(f"      [CBOE] {ticker} {last_err} — tentativa {attempt}/{attempts}.")
                if attempt < attempts:
                    time.sleep(2 ** attempt)
                continue
            return resp.json()
        except Exception as e:
            last_err = e
            print(f"      [CBOE] {ticker} erro na tentativa {attempt}/{attempts}: {e}")
            if attempt < attempts:
                time.sleep(2 ** attempt)
    print(f"      [CBOE Warning] Falha ao buscar {ticker} na CBOE após retries ({last_err}).")
    return None


# Cache do payload bruto por ticker dentro do processo (evita baixar 2x ao expandir o DTE)
_PAYLOAD_CACHE = {}

try:
    from zoneinfo import ZoneInfo
    _NY_TZ = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    _NY_TZ = None


def _years_to_expiry(exp_date, now_utc=None):
    """Tempo até o vencimento em anos, com fração intradiária.
    Vencimento = 16:00 de Nova York do dia de expiração (PM-settled; aproximação também para AM-settled).
    Retorna <= 0 se a opção já venceu."""
    now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc)
    if _NY_TZ is None:
        expiry_utc = datetime.datetime(exp_date.year, exp_date.month, exp_date.day, 20, 0, tzinfo=datetime.timezone.utc)
    else:
        expiry_utc = datetime.datetime(exp_date.year, exp_date.month, exp_date.day, 16, 0, tzinfo=_NY_TZ).astimezone(datetime.timezone.utc)
    return (expiry_utc - now_utc).total_seconds() / (365.0 * 24 * 3600)


# Regex OCC Option Symbol: ex: SPX261120P06325000, SPXW261028C07700000, SPY261028C00770000
OCC_REGEX = re.compile(r"^([A-Z0-9_]+?)(\d{6})([CP])(\d{8})$")


def parse_occ_symbol(opt_sym: str):
    """
    Extrai (root, expiry_date, opt_type, strike) de um código OCC padrão.
    Ex: 'SPXW261028C07700000' -> ('SPXW', date(2026, 10, 28), 'CALL', 7700.0)
    """
    m = OCC_REGEX.match(opt_sym.strip())
    if not m:
        return None
    root, yymmdd, cp, strike_raw = m.groups()
    try:
        year = 2000 + int(yymmdd[0:2])
        month = int(yymmdd[2:4])
        day = int(yymmdd[4:6])
        expiry_date = datetime.date(year, month, day)
    except ValueError:
        return None

    opt_type = "CALL" if cp == "C" else "PUT"
    strike = int(strike_raw) / 1000.0
    return root, expiry_date, opt_type, strike


def fetch_cboe_chain(
    ticker: str,
    max_dte: int = 45,
    strike_range_pct: float = 0.15,
    default_iv: float = 0.18,
):
    """
    Baixa a grade completa de opções da CBOE para `ticker` (ex: '_SPX', 'SPY', 'GLD')
    e filtra os contratos com Open Interest (ou Volume em 0DTE) dentro de `max_dte` dias corridos
    e `±strike_range_pct` do preço Spot.

    Retorna:
        (spot_price: float, df_options: pd.DataFrame, ref_expiry_str: str)
    Onde df_options possui as colunas:
        ['ticker', 'type', 'strike', 'expiry', 'dte_days', 'bus_days', 'T', 'oi', 'volume', 'iv', 'cboe_gamma']
    """
    url = CBOE_BASE_URL.format(ticker=ticker)
    archive_date = os.environ.get("GEX_ARCHIVE_DATE")
    use_morning_archive = os.environ.get("GEX_USE_MORNING_ARCHIVE") == "1"
    archived_now_utc = None

    if ticker in _PAYLOAD_CACHE:
        raw_json, archived_now_utc = _PAYLOAD_CACHE[ticker]
    elif archive_date or use_morning_archive:
        target_date = archive_date or datetime.date.today().isoformat()
        files = list_archived("cboe", ticker, target_date)
        rec = None
        if files:
            import gzip, json
            # Usar o primeiro arquivo do dia (coleta matinal pré-mercado das 07:30–07:45 BRT)
            with gzip.open(files[0], "rt", encoding="utf-8") as f:
                rec = json.load(f)
        if rec and rec.get("payload"):
            raw_json = rec["payload"]
            if rec.get("fetched_at_utc"):
                try:
                    archived_now_utc = datetime.datetime.fromisoformat(rec["fetched_at_utc"].replace("Z", "+00:00"))
                except Exception:
                    pass
            _PAYLOAD_CACHE[ticker] = (raw_json, archived_now_utc)
            print(f"      [Archive Replay] Usando snapshot matinal arquivado de {ticker} ({rec.get('fetched_at_local', target_date)})")
        else:
            raw_json = _download_cboe_json(ticker, url)
            if raw_json is None:
                return None, pd.DataFrame(), None
            _PAYLOAD_CACHE[ticker] = (raw_json, None)
    else:
        raw_json = _download_cboe_json(ticker, url)
        if raw_json is None:
            return None, pd.DataFrame(), None
        _PAYLOAD_CACHE[ticker] = (raw_json, None)
        # Arquivo diário da resposta bruta (permite recalcular este dia no futuro)
        archive_payload("cboe", ticker, url, raw_json)
    payload = raw_json.get("data", {}) or {}

    # Dado velho: a CBOE às vezes serve um snapshot antigo (feriado/falha no CDN)
    ts_raw = raw_json.get("timestamp") or payload.get("last_trade_time")
    if ts_raw:
        try:
            ts = datetime.datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")[:19])
            age_days = (datetime.datetime.now() - ts).days
            if age_days > 4:
                print(f"      [CBOE Warning] Snapshot de {ticker} tem {age_days} dias ({ts_raw}). Descartado.")
                return None, pd.DataFrame(), None
        except Exception:
            pass

    spot = payload.get("current_price") or payload.get("close") or payload.get("prev_day_close")
    if not spot or float(spot) <= 0:
        return None, pd.DataFrame(), None
    spot = float(spot)

    raw_options = payload.get("options", [])
    if not raw_options:
        return spot, pd.DataFrame(), None

    today = datetime.date.fromisoformat(archive_date) if archive_date else datetime.date.today()
    now_utc = archived_now_utc or datetime.datetime.now(datetime.timezone.utc)
    min_strike = spot * (1.0 - strike_range_pct)
    max_strike = spot * (1.0 + strike_range_pct)

    rows = []
    for item in raw_options:
        sym = item.get("option", "")
        parsed = parse_occ_symbol(sym)
        if not parsed:
            continue
        root, exp_date, opt_type, strike = parsed

        dte_days = (exp_date - today).days
        if dte_days < 0 or dte_days > max_dte:
            continue

        if not (min_strike <= strike <= max_strike):
            continue

        oi = float(item.get("open_interest") or 0.0)
        vol = float(item.get("volume") or 0.0)

        # Se OI for 0 no próprio dia (0DTE recém-aberto), permite usar volume se positivo
        effective_oi = oi if oi > 0 else (vol if dte_days == 0 and vol > 0 else 0.0)
        if effective_oi <= 0:
            continue

        iv = float(item.get("iv") or 0.0)
        if iv <= 0.001 or iv > 5.0:
            # IV inválida: só aproveita com IV padrão se o contrato tiver OI relevante; senão descarta
            # (IV fixa em contratos ilíquidos criava walls artificiais).
            if oi < 100:
                continue
            iv = default_iv

        cboe_gamma = float(item.get("gamma") or 0.0)
        if cboe_gamma < 0 or cboe_gamma > 10.0:
            cboe_gamma = 0.0

        bus_days = max(1, int(np.busday_count(today.isoformat(), exp_date.isoformat())))
        T_years = _years_to_expiry(exp_date, now_utc)
        if T_years <= 0:
            continue  # já venceu hoje (run após 16:00 ET) — não entra no gamma
        # Piso de ~1h de pregão para 0DTE (evita gamma explosivo nos minutos finais)
        T = max(T_years, 1.0 / (252.0 * 6.5))

        rows.append({
            "ticker": sym,
            "root": root,
            "type": opt_type,
            "strike": strike,
            "expiry": exp_date.isoformat(),
            "dte_days": dte_days,
            "bus_days": bus_days,
            "T": T,
            "oi": effective_oi,
            "raw_oi": oi,
            "volume": vol,
            "iv": iv,
            "cboe_gamma": cboe_gamma,
        })

    # Se com max_dte=45 vieram poucos contratos (ex: ETFs trimestrais como FXB/EWG/FXI),
    # expandir automaticamente para max_dte=120 dias!
    if len(rows) < 25 and max_dte < 120:
        return fetch_cboe_chain(
            ticker=ticker,
            max_dte=120,
            strike_range_pct=max(strike_range_pct, 0.20),
            default_iv=default_iv,
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return spot, df, None

    # Encontrar o vencimento de maior Open Interest ou o mais próximo para referência no cabeçalho
    exp_summary = df.groupby("expiry")["oi"].sum()
    top_expiry = exp_summary.idxmax()
    front_expiry = sorted(df["expiry"].unique())[0]
    n_expiries = df["expiry"].nunique()
    ref_expiry_str = f"{front_expiry} (Multi-Exp: {n_expiries} vencs, Top OI: {top_expiry})"

    return spot, df, ref_expiry_str


def compute_multi_expiry_gamma_curve(
    df_options: pd.DataFrame,
    sweep_prices: np.ndarray,
    r: float = 0.0515,
    q: float = 0.0,
    multiplier: float = 100.0,
    invert_sign: bool = False,
):
    """
    Calcula a curva de Gamma total do mercado (vetorizada em NumPy) ao longo de `sweep_prices`,
    respeitando o tempo até o vencimento `T` individual de cada opção em `df_options`.

    Retorna:
        (max_gamma_price, max_gamma_val, min_gamma_price, min_gamma_val, flip_price)
    """
    if df_options.empty:
        mid = float(np.mean(sweep_prices))
        return mid, 0.0, mid, 0.0, mid

    S = sweep_prices[:, np.newaxis]               # (M, 1)
    K = df_options["strike"].to_numpy()[np.newaxis, :]  # (1, N)
    T = np.maximum(df_options["T"].to_numpy()[np.newaxis, :], 1.0 / 365.0)
    sigma = np.maximum(df_options["iv"].to_numpy()[np.newaxis, :], 0.01)
    oi = df_options["oi"].to_numpy()[np.newaxis, :]
    sign = np.where(df_options["type"].to_numpy() == "CALL", 1.0, -1.0)[np.newaxis, :]
    if invert_sign:
        sign = -sign

    # Mult por linha se existir coluna 'mult', senão usa multiplier escalar
    if "mult" in df_options.columns:
        mult_arr = df_options["mult"].to_numpy()[np.newaxis, :]
    else:
        mult_arr = multiplier

    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * (sigma ** 2)) * T) / (sigma * sqrt_T)
    pdf_d1 = np.exp(-0.5 * (d1 ** 2)) / np.sqrt(2.0 * np.pi)
    gamma_matrix = (np.exp(-q * T) * pdf_d1) / (S * sigma * sqrt_T)

    # GEX Dollar Contribution: OI * Gamma * S^2 * 0.01 * multiplier
    gex_matrix = oi * gamma_matrix * (S ** 2) * 0.01 * mult_arr * sign
    gex_values = np.sum(gex_matrix, axis=1)  # (M,)

    max_idx = int(np.argmax(gex_values))
    min_idx = int(np.argmin(gex_values))
    max_price = float(sweep_prices[max_idx])
    min_price = float(sweep_prices[min_idx])
    max_val = float(gex_values[max_idx])
    min_val = float(gex_values[min_idx])

    spot_approx = float(np.median(sweep_prices))
    flip_price = None
    best_dist = float("inf")

    for i in range(len(gex_values) - 1):
        y0, y1 = gex_values[i], gex_values[i + 1]
        if y0 * y1 < 0:
            x0, x1 = sweep_prices[i], sweep_prices[i + 1]
            cross = float(x0 - y0 * (x1 - x0) / (y1 - y0))
            dist = abs(cross - spot_approx)
            if dist < best_dist:
                best_dist = dist
                flip_price = cross

    if flip_price is None:
        # Se não cruzou zero, pega o ponto mais próximo de zero dentro da banda central
        abs_idx = int(np.argmin(np.abs(gex_values)))
        flip_price = float(sweep_prices[abs_idx])

    return max_price, max_val, min_price, min_val, flip_price

