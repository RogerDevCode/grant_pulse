import pytest
import respx


@pytest.mark.asyncio
@respx.mock
async def test_one():
    pass

@respx.mock
@pytest.mark.asyncio
async def test_two():
    pass
