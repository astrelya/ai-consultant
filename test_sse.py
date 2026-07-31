import asyncio
import httpx
from backend.main import app

async def test():
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/stream/invalid-project")
        assert response.status_code == 404
        
        async with ac.stream("GET", "/stream/valid-project") as response:
            assert response.status_code == 404 # since we don't have mock

if __name__ == "__main__":
    asyncio.run(test())
