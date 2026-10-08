"""
Script paralelo para conversão direta de Geodatabase (GDB) da BDGD para OpenDSS
utilizando a biblioteca oficial bdgd2opendss (desenvolvida por Paulo Radatz).

Permite filtrar por Subestação específica (ex: Goiânia Leste) ou por lista de
alimentadores, evitando a conversão desnecessária de todos os circuitos do estado.
"""

import os
import sys
import time
import argparse
from typing import Optional, List
import pyogrio

def parse_args():
    parser = argparse.ArgumentParser(description="Conversor direto GDB para OpenDSS via bdgd2opendss")
    parser.add_argument(
        "--gdb",
        type=str,
        default="ENEL_GO-30-04-2023.gdb",
        help="Caminho do arquivo Geodatabase (.gdb)"
    )
    parser.add_argument(
        "--saida",
        type=str,
        default="modelo_bdgd2opendss",
        help="Diretório de saída para os arquivos OpenDSS gerados"
    )
    parser.add_argument(
        "--subestacao",
        type=str,
        default="5001462",
        help="Código ou nome da subestação alvo (padrão: 5001462 - Goiânia Leste)"
    )
    parser.add_argument(
        "--alimentadores",
        type=str,
        default=None,
        help="Lista de alimentadores separados por vírgula (ex: 5002188,5002409). Sobrescreve --subestacao"
    )
    parser.add_argument(
        "--todos-alimentadores",
        action="store_true",
        help="Converte TODOS os alimentadores do GDB estadual (atenção: processo demorado)"
    )
    parser.add_argument(
        "--listar-alimentadores",
        action="store_true",
        help="Apenas lista os alimentadores encontrados no filtro e encerra"
    )
    return parser.parse_args()

def verificar_instalacao():
    """Valida se o pacote bdgd2opendss está instalado no ambiente."""
    try:
        import bdgd2opendss
        return bdgd2opendss
    except ImportError:
        print("\n[ERRO] O pacote 'bdgd2opendss' não está instalado no ambiente Python.")
        print("Para instalar, execute o comando:")
        print("    pip install bdgd2opendss\n")
        sys.exit(1)

def obter_alimentadores_subestacao(caminho_gdb: str, subestacao_alvo: str) -> List[str]:
    """Lê a camada CTMT do GDB e extrai os alimentadores pertencentes à subestação."""
    sub_str = str(subestacao_alvo).strip().upper()
    df_ctmt = pyogrio.read_dataframe(
        caminho_gdb,
        layer="CTMT",
        columns=["COD_ID", "SUB", "NOME"]
    )
    mask = (
        (df_ctmt['SUB'].astype(str).str.strip().str.upper() == sub_str) |
        (df_ctmt['NOME'].astype(str).str.strip().str.upper().str.contains(sub_str, na=False))
    )
    alimentadores = df_ctmt.loc[mask, 'COD_ID'].astype(str).tolist()
    return alimentadores

def converter_gdb_para_dss(
    caminho_gdb: str,
    pasta_saida: str,
    subestacao: Optional[str] = "5001462",
    alimentadores_especificos: Optional[str] = None,
    todos_alimentadores: bool = False,
    somente_listar: bool = False
):
    """
    Executa a conversão filtrando pela subestação selecionada ou por alimentadores.
    """
    bdgd2opendss = verificar_instalacao()

    caminho_gdb_abs = os.path.abspath(caminho_gdb)
    if not os.path.exists(caminho_gdb_abs):
        raise FileNotFoundError(f"Arquivo Geodatabase não encontrado no caminho: {caminho_gdb_abs}")

    os.makedirs(pasta_saida, exist_ok=True)
    pasta_saida_abs = os.path.abspath(pasta_saida)

    print("-" * 70)
    print("CONVERSOR DIRETO GDB -> OpenDSS (via bdgd2opendss)")
    print("-" * 70)
    print(f"  * GDB de entrada: {caminho_gdb_abs}")
    print(f"  * Pasta de saida: {pasta_saida_abs}")

    # Determinacao da lista de alimentadores alvo
    if todos_alimentadores:
        print("  * Modo: TODOS OS ALIMENTADORES DO ESTADO")
        all_feeders_flag = True
        lst_feeders_target = None
    elif alimentadores_especificos:
        lst_feeders_target = [f.strip() for f in alimentadores_especificos.split(",") if f.strip()]
        all_feeders_flag = False
        print(f"  * Modo: Alimentadores especificos ({len(lst_feeders_target)} informados): {lst_feeders_target}")
    else:
        print(f"  * Modo: Filtrando por Subestacao: {subestacao}")
        lst_feeders_target = obter_alimentadores_subestacao(caminho_gdb_abs, subestacao)
        all_feeders_flag = False
        print(f"  [OK] {len(lst_feeders_target)} alimentadores encontrados para a subestacao {subestacao}.")

    if not all_feeders_flag and not lst_feeders_target:
        print(f"\n[AVISO] Nenhum alimentador localizado para a subestação '{subestacao}'.")
        return

    if somente_listar:
        print("\nLista de Alimentadores Selecionados:")
        for idx, cod in enumerate(lst_feeders_target, 1):
            print(f"  {idx:02d}: {cod}")
        return

    # Execução da conversão
    print(f"\n[INÍCIO] Iniciando conversão de {len(lst_feeders_target) if lst_feeders_target else 'todos os'} alimentador(es)...")
    t0 = time.time()
    try:
        bdgd2opendss.run(
            bdgd_file_path=caminho_gdb_abs,
            output_folder=pasta_saida_abs,
            all_feeders=all_feeders_flag,
            lst_feeders=lst_feeders_target
        )
        duracao = time.time() - t0
        print(f"\n[OK] Conversão concluída com sucesso em {duracao:.2f}s!")
        print(f"  Arquivos OpenDSS gravados em: {pasta_saida_abs}")
    except Exception as e:
        print(f"\n[FALHA] Erro durante a conversão do GDB: {e}")
        raise

def main():
    args = parse_args()
    try:
        converter_gdb_para_dss(
            caminho_gdb=args.gdb,
            pasta_saida=args.saida,
            subestacao=args.subestacao,
            alimentadores_especificos=args.alimentadores,
            todos_alimentadores=args.todos_alimentadores,
            somente_listar=args.listar_alimentadores
        )
    except KeyboardInterrupt:
        print("\n[AVISO] Processo interrompido pelo usuário.")
    except Exception as err:
        print(f"\n[ERRO CRÍTICO] {err}")
        sys.exit(1)

if __name__ == "__main__":
    main()
