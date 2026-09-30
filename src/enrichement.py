#!/usr/bin/env python3
"""
EA3 - Enriquecimiento de datos en plataforma de Big Data (simulada en la nube).
Autor: Jhon Jairo Fuentes Turizo | Curso: Infraestructura y arquitectura para Big Data

Que hace este script:
  1. Carga el dataset limpio de la Actividad 2 (src/static/xlsx/cleaned_data.xlsx, que saco con
     src/cleaning.py de la tabla `cerveceria` de src/static/db/ingestion.db) y lo comparo con la base SQLite.
  2. Lee con Pandas las 6 fuentes adicionales (src/static/fuentes): JSON, XLSX, CSV, XML, HTML y TXT.
  3. Normalizo las claves y hago 6 merges LEFT, asi el numero de registros base no cambia.
  4. Guardo el dataset enriquecido completo en src/static/xlsx/enriched_data.xlsx y, como el enunciado pide
     la carpeta src/xlsx/, tambien una copia en src/xlsx/enriched_data.xlsx.
     El reporte de auditoria queda en src/static/auditoria/enriched_report.txt (las cifras salen de la ejecucion).
Uso:  python src/enrichement.py
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "src" / "static" / "db" / "ingestion.db"
DB_COPY = BASE_DIR / "src" / "db" / "ingestion.db"      # copia opcional (estructura literal del enunciado EA3)
CLEAN_XLSX = BASE_DIR / "src" / "static" / "xlsx" / "cleaned_data.xlsx"
FUENTES = BASE_DIR / "src" / "static" / "fuentes"
OUT_XLSX = BASE_DIR / "src" / "static" / "xlsx" / "enriched_data.xlsx"
OUT_XLSX_COPY = BASE_DIR / "src" / "xlsx" / "enriched_data.xlsx"  # solo si existe la carpeta src/xlsx/
OUT_TXT = BASE_DIR / "src" / "static" / "auditoria" / "enriched_report.txt"
TABLE = "cerveceria"
BOGOTA = timezone(timedelta(hours=-5))


def norm(v) -> str:
    """Clave normalizada: sin tildes, minusculas, sin puntuacion, espacios colapsados, sin sufijo 'region'."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\s+region$", "", s)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def leer_base() -> tuple[pd.DataFrame, dict]:
    if not CLEAN_XLSX.exists():
        raise FileNotFoundError(f"Falta {CLEAN_XLSX}. Ejecute primero: python src/cleaning.py")
    base = pd.read_excel(CLEAN_XLSX, dtype=str, keep_default_na=False)
    for c in ("longitud", "latitud"):
        base[c] = pd.to_numeric(base[c].replace("", pd.NA), errors="coerce")
    with sqlite3.connect(DB_PATH) as con:
        raw = pd.read_sql_query(f"SELECT id FROM {TABLE}", con)
    info = {
        "db_filas": len(raw), "ids_limpios_en_db": int(base["id"].isin(raw["id"]).sum()),
        "ids_unicos": int(base["id"].nunique()), "db_sha256": sha256(DB_PATH),
        "db_copia_identica": DB_COPY.exists() and sha256(DB_COPY) == sha256(DB_PATH),
    }
    return base, info


def leer_fuentes() -> dict[str, pd.DataFrame]:
    """Una lectura con Pandas por formato."""
    js = pd.read_json(FUENTES / "paises.json", encoding="utf-8", dtype={"iso_numerico": str})  # conserva ceros ("036")
    js = js.explode("nombres_dataset").rename(columns={"nombres_dataset": "pais_dataset"})
    xl = pd.read_excel(FUENTES / "paises_capital.xlsx", sheet_name="paises", dtype=str)
    csv = pd.read_csv(FUENTES / "tipos_cerveceria.csv", dtype=str, encoding="utf-8")
    xml = pd.read_xml(FUENTES / "estados.xml", xpath=".//subdivision", dtype=str).fillna("")
    html = pd.read_html(StringIO((FUENTES / "ciudades.html").read_text(encoding="utf-8")),
                        attrs={"id": "ciudades"}, keep_default_na=False)[0]
    txt = pd.read_csv(FUENTES / "idiomas.txt", sep="|", comment="#", dtype=str, encoding="utf-8")
    return {"json": js, "xlsx": xl, "csv": csv, "xml": xml, "html": html, "txt": txt}


