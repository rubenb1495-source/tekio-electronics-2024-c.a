"""
Script de limpieza y normalización de SKUs para la migración de Tekio Electronics.
Convención del proyecto: Todo en español.

Uso:
    python normalizar_skus_tekio.py --entrada catalogo.xlsx --hoja Listas --salida ./salida_limpia
    python normalizar_skus_tekio.py --entrada ventas.csv --columna-sku "Código" --salida ./salida_limpia
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple

import openpyxl
import pandas as pd

# =============================================================================
# 1. MAPA DE ALIAS CONOCIDOS (DETECTADOS EN GOOGLE DRIVE DE TEKIO ELECTRONICS)
#    Clave: SKU ya normalizado (mayúsculas, sin espacios)
#    Valor: SKU canónico definitivo para la nueva base de datos
# =============================================================================
ALIAS_SKU_CONOCIDOS: Dict[str, str] = {
    "BAT-DELL33YDH": "BAT-33YDH",
    "BAT-DELL6MT4T": "BAT-6MT4T",
    # Agrega aquí nuevos alias confirmados tras revisar el reporte de sospechosos
}


def limpiar_texto_base(texto: object) -> str:
    """Elimina espacios sobrantes y maneja valores nulos."""
    if pd.isna(texto):
        return ""
    return re.sub(r"\s+", " ", str(texto).strip())


def quitar_acentos(texto: str) -> str:
    """Remueve tildes para comparaciones de similitud."""
    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in normalizado if not unicodedata.combining(c))


def normalizar_sku(sku_crudo: object, alias_map: Dict[str, str] | None = None) -> str:
    """
    Aplica las reglas de CONTEXT.md para SKUs de Tekio Electronics:
    1. Elimina espacios al inicio y al final.
    2. Convierte a MAYÚSCULAS y remueve acentos.
    3. Reemplaza espacios internos y guiones bajos por guiones (-).
    4. Elimina caracteres no permitidos (conserva A-Z, 0-9 y '-').
    5. Colapsa guiones repetidos y aplica el mapa de alias canónicos.
    """
    texto = limpiar_texto_base(sku_crudo)
    if not texto:
        return ""

    texto = quitar_acentos(texto).upper()
    texto = re.sub(r"[\s_]+", "-", texto)
    texto = re.sub(r"[^A-Z0-9\-]", "", texto)
    texto = re.sub(r"-{2,}", "-", texto).strip("-")

    mapa = alias_map if alias_map is not None else ALIAS_SKU_CONOCIDOS
    return mapa.get(texto, texto)


def detectar_posibles_duplicados(
    df_catalogo: pd.DataFrame,
    col_sku: str = "sku_canonico",
    col_desc: str = "descripcion",
    umbral_similitud: float = 0.82,
) -> pd.DataFrame:
    """
    Compara descripciones normalizadas entre SKUs distintos para alertar
    posibles duplicados semánticos antes de la importación definitiva.
    """
    if col_desc not in df_catalogo.columns:
        return pd.DataFrame(
            columns=["sku_1", "descripcion_1", "sku_2", "descripcion_2", "similitud"]
        )

    registros = (
        df_catalogo[[col_sku, col_desc]]
        .drop_duplicates(subset=[col_sku])
        .reset_index(drop=True)
    )

    sospechosos: List[Dict[str, object]] = []
    n = len(registros)
    for i in range(n):
        sku_a = registros.at[i, col_sku]
        desc_a = limpiar_texto_base(registros.at[i, col_desc])
        desc_a_norm = quitar_acentos(desc_a).lower()
        if not desc_a_norm:
            continue

        for j in range(i + 1, n):
            sku_b = registros.at[j, col_sku]
            desc_b = limpiar_texto_base(registros.at[j, col_desc])
            desc_b_norm = quitar_acentos(desc_b).lower()
            if not desc_b_norm:
                continue

            ratio = SequenceMatcher(None, desc_a_norm, desc_b_norm).ratio()
            if ratio >= umbral_similitud:
                sospechosos.append(
                    {
                        "sku_1": sku_a,
                        "descripcion_1": desc_a,
                        "sku_2": sku_b,
                        "descripcion_2": desc_b,
                        "similitud": round(ratio, 3),
                    }
                )

    return pd.DataFrame(sospechosos)


def limpiar_tabla_catalogo(
    df: pd.DataFrame,
    col_sku: str,
    col_desc: str | None = None,
    col_costo: str | None = None,
    alias_map: Dict[str, str] | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Limpia una tabla de catálogo o movimientos:
    - Genera `sku_canonico` y guarda el `sku_original`.
    - Construye la tabla de equivalencias (`sku_original` -> `sku_canonico`)
      para reescribir llaves foráneas en Ventas, Compras y Movimientos.
    - Deduplica el catálogo conservando la fila más completa (priorizando
      filas con costo/descripción presentes).
    - Detecta posibles duplicados semánticos pendientes de revisión humana.
    """
    trabajo = df.copy()
    trabajo["sku_original"] = trabajo[col_sku].apply(limpiar_texto_base)
    trabajo = trabajo[trabajo["sku_original"] != ""].copy()

    trabajo["sku_canonico"] = trabajo["sku_original"].apply(
        lambda x: normalizar_sku(x, alias_map)
    )

    if col_desc and col_desc in trabajo.columns:
        trabajo[col_desc] = trabajo[col_desc].apply(limpiar_texto_base)

    # Mapa de equivalencias para migrar tablas históricas (Ventas, Compras, Movimientos)
    equivalencias = (
        trabajo[["sku_original", "sku_canonico"]]
        .drop_duplicates()
        .assign(fue_modificado=lambda d: d["sku_original"] != d["sku_canonico"])
        .sort_values(["fue_modificado", "sku_canonico", "sku_original"], ascending=[False, True, True])
        .reset_index(drop=True)
    )

    # Puntuación de completitud para elegir la mejor fila al fusionar duplicados
    trabajo["_completitud"] = trabajo.notna().sum(axis=1)
    if col_costo and col_costo in trabajo.columns:
        trabajo["_tiene_costo"] = pd.to_numeric(trabajo[col_costo], errors="coerce").notna().astype(int)
        trabajo = trabajo.sort_values(["_tiene_costo", "_completitud"], ascending=[False, False])
    else:
        trabajo = trabajo.sort_values(["_completitud"], ascending=[False])

    catalogo_limpio = (
        trabajo.drop_duplicates(subset=["sku_canonico"], keep="first")
        .drop(columns=[c for c in ["_completitud", "_tiene_costo"] if c in trabajo.columns])
        .sort_values("sku_canonico")
        .reset_index(drop=True)
    )

    sospechosos = detectar_posibles_duplicados(
        catalogo_limpio,
        col_sku="sku_canonico",
        col_desc=col_desc if col_desc else "descripcion",
    )

    return catalogo_limpio, equivalencias, sospechosos


