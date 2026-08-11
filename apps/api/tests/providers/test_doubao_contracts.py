import json
from pathlib import Path

FIXTURES = Path(__file__).parents[1] / "fixtures" / "doubao"


def test_redacted_live_success_contract_has_required_metadata() -> None:
    payload = json.loads((FIXTURES / "search_success.json").read_text())
    result = payload["Result"]["WebResults"][0]
    assert {
        "Id",
        "Title",
        "SiteName",
        "Url",
        "Snippet",
        "Summary",
        "PublishTime",
        "RankScore",
        "AuthInfoDes",
        "AuthInfoLevel",
    } <= set(result)


def test_redacted_error_contracts_cover_quota_and_rate_limit() -> None:
    codes = {
        json.loads((FIXTURES / name).read_text())["ResponseMetadata"]["Error"]["Code"]
        for name in ("search_quota_error.json", "search_rate_limit_error.json")
    }
    assert codes == {"10406", "700429"}
