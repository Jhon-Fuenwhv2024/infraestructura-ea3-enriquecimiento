#!/usr/bin/env python3
"""
EA2 - Limpieza de datos: Cervecerías (Open Brewery DB + datos sucios).
Autor: Jhon Jairo Fuentes Turizo
Curso: PREICA2602B010136
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "src" / "static" / "db" / "ingestion.db"
XLSX_PATH = BASE_DIR / "src" / "static" / "xlsx" / "cleaned_data.xlsx"
REPORT_PATH = BASE_DIR / "src" / "static" / "auditoria" / "cleaning_report.txt"

TABLE = "cerveceria"

TIPO_MAP = {
    "micro": "micro",
    "nano": "nano",
    "regional": "regional",
    "brewpub": "brewpub",
    "large": "large",
    "planning": "planning",
    "bar": "bar",
    "contract": "contract",
    "proprietor": "proprietor",
    "closed": "closed",
    "taproom": "taproom",
    "cidery": "cidery",
    "beergarden": "beergarden",
}


def _blank_to_na(series: pd.Series) -> pd.Series:
    """Convierte None/NaN/cadenas vacías o solo espacios a pd.NA."""
    out = series.copy()
    # Unificar nulos reales
    out = out.where(pd.notna(out), other=pd.NA)

    def _norm(v):
        if v is pd.NA or v is None:
            return pd.NA
        if isinstance(v, float) and pd.isna(v):
            return pd.NA
        if isinstance(v, str):
            s = v.strip()
            if s == "" or s.lower() in {"none", "nan", "null", "n/a"}:
                return pd.NA
            return s
        return v

    return out.map(_norm)


def load_data(db_path: Path) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(f"SELECT * FROM {TABLE}", conn)
    finally:
        conn.close()
    return df


def explore(df: pd.DataFrame) -> dict:
    blank_counts = {}
    for c in df.columns:
        s = df[c]
        blank_counts[c] = int(
            s.isna().sum()
            + s.astype(str).str.strip().isin(["", "None", "nan", "NaN", "NULL", "null"]).sum()
            - s.astype(str).str.strip().isin(["nan", "None", "NaN", "NULL", "null"]).sum()
            # aproximación: reportamos isna + vacíos textuales por separado abajo
        )
    return {
        "rows": len(df),
        "cols": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "nulls": {c: int(v) for c, v in df.isna().sum().items()},
        "null_strings": {
            c: int((df[c].astype(str).str.strip().isin(["", "None", "nan", "NaN", "NULL", "null"])).sum())
            for c in df.columns
        },
        "dupes_full": int(df.duplicated().sum()),
        "dupes_id": int(df.duplicated(subset=["id"]).sum()) if "id" in df.columns else 0,
        "tipo_cerveza_unique": (
            sorted({str(x) for x in df["tipo_cerveza"].tolist()})
            if "tipo_cerveza" in df.columns
            else []
        ),
    }


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    metrics: dict = {"rows_before": len(df)}
    work = df.copy()

    # 1) Placeholders / blancos -> NA
    for col in work.columns:
        work[col] = _blank_to_na(work[col])

    metrics["nulls_before"] = {k: int(v) for k, v in work.isna().sum().items()}

    # 2) Duplicados: id base sin sufijo -dup; luego fila completa
    before_dupes = len(work)
    if "id" in work.columns:
        work["_id_base"] = work["id"].astype("string").str.replace(r"-dup$", "", regex=True)
        work = work.drop_duplicates(subset=["_id_base"], keep="first")
        work = work.drop(columns=["_id_base"])
    work = work.drop_duplicates(keep="first")
    metrics["rows_dropped_duplicates"] = before_dupes - len(work)

    # 3) Tipos lon/lat -> float
    for col in ("longitud", "latitud"):
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")

    # 4) Normalizar tipo_cerveza
    if "tipo_cerveza" in work.columns:
        work["tipo_cerveza"] = work["tipo_cerveza"].astype("string").str.strip().str.lower()
        work["tipo_cerveza"] = work["tipo_cerveza"].map(
            lambda x: TIPO_MAP.get(x, x) if isinstance(x, str) else x
        )
        work["tipo_cerveza"] = _blank_to_na(work["tipo_cerveza"])

    # 5) Eliminar filas sin id o casi vacías (datos sintéticos dirty-*)
    before_bad = len(work)
    if "id" in work.columns:
        work = work.dropna(subset=["id"])
    # Filas sin nombre y sin tipo (basura) o id dirty-*
    mask_junk = pd.Series(False, index=work.index)
    if "nombre" in work.columns and "tipo_cerveza" in work.columns:
        mask_junk = work["nombre"].isna() & work["tipo_cerveza"].isna()
    if "id" in work.columns:
        mask_junk = mask_junk | work["id"].astype("string").str.startswith("dirty-", na=False)
    work = work.loc[~mask_junk].copy()
    metrics["rows_dropped_junk"] = before_bad - len(work)
    metrics["rows_dropped_null_id"] = 0

    # 6) Relleno de nulos textuales (lon/lat se dejan NaN)
    fill_map = {}
    if "nombre" in work.columns:
        fill_map["nombre"] = "DESCONOCIDO"
    if "tipo_cerveza" in work.columns:
        fill_map["tipo_cerveza"] = "unknown"
    for col in (
        "direccion",
        "ciudad",
        "estado_provincia",
        "codigo_postal",
        "pais",
        "telefono",
        "sitio_web",
        "estado",
        "street",
    ):
        if col in work.columns:
            fill_map[col] = "N/D"
    if fill_map:
        work = work.fillna(value=fill_map)
        # asegurar que no queden strings vacíos
        for col in fill_map:
            work[col] = work[col].astype("string")
            work.loc[work[col].isna() | (work[col].str.strip() == ""), col] = fill_map[col]

    if "tipo_cerveza" in work.columns:
        metrics["tipo_cerveza_after"] = (
            work["tipo_cerveza"].value_counts(dropna=False).to_dict()
        )

    metrics["nulls_after"] = {k: int(v) for k, v in work.isna().sum().items()}
    metrics["rows_after"] = len(work)
    metrics["rows_removed_total"] = metrics["rows_before"] - metrics["rows_after"]

    preferred = [
        "id",
        "nombre",
        "tipo_cerveza",
        "direccion",
        "ciudad",
        "estado_provincia",
        "codigo_postal",
        "pais",
        "longitud",
        "latitud",
        "telefono",
        "sitio_web",
        "estado",
        "street",
    ]
    cols = [c for c in preferred if c in work.columns] + [
        c for c in work.columns if c not in preferred
    ]
    return work[cols], metrics


def write_report(explore_stats: dict, metrics: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "=" * 70,
        "REPORTE DE LIMPIEZA DE DATOS - EA2",
        "Curso: PREICA2602B010136",
        "Autor: Jhon Jairo Fuentes Turizo",
        f"Fecha (UTC): {datetime.now(timezone.utc).isoformat()}",
        "Fuente: src/static/db/ingestion.db (tabla cerveceria)",
        "Línea de origen: Open Brewery DB + filas sucias (simulación nube EA1)",
        "=" * 70,
        "",
        "1. EXPLORACIÓN INICIAL",
        f"   Filas: {explore_stats['rows']}",
        f"   Columnas ({len(explore_stats['cols'])}): {', '.join(explore_stats['cols'])}",
        "   Tipos de dato (antes):",
    ]
    for c, t in explore_stats["dtypes"].items():
        lines.append(f"      - {c}: {t}")
    lines.append("   Nulos (pandas NA / None):")
    for c, n in explore_stats["nulls"].items():
        lines.append(f"      - {c}: {n}")
    lines.append("   Cadenas vacías / placeholders ('', None, nan, NULL):")
    for c, n in explore_stats["null_strings"].items():
        lines.append(f"      - {c}: {n}")
    lines.append(f"   Duplicados (fila completa): {explore_stats['dupes_full']}")
    lines.append(f"   Duplicados (por id): {explore_stats['dupes_id']}")
    lines.append(
        f"   Valores únicos tipo_cerveza (antes): {explore_stats['tipo_cerveza_unique']}"
    )
    lines.extend(
        [
            "",
            "2. TRANSFORMACIONES APLICADAS",
            "   - Conversión de placeholders y blancos a nulos",
            "   - Eliminación de duplicados por id (incl. sufijo -dup) y fila completa",
            "   - Eliminación de filas basura (id dirty-* o sin nombre/tipo)",
            "   - Conversión de longitud/latitud a float (pd.to_numeric, errors='coerce')",
            "   - Normalización de tipo_cerveza a minúsculas / catálogo conocido",
            "   - Relleno de nulos textuales (DESCONOCIDO / N/D / unknown);",
            "     lon/lat inválidas permanecen como NaN",
            "",
            "3. MÉTRICAS",
            f"   Filas antes: {metrics['rows_before']}",
            f"   Filas después: {metrics['rows_after']}",
            f"   Filas eliminadas (total): {metrics['rows_removed_total']}",
            f"   Eliminadas por duplicados: {metrics['rows_dropped_duplicates']}",
            f"   Eliminadas por basura/id nulo: {metrics.get('rows_dropped_junk', 0)}",
            "   Nulos antes (post-placeholder):",
        ]
    )
    for c, n in metrics["nulls_before"].items():
        lines.append(f"      - {c}: {n}")
    lines.append("   Nulos después:")
    for c, n in metrics["nulls_after"].items():
        lines.append(f"      - {c}: {n}")
    if "tipo_cerveza_after" in metrics:
        lines.append("   Distribución tipo_cerveza (después):")
        for k, v in sorted(
            metrics["tipo_cerveza_after"].items(), key=lambda x: (-x[1], str(x[0]))
        ):
            lines.append(f"      - {k}: {v}")
    lines.extend(
        [
            "",
            "4. SALIDAS",
            f"   Excel limpio: {XLSX_PATH.relative_to(BASE_DIR)}",
            f"   Este reporte: {path.relative_to(BASE_DIR)}",
            "",
            "=" * 70,
            "Fin del reporte",
            "=" * 70,
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"No se encontró la base de datos: {DB_PATH}")

    XLSX_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    df = load_data(DB_PATH)
    stats = explore(df)
    cleaned, metrics = clean(df)

    cleaned.to_excel(XLSX_PATH, index=False, engine="openpyxl")
    write_report(stats, metrics, REPORT_PATH)

    print(f"OK: filas {metrics['rows_before']} -> {metrics['rows_after']}")
    print(f"  duplicados: {metrics['rows_dropped_duplicates']}")
    print(f"  basura: {metrics.get('rows_dropped_junk', 0)}")
    print(f"Excel: {XLSX_PATH}")
    print(f"Reporte: {REPORT_PATH}")


if __name__ == "__main__":
    main()
