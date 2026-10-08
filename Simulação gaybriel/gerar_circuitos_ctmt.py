"""
================================================================================
GERADOR DE MODELOS OPENDSS INDIVIDUAIS POR ALIMENTADOR (CTMT)
Base de Dados: Subestação Goiânia Leste (BDGD)
================================================================================
Este script converte os alimentadores de média tensão em arquivos OpenDSS (.dss)
individuais e 100% autocontidos. Cada alimentador gera um único arquivo .dss
contendo todos os seus componentes (trafo da SE, disjuntor, chaves, linhas MT/BT,
trafos MT/BT, cargas com Fator de Demanda e coordenadas geográficas).
================================================================================
"""

import os
import sys
import time
import math
import re
import argparse
import pandas as pd

DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.join(DIRETORIO_ATUAL, 'dados_goiania_leste')
DICT_FOLDER = os.path.join(DIRETORIO_ATUAL, 'dicionarios_bdgd')
OUTPUT_FOLDER = os.path.join(DIRETORIO_ATUAL, 'circuitos_ctmt')

FATOR_DEMANDA = 0.1

MAPA_FASES = {
    'ABC': ('.1.2.3', 3, 'delta'),
    'A': ('.1', 1, 'wye'),
    'B': ('.2', 1, 'wye'),
    'C': ('.3', 1, 'wye'),
    'AB': ('.1.2', 2, 'delta'),
    'BC': ('.2.3', 2, 'delta'),
    'CA': ('.3.1', 2, 'delta'),
    'ABCN': ('.1.2.3.0', 3, 'delta'),
    'AN': ('.1.0', 1, 'wye'),
    'BN': ('.2.0', 1, 'wye'),
    'CN': ('.3.0', 1, 'wye'),
    'ABN': ('.1.2.0', 3, 'delta'),
    'BCN': ('.2.3.0', 3, 'delta'),
    'CAN': ('.3.1.0', 3, 'delta'),
    'N': ('.0', 1, 'wye'),
}


def sanitizar_nome(nome):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', str(nome).strip())


def parse_wkt_line(wkt):
    if pd.isna(wkt):
        return []
    return re.findall(r'([-]?\d+\.\d+)\s+([-]?\d+\.\d+)', str(wkt))


