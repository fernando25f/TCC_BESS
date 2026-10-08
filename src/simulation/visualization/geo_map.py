import os
import re
from typing import Dict, List, Tuple, Optional
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from matplotlib.collections import LineCollection
from src.simulation.config import SimulationConfig

class GeoMapRenderer:
    """Renderiza a topologia vetorial da rede elétrica adaptada ao escopo selecionado."""

    @classmethod
    def renderizar_mapa(cls, config: SimulationConfig) -> None:
        coords_map: Dict[str, Tuple[float, float]] = {}
        segs_mt: List[List[Tuple[float, float]]] = []
        segs_bt: List[List[Tuple[float, float]]] = []

        # Determina arquivos a analisar conforme estrutura hierárquica ou legada
        arquivos_dss = cls._obter_arquivos_dss_escopo(config)

        # 1. Carrega coordenadas globais legadas se existirem
        buscoords_file = os.path.join(config.pasta_modelo, "buscoords.dss")
        if not os.path.exists(buscoords_file):
            buscoords_file_legado = os.path.join(config.diretorio_raiz, "opendss", "buscoords.dss")
            if os.path.exists(buscoords_file_legado):
                buscoords_file = buscoords_file_legado

        if os.path.exists(buscoords_file):
            with open(buscoords_file, 'r', encoding='utf-8') as fb:
                for line in fb:
                    parts = line.strip().split(',')
                    if len(parts) >= 3:
                        try:
                            coords_map[parts[0].strip().upper()] = (float(parts[1]), float(parts[2]))
                        except ValueError:
                            continue

        # 2. Carrega coordenadas do circuito ativo na memória do OpenDSS (se inicializado)
        try:
            import opendssdirect as dss
            buses = dss.Circuit.AllBusNames()
            if buses and buses[0]:
                for b_nome in buses:
                    dss.Circuit.SetActiveBus(b_nome)
                    bx, by = dss.Bus.X(), dss.Bus.Y()
                    if bx != 0.0 or by != 0.0:
                        coords_map[b_nome.strip().upper()] = (float(bx), float(by))
        except Exception:
            pass

        # 3. PASSO 1: Varre todos os arquivos do escopo extraindo SetBusXY para o mapa de coordenadas
        for arq in arquivos_dss:
            if not os.path.exists(arq):
                continue
            with open(arq, 'r', encoding='utf-8') as f:
                for line in f:
                    linha = line.strip()
                    if linha.lower().startswith("setbusxy"):
                        m_bus = re.search(r'bus=([^\s]+)', linha, re.IGNORECASE)
                        m_x = re.search(r'x=([^\s]+)', linha, re.IGNORECASE)
                        m_y = re.search(r'y=([^\s]+)', linha, re.IGNORECASE)
                        if m_bus and m_x and m_y:
                            try:
                                b_id = m_bus.group(1).strip().strip('"\'').split('.')[0].upper()
                                coords_map[b_id] = (float(m_x.group(1)), float(m_y.group(1)))
                            except ValueError:
                                pass

        # 4. PASSO 2: Varre todos os arquivos do escopo extraindo os segmentos de linha (MT e BT)
        for arq in arquivos_dss:
            if not os.path.exists(arq):
                continue
            secao_bt = "linhas_bt" in arq.lower() or "ssdbt" in arq.lower()
            with open(arq, 'r', encoding='utf-8') as f:
                for line in f:
                    linha = line.strip()
                    linha_lower = linha.lower()

                    # Rastreia seções explicitamente marcadas no modelo hierárquico
                    if "! 6. linhas de baixa tensao" in linha_lower:
                        secao_bt = True
                    elif "! 2. linhas de media tensao" in linha_lower or "! 3. chaves seccionadoras" in linha_lower or "! 1. disjuntor" in linha_lower:
                        secao_bt = False

                    if linha_lower.startswith("new line."):
                        parts = linha.split()
                        b1 = next((p.split('=')[1].strip('"\'').split('.')[0].upper() for p in parts if p.lower().startswith('bus1=')), None)
                        b2 = next((p.split('=')[1].strip('"\'').split('.')[0].upper() for p in parts if p.lower().startswith('bus2=')), None)
                        if b1 and b2 and b1 in coords_map and b2 in coords_map:
                            if secao_bt:
                                segs_bt.append([coords_map[b1], coords_map[b2]])
                            else:
                                segs_mt.append([coords_map[b1], coords_map[b2]])

        if not segs_mt and not segs_bt:
            print("  [AVISO] Nenhum segmento de linha com coordenadas encontradas para o mapa.")
            return

        fig, ax = plt.subplots(figsize=(15, 11))
        ax.set_facecolor('#ffffff')
        fig.patch.set_facecolor('#ffffff')

        if segs_bt:
            ax.add_collection(LineCollection(segs_bt, colors='#16a34a', linewidths=0.35, alpha=0.4))
        if segs_mt:
            ax.add_collection(LineCollection(segs_mt, colors='#1d4ed8', linewidths=0.85, alpha=0.85))

        handles = []
        if segs_mt:
            handles.append(mlines.Line2D([], [], color='#1d4ed8', linewidth=2, label=f'Rede MT ({len(segs_mt):,} trechos)'))
        if segs_bt:
            handles.append(mlines.Line2D([], [], color='#16a34a', linewidth=1.5, label=f'Rede BT ({len(segs_bt):,} trechos)'))

        if handles:
            ax.legend(handles=handles, loc='upper left', fontsize=8.5, facecolor='white',
                      edgecolor='#cbd5e0', labelcolor='#1a202c', framealpha=0.95)

        info_escopo = f"Escopo: {config.escopo}" + (f" ({config.alvo})" if config.alvo else "")
        ax.set_title(f"Mapa Geográfico - {info_escopo}\n{config.meta_simulacao}",
                     color='#1a202c', fontsize=13, fontweight='bold', pad=12)
        ax.set_xlabel("Longitude", color='#2d3748', fontsize=9)
        ax.set_ylabel("Latitude", color='#2d3748', fontsize=9)
        ax.tick_params(colors='#2d3748', labelsize=8)
        for spine in ax.spines.values():
            spine.set_color('#cbd5e0')
        ax.autoscale_view()
        ax.set_aspect('equal')
        plt.tight_layout()

        sufixo_alvo = f"_{config.alvo.lower()}" if config.alvo else ""
        nome_arquivo = f"mapa_rede_{config.escopo.lower()}{sufixo_alvo}"
        out_png = config.obter_caminho_saida(config.pasta_graf_mapa_rede, nome_arquivo, "png")
        plt.savefig(out_png, dpi=300, facecolor='white', edgecolor='none')
        plt.close('all')
        print(f"  [OK] Mapa salvo: {config.relpath(out_png)}")

    @classmethod
    def _obter_arquivos_dss_escopo(cls, config: SimulationConfig) -> List[str]:
        pastas_tr = [os.path.join(config.pasta_modelo, d) for d in ["TR1", "TR2", "TR3", "TR4"] if os.path.isdir(os.path.join(config.pasta_modelo, d))]
        if not pastas_tr:
            # Estrutura legada plana
            return [
                os.path.join(config.pasta_modelo, "linhas_mt.dss"),
                os.path.join(config.pasta_modelo, "linhas_bt.dss")
            ]

        escopo = config.escopo.upper()
        arquivos: List[str] = []

        if escopo == "ALIMENTADOR":
            cod_alvo = str(config.alvo or config.alimentador_alvo).strip()
            for pasta_tr in pastas_tr:
                candidato = os.path.join(pasta_tr, f"CTMT_{cod_alvo}.dss")
                if os.path.exists(candidato):
                    arquivos.append(candidato)
                    break

        elif escopo == "TRAFO_AT":
            tr_alvo = str(config.alvo or "TR1").upper().replace("GOL-S-TRF-", "")
            pasta_alvo = os.path.join(config.pasta_modelo, tr_alvo)
            if os.path.isdir(pasta_alvo):
                for f in os.listdir(pasta_alvo):
                    if f.startswith("CTMT_") and f.endswith(".dss"):
                        arquivos.append(os.path.join(pasta_alvo, f))

        else:
            # SUBESTACAO completa
            for pasta_tr in pastas_tr:
                for f in os.listdir(pasta_tr):
                    if f.startswith("CTMT_") and f.endswith(".dss"):
                        arquivos.append(os.path.join(pasta_tr, f))

        return arquivos
