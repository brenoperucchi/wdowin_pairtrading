import datetime
import json
import os

def save_walls_to_cache(walls, ticker, ref_date):
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
        "walls": walls
    }
    
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        
    print(f"[TV Cache] Níveis de {ticker} cacheados com sucesso em: {cache_file}")


def _generate_pine_array_pushes(walls, ticker):
    """
    Gera as linhas de push de array em Pine Script para um determinado conjunto de walls.
    """
    if not walls:
        return []
        
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
        "GBP_USD": "gbp"
    }
    prefix = prefix_map.get(ticker, "us")
    lines = []
    
    for w in sorted(walls_sorted, key=lambda x: x['price']):
        p = w['price']
        w_type = w['type']
        width = w.get('width', 1)
        style = "dashed" if w_type == "MidWall" else "solid"
        col = color_map.get(w_type, "color.new(#00e676, 0)")
        
        # Rótulo amigável
        if w_type == "Wall":
            stars = "*" * width
            lbl = f"WALL {stars}"
            if w.get('strike_ibov'):
                lbl += f" (IBOV {w['strike_ibov']})"
            elif w.get('strike_spy'):
                # SPY ou QQQ ou BTC
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
                else:
                    lbl += f" (SPY {w['strike_spy']})"
        elif w_type == "MidWall":
            lbl = "MID WALL"
        elif w_type == "GammaFlip":
            lbl = "GAMMA FLIP (Pivot)"
        elif w_type == "MaxGamma":
            lbl = "MAX GAMMA (Teto)"
        elif w_type == "MinGamma":
            lbl = "MIN GAMMA (Piso)"
        else:
            lbl = w_type.upper()
            
        if prefix in ('eur', 'gbp'):
            lines.append(f"    array.push({prefix}_prices, {p:.4f})")
        else:
            lines.append(f"    array.push({prefix}_prices, {p:.3f})")
        lines.append(f'    array.push({prefix}_labels, "{lbl}")')
        lines.append(f"    array.push({prefix}_colors, {col})")
        lines.append(f"    array.push({prefix}_widths, {width})")
        lines.append(f'    array.push({prefix}_styles, "{style}")')
        
    return lines


