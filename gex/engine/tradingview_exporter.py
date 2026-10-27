import datetime
import json
import os

def save_walls_to_cache(walls, ticker, ref_date, current_price=None):
    """
    Salva as walls calculadas em um arquivo JSON de cache para posterior consolidação.
    """
    if ref_date is None:
        ref_date = datetime.date.today()
    elif isinstance(ref_date, (datetime.datetime, datetime.date)):
        ref_date = ref_date.strftime("%Y-%m-%d")
        
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(cache_dir, exist_ok=True)
    
    cache_file = os.path.join(cache_dir, f"{ticker.lower()}_walls_cache.json")
    
    data = {
        "ticker": ticker.upper(),
        "ref_date": ref_date,
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_price": current_price,
        "walls": walls
    }
    
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        
    print(f"[TV Cache] Níveis de {ticker} cacheados com sucesso em: {cache_file}")


def _generate_pine_array_pushes(walls, ticker):
    """
    Gera as definições de função e chamadas em Pine Script para evitar o erro CE10295 (main body too long).
    Cada chunk de 40 níveis é compilado como uma função no escopo global para manter o corpo principal do script curto.
    """
    if not walls:
        return f"    // Nenhum dado cacheado de {ticker} disponível"
        
    # Ordenar por preço para que as linhas fiquem organizadas
    walls_sorted = sorted(walls, key=lambda x: x['price'])
    
    # Cores premium
    color_map = {
        "Wall": "color.new(#00e676, 0)",      # Verde Neon
        "MidWall": "color.new(#90a4ae, 0)",   # Cinza Azulado Mudo
        "GammaFlip": "color.new(#ffd600, 0)", # Amarelo Neon
        "MaxGamma": "color.new(#00b0ff, 0)",  # Azul Celeste / Ice Blue
        "MinGamma": "color.new(#ff1744, 0)"   # Vermelho Vibrante
    }
    
    prefix_map = {
        "WIN": "win",
        "SP500_ES": "us",
        "NASDAQ_NQ": "nq",
        "BTC_USD": "btc",
        "USD_BRL": "dol",
        "EUR_USD": "eur",
        "GBP_USD": "gbp",
        "GOLD_XAU": "gold",
        "DOW_US30": "dow",
        "USD_JPY": "jpy",
        "DAX_DE40": "dax",
        "NIKKEI_JP225": "jp",
        "RUSSELL_US2000": "rut",
        "CHINA_FXI": "china"
    }
    prefix = prefix_map.get(ticker, "us")
    
    func_definitions = []
    func_calls = ["if barstate.isfirst"]
    
    chunk_size = 40
    chunk_count = 0
    
    for chunk_idx in range(0, len(walls_sorted), chunk_size):
        chunk = walls_sorted[chunk_idx : chunk_idx + chunk_size]
        func_name = f"populate_{prefix}_{chunk_count}"
        
        block_lines = [
            f"{func_name}(float[] pr, string[] lb, color[] cl, int[] wd, string[] st) =>"
        ]
        
        for w in chunk:
            p = w['price']
            w_type = w['type']
            width = w.get('width', 1)
            style = "dashed" if w_type == "MidWall" else "solid"
            col = color_map.get(w_type, "color.new(#00e676, 0)")
            
            # Rótulo amigável
            if w_type == "Wall":
                stars = "*" * width
                lbl = f"MAGICWALL {stars}"
                if w.get('strike_ibov'):
                    lbl += f" (IBOV {w['strike_ibov']})"
                elif w.get('strike_spy'):
                    # SPY ou QQQ ou BTC ou moedas ou Gold ou Dow ou JPY ou DXY
                    if prefix == "nq":
                        lbl += f" (QQQ {w['strike_spy']})"
                    elif prefix == "btc":
                        lbl += f" (BTC {w['strike_spy']})"
                    elif prefix == "dol":
                        lbl += f" (DOL {w['strike_spy']})"
                    elif prefix == "eur":
                        lbl += f" (FXE {w['strike_spy']})"
                    elif prefix == "gbp":
                        lbl += f" (FXB {w['strike_spy']})"
                    elif prefix == "gold":
                        lbl += f" (GLD {w['strike_spy']})"
                    elif prefix == "dow":
                        lbl += f" (DIA {w['strike_spy']})"
                    elif prefix == "jpy":
                        lbl += f" (FXY {w['strike_spy']})"
                    elif prefix == "dxy":
                        lbl += f" (UUP {w['strike_spy']})"
                    else:
                        lbl += f" (SPY {w['strike_spy']})"
            elif w_type == "MidWall":
                lbl = "MIDLEWALL"
            elif w_type == "GammaFlip":
                lbl = "GAMMA FLIP (Pivot)"
            elif w_type == "MaxGamma":
                lbl = "MAX GAMMA (Teto)"
            elif w_type == "MinGamma":
                lbl = "MIN GAMMA (Piso)"
            else:
                lbl = w_type.upper()
                
            if prefix in ('eur', 'gbp'):
                block_lines.append(f"    array.push(pr, {p:.5f})")
            elif prefix == 'jpy':
                block_lines.append(f"    array.push(pr, {p:.3f})")
            else:
                block_lines.append(f"    array.push(pr, {p:.3f})")
            block_lines.append(f'    array.push(lb, "{lbl}")')
            block_lines.append(f"    array.push(cl, {col})")
            block_lines.append(f"    array.push(wd, {width})")
            block_lines.append(f'    array.push(st, "{style}")')
            
        block_lines.append("    true")  # Dummy return for valid Pine function body
        func_definitions.append("\n".join(block_lines))
        func_calls.append(f"    {func_name}({prefix}_prices, {prefix}_labels, {prefix}_colors, {prefix}_widths, {prefix}_styles)")
        
        chunk_count += 1
        
    defs_str = "\n\n".join(func_definitions)
    calls_str = "\n".join(func_calls)
    
    return defs_str + "\n\n" + calls_str


