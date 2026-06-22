import asyncio

from src.core.application.monitoreo import MonitoreoUseCase

from src.infra.cli import _apply_source_profile, _get_notifier, _get_scraper
from src.infra.db.models import AsyncSessionLocal
from src.infra.db.repository import (
    SQLConvocatoriaRepository,
    SQLFuenteRepository,
    SQLNotificacionRepository,
    SQLSnapshotRepository,
)
from src.infra.logging import configure_logging


async def main():
    configure_logging()
    async with AsyncSessionLocal() as session:
        frepo = SQLFuenteRepository(session)
        fuentes = await frepo.get_all_active()
        if not fuentes:
            print("No hay fuentes activas")
            return

        f = fuentes[0]
        print(f"Probando scrapeo de: {f.nombre}")
        f = _apply_source_profile(f)
        scraper = _get_scraper(f)
        srepo = SQLSnapshotRepository(session)
        crepo = SQLConvocatoriaRepository(session)
        nrepo = SQLNotificacionRepository(session)
        notifier = await _get_notifier(session)

        use_case = MonitoreoUseCase(scraper, srepo, crepo, notifier, nrepo)
        try:
            await use_case.ejecutar_monitoreo(f)
            print("Monitoreo ejecutado correctamente")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
