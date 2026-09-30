from setuptools import setup

setup(
    name="fuentes_jhon_bigdata_ea3",
    version="1.0.0",
    description=(
        "EA3 - Enriquecimiento de datos (Open Brewery DB limpio) con fuentes "
        "JSON, XLSX, CSV, XML, HTML y TXT"
    ),
    author="Jhon Jairo Fuentes Turizo",
    python_requires=">=3.10",
    packages=[],
    install_requires=[
        "pandas>=2.0.0",
        "openpyxl>=3.1.0",
        "lxml>=4.9.0",
        "beautifulsoup4>=4.12.0",
        "html5lib>=1.1",
    ],
    extras_require={
        # solo para regenerar src/static/fuentes con src/generar_fuentes.py
        "fuentes": ["pycountry>=24.6.1", "babel>=2.14.0", "timezonefinder>=6.5.0"],
    },
)
