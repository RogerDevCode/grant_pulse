import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.domain.entities import Fuente, Snapshot, RulesConfig, SelectorConfig
from src.infra.scraping.consensus import ConsensusScraper
from src.infra.scraping.funding_pipeline import CompositeFundingScraper
from src.infra.sources.catalog import SourceProfile, ScrapeStep

@pytest.fixture
def mock_fuente():
    return Fuente(
        nombre="TestFuente",
        url_base="https://test.com",
        configuracion_reglas=RulesConfig(
            nombre="Test",
            url_busqueda="https://test.com/list",
            selectores=SelectorConfig(
                contenedor_items=".item",
                identificador=".title",
                titulo=".title"
            )
        )
    )

@pytest.mark.asyncio
async def test_consensus_scraper_success(mock_fuente):
    primary = AsyncMock()
    secondary = AsyncMock()
    
    item = {"titulo": "Fondo 1", "identificador": "f1"}
    primary.extract.return_value = [item]
    secondary.extract.return_value = [item]
    
    scraper = ConsensusScraper(primary, secondary)
    snapshot = Snapshot(fuente_id=mock_fuente.id, contenido_crudo="<html></html>", hash_contenido="h", estado_ejecucion="SUCCESS")
    
    results = await scraper.extract(snapshot, mock_fuente)
    
    assert len(results) == 1
    assert results[0]["titulo"] == "Fondo 1"
    assert primary.extract.called
    assert secondary.extract.called

@pytest.mark.asyncio
async def test_consensus_scraper_discrepancy_with_referee(mock_fuente):
    primary = AsyncMock()
    secondary = AsyncMock()
    referee = AsyncMock()
    
    primary.extract.return_value = [{"titulo": "A"}]
    secondary.extract.return_value = [{"titulo": "B"}]
    referee.extract.return_value = [{"titulo": "Ref"}]
    
    scraper = ConsensusScraper(primary, secondary, referee=referee)
    snapshot = Snapshot(fuente_id=mock_fuente.id, contenido_crudo="<html></html>", hash_contenido="h", estado_ejecucion="SUCCESS")
    
    results = await scraper.extract(snapshot, mock_fuente)
    
    assert results[0]["titulo"] == "Ref"
    assert referee.extract.called

@pytest.mark.asyncio
async def test_pipeline_auto_healing(mock_fuente):
    # Mock profile with html_static step
    profile = SourceProfile(
        key="test",
        root_url="https://test.com",
        list_url="https://test.com/list",
        steps=(ScrapeStep(url="https://test.com", fetcher="html_static", extractor="html_static"),)
    )
    
    mock_static = AsyncMock()
    # First call returns empty, then after healing we mock it to return something
    mock_static.extract.side_effect = [[], [{"titulo": "Healed"}]]
    mock_static.fetch.return_value = Snapshot(fuente_id=mock_fuente.id, contenido_crudo="<html></html>", hash_contenido="h", estado_ejecucion="SUCCESS")
    
    # Mock LLM client for healing
    mock_llm_client = MagicMock()
    mock_llm_client.heal_selectors = AsyncMock(return_value={"titulo": ".new-title"})
    
    from unittest.mock import patch
    with patch("src.infra.llm.client.build_llm_client", return_value=mock_llm_client):
        pipeline = CompositeFundingScraper(profile, html_static=mock_static)
        snapshot = await pipeline.fetch(mock_fuente)
        results = await pipeline.extract(snapshot, mock_fuente)
        
        assert results[0]["titulo"] == "Healed"
        assert mock_llm_client.heal_selectors.called
