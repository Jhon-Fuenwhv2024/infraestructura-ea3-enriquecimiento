# EA3 – Enriquecimiento de datos en plataforma de Big Data en la nube

**Autor:** Jhon Jairo Fuentes Turizo · **Institución:** IU Digital de Antioquia
**Curso:** Infraestructura y arquitectura para Big Data · **Actividad:** EA3 – Enriquecimiento de datos
**Fecha:** de septiembre de 2026
**Repositorio:** https://github.com/Jhon-Fuenwhv2024/infraestructura-ea3-enriquecimiento

## Qué hice y cómo se conecta con las otras actividades

En esta actividad tomé el dataset limpio de la EA2 y lo enriquecí con seis fuentes adicionales, una por cada formato que pedía el enunciado
(JSON, XLSX, CSV, XML, HTML y TXT). Dejé el trabajo en un repositorio propio para que la evidencia de la EA3 se pueda revisar sola.

| Etapa | Qué hace | Evidencia en este repositorio |
|---|---|---|
| EA1 | Ingesta desde Open Brewery DB (API) a base de datos | `src/static/db/ingestion.db` (SQLite que simula la nube; tabla `cerveceria`, 3 025 filas) |
| EA2 | Limpieza de datos | `src/cleaning.py` → `src/static/xlsx/cleaned_data.xlsx` (3 000 filas) y `src/static/auditoria/cleaning_report.txt` |
| **EA3** | **Enriquecimiento con 6 fuentes (JSON, XLSX, CSV, XML, HTML, TXT)** | `src/enrichement.py` → `src/xlsx/enriched_data.xlsx` y `src/static/auditoria/enriched_report.txt` |

## Sobre las fuentes adicionales (aclaración)

Las 6 fuentes de `src/static/fuentes/` **no son descargas de una API externa ni datos propios de las cervecerías**. Son archivos de referencia
que **construí yo** con `src/generar_fuentes.py`, a partir de catálogos públicos que se instalan como librerías de Python y de datos que compilé a mano.
El detalle está en `src/static/fuentes/PROCEDENCIA.txt` y en la primera sección del reporte de auditoría.

| Formato | Archivo | Contenido y origen | Clave de unión | Columnas agregadas |
|---|---|---|---|---|
| JSON | `paises.json` | ISO 3166-1 (`pycountry`) y continente que compilé a mano | `pais` | iso2, iso3, iso_numerico, continente |
| XLSX | `paises_capital.xlsx` | Capital que compilé a mano; moneda de CLDR (`babel`) | `pais` | capital_pais, moneda_iso4217, nombre_moneda |
| CSV | `tipos_cerveceria.csv` | Tipos según la documentación de Open Brewery DB | `tipo_cerveza` | descripcion_tipo, estado_operativo, tipo_obsoleto_en_api |
| XML | `estados.xml` | ISO 3166-2 completo de los países del dataset (`pycountry`) | `iso2` + `estado_provincia` (nombre o abreviatura) | subdivision_nombre_iso, subdivision_iso3166_2, subdivision_tipo |
| HTML | `ciudades.html` | Huso horario IANA (`timezonefinder`) del centroide de las coordenadas del propio dataset; solo ciudades con 3 o más cervecerías | `ciudad` + `estado_provincia` + `pais` | zona_horaria |
| TXT | `idiomas.txt` | Idiomas oficiales o de facto de CLDR (`babel`) | `iso2` (sale del cruce con el JSON) | idiomas_oficiales, idioma_principal |

Limitaciones que tiene este trabajo: asigné `England` y `Scotland` a GB; las capitales y los continentes son conocimiento general que compilé a mano y no los
contrasté con otra fuente; la cobertura del 100 % en JSON, XLSX y TXT se debe a que armé esas tablas con los países del dataset, así que no es una validación
externa independiente; y ningún archivo trae datos de negocio de cada cervecería. Los registros que no coinciden (por ejemplo `taproom`, `cidery` y
`beergarden` en el CSV; `Vlaanderen` o `Stockholm County` en el XML; las ciudades pequeñas en el HTML) **los dejé vacíos a propósito**, sin inventar valores.

## Resultados de la ejecución (los calcula el script y los comprueba `verificar_conteos.py`)

