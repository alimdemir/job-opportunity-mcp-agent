"""MCP araçlarını kullanan küçük bir ajan döngüsü.

Model sağlayıcıdan bağımsızdır: `generate(messages, tools) -> str` imzasına uyan
herhangi bir fonksiyon verilebilir (Colab'da Qwen2.5-Instruct, testlerde sahte model).
Model araç çağırmak istediğinde Qwen biçimini kullanır:

    <tool_call>
    {"name": "search_postings", "arguments": {"keyword": "Python"}}
    </tool_call>
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)

SYSTEM_PROMPT = (
    "Sen bir iş fırsatı asistanısın. Yalnızca araçlardan dönen bilgilere dayan; "
    "ilanda yazmayan bir bilgiyi tahmin etme, 'belirtilmemiş' de. "
    "Yanıtı Türkçe ve kısa ver, her ilanı id numarasıyla an."
)
FIT_RULE = (
    " Bir ilanı kullanıcıya önermeden önce mutlaka check_fit aracını kullanıcının becerileri ve "
    "ülkesiyle çağır; eligible=false ise ilanı uygun gösterme ve nedenini açıkça söyle."
)


@dataclass
class Step:
    kind: str                      # "tool_call" | "tool_result" | "answer" | "error"
    content: Any
    tool: str | None = None


@dataclass
class AgentResult:
    answer: str | None
    steps: list[Step] = field(default_factory=list)


def mcp_tools_to_openai(tools) -> list[dict]:
    """MCP `list_tools()` çıktısını sohbet şablonlarının beklediği fonksiyon tanımına çevirir."""
    return [{
        "type": "function",
        "function": {"name": t.name, "description": t.description or "", "parameters": t.inputSchema},
    } for t in tools]


def parse_tool_calls(text: str) -> list[dict]:
    calls = []
    for raw in TOOL_CALL_RE.findall(text):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "name" in data:
            calls.append({"name": data["name"], "arguments": data.get("arguments") or {}})
    return calls


def _result_text(result) -> str:
    if getattr(result, "structuredContent", None) is not None:
        return json.dumps(result.structuredContent, ensure_ascii=False)
    return "\n".join(getattr(c, "text", "") for c in result.content)


async def run_agent(question: str, session, generate: Callable[[list[dict], list[dict]], str | Awaitable[str]],
                    max_steps: int = 4, allowed_tools: set[str] | None = None) -> AgentResult:
    """Soru -> (araç çağrısı -> araç sonucu)* -> yanıt döngüsü.

    `max_steps` sınırı, modelin aynı aramayı tekrar tekrar üretip gecikmeyi büyütmesini önler.
    `allowed_tools` verilirse modele yalnız bu araçlar gösterilir (sürüm karşılaştırması için).
    """
    listed = (await session.list_tools()).tools
    if allowed_tools is not None:
        listed = [t for t in listed if t.name in allowed_tools]
    tools = mcp_tools_to_openai(listed)
    names = {t["function"]["name"] for t in tools}
    system = SYSTEM_PROMPT + (FIT_RULE if "check_fit" in names else "")
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    result = AgentResult(answer=None)
    seen: set[str] = set()

    for _ in range(max_steps):
        out = generate(messages, tools)
        if hasattr(out, "__await__"):
            out = await out
        calls = parse_tool_calls(out)
        messages.append({"role": "assistant", "content": out})
        if not calls:
            result.answer = out.strip()
            result.steps.append(Step("answer", result.answer))
            return result
        for call in calls:
            key = json.dumps(call, sort_keys=True, ensure_ascii=False)
            result.steps.append(Step("tool_call", call["arguments"], call["name"]))
            if call["name"] not in names:
                text = f"{call['name']} adlı bir araç yok."
                result.steps.append(Step("error", text, call["name"]))
            elif key in seen:  # aynı çağrı ikinci kez: yeni bilgi getirmez
                text = "Bu çağrı zaten yapıldı; mevcut sonuçlarla yanıt ver."
            else:
                seen.add(key)
                tool_result = await session.call_tool(call["name"], call["arguments"])
                text = _result_text(tool_result)
                if tool_result.isError:
                    result.steps.append(Step("error", text, call["name"]))
            result.steps.append(Step("tool_result", text, call["name"]))
            messages.append({"role": "tool", "name": call["name"], "content": text})

    result.steps.append(Step("error", f"{max_steps} adım sınırına ulaşıldı"))
    return result
