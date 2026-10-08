import opendssdirect as dss
import matplotlib.pyplot as plt

def main():
    # ==============================================================================
    # 1. DEFINIÇÃO DO CIRCUITO SIMPLIFICADO NO OPENDSS
    # ==============================================================================
    dss_script = """
    Clear
    New Circuit.BessTest BasekV=13.8 pu=1.00 Isc3=3000 Isc1=2250
    
    ! --- Curvas de Comportamento (24h) ---
    ! Curva de Carga (Pico à noite)
    New Loadshape.Carga_Diaria npts=24 interval=1 
    ~ mult=[0.3 0.3 0.3 0.3 0.4 0.5 0.7 0.8 0.7 0.6 0.6 0.5 0.5 0.5 0.5 0.6 0.7 0.9 1.0 0.9 0.8 0.6 0.4 0.3]
    
    ! Curva Solar (Meio-dia)
    New Loadshape.Solar_Diaria npts=24 interval=1
    ~ mult=[0 0 0 0 0 0 0.1 0.3 0.6 0.8 1.0 1.0 1.0 0.9 0.7 0.4 0.1 0 0 0 0 0 0 0]

    ! --- Topologia ---
    ! Rede muito fraca (rural/longa) para que a injeção da GD cause forte elevação de tensão
    New Line.L1 phases=3 Bus1=sourcebus Bus2=carga_bus length=25 units=km R1=0.40 X1=0.20
    
    ! Carga: 1000 kW nominal
    New Load.Carga1 Bus1=carga_bus kV=13.8 kW=1000 pf=0.92 daily=Carga_Diaria status=variable
    
    ! Usina GD Solar: 2500 kW (Gera muito mais do que a carga no meio-dia = Fluxo Reverso!)
    New Generator.GD1 Bus1=carga_bus kV=13.8 kW=2500 pf=1.0 daily=Solar_Diaria status=variable
    
    ! Bateria (BESS): Inversor de 1500 kW e Capacidade de 4000 kWh
    New Storage.BESS1 Bus1=carga_bus kV=13.8 kWrated=1500 kWhrated=4000 state=IDLING %stored=50
    
    Set Voltagebases=[13.8]
    CalcVoltageBases
    """
    
    for line in dss_script.strip().split("\n"):
        if line.strip():
            dss.Command(line.strip())

    # ==============================================================================
    # 2. RODADA 1: SIMULAÇÃO SEM BATERIA (Para ver o estrago do fluxo reverso)
    # ==============================================================================
    dss.Command("Disable Storage.BESS1")
    dss.Command("Set mode=daily stepsize=1h number=1 hour=0 sec=0")
    
    p_grid_sem_bess = []
    v_grid_sem_bess = []
    
    for h in range(24):
        dss.Solution.Solve()
        p_subestacao = -dss.Circuit.TotalPower()[0]
        p_grid_sem_bess.append(p_subestacao)
        
        dss.Circuit.SetActiveBus("carga_bus")
        v_grid_sem_bess.append(dss.Bus.puVmagAngle()[0])

    # ==============================================================================
    # 3. RODADA 2: SIMULAÇÃO COM BESS (O Controle em Python)
    # ==============================================================================
    dss.Command("Enable Storage.BESS1")
    dss.Command("Reset") 
    dss.Command("Storage.BESS1.%stored=10") # Bateria começa o dia com 10% (vazia)
    dss.Command("Set mode=daily stepsize=1h number=1 hour=0 sec=0")
    
    # REGRAS DO CONTROLADOR:
    LIMITE_FLUXO_REVERSO = -800 # Limite de suporte do Transformador para fluxo reverso
    LIMITE_PICO_CARGA = 800     # Peak Shaving clássico
    
    p_grid_com_bess = []
    v_grid_com_bess = []
    estado_bateria = [] 

    for h in range(24):
        p_previsao = p_grid_sem_bess[h]
        
        dss.Circuit.SetActiveElement("Storage.BESS1")
        soc_atual = float(dss.Properties.Value("%stored"))
        
        # O Algoritmo de Decisão do BESS
        if p_previsao < LIMITE_FLUXO_REVERSO and soc_atual < 90.0:
            # Tem fluxo reverso perigoso E a bateria ainda não atingiu o topo (90%)
            excesso_kw = abs(p_previsao - LIMITE_FLUXO_REVERSO) 
            pct_charge = (excesso_kw / 1500) * 100 
            pct_charge = min(pct_charge, 100.0)
            dss.Command(f"edit Storage.BESS1 state=CHARGING %Charge={pct_charge}")
            
        elif soc_atual > 10.0 and (p_previsao > LIMITE_PICO_CARGA or h >= 18.5):
            # Tem pico de carga OU já está de noite (h >= 17) -> Descarrega proativamente!
            # Tenta suprir toda a demanda local (p_previsao - 0) para esvaziar a bateria para o dia seguinte
            alvo_rede = LIMITE_PICO_CARGA if h < 18.5 else 0 
            
            excesso_kw = p_previsao - alvo_rede
            if excesso_kw > 0:
                pct_discharge = (excesso_kw / 1500) * 100
                pct_discharge = min(pct_discharge, 100.0)
                dss.Command(f"edit Storage.BESS1 state=DISCHARGING %Discharge={pct_discharge}")
            else:
                dss.Command("edit Storage.BESS1 state=IDLING")
            
        else:
            dss.Command("edit Storage.BESS1 state=IDLING")

        dss.Solution.Solve()

        p_final = -dss.Circuit.TotalPower()[0]
        
        dss.Circuit.SetActiveBus("carga_bus")
        v_final = dss.Bus.puVmagAngle()[0]
        
        dss.Circuit.SetActiveElement("Storage.BESS1")
        soc_final = float(dss.Properties.Value("%stored"))
        
        p_grid_com_bess.append(p_final)
        v_grid_com_bess.append(v_final)
        estado_bateria.append(soc_final)

    # ==============================================================================
    # 4. GRÁFICOS COMPARATIVOS
    # ==============================================================================
    print("\n--- RESUMO DE TENSÃO ---")
    print(f"Max Tensão SEM Bateria: {max(v_grid_sem_bess):.4f} pu")
    print(f"Max Tensão COM Bateria: {max(v_grid_com_bess):.4f} pu")
    print("------------------------\n")

    fig, (ax1, ax3) = plt.subplots(2, 1, figsize=(12, 10), sharex=True, gridspec_kw={'height_ratios': [1, 1]})
    
    # Eixo de Potência (Top)
    ax1.plot(range(24), p_grid_sem_bess, label='Subestação (SEM Bateria)', color='red', linestyle='--', linewidth=2)
    ax1.plot(range(24), p_grid_com_bess, label='Subestação (COM Bateria)', color='blue', linewidth=3)
    ax1.axhline(LIMITE_FLUXO_REVERSO, color='black', linestyle=':', label='Limite Exportação (Reverso)')
    ax1.axhline(LIMITE_PICO_CARGA, color='green', linestyle=':', label='Limite Importação (Pico)')
    ax1.set_ylabel("Potência Trocada (kW)")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper left')

    # Eixo da Carga da Bateria (State of Charge)
    ax2 = ax1.twinx()
    ax2.fill_between(range(24), estado_bateria, color='orange', alpha=0.2, label='SoC (%)')
    ax2.set_ylabel("Carga da Bateria (%)", color='orange')
    ax2.set_ylim(0, 110)
    ax2.legend(loc='upper right')
    
    # Eixo de Tensão (Bottom)
    ax3.plot(range(24), v_grid_sem_bess, label='Tensão Carga (SEM Bateria)', color='red', linestyle='--', linewidth=2)
    ax3.plot(range(24), v_grid_com_bess, label='Tensão Carga (COM Bateria)', color='blue', linewidth=3)
    ax3.axhline(1.05, color='darkred', linestyle='-', linewidth=2, label='Limite Sobretensão (1.05 pu)')
    ax3.axhline(0.93, color='darkred', linestyle='-', linewidth=2, label='Limite Subtensão (0.93 pu)')
    
    # Preencher área de violação para ficar bem visível
    ax3.fill_between(range(24), 1.05, v_grid_sem_bess, where=[v > 1.05 for v in v_grid_sem_bess], color='red', alpha=0.3, label='Violação de Tensão!')
    
    ax3.set_ylabel("Tensão (pu)")
    ax3.set_xlabel("Hora do Dia")
    ax3.set_ylim(0.95, 1.15)
    ax3.grid(True, alpha=0.3)
    ax3.legend(loc='upper left')

    plt.suptitle("Estudo Teórico: Mitigação de Fluxo Reverso e Regulação de Tensão via BESS", y=0.95, fontsize=14)
    plt.tight_layout()
    plt.savefig("teste_gd_simples_grafico.png")
    print("\n[OK] Gráfico gerado e salvo como 'teste_gd_simples_grafico.png'")

if __name__ == "__main__":
    main()
