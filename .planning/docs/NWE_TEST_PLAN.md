# Integração e Otimização do Filtro Nadaraya-Watson Envelope (NWE)

## Objetivo
Testar estatisticamente se a adição do filtro NWE (Nadaraya-Watson Envelope) melhora a performance do "Setup Matador" atual, filtrando sinais com base na inclinação da curva de preço suavizada do índice WIN.

## Fases de Implementação e Limites de Parâmetros

### Fase 1: Replicação Matemática do NWE em Python
**Objetivo:** Traduzir a função `calc_nwe()` do Javascript (Dashboard) para Python, garantindo correspondência exata 1:1 com cálculos vetorizados (Pandas/NumPy).
**Parâmetros do Kernel NWE a serem expostos:**
*   **Janela de Lookback (`h`):** Define o tamanho do "horizonte" do kernel de regressão.
    *   *Limite Inferior:* 50 barras.
    *   *Limite Superior:* 300 barras.
    *   *Passo (Step) da Busca:* 50 barras.
*   **Bandwidth (`bw` ou `sigma`):** Define a "suavidade" do kernel Gaussiano.
    *   *Limite Inferior:* 3.
    *   *Limite Superior:* 15.
    *   *Passo (Step) da Busca:* 1.

### Fase 2: Otimização da Lógica de Filtro (Trend vs. Counter-Trend)
**Objetivo:** Testar duas lógicas comportamentais conflitantes contra o histórico, sem viés humano.
**Parâmetro Categórico (Modo de Operação):**
1.  **Modo "Fader" (Contra-Tendência):** Comprar apenas se a macro-tendência (NWE) estiver caindo (vermelha). Vender se NWE estiver subindo (verde). *Atualmente é o que o Dashboard desenha nas entrelinhas.*
2.  **Modo "Seguidor" (A Favor da Tendência):** Comprar apenas se NWE estiver verde. Vender apenas se NWE estiver vermelho. *Logicamente faz mais sentido para pair-trading.*
3.  **Modo "Desligado" (Baseline):** Para medir qual seria o resultado sem a interferência do NWE, estabelecendo uma linha de base.

### Fase 3: Integração com as Variáveis do Setup Matador
**Objetivo:** Combinar o filtro NWE com os gatilhos já existentes de Z-Score e DI.
**Parâmetros de Gatilho para Otimização Múltipla:**
*   **Alvo de Z-Score de Entrada (`z_entry`):**
    *   *Limites:* 0.8 a 2.0 desvios.
    *   *Passo:* 0.2.
*   **Filtro Direcional de Juros (`di_threshold`):**
    *   *Limites:* 0.5 a 2.5.
    *   *Passo:* 0.5.

### Fase 4: Otimização de Força Bruta (Grid Search)
**Objetivo:** Rodar uma matriz testando todas as permutações dos parâmetros das Fases 1 a 3.
**Passos da Execução:**
1.  Baixar e tratar base de dados com mínimo de 15.000 barras.
2.  Aplicar função Gaussiana do NWE sobre toda a série histórica.
3.  Calcular o vetor de inclinação (Slope).
4.  Iterar sobre todas as permutações gerando uma tabela unificada de performance.
5.  Gravar métricas por permutação: Taxa de Acerto (Win Rate %), Profit Factor (Fator de Lucro), Max Drawdown e Número de Trades (excluindo combinações com < 30 amostras por irrelevância estatística).

### Fase 5: Validação e Injeção em Produção
**Objetivo:** Escolher os melhores valores, garantir que não houve over-fitting e aplicar no bot real.
**Passos da Execução:**
1.  Identificar as zonas de parâmetros onde o Fator de Lucro é consistentemente superior ao *Baseline* (Superfície Plana, não "Picos" isolados).
2.  Definir os valores ótimos definitivos.
3.  Atualizar o arquivo `config.json` com a nova estrutura de parâmetros do NWE.
4.  Inserir a condição de Slope no arquivo principal do robô em Python.
5.  Opcional: Sincronizar os mesmos parâmetros ótimos no Kernel do Frontend React.
