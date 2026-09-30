#!/usr/bin/env python3
"""
EA3 - Generador de las 6 fuentes adicionales (JSON, XLSX, CSV, XML, HTML, TXT).
Autor: Jhon Jairo Fuentes Turizo

Aclaracion sobre la procedencia: las fuentes NO las descargue de una API externa.
Son archivos de referencia que arme yo con este script a partir de:
  * catalogos publicos instalados como librerias de Python (ISO 3166 con `pycountry`,
    CLDR con `babel`, poligonos de husos horarios IANA con `timezonefinder`);
  * la documentacion publica de Open Brewery DB (tipos de cerveceria);
  * datos de conocimiento general que compile a mano (capitales y continente),
    y que dejo declarados como tales en PROCEDENCIA.txt;
  * las coordenadas y ciudades del propio dataset limpio (solo para el HTML de
    ciudades: calculo el huso horario IANA del centroide de cada ciudad).
No invente ninguna cifra; si un dato no se pudo derivar, la fila no existe.

Uso (solo si se quiere regenerar; los archivos ya estan en el repositorio):
    pip install ".[fuentes]"
    python src/generar_fuentes.py
"""
from __future__ import annotations

import json
import re
from importlib import metadata
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
OUT = BASE_DIR / "src" / "static" / "fuentes"
CLEAN_XLSX = BASE_DIR / "src" / "static" / "xlsx" / "cleaned_data.xlsx"

# --- Conocimiento general compilado a mano (22 paises/territorios del dataset) ---
# pais (como aparece en el dataset) -> (capital en espanol, continente en espanol)
MANUAL = {
    "United States": ("Washington D. C.", "America del Norte"),
    "Germany": ("Berlin", "Europa"),
    "Belgium": ("Bruselas", "Europa"),
    "Australia": ("Canberra", "Oceania"),
    "Canada": ("Ottawa", "America del Norte"),
    "New Zealand": ("Wellington", "Oceania"),
    "Netherlands": ("Amsterdam", "Europa"),
    "South Africa": ("Pretoria (sede ejecutiva)", "Africa"),
    "Poland": ("Varsovia", "Europa"),
    "Portugal": ("Lisboa", "Europa"),
    "Ireland": ("Dublin", "Europa"),
    "England": ("Londres", "Europa"),
    "Sweden": ("Estocolmo", "Europa"),
    "Singapore": ("Singapur", "Asia"),
    "Japan": ("Tokio", "Asia"),
    "Finland": ("Helsinki", "Europa"),
    "South Korea": ("Seul", "Asia"),
    "Italy": ("Roma", "Europa"),
    "Scotland": ("Edimburgo", "Europa"),
    "Austria": ("Viena", "Europa"),
    "France": ("Paris", "Europa"),
    "Isle of Man": ("Douglas", "Europa"),
}
# England y Scotland son naciones constituyentes del Reino Unido -> ISO GB
ISO2_OVERRIDE = {"England": "GB", "Scotland": "GB"}

# Tipos de cerveceria segun https://openbrewerydb.org/documentation (consultada 2026-09-30).
# taproom, cidery y beergarden aparecen en el dataset pero NO en esa documentacion -> no se incluyen.
TIPOS = {
    "micro": ("La mayoria de las cerveceras artesanales", "Operativa", "No"),
    "nano": ("Cerveceria extremadamente pequena, distribucion local", "Operativa", "No"),
    "regional": ("Sede regional de una cerveceria ampliada", "Operativa", "No"),
    "brewpub": ("Restaurante o bar orientado a la cerveza con cerveceria en el local", "Operativa", "No"),
    "large": ("Cerveceria muy grande, probablemente no apta para visitantes", "Operativa", "Si"),
    "planning": ("Cerveceria en planeacion o aun sin abrir al publico", "No abierta", "No"),
    "bar": ("Bar sin equipo de cerveceria en el local", "Operativa", "Si"),
    "contract": ("Cerveceria que usa el equipo de otra cerveceria", "Operativa", "No"),
    "proprietor": ("Similar a contrato; incubadora de cervecerias", "Operativa", "No"),
    "closed": ("Ubicacion cerrada", "Cerrada", "No"),
}


def ver(pkg: str) -> str:
    return metadata.version(pkg)


