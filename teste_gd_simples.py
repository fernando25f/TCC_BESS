"""
Simulação didática de circuito de teste reduzido com Geração Distribuída (PVSystem).
Demonstra a curva de geração solar diária de Goiânia (Abril - 96 passos de 15 min),
o impacto no fluxo de potência (fluxo reverso) e no perfil de tensão da barra.
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import opendssdirect as dss

def criar_circuito_teste(potencia_pv_kw: float = 75.0, usar_pico_unitario: bool = False):
    """
    Monta um circuito radial trifásico simples em OpenDSS:
    Rede 13.8 kV -> Trafo 150 kVA (13.8/0.38 kV) -> Linha BT 100m -> Carga + Usina Solar
    """
    dss.Command("Clear")
    
    # 1. Fonte da Subestação (Rede MT 13.8 kV)
    dss.Command("New Circuit.TesteGD basekv=13.8 pu=1.00 bus1=Barra_MT r1=0.01 x1=0.02")

    # 2. Definição da Curva Solar de Goiânia para o mês de Abril (24h interpoladas em 96 passos de 15 min)
    # Valores horários médios de irradiação solar em W/m² (Goiânia - Abril)
    irrad_24h = [0, 0, 0, 0, 0, 0, 68, 353, 521, 624, 676, 655, 591, 522, 465, 416, 363, 215, 0, 0, 0, 0, 0, 0]
    x_24 = np.arange(24) + 0.5
    x_96 = np.arange(1, 97) * 0.25
    interp_96 = np.interp(x_96, x_24, irrad_24h)
    interp_96[x_96 < 5.75] = 0.0
    interp_96[x_96 > 18.5] = 0.0

    if usar_pico_unitario:
        mult_solar = interp_96 / max(interp_96)
        nome_loadshape = "Curva_Solar_Abril_PicoUnitario"
    else:
        # Normalização STC padrão (1000 W/m² = 1.0 pu)
        mult_solar = interp_96 / 1000.0
        nome_loadshape = "Curva_Solar_Abril"

    mult_str = " ".join(f"{v:.4f}" for v in mult_solar)
    dss.Command(f"New Loadshape.{nome_loadshape} npts=96 interval=0.25 mult=({mult_str})")

    # 3. Curva de Carga Comercial/Residencial diária típica (96 passos)
    curva_carga_24h = [0.30, 0.25, 0.22, 0.20, 0.20, 0.25, 0.40, 0.60, 0.75, 0.85, 0.90, 0.88, 
                       0.85, 0.82, 0.80, 0.82, 0.85, 0.95, 1.00, 0.98, 0.90, 0.75, 0.55, 0.40]
    mult_carga = np.interp(x_96, x_24, curva_carga_24h)
    mult_carga_str = " ".join(f"{v:.4f}" for v in mult_carga)
    dss.Command(f"New Loadshape.CurvaCarga_Comercial npts=96 interval=0.25 mult=({mult_carga_str})")

    # 4. Transformador de Distribuição MT/BT (150 kVA, 13.8 kV / 0.38 kV)
    dss.Command("New Transformer.TrafoMTBT phases=3 windings=2 %r=1.0 xhl=4.0 kva=150")
    dss.Command("~ wdg=1 bus=Barra_MT conn=delta kv=13.8")
    dss.Command("~ wdg=2 bus=Barra_Sec conn=wye kv=0.38 tap=1.00")

    # 5. Ramal Secundário de Baixa Tensão (100 metros)
    dss.Command("New Line.LinhaBT phases=3 bus1=Barra_Sec.1.2.3.0 bus2=Barra_GD.1.2.3.0 r1=0.27 x1=0.08 length=0.10 units=km normamps=200")

    # 6. Carga Local na Baixa Tensão (Pico de 35 kW)
    dss.Command("New Load.CargaLocal phases=3 bus1=Barra_GD.1.2.3.0 kv=0.38 conn=wye kw=35 pf=0.95 model=1 daily=CurvaCarga_Comercial vminpu=0.85")

    # 7. Usina Solar Fotovoltaica (PVSystem)
    kva_inversor = round(potencia_pv_kw * 1.05, 2)
    dss.Command(f"New PVSystem.UsinaSolar phases=3 bus1=Barra_GD.1.2.3.0 kv=0.38 conn=wye pmpp={potencia_pv_kw} kva={kva_inversor} pf=1.0 irradiance=1.0 daily={nome_loadshape} %cutin=0.1 %cutout=0.1")

    # 8. Configuração das bases de tensão e modo de simulação
    dss.Command("Set VoltageBases=[13.8, 0.38]")
    dss.Command("CalcVoltageBases")
    dss.Command("Set Mode=Daily StepSize=15m Number=1 Hour=0 Sec=0")

    return nome_loadshape, interp_96

def executar_simulacao(potencia_pv_kw: float = 75.0, usar_pico_unitario: bool = False):
    """Executa a simulação de 24 horas passo a passo e coleta as métricas elétricas."""
    nome_curva, irrad_w_m2 = criar_circuito_teste(potencia_pv_kw, usar_pico_unitario)

    passos = 96
    horas = [i * 0.25 for i in range(passos)]
    rotulos_hora = [f"{int(h):02d}:{int((h % 1)*60):02d}" for h in horas]

    geracao_pv_kw = []
    consumo_carga_kw = []
    fluxo_subestacao_kw = []
    tensao_barra_pu = []

    for step in range(passos):
        dss.Solution.Solve()

        # Potência gerada pela Usina Solar (kW)
        # Convenção do OpenDSS: injeção de potência na barra resulta em valor negativo no terminal 1
        dss.Circuit.SetActiveElement("PVSystem.UsinaSolar")
        pot_pv = dss.CktElement.Powers()
        p_pv = -sum(pot_pv[0::2]) if pot_pv else 0.0
        geracao_pv_kw.append(max(0.0, p_pv))

        # Potência consumida pela Carga (kW)
        dss.Circuit.SetActiveElement("Load.CargaLocal")
        pot_carga = dss.CktElement.Powers()
        p_carga = sum(pot_carga[0::2]) if pot_carga else 0.0
        consumo_carga_kw.append(p_carga)

        # Fluxo líquido na Subestação (kW) - Positivo: Subestação fornece; Negativo: Fluxo reverso
        dss.Circuit.SetActiveElement("Vsource.source")
        pot_se = dss.CktElement.Powers()
        p_se = -sum(pot_se[0::2]) if pot_se else 0.0
        fluxo_subestacao_kw.append(p_se)

        # Tensão na barra da Usina (pu) - extrai magnitude fasorial correta
        dss.Circuit.SetActiveBus("Barra_GD")
        pu_mags = dss.Bus.puVmagAngle()
        v_mags = pu_mags[0::2] if pu_mags else [1.0]
        tensao_barra_pu.append(float(np.mean(v_mags[:3])))

    return {
        "horas": horas,
        "rotulos": rotulos_hora,
        "irrad_w_m2": irrad_w_m2,
        "geracao_pv": geracao_pv_kw,
        "consumo_carga": consumo_carga_kw,
        "fluxo_se": fluxo_subestacao_kw,
        "tensao_pu": tensao_barra_pu,
        "potencia_pv_kw": potencia_pv_kw,
        "nome_curva": nome_curva
    }

def imprimir_relatorio(dados: dict):
    """Exibe no terminal a tabela horária e o sumário operacional."""
    print("=" * 88)
    print(f"  CIRCUITO DE TESTE: USINA SOLAR FOTOVOLTAICA ({dados['potencia_pv_kw']:.1f} kWp)")
    print(f"  Curva Solar Referência: {dados['nome_curva']} (Goiânia/GO)")
    print("=" * 88)
    print(f"{'Hora':<7} | {'Irrad (W/m²)':<13} | {'Geração GD (kW)':<16} | {'Carga (kW)':<12} | {'Fluxo SE (kW)':<14} | {'Tensão (pu)':<11}")
    print("-" * 88)

    # Imprime amostragem de 1 em 1 hora (passos a cada 4 intervalos de 15 min)
    for i in range(0, 96, 4):
        hora = dados["rotulos"][i]
        irrad = dados["irrad_w_m2"][i]
        p_gd = dados["geracao_pv"][i]
        p_ld = dados["consumo_carga"][i]
        p_se = dados["fluxo_se"][i]
        v_pu = dados["tensao_pu"][i]

        status_fluxo = "<- REVERSO" if p_se < -0.5 else ""
        print(f"{hora:<7} | {irrad:>11.1f}   | {p_gd:>14.2f}   | {p_ld:>10.2f}   | {p_se:>12.2f}   | {v_pu:>9.4f} {status_fluxo}")

    print("-" * 88)
    
    # Métricas agregadas
    energia_gd_kwh = sum(dados["geracao_pv"]) * 0.25
    pico_gd_kw = max(dados["geracao_pv"])
    idx_pico = np.argmax(dados["geracao_pv"])
    hora_pico = dados["rotulos"][idx_pico]
    v_max = max(dados["tensao_pu"])
    v_min = min(dados["tensao_pu"])

    print(f"  * Energia Solar Gerada no Dia : {energia_gd_kwh:.2f} kWh")
    print(f"  * Potência de Pico Atingida   : {pico_gd_kw:.2f} kW às {hora_pico}")
    print(f"  * Fator de Capacidade Diário  : {(energia_gd_kwh / (dados['potencia_pv_kw'] * 24)) * 100:.1f}%")
    print(f"  * Tensão Mínima na Barra      : {v_min:.4f} pu")
    print(f"  * Tensão Máxima na Barra      : {v_max:.4f} pu (Elevação solar no meio-dia)")
    print("=" * 88)

def gerar_grafico(dados: dict, caminho_imagem: str = "teste_gd_abril.png"):
    """Gera visualização gráfica das 24 horas da simulação."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True)

    horas = dados["horas"]

    # 1. Gráfico Superior: Curvas de Potência
    ax1.plot(horas, dados["geracao_pv"], label="Geração Solar (kW)", color="#eab308", linewidth=2.5)
    ax1.plot(horas, dados["consumo_carga"], label="Demanda da Carga (kW)", color="#dc2626", linewidth=2.0, linestyle="--")
    ax1.plot(horas, dados["fluxo_se"], label="Fluxo na Subestação (kW)", color="#2563eb", linewidth=2.0)
    ax1.axhline(0, color="#6b7280", linestyle=":", alpha=0.8)
    ax1.fill_between(horas, 0, dados["geracao_pv"], color="#fde047", alpha=0.35, label="Área de Geração Solar")

    ax1.set_title(f"Simulação 24h - Curva Solar de Abril (Usina PV {dados['potencia_pv_kw']:.0f} kWp)", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Potência Ativa (kW)", fontsize=11)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(loc="upper right", framealpha=0.9)

    # 2. Gráfico Inferior: Perfil de Tensão
    ax2.plot(horas, dados["tensao_pu"], label="Tensão na Barra da Usina (pu)", color="#059669", linewidth=2.2)
    ax2.axhline(1.05, color="#b91c1c", linestyle="--", alpha=0.6, label="Limite Superior (1.05 pu)")
    ax2.axhline(0.93, color="#b91c1c", linestyle="--", alpha=0.6, label="Limite Inferior (0.93 pu)")
    ax2.axhline(1.00, color="#6b7280", linestyle=":", alpha=0.6)

    ax2.set_xlabel("Hora do Dia (h)", fontsize=11)
    ax2.set_ylabel("Tensão (pu)", fontsize=11)
    ax2.set_xlim(0, 24)
    ax2.set_xticks(range(0, 25, 2))
    ax2.set_xticklabels([f"{h:02d}:00" for h in range(0, 25, 2)])
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(loc="lower right", framealpha=0.9)

    plt.tight_layout()
    plt.savefig(caminho_imagem, dpi=160)
    plt.close()
    print(f"\n[GRÁFICO] Imagem salva com sucesso em: {os.path.abspath(caminho_imagem)}")

if __name__ == "__main__":
    # Executa com usina de 75 kWp utilizando a curva de irradiação solar de Abril
    resultados = executar_simulacao(potencia_pv_kw=75.0, usar_pico_unitario=True)
    imprimir_relatorio(resultados)
    gerar_grafico(resultados, "teste_gd_abril.png")
