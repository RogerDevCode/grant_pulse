#!/bin/bash
# Script para sincronizar todas las reglas y ejecutar el monitoreo inicial
docker compose exec api python -m src.infra.cli sync-rules
