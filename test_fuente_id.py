import asyncio
from pathlib import Path

from src.infra.rules_loader import load_rules_from_yaml


async def main():
    path = Path("rules/corfo.yaml")
    rules_config = load_rules_from_yaml(path)
    from typing import Any, cast

    from src.core.domain.entities import Fuente
    from src.infra.cli import _apply_source_profile
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
