import json
import sys
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import parse_tool_calls, run_agent  # noqa: E402
from server import mcp  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_tools_are_listed():
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert names == {"search_postings", "get_posting", "check_fit"}


async def test_search_filters_remote():
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        res = await client.call_tool("search_postings", {"keyword": "python", "remote_only": True, "limit": 10})
    rows = res.structuredContent["result"]
    assert rows and all(r["work_mode"] == "remote" for r in rows)


async def test_unknown_posting_returns_tool_error():
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        res = await client.call_tool("get_posting", {"posting_id": 1})
    assert res.isError
    assert "bulunamadı" in res.content[0].text


def test_parse_tool_calls_ignores_broken_json():
    text = '<tool_call>{"name": "get_posting", "arguments": {"posting_id": 5}}</tool_call><tool_call>{bozuk</tool_call>'
    assert parse_tool_calls(text) == [{"name": "get_posting", "arguments": {"posting_id": 5}}]


async def test_agent_loop_with_scripted_model():
    script = iter([
        '<tool_call>{"name": "search_postings", "arguments": {"keyword": "PostgreSQL", "remote_only": true}}</tool_call>',
        '<tool_call>{"name": "search_postings", "arguments": {"keyword": "PostgreSQL", "remote_only": true}}</tool_call>',
        "Uzaktan ve PostgreSQL kullanan ilanlar bulundu.",
    ])

    def fake_model(messages, tools):
        assert {t["function"]["name"] for t in tools} == {"search_postings", "get_posting", "check_fit"}
        assert "check_fit" in messages[0]["content"]  # ön kontrol kuralı sistem istemine eklendi
        return next(script)

    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await run_agent("Uzaktan PostgreSQL ilanı var mı?", client, fake_model)

    kinds = [s.kind for s in result.steps]
    assert kinds == ["tool_call", "tool_result", "tool_call", "tool_result", "answer"]
    assert "zaten yapıldı" in result.steps[3].content      # tekrar eden çağrı sunucuya gitmedi
    assert json.loads(result.steps[1].content)["result"]


async def test_agent_stops_at_step_limit():
    def looping_model(messages, tools):
        n = sum(m["role"] == "tool" for m in messages)
        return f'<tool_call>{{"name": "get_posting", "arguments": {{"posting_id": {n}}}}}</tool_call>'

    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await run_agent("döngü", client, looping_model, max_steps=2)
    assert result.answer is None
    assert result.steps[-1].kind == "error"


async def test_check_fit_flags_region_restricted_remote_job():
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        res = await client.call_tool("check_fit", {"posting_id": 49156689, "skills": ["Python", "Docker", "AWS"]})
    fit = res.structuredContent
    assert fit["company"] == "Snout" and fit["region_restricted"] and not fit["eligible"]
    assert fit["matched_skills"] == ["AWS", "Python"]


async def test_allowed_tools_hides_tools_and_rejects_unknown_calls():
    seen_tools = []

    def model(messages, tools):
        seen_tools.append({t["function"]["name"] for t in tools})
        if len(messages) == 2:
            return '<tool_call>{"name": "check_fit", "arguments": {"posting_id": 1, "skills": []}}</tool_call>'
        return "tamam"

    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await run_agent("x", client, model, allowed_tools={"search_postings", "get_posting"})
    assert seen_tools[0] == {"search_postings", "get_posting"}
    assert result.steps[1].kind == "error" and "araç yok" in result.steps[1].content