- Base SQLite: **3 025** registros → dataset limpio (base del enriquecimiento): **3 000** → enriquecido: **3 000** (diferencia 0, porque los merges son *left*).
- Columnas: 14 base + 16 nuevas + 2 de control (`fuentes_coincidentes`, `enriquecimiento_completo`) = 32.
- Coincidentes por fuente: JSON 3 000 · XLSX 3 000 · CSV 2 984 · XML 2 799 · HTML 900 · TXT 3 000.
- `iso_numerico` queda como texto de 3 dígitos (por ejemplo `036`, `056`) para no perder los ceros a la izquierda.
- Registros con las 16 columnas nuevas informadas: **827** (27,6 %).
- El Excel `enriched_data.xlsx` (en `src/xlsx/` y en `src/static/xlsx/`, dos copias idénticas) tiene el dataset **completo** en la hoja `enriquecido` y la hoja `resumen_cruces`.

## Estructura

```text
infraestructura-ea3-enriquecimiento/     # raíz del repositorio
├── setup.py
├── README.md
├── .gitignore
├── .github/workflows/bigdata.yml
└── src/
    ├── cleaning.py              # EA2 (limpieza)
    ├── enrichement.py           # EA3 (con el nombre exacto del enunciado)
    ├── enrichment.py            # alias que llama a enrichement.py
    ├── generar_fuentes.py       # construye las 6 fuentes de referencia
    ├── verificar_conteos.py     # conteo independiente (librería estándar) que revisa el reporte y el Excel
    ├── db/ingestion.db          # ruta que pide el enunciado (idéntica a static/db)
    ├── xlsx/enriched_data.xlsx  # ruta que pide el enunciado (copia idéntica)
    └── static/
        ├── auditoria/           # cleaning_report.txt, enriched_report.txt
        ├── db/ingestion.db      # ubicación que uso desde la EA2
        ├── fuentes/             # las 6 fuentes y PROCEDENCIA.txt
        └── xlsx/                # cleaned_data.xlsx, enriched_data.xlsx (salida principal)
```

`src/db/ingestion.db` y `src/static/db/ingestion.db` son el mismo archivo (mismo SHA-256; lo comprueban el reporte y el workflow). Mantengo las dos rutas
solo para cumplir la estructura del enunciado y la que ya usaba desde la EA2. Lo mismo pasa con `enriched_data.xlsx`.

## Clonar, instalar y ejecutar

```bash
git clone https://github.com/Jhon-Fuenwhv2024/infraestructura-ea3-enriquecimiento.git
cd infraestructura-ea3-enriquecimiento

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install .                        # pandas, openpyxl, lxml, beautifulsoup4, html5lib

python src/cleaning.py               # EA2: regenera cleaned_data.xlsx desde la base SQLite
python src/enrichement.py            # EA3: enriquecimiento → enriched_data.xlsx + enriched_report.txt
python src/verificar_conteos.py      # verificación independiente (termina con código 1 si algo no coincide)

# Opcional: volver a construir las fuentes de referencia
pip install ".[fuentes]" && python src/generar_fuentes.py
```

## Workflow de GitHub Actions (`.github/workflows/bigdata.yml`)

Corre con `push` (a `main` o `master`), `pull_request` y `workflow_dispatch`. Tiene un solo job en `ubuntu-latest`:

1. `actions/checkout@v4` y `actions/setup-python@v5` (Python 3.11).
2. `pip install .`
3. `python src/cleaning.py` (limpieza de la EA2).
4. `python src/enrichement.py` (enriquecimiento de la EA3).
5. `python src/verificar_conteos.py` (el job falla si el reporte o el Excel no coinciden con el conteo independiente).
6. Comprueba que existan los archivos de salida y que las dos copias de `ingestion.db` sean idénticas.
7. `actions/upload-artifact@v4` publica `ea2-cleaned-data` (Excel limpio y reporte de limpieza) y `ea3-enriched-data`
   (`enriched_data.xlsx` y `enriched_report.txt`).

Todo se ejecuta desde la **raíz del repositorio**, sin carpeta padre; las rutas del código se resuelven con `Path(__file__)`.

Revisé el YAML con `actionlint` y probé los mismos comandos en un clon limpio con un entorno virtual nuevo. Todavía **no** lo he corrido en GitHub Actions
porque aún no he hecho el push, así que no puedo afirmar el resultado en Actions.
