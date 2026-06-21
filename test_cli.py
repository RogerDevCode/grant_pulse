import asyncio
from src.infra.cli import run_all_active_sources

async def main():
    try:
        await run_all_active_sources()
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