class GeradorAlimentadoresDSS:
    def __init__(self, input_dir=INPUT_FOLDER, dict_dir=DICT_FOLDER, output_dir=OUTPUT_FOLDER):
        self.input_dir = input_dir
        self.dict_dir = dict_dir
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        print('======================================================================')
        print('CARREGANDO BASES DA BDGD PARA CONVERSÃO MODULAR...')
        print('======================================================================')

        self.ctmt = pd.read_csv(os.path.join(self.input_dir, '02_CTMT_alimentadores.csv'))
        self.untrat = pd.read_csv(os.path.join(self.input_dir, '03a_UNTRAT_trafos_subestacao.csv'))
        self.eqtrat = pd.read_csv(os.path.join(self.input_dir, '03b_EQTRAT_dados_eletricos_trafos_sub.csv'))

        self.tten = pd.read_csv(os.path.join(self.dict_dir, 'TTEN.csv'))
        self.dict_ten = dict(zip(self.tten['COD_ID'], self.tten['TEN'] / 1000.0))

        self.segcon = pd.read_csv(os.path.join(self.input_dir, '06_SEGCON_condutores.csv'))
        self.dict_r1 = dict(zip(self.segcon['COD_ID'], self.segcon['R1']))
        self.dict_x1 = dict(zip(self.segcon['COD_ID'], self.segcon['X1']))
        self.dict_cnom = dict(zip(self.segcon['COD_ID'], self.segcon['CNOM']))

        self.eqtrmt = pd.read_csv(os.path.join(self.input_dir, '07b_EQTRMT_dados_eletricos_trafos_dist.csv'))
        self.dict_eq_r = dict(zip(self.eqtrmt['UNI_TR_MT'], self.eqtrmt['R']))
        self.dict_eq_xhl = dict(zip(self.eqtrmt['UNI_TR_MT'], self.eqtrmt['XHL']))
        self.dict_eq_ten_pri = dict(zip(self.eqtrmt['UNI_TR_MT'], self.eqtrmt['TEN_PRI']))
        self.dict_eq_ten_sec = dict(zip(self.eqtrmt['UNI_TR_MT'], self.eqtrmt['TEN_SEC']))

        self.ssdmt = pd.read_csv(os.path.join(self.input_dir, '04_SSDMT_linhas_MT.csv'))
        self.ssdbt = pd.read_csv(os.path.join(self.input_dir, '05_SSDBT_linhas_BT.csv'))
        self.untrmt = pd.read_csv(os.path.join(self.input_dir, '07a_UNTRMT_trafos_distribuicao.csv'))
        self.unsemt = pd.read_csv(os.path.join(self.input_dir, '15_UNSEMT_chaves_seccionadoras.csv'))
        self.uncrmt = pd.read_csv(os.path.join(self.input_dir, '13_UNCRMT_capacitores_MT.csv'))

        self.crvcrg = pd.read_csv(os.path.join(self.input_dir, '10_CRVCRG_curvas_de_carga.csv'))

        self.ucbt = pd.read_csv(
            os.path.join(self.input_dir, '08_UCBT_consumidores_BT.csv'),
            usecols=['COD_ID', 'PAC', 'PN_CON', 'UNI_TR_MT', 'FAS_CON', 'TEN_FORN', 'CAR_INST', 'TIP_CC', 'ARE_LOC', 'CTMT']
        )
        self.ucmt = pd.read_csv(
            os.path.join(self.input_dir, '09_UCMT_consumidores_MT.csv'),
            usecols=['COD_ID', 'PAC', 'PN_CON', 'FAS_CON', 'TEN_FORN', 'CAR_INST', 'TIP_CC', 'ARE_LOC', 'CTMT']
        )

        print('[OK] Todas as bases foram carregadas com sucesso na memória.\n')

    def listar_alimentadores(self):
        resumo = []
        for _, row in self.ctmt.iterrows():
            cid = int(row['COD_ID'])
            nome = str(row['NOME'])
            trafo_at = str(row['UNI_TR_AT'])

            n_ucbt = (self.ucbt['CTMT'] == cid).sum()
            n_rural = ((self.ucbt['CTMT'] == cid) & (self.ucbt['ARE_LOC'] == 'NU')).sum()
            n_ucmt = (self.ucmt['CTMT'] == cid).sum()
            n_trafo = (self.untrmt['CTMT'] == cid).sum()
            n_linhas_mt = (self.ssdmt['CTMT'] == cid).sum()
            pct_rural = (n_rural / n_ucbt * 100.0) if n_ucbt > 0 else 0.0

            resumo.append({
                'COD_ID': cid,
                'NOME': nome,
                'TRAFO_AT': trafo_at,
                'UCBT': n_ucbt,
                'UCMT': n_ucmt,
                'TRAFOS_MT': n_trafo,
                'LINHAS_MT': n_linhas_mt,
                'PCT_RURAL': pct_rural
            })
        df_res = pd.DataFrame(resumo)
        return df_res

    def gerar_alimentador(self, cod_id, fd=FATOR_DEMANDA):
        cod_id = int(cod_id)
        f_match = self.ctmt[self.ctmt['COD_ID'] == cod_id]
        if f_match.empty:
            print(f"[ERRO] Alimentador com COD_ID {cod_id} não encontrado na tabela 02_CTMT.")
            return None

        f_info = f_match.iloc[0]
        nome_alim = sanitizar_nome(f_info['NOME'])
        nome_arquivo = f"CTMT_{cod_id}_{nome_alim}.dss"
        caminho_dss = os.path.join(self.output_dir, nome_arquivo)

        tr_match = self.untrat[self.untrat['COD_ID'] == f_info['UNI_TR_AT']]
        if tr_match.empty:
            print(f"[ERRO] Transformador AT {f_info['UNI_TR_AT']} não encontrado na tabela 03a_UNTRAT.")
            return None

        tr_info = tr_match.iloc[0]
        eq_info = self.eqtrat[self.eqtrat['COD_ID'] == f_info['UNI_TR_AT']].iloc[0]

        ssdmt_f = self.ssdmt[self.ssdmt['CTMT'] == cod_id]
        ssdbt_f = self.ssdbt[self.ssdbt['CTMT'] == cod_id]
        untrmt_f = self.untrmt[self.untrmt['CTMT'] == cod_id]
        unsemt_f = self.unsemt[self.unsemt['CTMT'] == cod_id]
        uncrmt_f = self.uncrmt[self.uncrmt['CTMT'] == cod_id]
        ucbt_f = self.ucbt[self.ucbt['CTMT'] == cod_id].copy()
        ucmt_f = self.ucmt[self.ucmt['CTMT'] == cod_id].copy().drop_duplicates(subset=['COD_ID'])

        with open(caminho_dss, 'w', encoding='utf-8') as f:
            f.write('! ==============================================================================\n')
            f.write('! OPENDSS - MODELO INDIVIDUAL DE ALIMENTADOR DE MÉDIA TENSÃO\n')
            f.write(f"! Alimentador: {f_info['NOME']} (COD_ID: {cod_id})\n")
            f.write(f"! Subestação: {f_info['SUB']} | Trafo SE: {f_info['UNI_TR_AT']} ({tr_info['POT_NOM']} MVA)\n")
            f.write(f"! Fator de Demanda aplicado sobre CAR_INST: {fd * 100:.1f}%\n")
            f.write('! ==============================================================================\n\n')

            f.write('clear\n')
            f.write(f"new circuit.CTMT_{cod_id} basekv=230 bus1={tr_info['BARR_1']} pu=1.05 phases=3\n\n")

            # --- 1. TRANSFORMADOR DA SUBESTAÇÃO (AT/MT) ---
            f.write('! --- 1. TRANSFORMADOR DA SUBESTAÇÃO (AT/MT) ---\n')
            per_fer = eq_info['PER_FER']
            per_tot = eq_info['PER_TOT']
            kv1 = self.dict_ten.get(eq_info['TEN_PRI'], 230.0)
            kv2 = self.dict_ten.get(eq_info['TEN_SEC'], 13.8)
            pot_kva = tr_info['POT_NOM'] * 1000.0

            f.write(f"new transformer.{tr_info['COD_ID']} phases=3 xhl=4.5 windings=2 %loadloss={per_tot} %noloadloss={per_fer} kva={pot_kva}\n")
            f.write(f"~ wdg=1 bus={tr_info['BARR_1']} conn=delta kv={kv1}\n")
            f.write(f"~ wdg=2 bus={tr_info['BARR_2']} conn=wye kv={kv2}\n\n")

            # --- 2. DISJUNTOR DA CABEÇA DO ALIMENTADOR (MT) ---
            f.write('! --- 2. DISJUNTOR DA CABEÇA DO ALIMENTADOR (MT) ---\n')
            f.write(f"new line.DJ_{f_info['COD_ID']} phases=3 bus1={f_info['BARR']} bus2={f_info['PAC_INI']} switch=y r1=1e-4 x1=1e-4 length=0.001 units=km\n\n")

            # --- 3. CHAVES SECCIONADORAS (MT) ---
            f.write('! --- 3. CHAVES SECCIONADORAS (MT) ---\n')
            for row in unsemt_f.itertuples():
                f.write(f"new line.SC_{row.COD_ID} phases=3 bus1={row.PAC_1} bus2={row.PAC_2} switch=y r1=1e-4 x1=1e-4 length=0.001 units=km\n")
                if row.P_N_OPE == 'A':
                    f.write(f"open line.SC_{row.COD_ID} 1\n")
            f.write('\n')

            # --- 4. LINHAS DE MÉDIA TENSÃO (MT) ---
            f.write('! --- 4. LINHAS DE MÉDIA TENSÃO (MT) ---\n')
            for row in ssdmt_f.itertuples():
                fase_info = MAPA_FASES.get(row.FAS_CON, ('.1.2.3', 3, 'delta'))
                barra1 = str(row.PAC_1) + fase_info[0]
                barra2 = str(row.PAC_2) + fase_info[0]
                r1 = self.dict_r1.get(row.TIP_CND, 0.5)
                x1 = self.dict_x1.get(row.TIP_CND, 0.4)
                comp = max(0.001, round(row.COMP / 1000.0, 6))
                cnom = self.dict_cnom.get(row.TIP_CND, 200)
                f.write(f"new line.{row.COD_ID} phases={fase_info[1]} bus1={barra1} bus2={barra2} r1={r1} x1={x1} length={comp} units=km normamps={cnom}\n")
            f.write('\n')

            # --- 5. BANCOS DE CAPACITORES (MT) ---
            if not uncrmt_f.empty:
                f.write('! --- 5. BANCOS DE CAPACITORES (MT) ---\n')
                tpotrtv_path = os.path.join(self.dict_dir, 'TPOTRTV.csv')
                dict_potrtv = {}
                if os.path.exists(tpotrtv_path):
                    tpotrtv = pd.read_csv(tpotrtv_path)
                    dict_potrtv = dict(zip(tpotrtv['COD_ID'], tpotrtv['POT']))

                for row in uncrmt_f.itertuples():
                    fases_info = MAPA_FASES.get(row.FAS_CON, ('.1.2.3', 3, 'wye'))
                    barra1 = str(row.PAC_1).lstrip('R') + fases_info[0]
                    kvar = dict_potrtv.get(row.POT_NOM, 0.0)
                    f.write(f"new capacitor.{row.COD_ID} phases={fases_info[1]} bus1={barra1} conn=wye kv=13.8 kvar={kvar}\n")
                f.write('\n')

            # --- 6. TRANSFORMADORES DE DISTRIBUIÇÃO (MT/BT) ---
            f.write('! --- 6. TRANSFORMADORES DE DISTRIBUIÇÃO (MT/BT) ---\n')
            for row in untrmt_f.itertuples():
                fases_p = MAPA_FASES.get(row.FAS_CON_P, ('.1.2.3', 3, 'delta'))
                fases_s = MAPA_FASES.get(row.FAS_CON_S, ('.1.2.3.0', 3, 'wye'))
                phases = fases_p[1]
                conn1 = fases_p[2]
                barra1 = str(row.PAC_1) + fases_p[0]
                barra2 = str(row.PAC_2) + fases_s[0]

                r = self.dict_eq_r.get(row.COD_ID, 1.0)
                xhl = self.dict_eq_xhl.get(row.COD_ID, 4.0)
                kv1 = self.dict_ten.get(self.dict_eq_ten_pri.get(row.COD_ID, 49), 13.8)
                kv2 = self.dict_ten.get(self.dict_eq_ten_sec.get(row.COD_ID, 1), 0.38)
                kva = row.POT_NOM

                if phases == 3 and kv1 < 10.0:
                    kv1 = round(kv1 * math.sqrt(3), 2)

                f.write(f"new transformer.UNTRMT_{row.COD_ID} phases={phases} windings=2 %r={r} xhl={xhl} kva={kva}\n")
                f.write(f"~ wdg=1 bus={barra1} conn={conn1} kv={kv1}\n")
                f.write(f"~ wdg=2 bus={barra2} conn=wye kv={kv2}\n")
            f.write('\n')

            # --- 7. LINHAS DE BAIXA TENSÃO (BT) ---
            f.write('! --- 7. LINHAS DE BAIXA TENSÃO (BT) ---\n')
            for row in ssdbt_f.itertuples():
                fase_info = MAPA_FASES.get(row.FAS_CON, ('.1.2.3.0', 3, 'delta'))
                barra1 = str(row.PAC_1) + fase_info[0]
                barra2 = str(row.PAC_2) + fase_info[0]
                r1 = min(5.0, self.dict_r1.get(row.TIP_CND, 0.5))
                x1 = min(2.0, self.dict_x1.get(row.TIP_CND, 0.4))
                comp = max(0.001, round(row.COMP / 1000.0, 6))
                cnom = self.dict_cnom.get(row.TIP_CND, 100)
                f.write(f"new line.{row.COD_ID} phases={fase_info[1]} bus1={barra1} bus2={barra2} r1={r1} x1={x1} length={comp} units=km normamps={cnom}\n")
            f.write('\n')

            # --- 8. CURVAS DE CARGA (LOADSHAPES DIÁRIAS) ---
            f.write('! --- 8. CURVAS DE CARGA (LOADSHAPES DIÁRIAS) ---\n')
            cols_pot = [f"POT_{i:02d}" for i in range(1, 97)]
            for row in self.crvcrg[self.crvcrg['TIP_DIA'] == 'DU'].itertuples():
                nome = row.COD_ID
                max_pot = max(getattr(row, c) for c in cols_pot)
                divisor = 100.0 if max_pot > 5.0 else 1.0
                tx = ' '.join(f"{round(getattr(row, c) / divisor, 4)}" for c in cols_pot)
                f.write(f"new loadshape.{nome} npts=96 interval=0.25 mult=({tx})\n")
            f.write('\n')

            # --- 9. CARGAS DE BAIXA TENSÃO (BT) ---
            f.write(f"! --- 9. CARGAS DE BAIXA TENSÃO (BT) [Fator de Demanda = {fd * 100:.1f}%] ---\n")
            pacs_ssdbt = set(ssdbt_f['PAC_1'].dropna().astype(str)).union(set(ssdbt_f['PAC_2'].dropna().astype(str)))
            pacs_untrmt_sec = set(untrmt_f['PAC_2'].dropna().astype(str))
            pacs_validos_bt = pacs_ssdbt.union(pacs_untrmt_sec)
            mapa_trafo_sec = dict(zip(untrmt_f['COD_ID'].astype(str), untrmt_f['PAC_2'].astype(str)))

            cargas_bt_adicionadas = 0
            for row in ucbt_f.itertuples():
                pac_limpo = str(row.PAC).lstrip('R')
                pn_con = str(row.PN_CON)
                uni_tr_mt = str(row.UNI_TR_MT)
                chave_composta = f"{pn_con}_{uni_tr_mt}"

                barra_calc = None
                if chave_composta in pacs_validos_bt:
                    barra_calc = chave_composta
                elif pac_limpo in pacs_validos_bt:
                    barra_calc = pac_limpo
                elif uni_tr_mt in mapa_trafo_sec and mapa_trafo_sec[uni_tr_mt] in pacs_validos_bt:
                    barra_calc = mapa_trafo_sec[uni_tr_mt]

                if not barra_calc:
                    continue

                fase_info = MAPA_FASES.get(row.FAS_CON, ('.1.2.3.0', 3, 'delta'))
                barra = barra_calc + fase_info[0]
                phases = fase_info[1]
                kv = self.dict_ten.get(row.TEN_FORN, 0.22)
                kw = max(0.01, round(float(row.CAR_INST) * fd, 3))
                loadshape = row.TIP_CC
                f.write(f"new load.UCBT_{row.COD_ID} phases={phases} model=1 bus={barra} kv={kv} kw={kw} daily={loadshape} vminpu=0.85\n")
                cargas_bt_adicionadas += 1
            f.write('\n')

            # --- 10. CARGAS DE MÉDIA TENSÃO (MT) ---
            f.write(f"! --- 10. CARGAS DE MÉDIA TENSÃO (MT) [Fator de Demanda = {fd * 100:.1f}%] ---\n")
            pacs_validos_mt = set(ssdmt_f['PAC_1'].astype(str)) | set(ssdmt_f['PAC_2'].astype(str))
            cargas_mt_adicionadas = 0
            for row in ucmt_f.itertuples():
                pac = str(row.PAC).lstrip('R')
                pn_con = str(row.PN_CON)
                barra_calc = None
                if pn_con in pacs_validos_mt:
                    barra_calc = pn_con
                elif pac in pacs_validos_mt:
                    barra_calc = pac

                if not barra_calc:
                    continue

                fase_info = MAPA_FASES.get(row.FAS_CON, ('.1.2.3', 3, 'delta'))
                barra = barra_calc + fase_info[0]
                phases = fase_info[1]
                kv = self.dict_ten.get(row.TEN_FORN, 13.8)
                kw = max(0.1, round(float(row.CAR_INST) * fd, 3))
                loadshape = row.TIP_CC
                f.write(f"new load.UCMT_{row.COD_ID} phases={phases} model=1 bus={barra} kv={kv} kw={kw} daily={loadshape} vminpu=0.85\n")
                cargas_mt_adicionadas += 1
            f.write('\n')

            # --- 11. BASES DE TENSÃO E CÁLCULO DE BASES ---
            f.write('! --- 11. BASES DE TENSÃO E CÁLCULO DE BASES ---\n')
            f.write('set voltagebases=[230.0, 13.8, 0.38, 0.22]\n')
            f.write('calcvoltagebases\n\n')

            # --- 12. COORDENADAS GEOGRÁFICAS DAS BARRAS (BUSCOORDS) ---
            f.write('! --- 12. COORDENADAS GEOGRÁFICAS DAS BARRAS (BUSCOORDS) ---\n')
            coords_map = {}
            for df_linhas in (ssdmt_f, ssdbt_f):
                for row in df_linhas.itertuples():
                    p1 = str(row.PAC_1).lstrip('R')
                    p2 = str(row.PAC_2).lstrip('R')
                    pts = parse_wkt_line(row.geometria_wkt)
                    if len(pts) >= 2:
                        if p1 not in coords_map:
                            coords_map[p1] = pts[0]
                        if p2 not in coords_map:
                            coords_map[p2] = pts[-1]

            for pac, (lon, lat) in coords_map.items():
                f.write(f"setbusxy bus={pac} x={lon} y={lat}\n")

        print(f"  [OK] Gerado com sucesso: '{nome_arquivo}'")
        print(f"       -> Trafo AT: {f_info['UNI_TR_AT']} | Disjuntor: DJ_{cod_id}")
        print(f"       -> Linhas MT: {len(ssdmt_f)} | Linhas BT: {len(ssdbt_f)}")
        print(f"       -> Trafos MT: {len(untrmt_f)} | Chaves MT: {len(unsemt_f)}")
        print(f"       -> Cargas BT: {cargas_bt_adicionadas} | Cargas MT: {cargas_mt_adicionadas}")
        print(f"       -> Barras mapeadas (Buscoords): {len(coords_map)}")

        return caminho_dss

    def gerar_todos(self, fd=FATOR_DEMANDA):
        print('======================================================================')
        print('EXPORTANDO TODOS OS 27 ALIMENTADORES EM ARQUIVOS DSS INDIVIDUAIS...')
        print(f"Fator de Demanda selecionado: {fd * 100:.1f}%")
        print(f"Pasta de destino: '{self.output_dir}'")
        print('======================================================================')

        gerados = []
        for idx, row in self.ctmt.iterrows():
            cid = int(row['COD_ID'])
            nome = row['NOME']
            print(f"\n[{idx + 1:02d}/27] Alimentador: {nome} (COD_ID: {cid})")
            caminho = self.gerar_alimentador(cid, fd=fd)
            if caminho:
                gerados.append(caminho)

        print('\n======================================================================')
        print(f"[CONCLUÍDO] Total de alimentadores exportados: {len(gerados)} de {len(self.ctmt)}.")
        print(f"Todos os circuitos foram salvos em: '{self.output_dir}'.")
        print('======================================================================')
        return gerados


