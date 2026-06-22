import asyncio
from src.infra.config import settings
from src.infra.db.repository import SQLFuenteRepository
from src.infra.db.models import AsyncSessionLocal
from src.infra.cli import sync_single_source_config
from pathlib import Path
import yaml
from src.infra.rules_loader import load_rules_from_yaml
import sys

async def main():
    path = Path("rules/corfo.yaml")
    rules_config = load_rules_from_yaml(path)
    from src.core.domain.entities import Fuente
    from src.infra.cli import _apply_source_profile
    from typing import cast, Any
    fuente_db = Fuente(
        nombre=rules_config.nombre,
        url_base=cast(Any, rules_config.url_busqueda),
        configuracion_reglas=rules_config,
        activa=rules_config.activa,
    )
    fuente_db = _apply_source_profile(fuente_db)
    print("ID:", repr(fuente_db.id), type(fuente_db.id))

if __name__ == "__main__":
    asyncio.run(main())
