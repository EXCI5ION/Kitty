# Kitty

Kitty es una aplicación de código abierto para organizar y ejecutar análisis
estadístico univariado sobre matrices ómicas.

La primera etapa del proyecto implementa una importación supervisada de matrices
delimitadas en formato CSV o TXT. El usuario puede revisar la matriz original,
trasponerla, delimitar el bloque de datos,
editar los nombres mostrados y asignar manualmente las clases experimentales.
Kitty conserva los identificadores originales para mantener la trazabilidad.

## Desarrollo

Kitty requiere Python 3.12 o 3.13.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\kitty.exe
```

Durante el desarrollo también puede ejecutarse directamente, sin instalación
editable:

```powershell
.\.venv\Scripts\python.exe .\run_kitty.py
```

Desde un IDE se puede utilizar `run_kitty.py` como configuración de ejecución.


