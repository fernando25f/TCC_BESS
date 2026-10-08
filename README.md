<div align="center">
  <h1>TCC: Impactos da Geração Distribuída e Mitigação via BESS em Redes Reais</h1>
  <p><i>Simulação avançada de fluxo de potência em séries temporais utilizando OpenDSS e Python.</i></p>
</div>

---

## 📖 Descrição Completa do Trabalho

A transição energética e o crescimento exponencial da **Geração Distribuída (GD)** — principalmente sistemas solares fotovoltaicos — estão alterando drasticamente o comportamento elétrico das redes de distribuição. Redes que foram historicamente projetadas para um fluxo unidirecional (da subestação para os consumidores) agora lidam com injeções massivas de potência nas pontas do alimentador.

Este Trabalho de Conclusão de Curso foca em **quantificar, diagnosticar e mitigar** esses impactos estruturais operacionais. Através de simulações em **séries temporais de 24 horas**, o projeto analisa o efeito do **Fluxo Reverso** em transformadores e o aumento drástico no perfil de tensão da rede em horários de pico de irradiação solar.

Para resolver essas violações sistêmicas, o projeto desenvolve e propõe uma lógica de controle de **Sistemas de Armazenamento de Energia em Baterias (BESS)**. O algoritmo dimensiona as baterias e executa seu despacho dinâmico para absorver a energia excedente (Peak Shaving Inverso), aliviando a infraestrutura existente e regularizando os níveis de tensão sem a necessidade de reforços pesados na rede física.

---

## 🎯 Objetivos do Projeto

1. **Modelagem de Redes Reais:** Importação e conversão de redes georreferenciadas provenientes da BDGD (Base de Dados Geográfica da Distribuidora), neste estudo utilizando a rede de **Goiânia Leste (ENEL-GO)**.
2. **Estudo de Casos Extremos:** Aplicação de injeções forçadas de Usinas Solares em Média Tensão (MT) e Baixa Tensão (BT) simulando cenários de alta penetração que superam a capacidade de curto-circuito local.
3. **Análise de Violações:** Detecção algorítmica de barras submetidas a tensões fora do limite regulatório (PRODIST) e identificação da causa-raiz topológica (rastreamento de efeito cascata).
4. **Integração de Baterias (BESS):** Algoritmo automatizado que dimensiona o inversor (MW) e a capacidade do banco de baterias (MWh) necessários para neutralizar o fluxo de potência reverso na subestação.

---

## 🧠 Metodologia e Pipeline de Simulação

O fluxo de processamento é inteiramente orquestrado em **Python** utilizando a biblioteca **`opendssdirect.py`** (interface direta em memória com o OpenDSS), contornando as limitações do COM Interface padrão.

1. **Cenário Baseline:** O sistema realiza um Load Flow inicial (sem GD) varrendo 1440 minutos (ou passos definidos) do dia para estabelecer a carga técnica e as quedas de tensão naturais da rede.
2. **Cenário de Estresse (Com GD):** Um "Injetor de Sobrecarga" instala dinamicamente Usinas Solares ao longo da topologia seguindo padrões configurados (MT_FEEDER ou BT_DISTRIBUTION), gerando severa inversão de fluxo na curva do meio-dia.
3. **Coleta de Métricas:** Através de `Dataclasses` com tipagem estrita (`ElementStats`), o motor monitora P(kW), Q(kVAr), S(kVA) e tensões máxima/mínima (pu) em todos os Transformadores da Subestação e Disjuntores dos Alimentadores, em tempo contínuo (O(1)).
4. **Exportação e Análise Visual:** Exportação automatizada de matrizes de relatórios em `.csv` e plotagem de mapas coropléticos da rede, evidenciando as zonas de estresse elétrico e curvas diárias vetoriais (`.svg`).

---

## 🏗️ Arquitetura de Software (Clean Code)

A base de código foi projetada sob requisitos rigorosos de qualidade, visando a continuidade da pesquisa e escalabilidade em outros circuitos do Sistema Interligado Nacional:

- **SOLID (Cenários por Composição):** Cenários não dependem de heranças engessadas. O estudo é montado empilhando componentes (peças de Lego), como `DisableDistributedGenerationComponent`, `EnableSolarGenerationComponent` e `SolarOverloadInjector`.
- **Fail-Fast:** Regras de negócio e parâmetros (`SimulationConfig`) são validados instantaneamente no `__post_init__`, impedindo que simulações de alto custo computacional rodem com dados inconsistentes.
- **Isolamento de Domínio:** O Motor de Simulação (`engine.py`) não conhece regras de plotagem ou exportação CSV. Todo o processamento passa por injetores de dependência para analisadores independentes (`metrics.py`, `plots.py`).
- **Resolução de Malhas Topológicas:** O módulo `topology_debugger.py` realiza grafos de profundidade na árvore elétrica do OpenDSS para agrupar milhares de sobretensões de clientes em apenas 1 ou 2 "elementos causadores" na rede primária.

---

## 📂 Estrutura de Diretórios

```text
├── main.py                     # Ponto de entrada: orquestra a injeção de dependências e roda os cenários.
├── src/                        # Domínio e regras de negócio do simulador.
│   ├── simulation/
│   │   ├── config.py           # Configurações globais, steps, e variáveis estritas.
│   │   ├── core/               # Engine de passo, OpenDSS Reader, Circuit Manager e Tipagens (ElementStats).
│   │   ├── scenarios/          # Interfaces base e injetores de lógica para o circuito.
│   │   ├── analysis/           # Geração de CSVs, dimensionamento do BESS e rastreio topológico.
│   │   └── visualization/      # Módulo de plotagem (Matplotlib) e Geo-Renderização.
│   └── converter/              # Ferramental de ETL para conversão da BDGD para código `.dss`.
├── modelo_opendss/             # Base de arquivos compilados prontos para uso do simulador.
├── logs_TCC/                   # (Output) Relatórios quantitativos das execuções (.csv).
└── graficos_TCC/               # (Output) Visualizações gráficas em alta resolução (.svg/.png).
```

---

## 🚀 Guia de Execução

1. **Dependências:** Crie um ambiente virtual e instale as bibliotecas científicas padrão:
   ```bash
   pip install pandas numpy matplotlib opendssdirect.py
   ```
2. **Setup:** Clone o repositório e garanta que as bases elétricas (`.dss`) do circuito alvo existam na pasta `modelo_opendss/`.
3. **Parametrização:** Em `main.py`, defina as metas da simulação modificando os parâmetros de instância do `SimulationConfig` (ex: `escopo`, `modo_sobrecarga`, `fator_sobrecarga_alvo`).
4. **Simulação:**
   ```bash
   python main.py
   ```

---
*Este código representa a base metodológica para o desenvolvimento de monografias e publicações na área de Planejamento de Sistemas Elétricos Inteligentes e Smart Grids.*
