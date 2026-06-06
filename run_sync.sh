#!/bin/bash
cd "$(dirname "$0")"

# Ejecutar usando el entorno virtual local
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

export PYTHONPATH=.
# Ejecutar sync de todas las reglas configuradas
python -m src.infra.cli sync-rules

# Ejecutar limpieza de base de datos (>6 meses)
python -m src.infra.cli clean-db