def main() -> None:
    import pycountry
    from babel import Locale
    from babel.languages import get_official_languages
    from babel.numbers import get_territory_currencies
    from timezonefinder import TimezoneFinder

    OUT.mkdir(parents=True, exist_ok=True)
    clean = pd.read_excel(CLEAN_XLSX, dtype=str)
    es = Locale("es")
    paises_dataset = sorted(clean["pais"].unique())
    faltan = set(paises_dataset) - set(MANUAL)
    assert not faltan, f"paises del dataset sin compilar: {faltan}"

    def iso2_de(p):
        return ISO2_OVERRIDE.get(p) or pycountry.countries.lookup(p).alpha_2

    # ---------- 1) JSON: paises ISO 3166-1 (pycountry) + continente (manual) ----------
    filas, vistos = [], set()
    for p in paises_dataset:
        i2 = iso2_de(p)
        if i2 in vistos:          # GB una sola vez (England + Scotland)
            continue
        vistos.add(i2)
        c = pycountry.countries.get(alpha_2=i2)
        filas.append({"country": c.name, "iso2": c.alpha_2, "iso3": c.alpha_3,
                      "iso_numerico": c.numeric, "continente": MANUAL[p][1],
                      # nombres con los que este pais aparece en el dataset (clave de union)
                      "nombres_dataset": [q for q in paises_dataset if iso2_de(q) == i2]})
    (OUT / "paises.json").write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------- 2) XLSX: capital (manual) + moneda (CLDR/babel) por pais del dataset ----------
    filas = []
    for p in paises_dataset:
        cod = get_territory_currencies(iso2_de(p), tender=True, non_tender=False)[0]
        filas.append({"Pais": p, "Capital": MANUAL[p][0], "Moneda_ISO4217": cod,
                      "Nombre_moneda": es.currencies.get(cod, cod)})
    leeme = pd.DataFrame({"nota": [
        "Capital y continente: compilacion manual de conocimiento general (Jhon Fuentes).",
        f"Moneda: CLDR via babel {ver('babel')} (moneda de curso legal vigente por territorio).",
        "England y Scotland usan el territorio GB (Reino Unido).",
        "La hoja de datos es la primera (hoja 'paises')."]})
    with pd.ExcelWriter(OUT / "paises_capital.xlsx") as w:
        pd.DataFrame(filas).to_excel(w, sheet_name="paises", index=False)
        leeme.to_excel(w, sheet_name="LEEME", index=False)

    # ---------- 3) CSV: tipos de cerveceria (documentacion Open Brewery DB) ----------
    pd.DataFrame([{"tipo": k, "descripcion_tipo": v[0], "estado_operativo": v[1],
                   "obsoleto_en_api": v[2], "origen": "Open Brewery DB docs (2026-09-30)"}
                  for k, v in TIPOS.items()]).to_csv(OUT / "tipos_cerveceria.csv", index=False, encoding="utf-8")

    # ---------- 4) XML: TODAS las subdivisiones ISO 3166-2 de los paises del dataset ----------
    nodos = []
    for i2 in sorted(vistos):
        pais = pycountry.countries.get(alpha_2=i2).name
        for s in sorted(pycountry.subdivisions.get(country_code=i2), key=lambda x: x.code):
            abrev = s.code.split("-", 1)[1]
            nodos.append(
                "  <subdivision>"
                f"<iso2>{i2}</iso2><pais>{escape(pais)}</pais><nombre>{escape(s.name)}</nombre>"
                f"<abreviatura>{escape(abrev)}</abreviatura><iso_3166_2>{escape(s.code)}</iso_3166_2>"
                f"<tipo>{escape(s.type)}</tipo></subdivision>")
    xml = ("<?xml version='1.0' encoding='utf-8'?>\n"
           f"<!-- ISO 3166-2 via pycountry {ver('pycountry')} (Debian iso-codes). Lo armé con generar_fuentes.py -->\n"
           "<subdivisiones>\n" + "\n".join(nodos) + "\n</subdivisiones>\n")
    (OUT / "estados.xml").write_text(xml, encoding="utf-8")

    # ---------- 5) HTML: huso horario IANA por ciudad (centroide de coordenadas del dataset) ----------
    tf = TimezoneFinder()
    d = clean.copy()
    d["longitud"] = pd.to_numeric(d["longitud"], errors="coerce")
    d["latitud"] = pd.to_numeric(d["latitud"], errors="coerce")
    g = (d.groupby(["ciudad", "estado_provincia", "pais"])
           .agg(n=("id", "size"), lon=("longitud", "mean"), lat=("latitud", "mean")).reset_index())
    g = g[(g["n"] >= 3) & g["lat"].notna()].sort_values(["pais", "estado_provincia", "ciudad"])
    trs = []
    for r in g.itertuples():
        tz = tf.timezone_at(lng=r.lon, lat=r.lat)
        if tz:
            trs.append(f"<tr><td>{escape(r.ciudad)}</td><td>{escape(r.estado_provincia)}</td>"
                       f"<td>{escape(r.pais)}</td><td>{tz}</td></tr>")
    html = ("<!DOCTYPE html>\n<html lang='es'><head><meta charset='utf-8'><title>Husos horarios por ciudad</title></head>\n<body>\n"
            f"<p>Huso horario IANA calculado con timezonefinder {ver('timezonefinder')} sobre el centroide de las coordenadas "
            "del dataset limpio. Solo ciudades con al menos 3 cervecerias con coordenadas (cobertura parcial por diseno).</p>\n"
            "<table id='ciudades' border='1'>\n<thead><tr><th>ciudad</th><th>estado_provincia</th><th>pais</th>"
            "<th>zona_horaria</th></tr></thead>\n<tbody>\n" + "\n".join(trs) + "\n</tbody>\n</table>\n</body></html>\n")
    (OUT / "ciudades.html").write_text(html, encoding="utf-8")

    # ---------- 6) TXT: idiomas oficiales (CLDR/babel) por ISO2 ----------
    lineas = ["# Idiomas oficiales / de facto por territorio. Fuente: CLDR via babel "
              f"{ver('babel')} (get_official_languages, regional=False, de_facto=True).",
              "# Formato: iso2|idiomas_oficiales|idioma_principal (nombres en espanol). Lineas con # son comentarios.",
              "iso2|idiomas_oficiales|idioma_principal"]
    for i2 in sorted(vistos):
        langs = get_official_languages(i2, regional=False, de_facto=True)
        nombres = [es.languages.get(l, l).capitalize() for l in langs]
        lineas.append(f"{i2}|{'/'.join(nombres)}|{nombres[0]}")
    (OUT / "idiomas.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")

    # ---------- PROCEDENCIA ----------
    proc = f"""PROCEDENCIA DE LAS FUENTES ADICIONALES (EA3) - armadas con src/generar_fuentes.py
=====================================================================================
Estas fuentes son archivos de referencia que construi yo; no son descargas de una
API externa. Abajo dejo de donde sale el contenido de cada archivo.

paises.json          ISO 3166-1 (pycountry {ver('pycountry')}: nombre, alfa-2, alfa-3, numerico) + continente compilado a mano.
paises_capital.xlsx  Capital: la compile a mano (conocimiento general). Moneda: CLDR via babel {ver('babel')}.
tipos_cerveceria.csv Tipos segun la documentacion publica de Open Brewery DB (consultada 2026-09-30). taproom, cidery y
                     beergarden existen en el dataset pero no figuran en esa pagina: quedan SIN fuente (no coincidentes).
estados.xml          ISO 3166-2 completo (pycountry {ver('pycountry')}) de los paises del dataset. Sin recorte: los estados/provincias del
                     dataset que no coinciden (p. ej. 'Vlaanderen', 'Ostrobothnia') quedan como no coincidentes.
ciudades.html        Huso horario IANA (timezonefinder {ver('timezonefinder')}) del centroide de coordenadas del dataset, solo ciudades con
                     >= 3 cervecerias con coordenadas. Es DERIVADO del propio dataset; su cobertura es parcial por diseno.
idiomas.txt          Idiomas oficiales/de facto por territorio (CLDR via babel {ver('babel')}).

Limitaciones: England y Scotland los asigne a GB; las capitales y los continentes los compile a mano; ninguna fuente trae
informacion de negocio real de las cervecerias (ventas, produccion, etc.).
"""
    (OUT / "PROCEDENCIA.txt").write_text(proc, encoding="utf-8")
    print("Fuentes construidas en", OUT)
    for p in sorted(OUT.iterdir()):
        print(" ", p.name, p.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
