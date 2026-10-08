import matplotlib.pyplot as plt
import numpy as np
from typing import Dict
from src.simulation.core.engine import ScenarioResult
from src.simulation.core.circuit import CircuitManager
from src.simulation.config import SimulationConfig

class Plotter:
    """Gera e salva gráficos operacionais em formato vetorial SVG."""

    CORES = {
        'padrao': '#444444',  # Grafite escuro (#444)
        'com_gd': '#0284c7'   # Azul celeste claro
    }

    ESTILOS = {
        'padrao': {'linestyle': '-', 'linewidth': 2.2, 'label': 'Rede Padrão'},
        'com_gd': {'linestyle': '-', 'linewidth': 2.2, 'label': 'Rede com GD'}
    }

    @classmethod
    def plot_subestacao(cls, resultados: Dict[str, ScenarioResult], config: SimulationConfig) -> None:
        if not resultados:
            return

        plt.figure(figsize=(11, 5.5))

        for c_nome, res in resultados.items():
            curva_mw = [p / 1000.0 for p in res.curva_subestacao_kw]
            label = cls.ESTILOS.get(c_nome, {}).get('label', c_nome.capitalize())
            cor = cls.CORES.get(c_nome, '#333333')
            estilo = cls.ESTILOS.get(c_nome, {'linewidth': 2.0, 'linestyle': '-'})
            n_pts = min(len(curva_mw), len(config.vetor_tempo_horas))
            t_eixo = config.vetor_tempo_horas[:n_pts]
            plt.plot(t_eixo, curva_mw[:n_pts], color=cor,
                     linewidth=estilo['linewidth'],
                     linestyle=estilo['linestyle'], label=label)

        escopo = config.escopo.upper()
        if escopo == "ALIMENTADOR":
            titulo = f"Carregamento Diário 24h — Alimentador {config.alvo or config.alimentador_alvo}\n{config.meta_simulacao}"
            ylabel = "Potência Ativa no Disjuntor MT (MW)"
            nome_arq = f"demanda_ctmt_{config.alvo or config.alimentador_alvo}_24h"
        elif escopo == "TRAFO_AT":
            titulo = f"Carregamento Diário 24h — Transformador AT {config.alvo or 'TR'}\n{config.meta_simulacao}"
            ylabel = "Potência Ativa Total no Trafo AT (MW)"
            nome_arq = f"demanda_trafo_{config.alvo or 'tr'}_24h"
        else:
            titulo = f"Carregamento Diário Subestação 24h\n{config.meta_simulacao}"
            ylabel = "Potência Ativa Total da Subestação (MW)"
            nome_arq = "demanda_subestacao_24h"

        plt.title(titulo, fontsize=11, fontweight='bold')
        plt.xlabel("Hora do Dia (h)", fontsize=10)
        plt.ylabel(ylabel, fontsize=10)
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.xticks(range(1, 25))
        plt.axhline(0, color='#333333', linewidth=1.0, linestyle='--', alpha=0.45)
        plt.legend(loc='upper left', fontsize=9, framealpha=0.9)
        plt.tight_layout()

        out_svg = config.obter_caminho_saida(config.pasta_graf_subestacao, nome_arq, "svg")
        plt.savefig(out_svg, format='svg')
        plt.close()
        print(f"  [OK] Gráfico Potência ({escopo}) salvo: {config.relpath(out_svg)}")

    @classmethod
    def plot_trafos_at(cls, resultados: Dict[str, ScenarioResult], circuit: CircuitManager, config: SimulationConfig) -> None:
        """Gera gráficos comparativos 24h de carregamento e tensão dos transformadores AT presentes no escopo."""
        if not circuit.trafos_subestacao:
            return

        res_padrao = resultados.get('padrao')
        res_gd = resultados.get('com_gd')
        if not res_padrao and not res_gd:
            return

        paleta_cores = ['#e74c3c', '#0284c7', '#16a34a', '#9b59b6', '#e67e22', '#1abc9c']
        cores_tr = {tr: paleta_cores[i % len(paleta_cores)] for i, tr in enumerate(circuit.trafos_subestacao)}

        if res_padrao and res_gd:
            subtitulo = "Comparativo: Padrão (tracejado) vs Com GD (sólido)"
        elif res_padrao:
            subtitulo = "Cenário Padrão"
        else:
            subtitulo = "Cenário com GD"

        # ----------------------------------------------------
        # 1. Carregamento Ativo (MW) — Comparativo 24h
        # ----------------------------------------------------
        plt.figure(figsize=(11.5, 6.0))
        for tr in circuit.trafos_subestacao:
            tr_short = tr.split('-')[-1] if '-' in tr else tr
            cor = cores_tr.get(tr, '#333333')

            if res_padrao and tr in res_padrao.perfil_p_trafos_at:
                curva_p_padrao = [p / 1000.0 for p in res_padrao.perfil_p_trafos_at[tr]]
                n_pts = min(len(curva_p_padrao), len(config.vetor_tempo_horas))
                t_eixo = config.vetor_tempo_horas[:n_pts]
                lbl_padrao = f"{tr_short} (Padrão)" if res_gd else tr_short
                plt.plot(t_eixo, curva_p_padrao[:n_pts], label=lbl_padrao,
                         color=cor, linestyle='--', alpha=0.75, linewidth=1.7)

            if res_gd and tr in res_gd.perfil_p_trafos_at:
                curva_p_gd = [p / 1000.0 for p in res_gd.perfil_p_trafos_at[tr]]
                n_pts = min(len(curva_p_gd), len(config.vetor_tempo_horas))
                t_eixo = config.vetor_tempo_horas[:n_pts]
                lbl_gd = f"{tr_short} (Com GD)" if res_padrao else tr_short
                plt.plot(t_eixo, curva_p_gd[:n_pts], label=lbl_gd,
                         color=cor, linestyle='-', linewidth=2.2)

        plt.axhline(y=50.0, color='#e67e22', linestyle=':', linewidth=1.4, label='Capacidade Nominal (50 MVA)')
        plt.axhline(y=0.0, color='#111827', linestyle='-', linewidth=0.8, alpha=0.5)

        plt.title(f"Carregamento Diário Trafos AT (24h) — {subtitulo}\n{config.meta_simulacao}", fontsize=11, fontweight='bold')
        plt.xlabel("Hora do Dia (h)", fontsize=10)
        plt.ylabel("Potência Ativa (MW)", fontsize=10)
        plt.xticks(range(1, 25))
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.legend(loc='upper left', fontsize=8.5, ncol=2, framealpha=0.92)
        plt.tight_layout()

        out_mw = config.obter_caminho_saida(config.pasta_graf_subestacao, "carregamento_trafos_24h", "svg")
        plt.savefig(out_mw, format='svg')
        plt.close()

        # ----------------------------------------------------
        # 2. Tensão Secundária (pu) — Comparativo 24h
        # ----------------------------------------------------
        plt.figure(figsize=(11.5, 6.0))
        for tr in circuit.trafos_subestacao:
            tr_short = tr.split('-')[-1] if '-' in tr else tr
            cor = cores_tr.get(tr, '#333333')

            if res_padrao and tr in res_padrao.perfil_v_trafos_at:
                curva_v_padrao = res_padrao.perfil_v_trafos_at[tr]
                n_pts_v = min(len(curva_v_padrao), len(config.vetor_tempo_horas))
                t_eixo_v = config.vetor_tempo_horas[:n_pts_v]
                lbl_padrao = f"{tr_short} (Padrão)" if res_gd else tr_short
                plt.plot(t_eixo_v, curva_v_padrao[:n_pts_v], label=lbl_padrao,
                         color=cor, linestyle='--', alpha=0.75, linewidth=1.7)

            if res_gd and tr in res_gd.perfil_v_trafos_at:
                curva_v_gd = res_gd.perfil_v_trafos_at[tr]
                n_pts_v = min(len(curva_v_gd), len(config.vetor_tempo_horas))
                t_eixo_v = config.vetor_tempo_horas[:n_pts_v]
                lbl_gd = f"{tr_short} (Com GD)" if res_padrao else tr_short
                plt.plot(t_eixo_v, curva_v_gd[:n_pts_v], label=lbl_gd,
                         color=cor, linestyle='-', linewidth=2.2)

        plt.axhline(y=config.limite_sobretensao_pu, color='#e74c3c', linestyle='--', linewidth=1.2, label=f'Limite Superior Adequado ({config.limite_sobretensao_pu} pu)')
        plt.axhline(y=1.00, color='#7f8c8d', linestyle=':', linewidth=0.8, label='Tensão Nominal Base (1.00 pu)')
        plt.axhline(y=config.limite_subtensao_pu, color='#e74c3c', linestyle='--', linewidth=1.2, label=f'Limite Inferior Adequado ({config.limite_subtensao_pu} pu)')

        plt.title(f"Tensão Secundária Trafos AT (24h) — {subtitulo}\n{config.meta_simulacao}", fontsize=11, fontweight='bold')
        plt.xlabel("Hora do Dia (h)", fontsize=10)
        plt.ylabel("Tensão Secundária (pu)", fontsize=10)
        plt.xticks(range(1, 25))
        plt.ylim(0.91, 1.07)
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.legend(loc='lower left', fontsize=8.5, ncol=2, framealpha=0.92)
        plt.tight_layout()

        out_v = config.obter_caminho_saida(config.pasta_graf_subestacao, "tensao_trafos_24h", "svg")
        plt.savefig(out_v, format='svg')
        plt.close()
        print(f"  [OK] Gráficos Trafos AT salvos: {config.relpath(out_mw)} | {config.relpath(out_v)}")

    @classmethod
    def plot_estresse_alimentador(cls, resultados: Dict[str, ScenarioResult], circuit: CircuitManager, config: SimulationConfig) -> None:
        """Gera gráfico 24h evidenciando o fluxo reverso solar e as janelas de carga/descarga do BESS."""
        if 'com_gd' not in resultados or 'padrao' not in resultados:
            return

        res_gd = resultados['com_gd']
        res_padrao = resultados['padrao']

        info_sb = res_gd.info_sobrecarga or {}
        cod_alvo = info_sb.get('cod_alimentador')
        if not cod_alvo:
            cod_alvo, _ = circuit.resolver_alimentador(config.alimentador_alvo)

        info_ctmt = circuit.dict_ctmt_info.get(cod_alvo, {})
        nome_alvo = info_ctmt.get('nome', f'CTMT_{cod_alvo}')

        curva_padrao_kw = res_padrao.dados_ctmt.get(cod_alvo).curva_p_kw if res_padrao.dados_ctmt.get(cod_alvo) else []
        curva_gd_kw = res_gd.dados_ctmt.get(cod_alvo).curva_p_kw if res_gd.dados_ctmt.get(cod_alvo) else []

        if not curva_gd_kw or not curva_padrao_kw:
            return

        min_len = min(len(curva_padrao_kw), len(curva_gd_kw), len(config.vetor_tempo_horas))
        if min_len == 0:
            return

        p_padrao_mw = np.array(curva_padrao_kw[:min_len]) / 1000.0
        p_gd_mw = np.array(curva_gd_kw[:min_len]) / 1000.0
        t_eixo = np.array(config.vetor_tempo_horas[:min_len])

        p_rev_max_mw = max(0.0, -float(np.min(p_gd_mw)))
        e_rev_mwh = sum(-p * 0.25 for p in p_gd_mw if p < 0)

        plt.figure(figsize=(11, 5.8))

        # Curvas horárias
        plt.plot(t_eixo, p_padrao_mw, color='#4b5563', linestyle='--', linewidth=2.0, label='Demanda Padrão (Sem GD Extra)')
        plt.plot(t_eixo, p_gd_mw, color='#0284c7', linestyle='-', linewidth=2.4, label='Demanda com Sobrecarga Solar')

        # Limiar de fluxo reverso
        plt.axhline(0, color='#111827', linewidth=1.1, linestyle='-', alpha=0.75, label='Limiar de Fluxo Reverso (0 MW)')

        # Área sombreada: Janela de Carga do BESS (excedente solar diurno)
        where_reverso = p_gd_mw < 0
        if np.any(where_reverso):
            plt.fill_between(t_eixo, p_gd_mw, 0, where=where_reverso, color='#16a34a', alpha=0.28,
                             label=f'Janela Carga BESS (Excedente: {e_rev_mwh:.2f} MWh | Pico: {p_rev_max_mw:.2f} MW)')

        # Área sombreada: Janela de Descarga do BESS (pico noturno 18:30 às 21:30)
        plt.axvspan(18.5, 21.5, color='#f59e0b', alpha=0.18, label='Janela Descarga BESS (Horário de Pico: 18:30–21:30)')

        plt.title(f"Perfil Diário de Demanda e Fluxo Reverso — Alimentador {nome_alvo} ({cod_alvo})\nEstudo de Dimensionamento de BESS | {config.meta_simulacao}",
                  fontsize=11, fontweight='bold')
        plt.xlabel("Hora do Dia (h)", fontsize=10)
        plt.ylabel("Potência Ativa no Disjuntor (MW)", fontsize=10)
        plt.xticks(range(1, 25))
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.legend(loc='lower left', fontsize=8.5, framealpha=0.92)
        plt.tight_layout()

        out_svg = config.obter_caminho_saida(config.pasta_graf_subestacao, "perfil_estresse_alimentador_24h", "svg")
        plt.savefig(out_svg, format='svg')
        plt.close()
        print(f"  [OK] Gráfico Estresse Alimentador BESS salvo: {config.relpath(out_svg)}")

    @classmethod
    def plot_trafos_distribuicao_sobrecarga(cls, resultados: Dict[str, ScenarioResult], circuit: CircuitManager, config: SimulationConfig) -> None:
        """Gera gráficos 24h de potência e tensão para os transformadores com injeção de sobrecarga na BT."""
        if 'com_gd' not in resultados or 'padrao' not in resultados:
            return

        res_gd = resultados['com_gd']
        res_padrao = resultados['padrao']

        if not res_gd.curvas_trafos_bt:
            return

        for t_nome, dados_gd in res_gd.curvas_trafos_bt.items():
            dados_padrao = res_padrao.curvas_trafos_bt.get(t_nome, {})
            p_gd_kw = np.array(dados_gd.get('curva_p_kw', []))
            v_gd_pu = np.array(dados_gd.get('curva_v_pu', []))

            p_padrao_kw = np.array(dados_padrao.get('curva_p_kw', []))
            v_padrao_pu = np.array(dados_padrao.get('curva_v_pu', []))

            min_len_p = min(len(p_gd_kw), len(p_padrao_kw), len(config.vetor_tempo_horas))
            min_len_v = min(len(v_gd_pu), len(v_padrao_pu), len(config.vetor_tempo_horas))

            if min_len_p == 0 or min_len_v == 0:
                continue

            p_gd_kw = p_gd_kw[:min_len_p]
            p_padrao_kw = p_padrao_kw[:min_len_p]
            t_eixo_p = np.array(config.vetor_tempo_horas[:min_len_p])

            v_gd_pu = v_gd_pu[:min_len_v]
            v_padrao_pu = v_padrao_pu[:min_len_v]
            t_eixo_v = np.array(config.vetor_tempo_horas[:min_len_v])

            kva_nom = dados_gd.get('kva_nom', 112.0)
            barra_bt = dados_gd.get('barra_bt', '')

            # Cálculo do excedente reverso
            p_rev_max_kw = max(0.0, -float(np.min(p_gd_kw)))
            e_rev_kwh = sum(-p * 0.25 for p in p_gd_kw if p < 0)

            fig, (ax_p, ax_v) = plt.subplots(2, 1, figsize=(10.5, 7.8), sharex=True)

            # Painel 1: Potência Ativa e Fluxo Reverso (kW)
            ax_p.plot(t_eixo_p, p_padrao_kw, color='#4b5563', linestyle='--', linewidth=1.8, label='Demanda Padrão (Sem GD Extra)')
            ax_p.plot(t_eixo_p, p_gd_kw, color='#0284c7', linestyle='-', linewidth=2.2, label='Demanda com Sobrecarga Solar na BT')
            ax_p.axhline(0, color='#111827', linewidth=1.0, linestyle='-', alpha=0.7)
            ax_p.axhline(kva_nom, color='#ef4444', linestyle=':', linewidth=1.4, label=f'Capacidade Nominal (+{kva_nom:.0f} kVA)')
            ax_p.axhline(-kva_nom, color='#ef4444', linestyle=':', linewidth=1.4, label=f'Capacidade Reversa (-{kva_nom:.0f} kVA)')

            # Sombreado de fluxo reverso
            where_rev = p_gd_kw < 0
            if np.any(where_rev):
                ax_p.fill_between(t_eixo_p, p_gd_kw, 0, where=where_rev, color='#16a34a', alpha=0.25,
                                  label=f'Excedente Reverso: {e_rev_kwh:.1f} kWh | Pico: {p_rev_max_kw:.1f} kW')

            ax_p.set_title(f"Transformador de Distribuição {t_nome} ({kva_nom:.0f} kVA | Barra BT: {barra_bt})\n"
                           f"Curva 24h de Potência e Fluxo Reverso | {config.meta_simulacao}", fontsize=11, fontweight='bold')
            ax_p.set_ylabel("Potência Ativa Primária (kW)", fontsize=9.5)
            ax_p.grid(True, linestyle=':', alpha=0.6)
            ax_p.legend(loc='lower left', fontsize=8, framealpha=0.92)

            # Painel 2: Tensão no Barramento Secundário BT (pu)
            ax_v.plot(t_eixo_v, v_padrao_pu, color='#4b5563', linestyle='--', linewidth=1.8, label='Tensão BT Padrão (pu)')
            ax_v.plot(t_eixo_v, v_gd_pu, color='#8b5cf6', linestyle='-', linewidth=2.2, label='Tensão BT com Sobrecarga Solar (pu)')
            ax_v.axhline(config.limite_sobretensao_pu, color='#dc2626', linestyle='--', linewidth=1.2,
                         label=f'Limite Sobretensão ({config.limite_sobretensao_pu:.2f} pu)')
            ax_v.axhline(config.limite_subtensao_pu, color='#d97706', linestyle='--', linewidth=1.2,
                         label=f'Limite Subtensão ({config.limite_subtensao_pu:.2f} pu)')

            ax_v.set_title(f"Perfil de Tensão 24h no Secundário BT (Barra {barra_bt})", fontsize=10.5, fontweight='bold')
            ax_v.set_xlabel("Hora do Dia (h)", fontsize=9.5)
            ax_v.set_ylabel("Tensão (pu)", fontsize=9.5)
            ax_v.set_xticks(range(1, 25))
            ax_v.grid(True, linestyle=':', alpha=0.6)
            ax_v.legend(loc='lower right', fontsize=8, framealpha=0.92)

            plt.tight_layout()
            out_svg = config.obter_caminho_saida(config.pasta_graf_trafo_dist, f"estresse_{t_nome.lower()}_24h", "svg")
            plt.savefig(out_svg, format='svg')
            plt.close()
            print(f"  [OK] Gráfico Estresse Trafo BT {t_nome} salvo: {config.relpath(out_svg)}")

