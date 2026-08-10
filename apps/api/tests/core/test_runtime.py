import json

import httpx
import pytest

from app.core.settings import ProviderMode, Settings
from app.main import create_app


@pytest.mark.asyncio
async def test_fake_provider_mode_becomes_ready_and_streams_without_credentials() -> None:
    settings = Settings(provider_mode=ProviderMode.FAKE)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        readiness = await client.get("/ready")
        response = await client.post(
            "/api/chat/stream",
            json={"question": "分析贵州茅台最近有什么公告？"},
        )

    assert readiness.status_code == 200
    assert readiness.json() == {"status": "ready", "missing": []}
    frames = response.text.strip().split("\n\n")
    names = [frame.splitlines()[0] for frame in frames]
    assert names[0] == "event: accepted"
    assert "event: status" in names
    assert names[-1] == "event: answer-complete"
    payload = json.loads(frames[-1].splitlines()[1].removeprefix("data: "))
    assert payload["answer"]["citations"][0]["url"] == "https://example.com/notice"