def export_unified_tradingview(output_path):
    """
    Lê os caches de todos os ativos e gera um indicador unificado para o TradingView.
    """
    engine_dir = os.path.dirname(__file__)
    cache_dir = os.path.join(os.path.dirname(engine_dir), "data")
    
    # Lista de caches (14 Ativos)
    cache_configs = [
        ("win", "win_walls_cache.json"),
        ("sp500_es", "sp500_es_walls_cache.json"),
        ("nasdaq_nq", "nasdaq_nq_walls_cache.json"),
        ("btc_usd", "btc_usd_walls_cache.json"),
        ("usd_brl", "usd_brl_walls_cache.json"),
        ("eur_usd", "eur_usd_walls_cache.json"),
        ("gbp_usd", "gbp_usd_walls_cache.json"),
        ("gold_xau", "gold_xau_walls_cache.json"),
        ("dow_us30", "dow_us30_walls_cache.json"),
        ("usd_jpy", "usd_jpy_walls_cache.json"),
        ("dax_de40", "dax_de40_walls_cache.json"),
        ("nikkei_jp225", "nikkei_jp225_walls_cache.json"),
        ("russell_us2000", "russell_us2000_walls_cache.json"),
        ("china_fxi", "china_fxi_walls_cache.json")
    ]
    
    loaded_caches = {}
    dates_found = []
    
    for key, filename in cache_configs:
        path = os.path.join(cache_dir, filename)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    loaded_caches[key] = data
                    if data.get("ref_date"):
                        dates_found.append(data["ref_date"])
            except Exception as e:
                print(f"[TV Exporter] Erro ao ler cache de {key}: {e}")
                
    # Data padrão recomendada
    ref_year, ref_month, ref_day = datetime.date.today().year, datetime.date.today().month, datetime.date.today().day
    if dates_found:
        latest_date_str = max(dates_found)
        try:
            dt = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d")
            ref_year, ref_month, ref_day = dt.year, dt.month, dt.day
        except Exception:
            pass
            
    # Gerar os pushes
    win_code = _generate_pine_array_pushes(loaded_caches.get("win", {}).get("walls", []), "WIN")
    us_code = _generate_pine_array_pushes(loaded_caches.get("sp500_es", {}).get("walls", []), "SP500_ES")
    nq_code = _generate_pine_array_pushes(loaded_caches.get("nasdaq_nq", {}).get("walls", []), "NASDAQ_NQ")
    btc_code = _generate_pine_array_pushes(loaded_caches.get("btc_usd", {}).get("walls", []), "BTC_USD")
    dol_code = _generate_pine_array_pushes(loaded_caches.get("usd_brl", {}).get("walls", []), "USD_BRL")
    eur_code = _generate_pine_array_pushes(loaded_caches.get("eur_usd", {}).get("walls", []), "EUR_USD")
    gbp_code = _generate_pine_array_pushes(loaded_caches.get("gbp_usd", {}).get("walls", []), "GBP_USD")
    gold_code = _generate_pine_array_pushes(loaded_caches.get("gold_xau", {}).get("walls", []), "GOLD_XAU")
    dow_code = _generate_pine_array_pushes(loaded_caches.get("dow_us30", {}).get("walls", []), "DOW_US30")
    jpy_code = _generate_pine_array_pushes(loaded_caches.get("usd_jpy", {}).get("walls", []), "USD_JPY")
    dax_code = _generate_pine_array_pushes(loaded_caches.get("dax_de40", {}).get("walls", []), "DAX_DE40")
    jp_code = _generate_pine_array_pushes(loaded_caches.get("nikkei_jp225", {}).get("walls", []), "NIKKEI_JP225")
    rut_code = _generate_pine_array_pushes(loaded_caches.get("russell_us2000", {}).get("walls", []), "RUSSELL_US2000")
    china_code = _generate_pine_array_pushes(loaded_caches.get("china_fxi", {}).get("walls", []), "CHINA_FXI")
    
    win_date = loaded_caches.get("win", {}).get("ref_date", "Não disponível")
    us_date = loaded_caches.get("sp500_es", {}).get("ref_date", "Não disponível")
    nq_date = loaded_caches.get("nasdaq_nq", {}).get("ref_date", "Não disponível")
    btc_date = loaded_caches.get("btc_usd", {}).get("ref_date", "Não disponível")
    dol_date = loaded_caches.get("usd_brl", {}).get("ref_date", "Não disponível")
    eur_date = loaded_caches.get("eur_usd", {}).get("ref_date", "Não disponível")
    gbp_date = loaded_caches.get("gbp_usd", {}).get("ref_date", "Não disponível")
    gold_date = loaded_caches.get("gold_xau", {}).get("ref_date", "Não disponível")
    dow_date = loaded_caches.get("dow_us30", {}).get("ref_date", "Não disponível")
    jpy_date = loaded_caches.get("usd_jpy", {}).get("ref_date", "Não disponível")
    dax_date = loaded_caches.get("dax_de40", {}).get("ref_date", "Não disponível")
    jp_date = loaded_caches.get("nikkei_jp225", {}).get("ref_date", "Não disponível")
    rut_date = loaded_caches.get("russell_us2000", {}).get("ref_date", "Não disponível")
    china_date = loaded_caches.get("china_fxi", {}).get("ref_date", "Não disponível")
    
    pine_code = f"""//@version=6
// +-------------------------------------------------------------------------+
// | Magic GEX Levels - Unificado 14 Ativos para TradingView                |
// | Gerado em: {datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")}                     |
// | Referências das Coletas:                                                |
// | - WIN Futures  (B3) : {win_date}                                         |
// | - SP500 / ES   (EUA): {us_date}                                         |
// | - Nasdaq 100   (EUA): {nq_date}                                         |
// | - Bitcoin / USD(Cript): {btc_date}                                         |
// | - Dólar Futuro (B3) : {dol_date}                                         |
// | - EUR / USD    (Forex): {eur_date}                                         |
// | - GBP / USD    (Forex): {gbp_date}                                         |
// | - Ouro / GLD   (Metal): {gold_date}                                        |
// | - Dow / DIA    (EUA)  : {dow_date}                                         |
// | - USD / JPY    (Forex): {jpy_date}                                         |
// | - DAX 40 / EWG (Europa): {dax_date}                                        |
// | - Nikkei 225   (Japão): {jp_date}                                         |
// | - Russell 2000 (EUA)  : {rut_date}                                         |
// | - China 50 / FXI(Ásia) : {china_date}                                       |
// |                                                                         |
// | Desenha os níveis automaticamente dependendo do ativo aberto no gráfico!|
// +-------------------------------------------------------------------------+
// indicator e variáveis globais
indicator("Magic GEX Levels Unified (14 Ativos)", overlay=true, shorttitle="MagicGEX Unified", max_lines_count=200, max_labels_count=200)

// --- CONFIGURAÇÃO DE DATA ---
g_date         = "Configuração Temporal"
useDateFilter  = input.bool(false, "Filtrar por Data dos Dados", group=g_date)
targetYear     = input.int({ref_year}, "Ano", group=g_date, inline="d1")
targetMonth    = input.int({ref_month}, "Mês", group=g_date, inline="d1")
targetDay      = input.int({ref_day}, "Dia", group=g_date, inline="d1")

is_target_date = not useDateFilter or (year(time) == targetYear and month(time) == targetMonth and dayofmonth(time) == targetDay)

// --- CONFIGURAÇÃO VISUAL ---
g_visual       = "Configuração Visual"
showLabels     = input.bool(true, "Exibir Legendas das Walls", group=g_visual)
showMidleWalls = input.bool(true, "Exibir Midle-Walls", group=g_visual)
showMidleLabels= input.bool(false, "Exibir Legenda de Midle-Walls", group=g_visual)
showPrices     = input.bool(true, "Exibir Preço na Legenda", group=g_visual)
transparentBg  = input.bool(true, "Fundo da Legenda Transparente", group=g_visual)
labelSize      = input.string(size.small, "Tamanho do Texto", options=[size.auto, size.tiny, size.small, size.normal, size.large], group=g_visual)

// --- INICIALIZAÇÃO DE DADOS ---

// 1. Arrays para WIN Futures (B3)
var float[] win_prices = array.new_float()
var string[] win_labels = array.new_string()
var color[] win_colors = array.new_color()
var int[] win_widths = array.new_int()
var string[] win_styles = array.new_string()

// 2. Arrays para S&P 500 / ES Futures (EUA)
var float[] us_prices = array.new_float()
var string[] us_labels = array.new_string()
var color[] us_colors = array.new_color()
var int[] us_widths = array.new_int()
var string[] us_styles = array.new_string()

// 3. Arrays para Nasdaq 100 / NQ Futures (EUA)
var float[] nq_prices = array.new_float()
var string[] nq_labels = array.new_string()
var color[] nq_colors = array.new_color()
var int[] nq_widths = array.new_int()
var string[] nq_styles = array.new_string()

// 4. Arrays para Bitcoin / BTC USD (Cripto)
var float[] btc_prices = array.new_float()
var string[] btc_labels = array.new_string()
var color[] btc_colors = array.new_color()
var int[] btc_widths = array.new_int()
var string[] btc_styles = array.new_string()

// 5. Arrays para Dólar Futuro / WDO / DOL (B3)
var float[] dol_prices = array.new_float()
var string[] dol_labels = array.new_string()
var color[] dol_colors = array.new_color()
var int[] dol_widths = array.new_int()
var string[] dol_styles = array.new_string()

// 6. Arrays para EUR / USD (Forex)
var float[] eur_prices = array.new_float()
var string[] eur_labels = array.new_string()
var color[] eur_colors = array.new_color()
var int[] eur_widths = array.new_int()
var string[] eur_styles = array.new_string()

// 7. Arrays para GBP / USD (Forex)
var float[] gbp_prices = array.new_float()
var string[] gbp_labels = array.new_string()
var color[] gbp_colors = array.new_color()
var int[] gbp_widths = array.new_int()
var string[] gbp_styles = array.new_string()

// 8. Arrays para Ouro / XAUUSD / GLD (Metal)
var float[] gold_prices = array.new_float()
var string[] gold_labels = array.new_string()
var color[] gold_colors = array.new_color()
var int[] gold_widths = array.new_int()
var string[] gold_styles = array.new_string()

// 9. Arrays para Dow Jones / US30 / DIA (EUA)
var float[] dow_prices = array.new_float()
var string[] dow_labels = array.new_string()
var color[] dow_colors = array.new_color()
var int[] dow_widths = array.new_int()
var string[] dow_styles = array.new_string()

// 10. Arrays para USD / JPY (Forex)
var float[] jpy_prices = array.new_float()
var string[] jpy_labels = array.new_string()
var color[] jpy_colors = array.new_color()
var int[] jpy_widths = array.new_int()
var string[] jpy_styles = array.new_string()

// 11. Arrays para DAX 40 / DE40 (Alemanha)
var float[] dax_prices = array.new_float()
var string[] dax_labels = array.new_string()
var color[] dax_colors = array.new_color()
var int[] dax_widths = array.new_int()
var string[] dax_styles = array.new_string()

// 12. Arrays para Nikkei 225 / JP225 (Japão)
var float[] jp_prices = array.new_float()
var string[] jp_labels = array.new_string()
var color[] jp_colors = array.new_color()
var int[] jp_widths = array.new_int()
var string[] jp_styles = array.new_string()

// 13. Arrays para Russell 2000 / US2000 (EUA)
var float[] rut_prices = array.new_float()
var string[] rut_labels = array.new_string()
var color[] rut_colors = array.new_color()
var int[] rut_widths = array.new_int()
var string[] rut_styles = array.new_string()

// 14. Arrays para China Large-Cap / CHINA50 (China)
var float[] china_prices = array.new_float()
var string[] china_labels = array.new_string()
var color[] china_colors = array.new_color()
var int[] china_widths = array.new_int()
var string[] china_styles = array.new_string()

// --- POPULANDO DADOS (blocos separados para evitar limite de bytecode e escopo local) ---

// WIN Futures (B3)
{win_code}

// SP500 / ES (EUA)
{us_code}

// Nasdaq 100 / NQ (EUA)
{nq_code}

// Bitcoin / BTC USD (Cripto)
{btc_code}

// Dólar Futuro B3
{dol_code}

// EUR / USD (Forex)
{eur_code}

// GBP / USD (Forex)
{gbp_code}

// Ouro / XAUUSD (Metal)
{gold_code}

// Dow Jones / US30 (EUA)
{dow_code}

// USD / JPY (Forex)
{jpy_code}

// DAX 40 / DE40 (Alemanha)
{dax_code}

// Nikkei 225 / JP225 (Japão)
{jp_code}

// Russell 2000 / US2000 (EUA)
{rut_code}

// China 50 / CHINA50 (China)
{china_code}

// --- DETECÇÃO DINÂMICA E FALLBACK DE ATIVO ---
g_asset         = "Configuração de Ativo"
forced_asset    = input.string("Automático", "Forçar Ativo no Gráfico", options=["Automático", "WIN / B3", "SP500 / ES", "Nasdaq 100 / NQ", "Bitcoin / BTC", "Dólar / BRL", "EUR / USD", "GBP / USD", "Ouro / XAUUSD", "Dow Jones / US30", "USD / JPY", "DAX 40 / DE40", "Nikkei 225 / JP225", "Russell 2000 / US2000", "China 50 / CHINA50"], group=g_asset)

ticker_upper = str.upper(syminfo.ticker)
is_win_detected  = str.contains(ticker_upper, "WIN") or str.contains(ticker_upper, "IND") or str.contains(ticker_upper, "BRA50") or str.contains(ticker_upper, "BRA")
is_nq_detected   = str.contains(ticker_upper, "QQQ") or str.contains(ticker_upper, "NQ") or str.contains(ticker_upper, "NDX") or str.contains(ticker_upper, "MNQ") or str.contains(ticker_upper, "NAS100") or str.contains(ticker_upper, "USTEC") or str.contains(ticker_upper, "US100") or str.contains(ticker_upper, "NAS")
is_btc_detected  = str.contains(ticker_upper, "BTC") or str.contains(ticker_upper, "ETH")
is_dol_detected  = str.contains(ticker_upper, "DOL") or str.contains(ticker_upper, "WDO") or str.contains(ticker_upper, "BRL") or str.contains(ticker_upper, "USDBRL")
is_us_detected   = str.contains(ticker_upper, "SPY") or str.contains(ticker_upper, "ES") or str.contains(ticker_upper, "SPX") or str.contains(ticker_upper, "MES") or str.contains(ticker_upper, "US500") or str.contains(ticker_upper, "SPX500") or str.contains(ticker_upper, "US 500")
is_eur_detected  = str.contains(ticker_upper, "EURUSD") or (str.contains(ticker_upper, "EUR") and str.contains(ticker_upper, "USD"))
is_gbp_detected  = str.contains(ticker_upper, "GBPUSD") or (str.contains(ticker_upper, "GBP") and str.contains(ticker_upper, "USD"))
is_gold_detected = str.contains(ticker_upper, "XAU") or str.contains(ticker_upper, "GOLD") or str.contains(ticker_upper, "GLD")
is_dow_detected  = str.contains(ticker_upper, "US30") or str.contains(ticker_upper, "DIA") or str.contains(ticker_upper, "DJI") or str.contains(ticker_upper, "YM") or str.contains(ticker_upper, "DOW")
is_jpy_detected  = str.contains(ticker_upper, "USDJPY") or (str.contains(ticker_upper, "JPY") and not str.contains(ticker_upper, "GBPJPY") and not str.contains(ticker_upper, "EURJPY")) or str.contains(ticker_upper, "FXY")
is_dax_detected  = str.contains(ticker_upper, "DE40") or str.contains(ticker_upper, "GER40") or str.contains(ticker_upper, "DAX") or str.contains(ticker_upper, "EWG")
is_jp_detected   = str.contains(ticker_upper, "JP225") or str.contains(ticker_upper, "JPN225") or str.contains(ticker_upper, "NI225") or str.contains(ticker_upper, "NIKKEI") or str.contains(ticker_upper, "EWJ")
is_rut_detected  = str.contains(ticker_upper, "US2000") or str.contains(ticker_upper, "RUT") or str.contains(ticker_upper, "RUSSELL") or str.contains(ticker_upper, "IWM")
is_china_detected = str.contains(ticker_upper, "CHINA50") or str.contains(ticker_upper, "CN50") or str.contains(ticker_upper, "FXI") or str.contains(ticker_upper, "CHINAH")

is_win  = forced_asset == "WIN / B3" or (forced_asset == "Automático" and is_win_detected)
is_nq   = forced_asset == "Nasdaq 100 / NQ" or (forced_asset == "Automático" and is_nq_detected)
is_btc  = forced_asset == "Bitcoin / BTC" or (forced_asset == "Automático" and is_btc_detected)
is_dol  = forced_asset == "Dólar / BRL" or (forced_asset == "Automático" and is_dol_detected)
is_eur  = forced_asset == "EUR / USD" or (forced_asset == "Automático" and is_eur_detected)
is_gbp  = forced_asset == "GBP / USD" or (forced_asset == "Automático" and is_gbp_detected)
is_gold = forced_asset == "Ouro / XAUUSD" or (forced_asset == "Automático" and is_gold_detected)
is_dow  = forced_asset == "Dow Jones / US30" or (forced_asset == "Automático" and is_dow_detected)
is_jpy  = forced_asset == "USD / JPY" or (forced_asset == "Automático" and is_jpy_detected)
is_dax  = forced_asset == "DAX 40 / DE40" or (forced_asset == "Automático" and is_dax_detected)
is_jp   = forced_asset == "Nikkei 225 / JP225" or (forced_asset == "Automático" and is_jp_detected)
is_rut  = forced_asset == "Russell 2000 / US2000" or (forced_asset == "Automático" and is_rut_detected)
is_china = forced_asset == "China 50 / CHINA50" or (forced_asset == "Automático" and is_china_detected)
// Fallback inteligente para o SP500 / ES se nenhum outro ativo coincidir
is_us   = forced_asset == "SP500 / ES" or (forced_asset == "Automático" and (is_us_detected or (not is_win and not is_nq and not is_btc and not is_dol and not is_eur and not is_gbp and not is_gold and not is_dow and not is_jpy and not is_dax and not is_jp and not is_rut and not is_china)))

var float[] prices = na
var string[] labels = na
var color[] colors = na
var int[] widths = na
var string[] styles = na

if is_win
    prices := win_prices
    labels := win_labels
    colors := win_colors
    widths := win_widths
    styles := win_styles
else if is_nq
    prices := nq_prices
    labels := nq_labels
    colors := nq_colors
    widths := nq_widths
    styles := nq_styles
else if is_btc
    prices := btc_prices
    labels := btc_labels
    colors := btc_colors
    widths := btc_widths
    styles := btc_styles
else if is_dol
    prices := dol_prices
    labels := dol_labels
    colors := dol_colors
    widths := dol_widths
    styles := dol_styles
else if is_eur
    prices := eur_prices
    labels := eur_labels
    colors := eur_colors
    widths := eur_widths
    styles := eur_styles
else if is_gbp
    prices := gbp_prices
    labels := gbp_labels
    colors := gbp_colors
    widths := gbp_widths
    styles := gbp_styles
else if is_gold
    prices := gold_prices
    labels := gold_labels
    colors := gold_colors
    widths := gold_widths
    styles := gold_styles
else if is_dow
    prices := dow_prices
    labels := dow_labels
    colors := dow_colors
    widths := dow_widths
    styles := dow_styles
else if is_jpy
    prices := jpy_prices
    labels := jpy_labels
    colors := jpy_colors
    widths := jpy_widths
    styles := jpy_styles
else if is_dax
    prices := dax_prices
    labels := dax_labels
    colors := dax_colors
    widths := dax_widths
    styles := dax_styles
else if is_jp
    prices := jp_prices
    labels := jp_labels
    colors := jp_colors
    widths := jp_widths
    styles := jp_styles
else if is_rut
    prices := rut_prices
    labels := rut_labels
    colors := rut_colors
    widths := rut_widths
    styles := rut_styles
else if is_china
    prices := china_prices
    labels := china_labels
    colors := china_colors
    widths := china_widths
    styles := china_styles
else if is_us
    prices := us_prices
    labels := us_labels
    colors := us_colors
    widths := us_widths
    styles := us_styles

// --- ENGINE DE PLOTAGEM DINÂMICA DE ALTA PERFORMANCE ---
var line[] active_lines = array.new_line()
var label[] active_labels = array.new_label()
var bool initialized = false

if is_target_date and barstate.islast
    if not initialized
        if not na(prices) and array.size(prices) > 0
            // Detecção e ajuste automático de escala para corretoras de CFD / ETFs
            float scale_factor = 1.0
            if is_win and close < 2000.0
                scale_factor := 0.001
            else if is_dol and close < 100.0
                scale_factor := 0.001
            else if is_us and close < 2000.0
                scale_factor := 0.1
            else if is_nq and close < 5000.0
                scale_factor := 0.02427
            else if is_gold and close < 1000.0
                scale_factor := 0.1
            else if is_dow and close < 2000.0
                scale_factor := 0.01
                
            int size = array.size(prices)
            for i = 0 to size - 1
                p = array.get(prices, i) * scale_factor
                lbl = array.get(labels, i)
                col = array.get(colors, i)
                w = array.get(widths, i)
                sty = array.get(styles, i) == "dashed" ? line.style_dashed : line.style_solid
                
                // Desenhar a linha se nao for MidWall ou se a configuracao de exibir MidleWalls estiver ativa
                if lbl != "MIDLEWALL" or showMidleWalls
                    l = line.new(x1=bar_index - 100, y1=p, x2=bar_index, y2=p, xloc=xloc.bar_index, extend=extend.both, color=col, width=w, style=sty)
                    array.push(active_lines, l)
                    
                    // Rótulo dinâmico dependendo da escala e configurações visuais
                    bool draw_lbl = showLabels
                    if lbl == "MIDLEWALL" and not showMidleLabels
                        draw_lbl := false
                    
                    if draw_lbl
                        string p_str = (is_eur or is_gbp) ? str.tostring(p, "#.#####") : (is_jpy ? str.tostring(p, "#.###") : (scale_factor < 1.0 ? str.tostring(p, "#.#####") : str.tostring(p, is_win ? "#" : "#.##")))
                        string label_text = lbl
                        if showPrices
                            label_text := label_text + " [" + p_str + "]"
                        
                        color bg_color = transparentBg ? color.new(color.black, 100) : color.new(col, 95)
                        lb = label.new(x=bar_index + 12, y=p, text=label_text, xloc=xloc.bar_index, color=bg_color, textcolor=col, style=label.style_label_left, size=labelSize)
                        array.push(active_labels, lb)
                    
        initialized := true
    else
        // Acompanhar o deslocamento do gráfico em tempo real para manter as labels à direita
        int labels_size = array.size(active_labels)
        if labels_size > 0
            for i = 0 to labels_size - 1
                label.set_x(array.get(active_labels, i), bar_index + 12)
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(pine_code)
        
    print(f"[TV Exporter] Indicador unificado de 10 Ativos gerado com sucesso em: {output_path}")