def export_unified_tradingview(output_path):
    """
    Lê os caches de todos os ativos e gera um indicador unificado para o TradingView.
    """
    engine_dir = os.path.dirname(__file__)
    cache_dir = os.path.join(os.path.dirname(engine_dir), "data")
    
    # Lista de caches
    cache_configs = [
        ("win", "win_walls_cache.json"),
        ("sp500_es", "sp500_es_walls_cache.json"),
        ("nasdaq_nq", "nasdaq_nq_walls_cache.json"),
        ("btc_usd", "btc_usd_walls_cache.json"),
        ("usd_brl", "usd_brl_walls_cache.json"),
        ("eur_usd", "eur_usd_walls_cache.json"),
        ("gbp_usd", "gbp_usd_walls_cache.json")
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
    win_pushes = _generate_pine_array_pushes(loaded_caches.get("win", {}).get("walls", []), "WIN")
    us_pushes = _generate_pine_array_pushes(loaded_caches.get("sp500_es", {}).get("walls", []), "SP500_ES")
    nq_pushes = _generate_pine_array_pushes(loaded_caches.get("nasdaq_nq", {}).get("walls", []), "NASDAQ_NQ")
    btc_pushes = _generate_pine_array_pushes(loaded_caches.get("btc_usd", {}).get("walls", []), "BTC_USD")
    dol_pushes = _generate_pine_array_pushes(loaded_caches.get("usd_brl", {}).get("walls", []), "USD_BRL")
    eur_pushes = _generate_pine_array_pushes(loaded_caches.get("eur_usd", {}).get("walls", []), "EUR_USD")
    gbp_pushes = _generate_pine_array_pushes(loaded_caches.get("gbp_usd", {}).get("walls", []), "GBP_USD")
    
    win_date = loaded_caches.get("win", {}).get("ref_date", "Não disponível")
    us_date = loaded_caches.get("sp500_es", {}).get("ref_date", "Não disponível")
    nq_date = loaded_caches.get("nasdaq_nq", {}).get("ref_date", "Não disponível")
    btc_date = loaded_caches.get("btc_usd", {}).get("ref_date", "Não disponível")
    dol_date = loaded_caches.get("usd_brl", {}).get("ref_date", "Não disponível")
    eur_date = loaded_caches.get("eur_usd", {}).get("ref_date", "Não disponível")
    gbp_date = loaded_caches.get("gbp_usd", {}).get("ref_date", "Não disponível")
    
    win_code = "\n".join(win_pushes) if win_pushes else "    // Nenhum dado cacheado de WIN disponível"
    us_code = "\n".join(us_pushes) if us_pushes else "    // Nenhum dado cacheado de SP500 disponível"
    nq_code = "\n".join(nq_pushes) if nq_pushes else "    // Nenhum dado cacheado de NASDAQ disponível"
    btc_code = "\n".join(btc_pushes) if btc_pushes else "    // Nenhum dado cacheado de BITCOIN disponível"
    dol_code = "\n".join(dol_pushes) if dol_pushes else "    // Nenhum dado cacheado de DÓLAR B3 disponível"
    eur_code = "\n".join(eur_pushes) if eur_pushes else "    // Nenhum dado cacheado de EUR/USD disponível"
    gbp_code = "\n".join(gbp_pushes) if gbp_pushes else "    // Nenhum dado cacheado de GBP/USD disponível"
    
    pine_code = f"""//@version=5
// +-------------------------------------------------------------------------+
// | Jumba GEX Levels - Unificado 7 Ativos para TradingView                 |
// | Gerado em: {datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")}                     |
// | Referências das Coletas:                                                |
// | - WIN Futures  (B3) : {win_date}                                         |
// | - SP500 / ES   (EUA): {us_date}                                         |
// | - Nasdaq 100   (EUA): {nq_date}                                         |
// | - Bitcoin / USD(Cript): {btc_date}                                         |
// | - Dólar Futuro (B3) : {dol_date}                                         |
// | - EUR / USD    (Forex): {eur_date}                                         |
// | - GBP / USD    (Forex): {gbp_date}                                         |
// |                                                                         |
// | Desenha os níveis automaticamente dependendo do ativo aberto no gráfico!|
// +-------------------------------------------------------------------------+
indicator("Jumba GEX Levels Unified (7 Ativos)", overlay=true, shorttitle="JumbaGEX Unified", max_lines_count=150, max_labels_count=150)

// --- CONFIGURAÇÃO DE DATA ---
g_date         = "Configuração Temporal"
useDateFilter  = input.bool(false, "Filtrar por Data dos Dados", group=g_date)
targetYear     = input.int({ref_year}, "Ano", group=g_date, inline="d1")
targetMonth    = input.int({ref_month}, "Mês", group=g_date, inline="d1")
targetDay      = input.int({ref_day}, "Dia", group=g_date, inline="d1")

is_target_date = not useDateFilter or (year(time) == targetYear and month(time) == targetMonth and dayofmonth(time) == targetDay)

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

if barstate.isfirst
    // --- POPULANDO DADOS DE WIN ---
{win_code}

    // --- POPULANDO DADOS DE SP500 / ES ---
{us_code}

    // --- POPULANDO DADOS DE NASDAQ 100 / NQ ---
{nq_code}

    // --- POPULANDO DADOS DE BITCOIN ---
{btc_code}

    // --- POPULANDO DADOS DE DÓLAR FUTURO B3 ---
{dol_code}

    // --- POPULANDO DADOS DE EUR / USD ---
{eur_code}

    // --- POPULANDO DADOS DE GBP / USD ---
{gbp_code}

// --- DETECÇÃO DINÂMICA E FALLBACK DE ATIVO ---
g_asset         = "Configuração de Ativo"
forced_asset    = input.string("Automático", "Forçar Ativo no Gráfico", options=["Automático", "WIN / B3", "SP500 / ES", "Nasdaq 100 / NQ", "Bitcoin / BTC", "Dólar / BRL", "EUR / USD", "GBP / USD"], group=g_asset)

ticker_upper = str.upper(syminfo.ticker)
is_win_detected = str.contains(ticker_upper, "WIN") or str.contains(ticker_upper, "IND") or str.contains(ticker_upper, "BRA50") or str.contains(ticker_upper, "BRA")
is_nq_detected  = str.contains(ticker_upper, "QQQ") or str.contains(ticker_upper, "NQ") or str.contains(ticker_upper, "NDX") or str.contains(ticker_upper, "MNQ") or str.contains(ticker_upper, "NAS100") or str.contains(ticker_upper, "USTEC") or str.contains(ticker_upper, "US100") or str.contains(ticker_upper, "NAS")
is_btc_detected = str.contains(ticker_upper, "BTC") or str.contains(ticker_upper, "ETH")
is_dol_detected = str.contains(ticker_upper, "DOL") or str.contains(ticker_upper, "WDO") or str.contains(ticker_upper, "BRL") or str.contains(ticker_upper, "USDBRL")
is_us_detected  = str.contains(ticker_upper, "SPY") or str.contains(ticker_upper, "ES") or str.contains(ticker_upper, "SPX") or str.contains(ticker_upper, "MES") or str.contains(ticker_upper, "US500") or str.contains(ticker_upper, "SPX500") or str.contains(ticker_upper, "US 500")
is_eur_detected = str.contains(ticker_upper, "EURUSD") or (str.contains(ticker_upper, "EUR") and str.contains(ticker_upper, "USD"))
is_gbp_detected = str.contains(ticker_upper, "GBPUSD") or (str.contains(ticker_upper, "GBP") and str.contains(ticker_upper, "USD"))

is_win = forced_asset == "WIN / B3" or (forced_asset == "Automático" and is_win_detected)
is_nq  = forced_asset == "Nasdaq 100 / NQ" or (forced_asset == "Automático" and is_nq_detected)
is_btc = forced_asset == "Bitcoin / BTC" or (forced_asset == "Automático" and is_btc_detected)
is_dol = forced_asset == "Dólar / BRL" or (forced_asset == "Automático" and is_dol_detected)
is_eur = forced_asset == "EUR / USD" or (forced_asset == "Automático" and is_eur_detected)
is_gbp = forced_asset == "GBP / USD" or (forced_asset == "Automático" and is_gbp_detected)
// Fallback inteligente para o SP500 / ES se nenhum outro ativo coincidir
is_us  = forced_asset == "SP500 / ES" or (forced_asset == "Automático" and (is_us_detected or (not is_win and not is_nq and not is_btc and not is_dol and not is_eur and not is_gbp)))

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
                
                
            int size = array.size(prices)
            for i = 0 to size - 1
                p = array.get(prices, i) * scale_factor
                lbl = array.get(labels, i)
                col = array.get(colors, i)
                w = array.get(widths, i)
                sty = array.get(styles, i) == "dashed" ? line.style_dashed : line.style_solid
                
                // Desenhar a linha estendida para ambos os lados
                l = line.new(x1=bar_index - 100, y1=p, x2=bar_index, y2=p, xloc=xloc.bar_index, extend=extend.both, color=col, width=w, style=sty)
                
                // Rótulo dinâmico dependendo da escala
                string p_str = (is_eur or is_gbp) ? str.tostring(p, "#.####") : (scale_factor < 1.0 ? str.tostring(p, "#.####") : str.tostring(p, is_win ? "#" : "#.##"))
                lb = label.new(x=bar_index + 12, y=p, text=lbl + " [" + p_str + "]", xloc=xloc.bar_index, color=color.new(col, 95), textcolor=col, style=label.style_label_left, size=size.small)
                
                array.push(active_lines, l)
                array.push(active_labels, lb)
        initialized := true
    else
        // Acompanhar o deslocamento do gráfico em tempo real para manter as labels à direita
        int size = array.size(active_lines)
        if size > 0
            for i = 0 to size - 1
                label.set_x(array.get(active_labels, i), bar_index + 12)
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(pine_code)
        
    print(f"[TV Exporter] Indicador unificado de 5 Ativos gerado com sucesso em: {output_path}")
