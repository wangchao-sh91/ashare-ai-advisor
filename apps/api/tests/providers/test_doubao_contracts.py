import json
from pathlib import Path

from mcp.types import CallToolResult

from app.providers.search_gateway import DoubaoSearchGateway, SearchRequest

FIXTURE = Path(__file__).parents[1] / "fixtures" / "doubao" / "web_search_call_tool_result.json"


class FixtureCaller:
    async def call_web_search(self, arguments: dict[str, object]) -> CallToolResult:
        assert arguments["SearchType"] == "web"
        return CallToolResult(
            content=[],
            structuredContent=json.loads(FIXTURE.read_text(encoding="utf-8")),
        )


async def test_sanitized_call_tool_result_matches_normalizer_contract() -> None:
    results = await DoubaoSearchGateway(FixtureCaller()).search(
        SearchRequest(query="sanitized contract query")
    )

    assert len(results) == 1
    assert results[0].citation.publisher == "中国证监会"
    assert results[0].relevance_score == 0.98
