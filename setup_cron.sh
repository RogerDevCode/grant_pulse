#!/bin/bash
# Script para instalar el cron job de GrantPulse en Linux

# Obtener ruta absoluta del proyecto
PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# Crear script runner
cat << 'EOF' > "$PROJECT_DIR/run_sync.sh"
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
EOF

chmod +x "$PROJECT_DIR/run_sync.sh"

# Instalar en el crontab del usuario actual (ejecutar a las 08:00 y a las 20:00)
(crontab -l 2>/dev/null | grep -v "GrantPulse"; echo "0 8,20 * * * $PROJECT_DIR/run_sync.sh >> $PROJECT_DIR/cron.log 2>&1 # GrantPulse") | crontab -

echo "✅ Script run_sync.sh generado y permisos concedidos."
echo "✅ Cron instalado correctamente en tu Linux."
echo "El scraper se ejecutará todos los días a las 08:00 y a las 20:00."
echo "Puedes verificar con: crontab -l"
