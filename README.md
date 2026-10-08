# TCC: Simulação de Fluxo Reverso e BESS (OpenDSS + Python)

Este projeto é fruto de um Trabalho de Conclusão de Curso (TCC) com o objetivo de analisar o impacto da alta penetração de **Geração Distribuída (GD)** — especificamente energia solar fotovoltaica — em redes de distribuição reais. A simulação investiga fenômenos como **fluxo reverso** e **sobretensão**, e propõe o dimensionamento e controle dinâmico de um **BESS (Battery Energy Storage System)** para mitigar esses problemas.

O código controla o software **OpenDSS** por meio da biblioteca `opendssdirect.py`, automatizando a execução do fluxo de potência ao longo de perfis diários (24h).

---

## ⚡ Principais Funcionalidades

- **Controle Automatizado do OpenDSS:** Interface robusta utilizando `opendssdirect` em Python, encapsulando os detalhes complexos do OpenDSS.
- **Cenários por Composição:** A arquitetura do projeto utiliza o padrão de composição (interfaces modulares) para criar cenários flexíveis. Você pode empilhar componentes em um cenário, como:
  - `DisableDistributedGenerationComponent`: Roda a simulação apenas com carga (cenário padrão).
  - `EnableSolarGenerationComponent`: Ativa a base instalada de GD da rede.
  - `SolarOverloadInjector`: Injeta agressivamente novas usinas solares (na MT ou BT) para forçar o fluxo reverso.
  - `BESSControllerComponent` *(Em desenvolvimento)*: Controla o despacho de baterias para absorver excedentes solares.
- **Métricas e Relatórios Automáticos (Clean Code):** Extrai dados detalhados usando *Dataclasses* (`ElementStats`), calculando picos de demanda, violações de tensão (subtensão/sobretensão) e perfil de geração.
- **Exportação Visual:** Gera relatórios detalhados em `CSV` e plota gráficos em `SVG/PNG` do perfil de tensão e carregamento dos transformadores (Subestação e Distribuição).

---

## 📂 Estrutura do Projeto

```text
├── main.py                     # Ponto de entrada: configura e executa os cenários
├── src/                        # Código-fonte principal do simulador
│   ├── simulation/
│   │   ├── config.py           # Definição estrita dos parâmetros da simulação (dataclass)
│   │   ├── core/               # Motor do OpenDSS, Circuit Manager e Tipagens
│   │   ├── scenarios/          # Peças de Lego dos cenários (Injeção de GD, Sobrecarga, etc.)
│   │   ├── analysis/           # Geração de relatórios CSV, detecção de falhas de topologia
│   │   └── visualization/      # Plotagem de gráficos 24h e renderização de mapas
│   └── converter/              # Scripts de suporte e conversão (ex: BDGD para DSS)
├── modelo_opendss/             # Base de dados dos circuitos e alimentadores mapeados (.dss)
├── logs_TCC/                   # (Gerado) Saídas de log, debug e tabelas CSV
└── graficos_TCC/               # (Gerado) Relatórios visuais (tensão, potência, mapas)
```

---

## 🚀 Como Executar

1. **Pré-requisitos:** Certifique-se de que possui as bibliotecas necessárias instaladas (ex: `pandas`, `numpy`, `matplotlib`, `opendssdirect.py`).
2. **Configuração:** Abra o arquivo `main.py` para alterar o `escopo`, ativar/desativar `controle_tap_ativo`, ou ajustar a intensidade do fluxo reverso em `fator_sobrecarga_alvo`.
3. **Rodar:**
   ```bash
   python main.py
   ```
4. **Análise:** Verifique as pastas `graficos_TCC/` e `logs_TCC/` para os relatórios da simulação.

---

## 🛠️ Arquitetura

Este código foi desenvolvido respeitando rígidos princípios de Engenharia de Software e **Clean Code**:
- **SOLID**: Componentes fracamente acoplados. A adição do BESS requer apenas a injeção de uma nova classe na lista de modificadores do cenário.
- **Fail-Fast**: Validação proativa de parâmetros no módulo de configurações (evitando falhas silenciosas do OpenDSS horas após o início do processamento).
- **Type Hints Rigorosos**: Utilização de `dataclasses` para eliminação de "dicionários mágicos", prevenindo `KeyErrors` e documentando a estrutura dos dados elétricos em tempo de codificação.

---
*Este repositório faz parte de um estudo acadêmico focado no planejamento da infraestrutura de distribuição moderna frente à transição energética.*
