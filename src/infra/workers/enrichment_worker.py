"""
Worker de línea de comandos para procesar los enriquecimientos pendientes.
Se ejecuta de forma asíncrona, procesando en lotes para no saturar
los endpoints ni el presupuesto de LLM.
"""

import asyncio
from typing import Any

import httpx
from sqlalchemy import select

from src.core.application.enricher import EnriquecerConvocatoriaUseCase, PageFetcherPort
from src.core.domain.entities import Convocatoria
from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.models import ConvocatoriaORM
from src.infra.db.repository import SQLConvocatoriaRepository, SQLFuenteRepository
from src.infra.llm.client import build_llm_client
from src.infra.logging import get_logger

logger = get_logger(__name__)


class HttpxPageFetcher(PageFetcherPort):
    """Implementación de PageFetcherPort usando httpx con headers realistas."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-CL,es;q=0.9",
        }

    async def fetch_html(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=self.headers) as client:
            resp = await client.get(url)
            # Falla rápido si es un PDF o archivo binario
            content_type = resp.headers.get("Content-Type", "")
            if "application/pdf" in content_type.lower():
                raise ValueError("URL objetivo es un PDF, omitiendo enriquecimiento HTML.")
            resp.raise_for_status()
            return resp.text


async def run_enrichment_worker(batch_size: int = 5) -> None:
    """Busca convocatorias ABIERTAS pendientes de enriquecimiento y las procesa."""
    logger.info("Iniciando worker de enriquecimiento (Deep Scraping)", batch_size=batch_size)

    async with AsyncSessionLocal() as session:
        # Usamos json param filter o simplemente sacamos PENDIENTE / Null
        # JSONB query: metadatos->>'estado_enriquecimiento' IS NULL OR == 'PENDIENTE'
        # Y solo estado ABIERTO para no gastar en históricas
        
        # Filtramos a nivel de BD para eficiencia
        query = (
            select(ConvocatoriaORM)
            .where(ConvocatoriaORM.estado == "ABIERTO")
            .where(ConvocatoriaORM.url_detalle.is_not(None))
        )
        
        result = await session.execute(query)
        todas_abiertas = result.scalars().all()
        
        # Filtramos en memoria para evitar compatibilidad de dialectos SQL con JSON
        pendientes = []
        for c in todas_abiertas:
            estado_enr = c.metadatos.get("estado_enriquecimiento")
            if not estado_enr or estado_enr == "PENDIENTE":
                pendientes.append(c)
                
        if not pendientes:
            logger.info("No hay convocatorias pendientes de enriquecer")
            return
            
        lote = pendientes[:batch_size]
        logger.info("Procesando lote de convocatorias", size=len(lote), total_pendientes=len(pendientes))
        
        conv_repo = SQLConvocatoriaRepository(session)
        fuente_repo = SQLFuenteRepository(session)
        fetcher = HttpxPageFetcher()
        llm_client = build_llm_client()
        
        use_case = EnriquecerConvocatoriaUseCase(
            convocatoria_repo=conv_repo,
            fuente_repo=fuente_repo,
            fetcher=fetcher,
            llm_client=llm_client,
        )

        for orm_record in lote:
            # Convertimos a entidad de dominio
            conv_ent = Convocatoria(
                id=orm_record.id,
                fuente_id=orm_record.fuente_id,
                identificador_externo=orm_record.identificador_externo,
                titulo=orm_record.titulo,
                descripcion=orm_record.descripcion,
                url_detalle=orm_record.url_detalle,
                fecha_apertura=orm_record.fecha_apertura,
                fecha_cierre=orm_record.fecha_cierre,
                monto=orm_record.monto,
                region=orm_record.region,
                estado=orm_record.estado,
                metadatos=orm_record.metadatos,
                creado_en=orm_record.creado_en,
                actualizado_en=orm_record.actualizado_en,
            )
            
            # Ejecutamos caso de uso
            await use_case.execute(conv_ent)
            await session.commit()
            
            # Rate limit básico entre requests (3 segundos)
            await asyncio.sleep(3)
            
    logger.info("Lote de enriquecimiento procesado con éxito")