def aplicar_equivalencias_a_historico(
    df_historico: pd.DataFrame,
    col_sku: str,
    alias_map: Dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    Reescribe la columna SKU en tablas históricas (Ventas, Compras, Movimientos)
    usando exactamente las mismas reglas para mantener integridad referencial.
    """
    resultado = df_historico.copy()
    resultado[f"{col_sku}_original"] = resultado[col_sku]
    resultado[col_sku] = resultado[col_sku].apply(lambda x: normalizar_sku(x, alias_map))
    return resultado


def _detectar_fila_encabezado(ruta: Path, hoja: str | int, col_sku: str) -> int:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    ws = wb[hoja] if isinstance(hoja, str) else wb.worksheets[hoja]
    objetivo = col_sku.strip().lower()
    for idx, fila in enumerate(ws.iter_rows(values_only=True)):
        celdas = [str(c).strip().lower() for c in fila if c is not None]
        if objetivo in celdas:
            return idx
    return 0


def cargar_archivo(ruta: Path, hoja: str | None = None, col_sku: str = "Código") -> pd.DataFrame:
    sufijo = ruta.suffix.lower()
    if sufijo in {".xlsx", ".xls"}:
        hoja_obj: str | int = hoja if hoja else 0
        fila_header = _detectar_fila_encabezado(ruta, hoja_obj, col_sku) if sufijo == ".xlsx" else 0
        df = pd.read_excel(ruta, sheet_name=hoja_obj, header=fila_header)
        df.columns = [str(c).strip() for c in df.columns]
        return df.dropna(how="all")
    if sufijo == ".csv":
        return pd.read_csv(ruta)
    raise ValueError(f"Formato no soportado: {sufijo}. Usa .xlsx, .xls o .csv.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalizador y limpiador de SKUs para Tekio Electronics."
    )
    parser.add_argument("--entrada", required=True, help="Ruta al archivo .xlsx o .csv")
    parser.add_argument("--hoja", default=None, help="Nombre de la hoja (solo Excel)")
    parser.add_argument("--columna-sku", default="Código", help="Nombre de la columna de SKU")
    parser.add_argument("--columna-desc", default="Descripción", help="Nombre de la columna de descripción")
    parser.add_argument("--columna-costo", default=None, help="Columna de costo (opcional)")
    parser.add_argument("--salida", default="./salida_limpia", help="Carpeta de salida")
    args = parser.parse_args()

    ruta_entrada = Path(args.entrada)
    if not ruta_entrada.exists():
        alternativa = (
            Path(__file__).resolve().parent.parent
            / "tekio-control-ventas"
            / "TEKIO · Control de ventas"
            / "TEKIO · Configuración.xlsx"
        )
        if alternativa.exists():
            ruta_entrada = alternativa

    carpeta_salida = Path(args.salida)
    carpeta_salida.mkdir(parents=True, exist_ok=True)

    df = cargar_archivo(ruta_entrada, args.hoja, args.columna_sku)
    catalogo_limpio, equivalencias, sospechosos = limpiar_tabla_catalogo(
        df,
        col_sku=args.columna_sku,
        col_desc=args.columna_desc,
        col_costo=args.columna_costo,
    )

    catalogo_limpio.to_csv(carpeta_salida / "catalogo_limpio.csv", index=False, encoding="utf-8-sig")
    equivalencias.to_csv(carpeta_salida / "mapa_equivalencias_sku.csv", index=False, encoding="utf-8-sig")
    sospechosos.to_csv(carpeta_salida / "posibles_duplicados_revisar.csv", index=False, encoding="utf-8-sig")

    # Exportar también el mapa en JSON para consumirlo directo en FastAPI / scripts de migración
    mapa_json = dict(zip(equivalencias["sku_original"], equivalencias["sku_canonico"]))
    (carpeta_salida / "mapa_equivalencias_sku.json").write_text(
        json.dumps(mapa_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Filas procesadas: {len(df)}")
    print(f"SKUs únicos limpios: {len(catalogo_limpio)}")
    print(f"SKUs corregidos/unificados: {int(equivalencias['fue_modificado'].sum())}")
    print(f"Posibles duplicados para revisión manual: {len(sospechosos)}")
    print(f"Archivos generados en: {carpeta_salida.resolve()}")


if __name__ == "__main__":
    main()
