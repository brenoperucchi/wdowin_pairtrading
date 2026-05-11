import datetime

def generate_gex_report(current_win, flip_price, walls, output_path=None):
    """
    Analisa os niveis de GEX e gera um relatorio em texto com a probabilidade
    de tendencia do mercado para o dia.
    """
    report = []
    report.append("==================================================")
    report.append("  RELATÓRIO DIÁRIO DE TENDÊNCIA B3 (GEX ENGINE)")
    report.append(f"  Data: {datetime.datetime.now().strftime('%d/%m/%Y')}")
    report.append("==================================================\n")
    
    # 1. Analise de Regime (Gamma Flip)
    report.append("1. REGIME DE VOLATILIDADE (O FATOR PRINCIPAL)")
    report.append(f"   Preço Atual (WIN): {current_win:.0f}")
    report.append(f"   Gamma Flip Point:  {flip_price:.0f}")
    
    if current_win >= flip_price:
        regime = "POSITIVE GAMMA (Mercado Comprado)"
        bias = "ALTA / LATERALIZAÇÃO"
        desc = "   Leitura: O mercado esta operando ACIMA do Flip. Market Makers estao vendendo na alta e comprando na baixa para fazer hedge. Isso suprime a volatilidade e trava o mercado, favorecendo dias mais direcionais e calmos com leve vies de alta."
    else:
        regime = "NEGATIVE GAMMA (Mercado Vendido)"
        bias = "QUEDA / ALTA VOLATILIDADE"
        desc = "   Leitura: O mercado esta operando ABAIXO do Flip. Market Makers sao obrigados a vender na queda e comprar na alta. Isso amplifica os movimentos, gerando picos de alta volatilidade (choppy) e forte pressao vendedora."
        
    report.append(f"   => Status Atual:   {regime}")
    report.append(desc)
    report.append(f"   => Viés do Dia:    {bias}\n")
    
    # 2. Mapeamento de Magnetismo (Walls)
    report.append("2. MAGNETISMO E PONTOS DE INTERESSE")
    
    # Isolar apenas as Walls reais (ignorar MidWalls e Max/Min Gamma por enquanto)
    real_walls = [w for w in walls if w['type'] == 'Wall']
    
    major_walls = sorted([w for w in real_walls if w['width'] >= 3], key=lambda x: x['price'])
    secondary_walls = sorted([w for w in real_walls if w['width'] == 2], key=lambda x: x['price'])
    
    # Encontrar suportes e resistencias imediatos
    supports = [w for w in real_walls if w['price'] < current_win]
    resistances = [w for w in real_walls if w['price'] > current_win]
    
    imm_supp = supports[-1] if supports else None
    imm_res = resistances[0] if resistances else None
    
    if major_walls:
        report.append("   A Grande Muralha (O grande ímã do mercado):")
        for mw in major_walls:
            report.append(f"   - {mw['price']:.0f} (Baseada no IBOV {mw.get('strike_ibov', '')})")
            if mw['price'] < current_win:
                report.append("     (Atua como Piso Gravitacional de longo prazo)")
            else:
                report.append("     (Atua como Teto Gravitacional Magnético)")
    
    report.append("\n   Zonas de Conflito Imediato (Curtíssimo Prazo):")
    if imm_res:
        report.append(f"   - Resistência Imediata: {imm_res['price']:.0f} (Width {imm_res['width']})")
    if imm_supp:
        report.append(f"   - Suporte Imediato:     {imm_supp['price']:.0f} (Width {imm_supp['width']})")
        
    report.append("\n3. CONCLUSÃO PARA O PREGÃO:")
    if current_win < flip_price:
        if major_walls and major_walls[0]['price'] < current_win:
            report.append(f"   O viés é de QUEDA. Espere fortes solavancos na abertura e ao longo do dia. O preço tende a ser 'sugado' para baixo em direção a muralha dos {major_walls[0]['price']:.0f}. Vendas perto da resistencia de {imm_res['price']:.0f} (se houver repique) sao favorecidas pelas mesas proprietárias.")
        else:
            report.append(f"   O viés é de QUEDA e ALTA VOLATILIDADE. Cuidado com falsos rompimentos. Traders institucionais estao na ponta vendedora atuando a favor do momento.")
    else:
        if major_walls and major_walls[-1]['price'] > current_win:
            report.append(f"   O viés é LATERAL / ALTA. Mercado anestesiado pela venda de volatilidade dos institucionais. O preco tende a subir gradativamente em direção ao ímã de {major_walls[-1]['price']:.0f}. Compras no suporte de {imm_supp['price']:.0f} sao estatisticamente mais seguras hoje.")
        else:
            report.append("   O viés é LATERAL / ALTA. O mercado está travado por institucionais, operando com movimentos curtos e previsíveis. Operar contra a tendencia primaria é arriscado.")
            
    report.append("==================================================")
    
    final_text = "\n".join(report)
    
    # Printar no terminal
    print("\n" + final_text + "\n")
    
    # Salvar em arquivo se solicitado
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_text)
            
    return final_text
