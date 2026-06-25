import asyncio
import logging
from sqlalchemy import select

from src.infra.db.connection import AsyncSessionLocal
from src.infra.db.models import ConvocatoriaORM, FuenteORM
from src.core.application.normalizer import _is_valid_url

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("normalize_urls")

async def main():
    logger.info("Iniciando normalización de URLs inválidas en BD...")
    
    async with AsyncSessionLocal() as session:
        # Get all convocatorias with their fuentes to construct full URLs if needed
        result = await session.execute(
            select(ConvocatoriaORM, FuenteORM)
            .join(FuenteORM)
        )
        
        rows = result.all()
        to_delete = []
        to_close = []
        
        for conv, fuente in rows:
            url_detalle = conv.url_detail
            
            # Recreate the logic from normalizer.py
            if url_detalle:
                url_temp = (
                    str(fuente.url_base).rstrip("/") + "/" + url_detalle.lstrip("/")
                    if url_detalle.startswith("/")
                    else url_detalle
                )
                if not _is_valid_url(url_temp):
                    logger.info(f"Marcando para borrar (URL inválida): {conv.id} - {conv.titulo} (URL: {url_detalle})")
                    to_delete.append(conv)
                    continue  # Si es inválida, se descartaría, no se procesa más
            
            # Si llegó acá, la URL era None, vacía o válida
            # Si era None o inválida que llegó a None (aunque arriba ya descartamos las inválidas explícitas)
            # Replicamos el check de offline si la url_detail original es None o no es válida 
            # (en la lógica real "if not url_final" incluye cuando es None)
            
            # url_final según la lógica:
            url_final = None
            if url_detalle:
                url_temp = (
                    str(fuente.url_base).rstrip("/") + "/" + url_detalle.lstrip("/")
                    if url_detalle.startswith("/")
                    else url_detalle
                )
                if _is_valid_url(url_temp):
                    url_final = url_temp
                    
            if not url_final and conv.estado in ("ABIERTO", "PERMANENTE", "PROXIMAMENTE", "DESCONOCIDO"):
                descripcion = conv.descripcion or ""
                titulo = conv.titulo or ""
                texto_completo = f"{titulo} {descripcion}".lower()
                indicios_offline = [
                    "@", "correo", "presencial", "oficina de partes", 
                    "postulación en papel", "oficina de fomento", "oficina municipal"
                ]
                es_offline = any(ind in texto_completo for ind in indicios_offline)
                
                if not es_offline:
                    logger.info(f"Marcando para cerrar (Sin URL y sin indicios offline): {conv.id} - {conv.titulo}")
                    to_close.append(conv)

        
        logger.info(f"Total a borrar: {len(to_delete)}")
        logger.info(f"Total a cerrar: {len(to_close)}")
        
        # Aplicar borrados
        for conv in to_delete:
            await session.delete(conv)
            
        # Aplicar cerrados
        for conv in to_close:
            conv.estado = "CERRADO"
            # Nos aseguramos de inicializar metadatos si fuera necesario, 
            # aunque la DB default es dict.
            # En la vida real, el Bloque 2 es el que agrega url_check_failed, pero
            # por ahora dejamos el estado modificado tal cual lo hace normalizer.py
            
        await session.commit()
        logger.info("Normalización completada.")

if __name__ == "__main__":
    asyncio.run(main())