def main():
    t_inicio = time.time()
    parser = argparse.ArgumentParser(
        description='Gera modelos OpenDSS individuais por alimentador (CTMT) da BDGD em arquivos únicos.'
    )
    parser.add_argument('--ctmt', type=int, help='COD_ID do alimentador a ser gerado (ex: 5001994)')
    parser.add_argument('--todos', action='store_true', help='Gera todos os 27 alimentadores de uma vez')
    parser.add_argument('--listar', action='store_true', help='Lista todos os alimentadores e destaca os urbanos')
    parser.add_argument('--fd', type=float, default=FATOR_DEMANDA, help='Fator de Demanda (padrão: 0.25 = 25%%)')

    args = parser.parse_args()
    gerador = GeradorAlimentadoresDSS()

    if args.listar:
        df = gerador.listar_alimentadores()
        print('\nRESUMO DOS ALIMENTADORES DA SUBESTAÇÃO GOIÂNIA LESTE:')
        print(df.to_string(index=False))
        print('\nAlimentadores 100% Urbanos (0% Rural):')
        df_urb = df[df['PCT_RURAL'] == 0.0].sort_values('UCBT')
        print(df_urb[['COD_ID', 'NOME', 'TRAFO_AT', 'UCBT', 'UCMT', 'TRAFOS_MT', 'LINHAS_MT']].to_string(index=False))
        return

    if args.todos:
        gerador.gerar_todos(fd=args.fd)
    elif args.ctmt:
        print(f"Gerando alimentador específico: COD_ID {args.ctmt}")
        gerador.gerar_alimentador(args.ctmt, fd=args.fd)
    else:
        print('Nenhum argumento fornecido.')
        print('Gerando todos os 27 alimentadores automaticamente (padrão com FD = 25%)...')
        gerador.gerar_todos(fd=args.fd)

    tempo_total = time.time() - t_inicio
    minutos = int(tempo_total // 60)
    segundos = tempo_total % 60
    print("\n" + "=" * 70)
    if minutos > 0:
        print(f"[TEMPO DE EXECUÇÃO] Geração concluída em {minutos}m {segundos:.2f}s ({tempo_total:.2f} s)!")
    else:
        print(f"[TEMPO DE EXECUÇÃO] Geração concluída em {segundos:.2f} segundos!")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    main()
