import datetime

def export_to_profit(walls, output_path, current_win=None):
    """
    Exporta a lista de walls geradas para o formato NTSL (Nelogica Trading System Language).
    Cria automaticamente variaveis e plotagens para cada linha.
    """
    
    lines_declarations = []
    lines_assignments = []
    lines_plotting = []
    lines_noplot = []
    
    # Constantes de Cores NTSL
    color_map = {
        "Wall": "clWall",
        "MidWall": "clMidWall",
        "GammaFlip": "clFlip",
        "MaxGamma": "clMaxGamma",
        "MinGamma": "clMinGamma"
    }
    
    # Se current_win for fornecido, filtra as linhas que estao a mais de 5% de distancia do preco atual
    if current_win is not None:
        filtered_walls = []
        lower_bound = current_win * 0.95
        upper_bound = current_win * 1.05
        for w in walls:
            if lower_bound <= w['price'] <= upper_bound:
                filtered_walls.append(w)
            else:
                print(f"[Exporter] Ignorando nivel {w['type']} em {w['price']:.1f} por estar fora do range de +-5% do WIN ({lower_bound:.1f} - {upper_bound:.1f})")
        walls_sorted = sorted(filtered_walls, key=lambda x: x['price'])
    else:
        walls_sorted = sorted(walls, key=lambda x: x['price'])
    
    for i, w in enumerate(walls_sorted, start=1):
        # 1. Declaracao
        lines_declarations.append(f"  line{i} : float;")
        lines_declarations.append(f"  line{i}Color : integer;")
        lines_declarations.append(f"  line{i}Width : integer;")
        lines_declarations.append(f"  line{i}Style : integer;")
        
        # 2. Atribuicao
        c_var = color_map.get(w['type'], "clWall")
        width = w.get('width', 1)
        style = w.get('style', 0)
        
        lines_assignments.append(f"  line{i} := {w['price']:.3f};")
        lines_assignments.append(f"  line{i}Color := {c_var};")
        lines_assignments.append(f"  line{i}Width := {width};")
        lines_assignments.append(f"  line{i}Style := {style};")
        
        # 3. Plotagem
        plot_func = "Plot" if i == 1 else f"Plot{i}"
        lines_plotting.append(f"    SetPlotColor({i}, line{i}Color);")
        lines_plotting.append(f"    SetPlotWidth({i}, line{i}Width);")
        lines_plotting.append(f"    SetPlotStyle({i}, line{i}Style);")
        lines_plotting.append(f"    {plot_func}(line{i});")
        
        # 4. NoPlot
        lines_noplot.append(f"      NoPlot({i});")
        
    now = datetime.datetime.now()
    date_str = f"ELDate({now.year}, {now.month:02d}, {now.day:02d})"
    
    # Montar template NTSL
    ntsl_code = f"""var
  clWall : integer;
  clMidWall : integer;
  clMidWallFibo : integer;
  clFlip : integer;
  clMaxGamma: integer;
  clMinGamma : integer;
  stlMidWallFibo : integer;
  stlMidWall : integer;
{chr(10).join(lines_declarations)}

BEGIN
  clWall := clLime;
  clMidWall := clGray;
  clMidWallFibo := clDkGray;
  clFlip := clYellow;
  clMaxGamma:= clGreen;
  clMinGamma := clRed;
  stlMidWall := 1;
  stlMidWallFibo := 2;

{chr(10).join(lines_assignments)}

 if (((Date = {date_str}) and (Time >= 900)) and ((GetAsset() = "WINFUT") or (GetAsset() = "INDFUT") or (GetAsset() = "WINM26") or (GetAsset() = "INDM26"))) then
  begin
{chr(10).join(lines_plotting)}
  end;

  if (Time > 1900) then
    begin
{chr(10).join(lines_noplot)}
    end;
END;
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ntsl_code)
    
    print(f"[Exporter] Arquivo Nelogica gerado com {len(walls)} linhas em: {output_path}")