def unir(df: pd.DataFrame, src: pd.DataFrame, k: str, cols: dict[str, str]):
    """Merge LEFT por la clave normalizada `k` (misma columna en ambos lados). Verifica filas."""
    src = src[src[k].notna() & (src[k] != "")]
    dup = int(src.duplicated(k).sum())
    u = src.drop_duplicates(k)[[k] + list(cols)].rename(columns=cols)
    n0 = len(df)
    out = df.merge(u.assign(_m=1), how="left", on=k)
    assert len(out) == n0, "el merge altero el numero de registros"
    hit = out["_m"].notna().to_numpy()
    no_match = df.loc[~hit, k].value_counts()
    st = {
        "filas_fuente": len(src), "claves_unicas_fuente": int(u[k].nunique()), "dup_descartados": dup,
        "match": int(hit.sum()), "no_match": int((~hit).sum()),
        "claves_base_sin_match": int(no_match.size), "top_no_match": list(no_match.head(8).items()),
        "claves_fuente_sin_uso": int((~u[k].isin(df[k])).sum()),
        "ej_fuente_sin_uso": sorted(u.loc[~u[k].isin(df[k]), k])[:5], "cols": list(cols.values()),
    }
    return out.drop(columns="_m"), st


def main() -> None:
    inicio = datetime.now(BOGOTA)
    base, info = leer_base()
    n_base = len(base)
    F = leer_fuentes()
    js, xl, csv, xml, html, txt = (F[k] for k in ("json", "xlsx", "csv", "xml", "html", "txt"))

    # XML: cada subdivision se puede referenciar por nombre ISO o por abreviatura (p. ej. AU 'NSW')
    xml_k = pd.concat([xml.assign(_k=xml["iso2"] + "|" + xml["nombre"].map(norm)),
                       xml.assign(_k=xml["iso2"] + "|" + xml["abreviatura"].map(norm))], ignore_index=True)
    xml_k = xml_k.rename(columns={"nombre": "subdivision_nombre_iso"})

    # (nombre, formato, lector, clave, fuente, funcion clave base, funcion clave fuente, columnas, nota)
    pais = lambda d: d["pais"].map(norm)
    pasos = [
        ("paises.json", "JSON", "pd.read_json + explode(nombres_dataset)", "pais (normalizado)", js,
         pais, lambda s: s["pais_dataset"].map(norm),
         {"iso2": "iso2", "iso3": "iso3", "iso_numerico": "iso_numerico", "continente": "continente"},
         "ISO 3166-1 (pycountry) + continente manual. England y Scotland se mapean a GB."),
        ("paises_capital.xlsx", "XLSX", "pd.read_excel(sheet_name='paises')", "pais (normalizado)", xl,
         pais, lambda s: s["Pais"].map(norm),
         {"Capital": "capital_pais", "Moneda_ISO4217": "moneda_iso4217", "Nombre_moneda": "nombre_moneda"},
         "Capital manual; moneda CLDR (babel)."),
        ("tipos_cerveceria.csv", "CSV", "pd.read_csv", "tipo_cerveza (normalizado)", csv,
         lambda d: d["tipo_cerveza"].map(norm), lambda s: s["tipo"].map(norm),
         {"descripcion_tipo": "descripcion_tipo", "estado_operativo": "estado_operativo", "obsoleto_en_api": "tipo_obsoleto_en_api"},
         "Segun documentacion de Open Brewery DB; taproom/cidery/beergarden no estan documentados -> no coinciden."),
        ("estados.xml", "XML", "pd.read_xml(xpath='.//subdivision')", "iso2 + estado_provincia (nombre o abreviatura ISO)", xml_k,
         lambda d: d["iso2"].fillna("") + "|" + d["estado_provincia"].map(norm), lambda s: s["_k"],
         {"subdivision_nombre_iso": "subdivision_nombre_iso", "iso_3166_2": "subdivision_iso3166_2", "tipo": "subdivision_tipo"},
         "ISO 3166-2 completo de los paises del dataset (sin recorte); el desajuste de nombres es real."),
        ("ciudades.html", "HTML", "pd.read_html(attrs={'id':'ciudades'})", "ciudad + estado_provincia + pais", html,
         lambda d: d["ciudad"].map(norm) + "|" + d["estado_provincia"].map(norm) + "|" + d["pais"].map(norm),
         lambda s: s["ciudad"].map(norm) + "|" + s["estado_provincia"].map(norm) + "|" + s["pais"].map(norm),
         {"zona_horaria": "zona_horaria"},
         "Solo ciudades con >= 3 cervecerias con coordenadas: cobertura parcial por diseno."),
        ("idiomas.txt", "TXT", "pd.read_csv(sep='|', comment='#')", "iso2 (heredado del merge JSON)", txt,
         lambda d: d["iso2"].fillna("").str.upper(), lambda s: s["iso2"].str.strip().str.upper(),
         {"idiomas_oficiales": "idiomas_oficiales", "idioma_principal": "idioma_principal"},
         "Idiomas oficiales/de facto (CLDR via babel). Depende de que el pais haya coincidido en JSON."),
    ]
    df, resumen = base, []
    for nombre, fmt, lector, clave, src, kb, ks, cols, nota in pasos:
        df = df.assign(_k=kb(df).to_numpy())
        src = src.assign(_k=ks(src).to_numpy())
        df, st = unir(df, src, "_k", cols)
        df = df.drop(columns="_k")
        st.update(nombre=nombre, formato=fmt, lector=lector, clave=clave, nota=nota)
        resumen.append(st)

    nuevas = [c for r in resumen for c in r["cols"]]
    df["fuentes_coincidentes"] = sum(df[r["cols"][0]].notna().astype(int) for r in resumen)
    df["enriquecimiento_completo"] = df[nuevas].notna().all(axis=1)
    completos = int(df["enriquecimiento_completo"].sum())
    cobertura = {c: int(df[c].notna().sum()) for c in nuevas}
    dist = df["fuentes_coincidentes"].value_counts().sort_index()
    assert len(df) == n_base and df["id"].is_unique

    # ---- exportacion completa ----
    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    tabla = pd.DataFrame([{
        "fuente": r["nombre"], "formato": r["formato"], "clave_union": r["clave"], "filas_fuente": r["filas_fuente"],
        "registros_base": n_base, "coincidentes": r["match"], "no_coincidentes": r["no_match"],
        "pct_coincidencia": round(100 * r["match"] / n_base, 2), "columnas_agregadas": ", ".join(r["cols"])} for r in resumen])
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="enriquecido", index=False)
        tabla.to_excel(w, sheet_name="resumen_cruces", index=False)
    destinos = [OUT_XLSX]
    if OUT_XLSX_COPY.parent.is_dir():
        shutil.copyfile(OUT_XLSX, OUT_XLSX_COPY)
        destinos.append(OUT_XLSX_COPY)

    # ---- reporte de auditoria ----
    pct = lambda a, b=n_base: f"{100 * a / b:.1f}%"
    L = ["=" * 78, "REPORTE DE AUDITORIA - EA3 ENRIQUECIMIENTO DE DATOS", "Curso: Infraestructura y arquitectura para Big Data",
         "Autor: Jhon Jairo Fuentes Turizo",
         f"Fecha de ejecucion (America/Bogota, UTC-5): {inicio:%Y-%m-%d %H:%M:%S}", "=" * 78, "",
         "DECLARACION DE PROCEDENCIA DE LAS FUENTES ADICIONALES", "-" * 78,
         "Las 6 fuentes de src/static/fuentes/ son archivos de referencia que construi yo con src/generar_fuentes.py.",
         "No los descargue de una API externa y tampoco son datos propios de las cerveceras. Los arme a partir de",
         "ISO 3166 (pycountry), CLDR (babel), husos IANA (timezonefinder), los tipos de la documentacion de",
         "Open Brewery DB y capitales/continentes que compile a mano. Detalle en src/static/fuentes/PROCEDENCIA.txt.", "",
         "1. REGISTROS: BASE vs ENRIQUECIDO", "-" * 78,
         f"Base SQLite (src/static/db/ingestion.db, tabla {TABLE}, sin limpiar): {info['db_filas']} registros",
         f"Dataset limpio EA2 (src/static/xlsx/cleaned_data.xlsx) = BASE del enriquecimiento: {n_base} registros, {len(base.columns)} columnas",
         f"   ids limpios presentes en la base SQLite: {info['ids_limpios_en_db']} de {n_base} | ids unicos: {info['ids_unicos']}",
         f"   registros eliminados por la limpieza de EA2: {info['db_filas'] - n_base}",
         f"Dataset enriquecido: {len(df)} registros, {len(df.columns)} columnas "
         f"({len(nuevas)} nuevas de fuentes + fuentes_coincidentes + enriquecimiento_completo)",
         f"Diferencia de registros base vs enriquecido: {len(df) - n_base} (merges LEFT; se valida con assert)",
         f"Registros con las {len(nuevas)} columnas nuevas informadas (enriquecimiento_completo=True): {completos} ({pct(completos)})",
         f"Exportacion COMPLETA ({len(df)} filas, hoja 'enriquecido' + hoja 'resumen_cruces'): "
         + " y ".join(str(d.relative_to(BASE_DIR)) for d in destinos),
         (f"src/db/ingestion.db identica a src/static/db/ingestion.db: {'SI' if info['db_copia_identica'] else 'NO'} "
          f"(sha256 {info['db_sha256'][:16]}...)") if DB_COPY.exists() else
         f"sha256 de src/static/db/ingestion.db: {info['db_sha256'][:16]}...", "",
         "2. REGISTROS COINCIDENTES Y NO COINCIDENTES POR FUENTE", "-" * 78]
    for i, r in enumerate(resumen, 1):
        L += [f"[{i}] {r['nombre']} ({r['formato']}) - lector: {r['lector']}",
              f"    clave de union      : {r['clave']}",
              f"    filas fuente        : {r['filas_fuente']} | claves unicas: {r['claves_unicas_fuente']} | duplicados de clave descartados: {r['dup_descartados']}",
              f"    COINCIDENTES        : {r['match']} de {n_base} ({pct(r['match'])})",
              f"    NO COINCIDENTES     : {r['no_match']} de {n_base} ({pct(r['no_match'])}) en {r['claves_base_sin_match']} claves distintas de la base",
              "    mayores no coincid. : " + ("; ".join(f"{k} ({v})" for k, v in r["top_no_match"]) if r["top_no_match"] else "ninguna"),
              f"    claves de la fuente sin uso en la base: {r['claves_fuente_sin_uso']}"
              + (f" (ej.: {r['ej_fuente_sin_uso']})" if r["ej_fuente_sin_uso"] else ""),
              f"    columnas agregadas  : {', '.join(r['cols'])}", ""]
    L += ["Distribucion de registros segun cuantas de las 6 fuentes coincidieron:"]
    L += [f"    {int(k)} fuentes: {int(v)} registros ({pct(v)})" for k, v in dist.items()]
    L += ["", "3. COBERTURA POR COLUMNA NUEVA (registros con valor)", "-" * 78]
    L += [f"    {c}: {v} de {n_base} ({pct(v)}); vacios: {n_base - v}" for c, v in cobertura.items()]
    L += ["", "4. TRANSFORMACIONES APLICADAS", "-" * 78,
          "- Base = dataset limpio de EA2 (duplicados, filas basura y placeholders ya tratados en src/cleaning.py).",
          "- Lectura de cada fuente con Pandas segun su formato (ver 'lector'); XML con lxml, HTML con lxml/bs4/html5lib.",
          "- Normalizacion de claves (funcion norm): NFKD sin tildes, minusculas, puntuacion -> espacio, espacios colapsados,",
          "  sufijo final 'region' eliminado (p. ej. 'Bay of Plenty Region' = 'Bay of Plenty').",
          "- Claves compuestas: iso2|estado (XML, por nombre o abreviatura ISO) y ciudad|estado|pais (HTML).",
          "- Cadena de dependencia: el iso2 obtenido del JSON alimenta las claves de XML y TXT.",
          "- Duplicados de clave en la fuente se descartan antes del merge para no multiplicar registros.",
          "- Merges LEFT: los registros sin coincidencia conservan las columnas nuevas vacias (no se inventan valores).",
          "- Columnas de control: fuentes_coincidentes (0-6) y enriquecimiento_completo (booleano).", "",
          "5. OBSERVACIONES POR FUENTE", "-" * 78]
    L += [f"- {r['nombre']}: cobertura {pct(r['match'])}. {r['nota']}" for r in resumen]
    L += ["", "6. OBSERVACIONES GENERALES / LIMITACIONES", "-" * 78,
          "- La cobertura alta en JSON/XLSX/TXT se debe a que yo arme esas tablas con los paises del dataset; no mide la",
          "  calidad de una fuente externa independiente.",
          "- Las diferencias en XML (nombres locales como 'Vlaanderen', 'Ostrobothnia', 'Stockholm County') y HTML (ciudades con",
          "  menos de 3 cervecerias) las deje como no coincidentes a proposito, sin forzar alias manuales.",
          "- Las fuentes no traen informacion propia de cada cerveceria (ventas, produccion); solo agregan datos geograficos,",
          "  monetarios, de idioma y de clasificacion de tipo.",
          "- Verificacion independiente: python src/verificar_conteos.py", "", "Fin del reporte", "=" * 78]
    OUT_TXT.parent.mkdir(parents=True, exist_ok=True)
    OUT_TXT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"OK enriquecido: {len(df)} filas x {len(df.columns)} columnas")
    for r in resumen:
        print(f"  {r['nombre']}: match={r['match']} no_match={r['no_match']}")
    print("Excel: " + ", ".join(str(d) for d in destinos) + f"\nReporte: {OUT_TXT}")


if __name__ == "__main__":
    main()
