"""One-off maintenance: backfill region using only YAML defaults + coercion, without LLM."""
import asyncio

from src.core.application.normalizer import _coerce_region
from src.core.domain.entities import RulesConfig
from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.models import ConvocatoriaORM, FuenteORM
from src.infra.logging import get_logger

logger = get_logger(__name__)


async def main() -> int:
    changed = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            __import__("sqlalchemy")
            .select(ConvocatoriaORM)
            .where(ConvocatoriaORM.region.is_(None))
        )
        rows = result.scalars().all()

        for conv in rows:
            fuente = await session.get(FuenteORM, conv.fuente_id)
            if not fuente:
                continue
            fallback = None
            try:
                rc = RulesConfig.model_validate_json(fuente.configuracion_yaml)
                fallback = rc.region_defecto
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "No se pudo leer region_defecto",
                    fuente_id=str(fuente.id),
                    exc=exc,
                )
            if fallback:
                conv.region = fallback
                changed += 1
            else:
                conv.region = _coerce_region(conv.region)
                if conv.region:
                    changed += 1
        await session.commit()
    logger.info("Backfill regional terminado (sin LLM)", changed=changed)
    return changed


if __name__ == "__main__":
    asyncio.run(main())
