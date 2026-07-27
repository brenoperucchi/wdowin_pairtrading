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

def load_cached_walls(ticker):
    """
    Carrega as walls salvas em cache para um determinado ticker.
    """
    dir_name = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_path = os.path.join(dir_name, "data", f"{ticker.lower()}_walls_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("walls", [])
        except Exception as e:
            print(f"[Exporter] Erro ao ler cache {ticker}: {e}")
    return []

def get_approx_current_price(walls, default_val):
    for w in walls:
        if w['type'] == 'GammaFlip':
            return w['price']
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
            if lower_bound <= w['price'] <= upper_bound:
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
            if lower_bound <= w['price'] <= upper_bound:
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
        
    # Construir atribuições e plotagens para WIN
    win_blocks = []
    for i, w in enumerate(win_sorted, start=1):
        c_var = color_map.get(w['type'], "clMagicWall")
        width = w.get('width', 1)
        style = w.get('style', 0)
        win_blocks.append(f"      line{i} := {w['price']:.3f};")
        win_blocks.append(f"      line{i}Color := {c_var};")
        win_blocks.append(f"      line{i}Width := {width};")
        win_blocks.append(f"      line{i}Style := {style};")
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
        c_var = color_map.get(w['type'], "clMagicWall")
        width = w.get('width', 1)
        style = w.get('style', 0)
        dol_blocks.append(f"      line{i} := {w['price']:.3f};")
        dol_blocks.append(f"      line{i}Color := {c_var};")
        dol_blocks.append(f"      line{i}Width := {width};")
        dol_blocks.append(f"      line{i}Style := {style};")
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


def deploy_to_nelogica(walls=None, ticker="WIN", current_price=None):
    """
    Deploy completo unificado para Nelogica: carrega WIN e DOL do cache,
    combina-os e exporta o código NTSL para ambas as plataformas.
    """
    # 1. Carregar os dados
    if ticker.upper() == "WIN":
        win_walls = walls if walls is not None else load_cached_walls("win")
        dol_walls = load_cached_walls("usd_brl")
        current_win = current_price
        current_dol = get_approx_current_price(dol_walls, 5200)
    else:
        win_walls = load_cached_walls("win")
        dol_walls = walls if walls is not None else load_cached_walls("usd_brl")
        current_win = get_approx_current_price(win_walls, 174000)
        current_dol = current_price
        
    # Caminho base do repositório
    base_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "gex", "docs", "jumba_neologica"
    )
    
    # 2. Gerar e salvar no repositório
    ntsl_code = export_to_profit_unified(
        win_walls=win_walls,
        dol_walls=dol_walls,
        output_path=base_file,
        current_win=current_win,
        current_dol=current_dol
    )
    
    # 2.1 Atualizar o MagicWallManual.nts estático com os parâmetros do dia
    update_magic_wall_manual(win_walls, current_win=current_win)
    
    # 3. Salvar em todas as pastas da Nelogica
    nelogica_targets = [
        (r"C:\Users\ryzen\AppData\Roaming\Nelogica\Profit\strategy", "MagicWall"),
        (r"C:\Users\ryzen\AppData\Roaming\Nelogica\Scalper\strategy", "MagicWall"),
    ]
    
    for strategy_dir, name in nelogica_targets:
        if not os.path.exists(strategy_dir):
            parent = os.path.dirname(strategy_dir)
            if os.path.exists(parent):
                os.makedirs(strategy_dir, exist_ok=True)
            else:
                continue
        
        # Salvar .nne (formato de importação)
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
            
    # 4. Copiar para a clipboard do Windows
    if copy_to_clipboard(ntsl_code):
        print("[Exporter] Código NTSL unificado copiado para a clipboard do Windows! (Ctrl+V no Scalper)")
        
    # 5. Enviar notificação toast
    send_toast_notification(
        "GEX MagicWall Unificado",
        f"Níveis WIN e DOL atualizados e prontos na clipboard. Cole no Scalper."
    )
    
    return ntsl_code
