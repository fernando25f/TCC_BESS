import os
import pandas as pd
import geopandas as gpd

class GeometryProcessor:
    """Converte geometrias espaciais para colunas tabulares e persiste DataFrames em CSV."""

    @staticmethod
    def processar_e_salvar_csv(df: pd.DataFrame, caminho_saida: str, descricao: str) -> pd.DataFrame:
        """
        Converte Point em lat/lon e geometrias lineares/poligonais em WKT,
        removendo a coluna de geometria do GeoPandas para compatibilidade tabular.
        """
        df_export = df.copy()

        if isinstance(df_export, gpd.GeoDataFrame) and "geometry" in df_export.columns:
            if df_export.geometry is not None and not df_export.geometry.is_empty.all():
                tipo_geom = df_export.geometry.dropna().iloc[0].geom_type if not df_export.geometry.dropna().empty else None
                if tipo_geom == "Point":
                    df_export["longitude"] = df_export.geometry.x
                    df_export["latitude"] = df_export.geometry.y
                else:
                    df_export["geometria_wkt"] = df_export.geometry.to_wkt()

            df_export = pd.DataFrame(df_export.drop(columns=["geometry"]))

        df_export.to_csv(caminho_saida, index=False, encoding="utf-8-sig")
        nome_arquivo = os.path.basename(caminho_saida)
        print(f"   ✔ {descricao}: {len(df_export)} registros → {nome_arquivo}")
        return df_export
