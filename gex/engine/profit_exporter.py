import datetime
import subprocess
import os
import json
import re

def get_ntsl_asset_checks(ref_date=None):
    """
    Retorna uma lista de codigos de ativos WIN e IND (anterior, atual, proximo)
    para garantir que o indicador funcione durante transicoes de contratos.
    """
    if ref_date is None:
        ref_date = datetime.date.today()
    codes = ['G', 'J', 'M', 'Q', 'V', 'Z']
    
    def get_expiry_date(y, m):
        d_15 = datetime.date(y, m, 15)
        days_to_wed = 2 - d_15.weekday() # Quarta e index 2
        wed = d_15 + datetime.timedelta(days=days_to_wed)
        candidates = [wed - datetime.timedelta(weeks=1), wed, wed + datetime.timedelta(weeks=1)]
        return min(candidates, key=lambda d: abs((d - d_15).days))
        
    y = ref_date.year
    m = ref_date.month
    
    if m % 2 != 0:
        target_idx = (m // 2) % 6
        target_year = y
        if m == 1:
            target_idx = 0
        elif m == 11:
            target_idx = 5
    else:
        target_idx = (m // 2 - 1) % 6
        target_year = y
        expiry = get_expiry_date(y, m)
        if ref_date >= expiry:
            target_idx = (target_idx + 1) % 6
            if target_idx == 0:
                target_year += 1
                
    asset_checks = []
    for offset in [-1, 0, 1]:
        idx = (target_idx + offset) % 6
        year = target_year
        if target_idx + offset < 0:
            year -= 1
        elif target_idx + offset >= 6:
            year += 1
        code = codes[idx]
        year_suffix = str(year)[2:]
        asset_checks.append(f'WIN{code}{year_suffix}')
        asset_checks.append(f'IND{code}{year_suffix}')
        
    return asset_checks

def get_ntsl_dol_asset_checks(ref_date=None):
    """
    Retorna os codigos de ativos para DOL e WDO.
    """
    if ref_date is None:
        ref_date = datetime.date.today()
    codes = ['F', 'G', 'H', 'J', 'K', 'M', 'N', 'Q', 'U', 'V', 'X', 'Z']
    y = ref_date.year
    m = ref_date.month
    
    target_idx = (m - 1) % 12
    asset_checks = []
    for offset in [-1, 0, 1]:
        idx = (target_idx + offset) % 12
        year = y
        if target_idx + offset < 0:
            year -= 1
        elif target_idx + offset >= 12:
            year += 1
        code = codes[idx]
        year_suffix = str(year)[2:]
        asset_checks.append(f'WDO{code}{year_suffix}')
        asset_checks.append(f'DOL{code}{year_suffix}')
    return asset_checks

def load_cached_walls_data(ticker):
    dir_name = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(dir_name, "data", f"{ticker.lower()}_walls_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Exporter] Erro ao ler cache {ticker}: {e}")
    return {}

def load_cached_walls(ticker):
    """
    Carrega as walls salvas em cache para um determinado ticker.
    """
    data = load_cached_walls_data(ticker)
    return data.get("walls", [])

def load_cached_current_price(ticker):
    """
    Carrega o preco atual salvo em cache para um determinado ticker.
    """
    data = load_cached_walls_data(ticker)
    return data.get("current_price")

def get_approx_current_price(walls, default_val, ticker=None):
    if ticker:
        cp = load_cached_current_price(ticker)
        if cp is not None and cp > 0:
            return cp
    wall_prices = [w['price'] for w in walls if w.get('type') == 'Wall']
    if wall_prices:
        return sum(wall_prices) / len(wall_prices)
    if walls:
        return sum(w['price'] for w in walls) / len(walls)
    return default_val

def export_to_profit_unified(win_walls, dol_walls, output_path, current_win=None, current_dol=None):
    """
    Exporta a lista unificada de walls de WIN e DOL para o formato NTSL.
    """
    # Constantes de Cores NTSL
    color_map = {
        "Wall": "clMagicWall",
        "MidWall": "clMidleWall",
        "GammaFlip": "clFlip",
        "MaxGamma": "clMaxGamma",
        "MinGamma": "clMinGamma"
    }
    
    # 1. Filtrar e ordenar WIN
    if current_win is not None:
        win_filtered = []
        lower_bound = current_win * 0.95
        upper_bound = current_win * 1.05
        for w in win_walls:
            if w['type'] in ('GammaFlip', 'MaxGamma', 'MinGamma') or (lower_bound <= w['price'] <= upper_bound):
                win_filtered.append(w)
            else:
                print(f"[Exporter] Ignorando nivel WIN {w['type']} em {w['price']:.1f} por estar fora do range de +-5% ({lower_bound:.1f} - {upper_bound:.1f})")
        win_sorted = sorted(win_filtered, key=lambda x: x['price'])
    else:
        win_sorted = sorted(win_walls, key=lambda x: x['price'])
        
    # 2. Filtrar e ordenar DOL
    if current_dol is not None:
        dol_filtered = []
        lower_bound = current_dol * 0.95
        upper_bound = current_dol * 1.05
        for w in dol_walls:
            if w['type'] in ('GammaFlip', 'MaxGamma', 'MinGamma') or (lower_bound <= w['price'] <= upper_bound):
                dol_filtered.append(w)
            else:
                print(f"[Exporter] Ignorando nivel DOL {w['type']} em {w['price']:.1f} por estar fora do range de +-5% ({lower_bound:.1f} - {upper_bound:.1f})")
        dol_sorted = sorted(dol_filtered, key=lambda x: x['price'])
    else:
        dol_sorted = sorted(dol_walls, key=lambda x: x['price'])
        
    max_lines = max(len(win_sorted), len(dol_sorted))
    
    lines_declarations = []
    for i in range(1, max_lines + 1):
        lines_declarations.append(f"  line{i} : float;")
        lines_declarations.append(f"  line{i}Color : integer;")
        lines_declarations.append(f"  line{i}Width : integer;")
        lines_declarations.append(f"  line{i}Style : integer;")
        
    win_flip = next((w['price'] for w in win_walls if w.get('type') == 'GammaFlip'), None)
    dol_flip = next((w['price'] for w in dol_walls if w.get('type') == 'GammaFlip'), None)

    def get_wall_color(w, flip_price=None):
        w_type = w.get('type')
        if w_type == 'GammaFlip':
            return 'clFlip'
        elif w_type == 'MaxGamma':
            return 'clMaxGamma'
        elif w_type == 'MinGamma':
            return 'clMinGamma'
        elif w_type == 'Wall':
            gex = w.get('gex', 0)
            if gex < 0:
                return 'clRed'        # Put Wall (Vermelho / Suporte)
            elif gex > 0:
                return 'clLime'       # Call Wall (Verde Neon / Resistência)
            elif flip_price is not None and w['price'] < flip_price:
                return 'clRed'
            else:
                return 'clLime'
        elif w_type == 'MidWall':
            return 'clMidleWall'
        return 'clMagicWall'

    # Construir atribuições e plotagens para WIN
    win_blocks = []
    for i, w in enumerate(win_sorted, start=1):
        c_var = get_wall_color(w, win_flip)
        width = w.get('width', 1)
        style_expr = 'stlMidleWall' if w.get('type') == 'MidWall' else str(w.get('style', 0))
        win_blocks.append(f"      line{i} := {w['price']:.3f};")
        win_blocks.append(f"      line{i}Color := {c_var};")
        win_blocks.append(f"      line{i}Width := {width};")
        win_blocks.append(f"      line{i}Style := {style_expr};")
        win_blocks.append(f"      SetPlotColor({i}, line{i}Color);")
        win_blocks.append(f"      SetPlotWidth({i}, line{i}Width);")
        win_blocks.append(f"      SetPlotStyle({i}, line{i}Style);")
        plot_func = "Plot" if i == 1 else f"Plot{i}"
        win_blocks.append(f"      {plot_func}(line{i});")
    for i in range(len(win_sorted) + 1, max_lines + 1):
        win_blocks.append(f"      NoPlot({i});")
        
    # Construir atribuições e plotagens para DOL
    dol_blocks = []
    for i, w in enumerate(dol_sorted, start=1):
        c_var = get_wall_color(w, dol_flip)
        width = w.get('width', 1)
        style_expr = 'stlMidleWall' if w.get('type') == 'MidWall' else str(w.get('style', 0))
        dol_blocks.append(f"      line{i} := {w['price']:.3f};")
        dol_blocks.append(f"      line{i}Color := {c_var};")
        dol_blocks.append(f"      line{i}Width := {width};")
        dol_blocks.append(f"      line{i}Style := {style_expr};")
        dol_blocks.append(f"      SetPlotColor({i}, line{i}Color);")
        dol_blocks.append(f"      SetPlotWidth({i}, line{i}Width);")
        dol_blocks.append(f"      SetPlotStyle({i}, line{i}Style);")
        plot_func = "Plot" if i == 1 else f"Plot{i}"
        dol_blocks.append(f"      {plot_func}(line{i});")
    for i in range(len(dol_sorted) + 1, max_lines + 1):
        dol_blocks.append(f"      NoPlot({i});")
        
    # NoPlot geral para fora do horario
    noplot_all = []
    for i in range(1, max_lines + 1):
        noplot_all.append(f"      NoPlot({i});")
        
    now = datetime.datetime.now()
    date_str = f"ELDate({now.year}, {now.month:02d}, {now.day:02d})"
    
    # Calcular o início da plotagem (retrocede 3 dias na segunda-feira para cobrir fim de semana, ou 1 dia nos demais dias)
    prev_days = 3 if now.weekday() == 0 else 1
    prev_date = now.date() - datetime.timedelta(days=prev_days)
    prev_date_str = f"ELDate({prev_date.year}, {prev_date.month:02d}, {prev_date.day:02d})"
    
    # WIN checks
    win_checks = ['"WINFUT"', '"INDFUT"']
    try:
        dynamic_win_checks = get_ntsl_asset_checks(now.date())
        win_checks.extend([f'"{ac}"' for ac in dynamic_win_checks])
    except Exception as e:
        print(f"[Exporter] Erro ao calcular ativos WIN dinâmicos: {e}")
        win_checks.extend(['"WINM26"', '"INDM26"', '"WINQ26"', '"INDQ26"'])
    win_asset_condition = " or ".join([f'(GetAsset() = {ac})' for ac in win_checks])
    
    # DOL checks
    dol_checks = ['"DOLFUT"', '"WDOFUT"']
    try:
        dynamic_dol_checks = get_ntsl_dol_asset_checks(now.date())
        dol_checks.extend([f'"{ac}"' for ac in dynamic_dol_checks])
    except Exception as e:
        print(f"[Exporter] Erro ao calcular ativos DOL dinâmicos: {e}")
        dol_checks.extend(['"WDON26"', '"DOLN26"'])
    dol_asset_condition = " or ".join([f'(GetAsset() = {ac})' for ac in dol_checks])
    
    # Montar template NTSL unificado
    ntsl_code = f"""var
  clMagicWall : integer;
  clMidleWall : integer;
  clMidWallFibo : integer;
  clFlip : integer;
  clMaxGamma: integer;
  clMinGamma : integer;
  stlMidWallFibo : integer;
  stlMidleWall : integer;
  isWIN : boolean;
  isDOL : boolean;
{chr(10).join(lines_declarations)}

BEGIN
  clMagicWall := clLime;
  clMidleWall := clGray;
  clMidWallFibo := clDkGray;
  clFlip := clYellow;
  clMaxGamma:= clGreen;
  clMinGamma := clRed;
  stlMidleWall := 1;
  stlMidWallFibo := 2;

  isWIN := {win_asset_condition};
  isDOL := {dol_asset_condition};

  if (((Date >= {prev_date_str}) and (Time >= 900) and (Time <= 1900))) then
  begin
    if isWIN then
    begin
{chr(10).join(win_blocks)}
    end
    else if isDOL then
    begin
{chr(10).join(dol_blocks)}
    end
    else
    begin
{chr(10).join(noplot_all)}
    end;
  end
  else
  begin
{chr(10).join(noplot_all)}
  end;
END;
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ntsl_code)
        
    print(f"[Exporter] Arquivo Nelogica unificado gerado com {len(win_sorted)} WIN e {len(dol_sorted)} DOL linhas em: {output_path}")
    return ntsl_code

def copy_to_clipboard(text):
    """Copia o texto para a clipboard do Windows usando PowerShell."""
    try:
        process = subprocess.Popen(
            ['powershell', '-NoProfile', '-Command', 'Set-Clipboard -Value $input'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8'
        )
        process.communicate(input=text, timeout=5)
        return process.returncode == 0
    except Exception as e:
        print(f"[Exporter] Aviso: Falha ao copiar para clipboard ({e})")
        return False

def send_toast_notification(title, message):
    """Envia uma notificação toast do Windows usando PowerShell."""
    try:
        ps_script = f'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$template = @"
<toast duration="long">
    <visual>
        <binding template="ToastGeneric">
            <text>{title}</text>
            <text>{message}</text>
        </binding>
    </visual>
    <audio src="ms-winsoundevent:Notification.Default"/>
</toast>
"@

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("GEX Engine").Show($toast)
'''
        subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True, timeout=10
        )
    except Exception as e:
        print(f"[Exporter] Aviso: Notificação toast falhou ({e})")

def export_to_profit(walls, output_path, current_win=None):
    # Mantém compatibilidade com chamadas antigas
    return export_to_profit_unified(
        win_walls=walls,
        dol_walls=load_cached_walls("usd_brl"),
        output_path=output_path,
        current_win=current_win,
        current_dol=None
    )

def update_magic_wall_flow(win_walls, dol_walls, current_win=None, current_dol=None):
    """
    Gera o indicador NTSL completo MagicWall_Flow.nts combinando:
      1. Todas as Walls e MidWalls do dia (WIN e WDO) com Polaridade Dinâmica e Espessura por Defesa de Lotes;
      2. Medição de Fluxo de Agressão Ponderado por Tamanho de Boletada (AgressionVolBalance * LoteMédio);
      3. Janelas de Fluxo A.S.G (EMA 4 vs EMA 11 do CVD Ponderado com Histerese);
      4. Pintura de Candles (PaintBar) e Sinais no Gráfico (PlotText: ▲ WALL, ▼ WALL, ▲ FLUXO, ▼ FLUXO).
    """
    if current_win is not None:
        lower_w, upper_w = current_win * 0.95, current_win * 1.05
        win_sorted = sorted(
            [w for w in win_walls if w.get("type") in ("GammaFlip", "MaxGamma", "MinGamma") or (lower_w <= w["price"] <= upper_w)],
            key=lambda x: x["price"],
        )
    else:
        win_sorted = sorted(win_walls, key=lambda x: x["price"])

    if current_dol is not None:
        lower_d, upper_d = current_dol * 0.95, current_dol * 1.05
        dol_sorted = sorted(
            [w for w in dol_walls if w.get("type") in ("GammaFlip", "MaxGamma", "MinGamma") or (lower_d <= w["price"] <= upper_d)],
            key=lambda x: x["price"],
        )
    else:
        dol_sorted = sorted(dol_walls, key=lambda x: x["price"])

    win_sorted = win_sorted[:30]
    dol_sorted = dol_sorted[:30]
    max_lines = max(len(win_sorted), len(dol_sorted), 1)

    lines_declarations = []
    for i in range(1, max_lines + 1):
        lines_declarations.append(f"  line{i} : float;")
        lines_declarations.append(f"  line{i}Color : integer;")
        lines_declarations.append(f"  line{i}Width : integer;")
        lines_declarations.append(f"  line{i}Style : integer;")
        lines_declarations.append(f"  line{i}IsMid : boolean;")

    win_flip = next((w["price"] for w in win_walls if w.get("type") == "GammaFlip"), None)
    dol_flip = next((w["price"] for w in dol_walls if w.get("type") == "GammaFlip"), None)

    def get_base_color(w, flip_price=None):
        w_type = w.get("type")
        if w_type == "GammaFlip":
            return "clFlip"
        elif w_type == "MaxGamma":
            return "clMaxGamma"
        elif w_type == "MinGamma":
            return "clMinGamma"
        elif w_type == "MidWall":
            return "clMidleWall"
        gex = w.get("gex", 0)
        if gex < 0:
            return "clRed"
        elif gex > 0:
            return "clLime"
        elif flip_price is not None and w["price"] < flip_price:
            return "clRed"
        return "clLime"

    def build_asset_block(sorted_walls, flip_price, radius_var):
        blocks = []
        blocks.append("      emZonaSuporte := false;")
        blocks.append("      emZonaResistencia := false;")
        for i, w in enumerate(sorted_walls, start=1):
            c_var = get_base_color(w, flip_price)
            base_w = w.get("width", 1)
            is_mid = w.get("type") == "MidWall"
            is_flip = w.get("type") == "GammaFlip"
            style_expr = "stlMidleWall" if is_mid else str(w.get("style", 0))
            plot_func = "Plot" if i == 1 else f"Plot{i}"

            blocks.append(f"      line{i} := {w['price']:.3f};")
            blocks.append(f"      line{i}IsMid := {'true' if is_mid else 'false'};")
            blocks.append(f"      line{i}Style := {style_expr};")
            blocks.append(f"      line{i}Width := {base_w};")

            # Polaridade dinâmica: abaixo do preço = Suporte (Verde), acima do preço = Resistência (Vermelho)
            if is_flip:
                blocks.append(f"      line{i}Color := clFlip;")
            elif is_mid:
                blocks.append(
                    f"      if UsarPolaridadeDinamica then begin if Close >= line{i} then line{i}Color := clGreen else line{i}Color := clMaroon; end else line{i}Color := {c_var};"
                )
            else:
                blocks.append(
                    f"      if UsarPolaridadeDinamica then begin if Close >= line{i} then line{i}Color := clLime else line{i}Color := clRed; end else line{i}Color := {c_var};"
                )

            # Teste da Wall na barra atual + diferenciação de espessura por lote de defesa
            blocks.append(
                f"      if (Low - {radius_var} <= line{i}) and (High + {radius_var} >= line{i}) then"
            )
            blocks.append("      begin")
            blocks.append(
                f"        if DestacarDefesaNaWall and (not line{i}IsMid) and (volTotal >= mediaVol * FatorLoteDefesa) then line{i}Width := {min(4, base_w + 2)};"
            )
            blocks.append(
                f"        if (Close >= line{i}) and (Low - {radius_var} <= line{i}) then emZonaSuporte := true;"
            )
            blocks.append(
                f"        if (Close <= line{i}) and (High + {radius_var} >= line{i}) then emZonaResistencia := true;"
            )
            blocks.append("      end;")

            blocks.append(f"      SetPlotColor({i}, line{i}Color);")
            blocks.append(f"      SetPlotWidth({i}, line{i}Width);")
            blocks.append(f"      SetPlotStyle({i}, line{i}Style);")
            blocks.append(f"      {plot_func}(line{i});")

        for i in range(len(sorted_walls) + 1, max_lines + 1):
            blocks.append(f"      NoPlot({i});")
        return blocks

    win_blocks = build_asset_block(win_sorted, win_flip, "RaioWallWIN")
    dol_blocks = build_asset_block(dol_sorted, dol_flip, "RaioWallWDO")
    noplot_all = [f"      NoPlot({i});" for i in range(1, max_lines + 1)]

    now = datetime.datetime.now()
    prev_days = 3 if now.weekday() == 0 else 1
    prev_date = now.date() - datetime.timedelta(days=prev_days)
    prev_date_str = f"ELDate({prev_date.year}, {prev_date.month:02d}, {prev_date.day:02d})"

    win_checks = ['"WINFUT"', '"INDFUT"']
    try:
        win_checks.extend([f'"{ac}"' for ac in get_ntsl_asset_checks(now.date())])
    except Exception:
        win_checks.extend(['"WINZ26"', '"INDZ26"'])
    win_asset_condition = " or ".join([f"(GetAsset() = {ac})" for ac in win_checks])

    dol_checks = ['"DOLFUT"', '"WDOFUT"']
    try:
        dol_checks.extend([f'"{ac}"' for ac in get_ntsl_dol_asset_checks(now.date())])
    except Exception:
        dol_checks.extend(['"WDOX26"', '"DOLX26"'])
    dol_asset_condition = " or ".join([f"(GetAsset() = {ac})" for ac in dol_checks])

    ntsl_flow_code = f"""Input
  UsarPolaridadeDinamica(true);   // Pinta Walls abaixo do preço de Verde (Suporte) e acima de Vermelho (Resistência)
  DestacarDefesaNaWall(true);     // Engrossa a linha da Wall quando há defesa com lote alto
  ColorirVelasFluxoASG(true);     // Pinta os candles pelas Janelas de Fluxo A.S.G + Absorção na Wall
  MostrarSetasSinais(true);       // Plota ▲/▼ quando há Defesa na Wall ou Explosão de Fluxo Institucional
  ApenasAFavorDaJanela(false);    // false = Metodologia 1 (Antecipa viradas na Wall); true = Metodologia 2 (Só opera a favor da Janela)
  RaioWallWIN(75.0);              // Raio de tolerância em pontos na Wall para o Índice (WIN)
  RaioWallWDO(2.0);               // Raio de tolerância em pontos na Wall para o Dólar (WDO)
  FatorLoteDefesa(1.15);          // Múltiplo da média de volume para validar defesa institucional

var
  clMagicWall : integer;
  clMidleWall : integer;
  clMidWallFibo : integer;
  clFlip : integer;
  clMaxGamma: integer;
  clMinGamma : integer;
  stlMidWallFibo : integer;
  stlMidleWall : integer;
  isWIN : boolean;
  isDOL : boolean;
  emZonaSuporte : boolean;
  emZonaResistencia : boolean;
  rangeBarra : float;
  pavioInf : float;
  pavioSup : float;
  volCompra : float;
  volVenda : float;
  volTotal : float;
  saldoAgr : float;
  mediaVol : float;
  negocios : float;
  loteMedio : float;
  mediaLote : float;
  pesoInst : float;
  deltaInstProxy : float;
  cvdInst : float;
  emaFast : float;
  emaSlow : float;
  passoCvd : float;
  oscCvd : float;
  histFluxo : float;
  janelaDir : integer;
  desequilibrioPct : float;
  sinalCompraWall : boolean;
  sinalVendaWall : boolean;
  sinalCompraFluxo : boolean;
  sinalVendaFluxo : boolean;
  barraUltimoSinal : integer;
{chr(10).join(lines_declarations)}

BEGIN
  clMagicWall := clLime;
  clMidleWall := clGray;
  clMidWallFibo := clDkGray;
  clFlip := clYellow;
  clMaxGamma:= clGreen;
  clMinGamma := clRed;
  stlMidleWall := 1;
  stlMidWallFibo := 2;

  isWIN := {win_asset_condition};
  isDOL := {dol_asset_condition};

  // ── 1. MOTOR DE FLUXO DE AGRESSÃO PONDERADO POR LOTE (PROXY INSTITUCIONAL) ──
  volCompra := AgressionVolBuy;
  volVenda := AgressionVolSell;
  volTotal := volCompra + volVenda;
  saldoAgr := AgressionVolBalance;
  mediaVol := Max(1, Media(20, volTotal));

  negocios := Max(1, Trades);
  loteMedio := volTotal / negocios;
  mediaLote := Max(1, Media(20, loteMedio));
  pesoInst := loteMedio / mediaLote;
  if pesoInst > 3.0 then pesoInst := 3.0;
  if pesoInst < 0.5 then pesoInst := 0.5;

  deltaInstProxy := saldoAgr * pesoInst;
  if (Date <> Date[1]) then
    cvdInst := deltaInstProxy
  else
    cvdInst := cvdInst[1] + deltaInstProxy;

  emaFast := MediaExp(4, cvdInst);
  emaSlow := MediaExp(11, cvdInst);
  passoCvd := Max(1, MediaExp(7, Abs(deltaInstProxy)));
  oscCvd := ((emaFast - emaSlow) / (passoCvd * 1.4)) * 55.0;
  histFluxo := MediaExp(3, oscCvd);

  // Histerese da Janela A.S.G (+6.5 / -6.5)
  if (Date <> Date[1]) then
  begin
    if histFluxo >= 0 then janelaDir := 1 else janelaDir := -1;
    barraUltimoSinal := 0;
  end
  else
  begin
    janelaDir := janelaDir[1];
    barraUltimoSinal := barraUltimoSinal[1];
    if (janelaDir = 1) and (histFluxo <= -6.5) then janelaDir := -1;
    if (janelaDir = -1) and (histFluxo >= 6.5) then janelaDir := 1;
  end;

  if volTotal > 0 then
    desequilibrioPct := (saldoAgr / volTotal) * 100.0
  else
    desequilibrioPct := 0;

  if (((Date >= {prev_date_str}) and (Time >= 900) and (Time <= 1900))) then
  begin
    if isWIN then
    begin
{chr(10).join(win_blocks)}
    end
    else if isDOL then
    begin
{chr(10).join(dol_blocks)}
    end
    else
    begin
{chr(10).join(noplot_all)}
    end;

    // ── 2. AVALIAÇÃO DE DEFESA NA WALL + EXPLOSÃO DE FLUXO ──
    if isWIN or isDOL then
    begin
      rangeBarra := High - Low;
      if Open < Close then pavioInf := Open - Low else pavioInf := Close - Low;
      if Open > Close then pavioSup := High - Open else pavioSup := High - Close;

      sinalCompraWall := false;
      sinalVendaWall := false;
      sinalCompraFluxo := false;
      sinalVendaFluxo := false;

      if rangeBarra > 0 then
      begin
        // Regra 1: Compra por Absorção / Defesa na Wall de Suporte
        if emZonaSuporte and (Close >= Low + rangeBarra * 0.50) and (volTotal >= mediaVol * 0.85) and
           (((pavioInf >= rangeBarra * 0.32) and ((saldoAgr < 0) or (deltaInstProxy > 0))) or
            ((Close > Open) and (pesoInst >= 1.15) and (saldoAgr > 0))) then
          sinalCompraWall := true;

        // Regra 2: Venda por Rejeição / Absorção na Wall de Resistência
        if emZonaResistencia and (Close <= High - rangeBarra * 0.50) and (volTotal >= mediaVol * 0.85) and
           (((pavioSup >= rangeBarra * 0.32) and ((saldoAgr > 0) or (deltaInstProxy < 0))) or
            ((Close < Open) and (pesoInst >= 1.15) and (saldoAgr < 0))) then
          sinalVendaWall := true;

        // Regra 3: Compra por Explosão de Fluxo Institucional
        if (not sinalCompraWall) and (Close > Open) and (pesoInst >= 1.25) and
           (volTotal >= mediaVol * 1.25) and (desequilibrioPct >= 12.0) and (janelaDir = 1) then
          sinalCompraFluxo := true;

        // Regra 4: Venda por Explosão de Fluxo Institucional
        if (not sinalVendaWall) and (Close < Open) and (pesoInst >= 1.25) and
           (volTotal >= mediaVol * 1.25) and (desequilibrioPct <= -12.0) and (janelaDir = -1) then
          sinalVendaFluxo := true;
      end;

      // Se ApenasAFavorDaJanela = true (Metodologia 2), bloqueia sinais contra a Janela A.S.G
      if ApenasAFavorDaJanela then
      begin
        if janelaDir = 1 then
        begin
          sinalVendaWall := false;
          sinalVendaFluxo := false;
        end
        else
        begin
          sinalCompraWall := false;
          sinalCompraFluxo := false;
        end;
      end;

      // ── 3. PINTURA DOS CANDLES (FLUXO REAL A.S.G + DEFESA NA WALL) ──
      if ColorirVelasFluxoASG then
      begin
        if sinalCompraWall then
          PaintBar(clAqua)
        else if sinalVendaWall then
          PaintBar(clFuchsia)
        else if janelaDir = 1 then
        begin
          if (Close >= Open) or (saldoAgr >= 0) then
            PaintBar(clLime)
          else
            PaintBar(clSilver); // Pullback / Respiro dentro da Janela Verde
        end
        else
        begin
          if (Close <= Open) or (saldoAgr <= 0) then
            PaintBar(clRed)
          else
            PaintBar(clSilver); // Pullback / Respiro dentro da Janela Vermelha
        end;
      end;

      // ── 4. SETINHAS OPERACIONAIS NO GRÁFICO (COM COOLDOWN DE 3 BARRAS) ──
      if MostrarSetasSinais and ((CurrentBar - barraUltimoSinal) >= 3) then
      begin
        if sinalCompraWall then
        begin
          PlotText("▲ WALL", clAqua, 0, 10);
          barraUltimoSinal := CurrentBar;
        end
        else if sinalVendaWall then
        begin
          PlotText("▼ WALL", clFuchsia, 2, 10);
          barraUltimoSinal := CurrentBar;
        end
        else if sinalCompraFluxo then
        begin
          PlotText("▲ FLUXO", clLime, 0, 9);
          barraUltimoSinal := CurrentBar;
        end
        else if sinalVendaFluxo then
        begin
          PlotText("▼ FLUXO", clRed, 2, 9);
          barraUltimoSinal := CurrentBar;
        end;
      end;
    end;
  end
  else
  begin
{chr(10).join(noplot_all)}
  end;
END;
"""

    flow_doc_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "gex", "docs", "MagicWall_Flow.nts"
    )
    try:
        with open(flow_doc_path, "w", encoding="utf-8") as f:
            f.write(ntsl_flow_code)
        print(f"[Exporter] MagicWall_Flow.nts atualizado com sucesso em: {flow_doc_path}")

        nelogica_targets = [
            r"C:\Users\ryzen\AppData\Roaming\Nelogica\Profit\strategy",
            r"C:\Users\ryzen\AppData\Roaming\Nelogica\Scalper\strategy",
        ]
        for strategy_dir in nelogica_targets:
            if os.path.exists(strategy_dir):
                for ext in [".nts", ".nne"]:
                    dest_file = os.path.join(strategy_dir, f"MagicWall_Flow{ext}")
                    with open(dest_file, "w", encoding="utf-8") as f:
                        f.write(ntsl_flow_code)
                nelogica_subdir = os.path.join(strategy_dir, "Nelogica")
                if os.path.exists(nelogica_subdir):
                    src_dest = os.path.join(nelogica_subdir, "MagicWall_Flow.src")
                    with open(src_dest, "w", encoding="utf-8") as f:
                        f.write(ntsl_flow_code)
    except Exception as e:
        print(f"[Exporter] Aviso: Não foi possível atualizar MagicWall_Flow.nts ({e})")


def update_magic_wall_manual(win_walls, current_win=None):
    """
    Atualiza os parâmetros no topo do arquivo MagicWallManual.nts (GammaMax, GammaMin, GammaFlip, FatorConversao)
    com os valores calculados do dia de hoje.
    """
    if not win_walls:
        return

    gamma_max = None
    gamma_min = None
    gamma_flip = None
    factor = 1.008189  # fallback padrão

    for w in win_walls:
        w_type = w.get('type')
        if w_type == 'MaxGamma':
            gamma_max = w['price']
        elif w_type == 'MinGamma':
            gamma_min = w['price']
        elif w_type == 'GammaFlip':
            gamma_flip = w['price']
            if 'factor' in w and w['factor']:
                factor = w['factor']

    if gamma_max is None or gamma_min is None or gamma_flip is None:
        return

    manual_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "gex", "docs", "MagicWallManual.nts"
    )

    if not os.path.exists(manual_path):
        return

    try:
        with open(manual_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Substituir os valores de Input no topo do arquivo
        content = re.sub(r'GammaMax\([\d\.]+\);', f'GammaMax({gamma_max:.1f});', content)
        content = re.sub(r'GammaMin\([\d\.]+\);', f'GammaMin({gamma_min:.1f});', content)
        content = re.sub(r'GammaFlip\([\d\.]+\);', f'GammaFlip({gamma_flip:.1f});', content)
        content = re.sub(r'FatorConversao\([\d\.]+\);', f'FatorConversao({factor:.6f});', content)

        with open(manual_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"[Exporter] MagicWallManual.nts atualizado com sucesso (Flip={gamma_flip:.1f}, Factor={factor:.6f})")

        # Copiar para as pastas de estratégia do Profit e Scalper
        nelogica_targets = [
            r"C:\Users\ryzen\AppData\Roaming\Nelogica\Profit\strategy",
            r"C:\Users\ryzen\AppData\Roaming\Nelogica\Scalper\strategy",
        ]
        for strategy_dir in nelogica_targets:
            if os.path.exists(strategy_dir):
                dest_file = os.path.join(strategy_dir, "MagicWallManual.nts")
                with open(dest_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                nelogica_subdir = os.path.join(strategy_dir, "Nelogica")
                if os.path.exists(nelogica_subdir):
                    src_dest = os.path.join(nelogica_subdir, "MagicWallManual.src")
                    with open(src_dest, 'w', encoding='utf-8') as f:
                        f.write(content)
    except Exception as e:
        print(f"[Exporter] Aviso: Não foi possível atualizar MagicWallManual.nts ({e})")


def deploy_to_nelogica(walls=None, ticker="WIN", current_price=None, strategy_name="MagicWall"):
    return export_all(ticker=ticker, walls=walls, current_price=current_price, strategy_name=strategy_name)

def export_all(ticker="WIN", walls=None, current_price=None, strategy_name="MagicWall"):
    """
    Deploy completo unificado para Nelogica: carrega WIN e DOL do cache,
    combina-os e exporta o codigo NTSL para ambas as plataformas.
    """
    # 1. Carregar os dados
    if ticker.upper() == "WIN":
        win_walls = walls if walls is not None else load_cached_walls("win")
        dol_walls = load_cached_walls("usd_brl")
        current_win = current_price if current_price is not None else get_approx_current_price(win_walls, 174000, ticker="win")
        current_dol = get_approx_current_price(dol_walls, 5200, ticker="usd_brl")
    else:
        win_walls = load_cached_walls("win")
        dol_walls = walls if walls is not None else load_cached_walls("usd_brl")
        current_win = get_approx_current_price(win_walls, 174000, ticker="win")
        current_dol = current_price if current_price is not None else get_approx_current_price(dol_walls, 5200, ticker="usd_brl")
        
    # Caminho base do repositorio
    doc_suffix = "" if strategy_name == "MagicWall" else "_dinamico"
    base_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "gex", "docs", f"jumba_neologica{doc_suffix}"
    )
    
    # 2. Gerar e salvar no repositorio
    ntsl_code = export_to_profit_unified(
        win_walls=win_walls,
        dol_walls=dol_walls,
        output_path=base_file,
        current_win=current_win,
        current_dol=current_dol
    )
    
    # 2.1 Atualizar o MagicWallManual.nts estatico com os parametros do dia (apenas para a versao principal)
    if strategy_name == "MagicWall":
        update_magic_wall_manual(win_walls, current_win=current_win)
    
    # 3. Salvar em todas as pastas da Nelogica
    nelogica_targets = [
        (r"C:\Users\ryzen\AppData\Roaming\Nelogica\Profit\strategy", strategy_name),
        (r"C:\Users\ryzen\AppData\Roaming\Nelogica\Scalper\strategy", strategy_name),
    ]
    
    for strategy_dir, name in nelogica_targets:
        if not os.path.exists(strategy_dir):
            parent = os.path.dirname(strategy_dir)
            if os.path.exists(parent):
                os.makedirs(strategy_dir, exist_ok=True)
            else:
                continue
        
        # Salvar .nne (formato de importacao)
        nne_path = os.path.join(strategy_dir, f"{name}.nne")
        export_to_profit_unified(
            win_walls=win_walls,
            dol_walls=dol_walls,
            output_path=nne_path,
            current_win=current_win,
            current_dol=current_dol
        )
        
        # Salvar .src na subpasta Nelogica
        nelogica_subdir = os.path.join(strategy_dir, "Nelogica")
        if os.path.exists(nelogica_subdir):
            src_path = os.path.join(nelogica_subdir, f"{name}.src")
            with open(src_path, 'w', encoding='utf-8') as f:
                f.write(ntsl_code)
            print(f"[Exporter] Fonte .src salvo em: {src_path}")
            
    # 4. Copiar para a clipboard do Windows (apenas para a versao principal)
    if strategy_name == "MagicWall":
        if copy_to_clipboard(ntsl_code):
            print("[Exporter] Codigo NTSL unificado (Ancorado) copiado para a clipboard do Windows! (Ctrl+V no Scalper)")
        
    return ntsl_code
