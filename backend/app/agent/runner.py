"""
The AGENT LOOP.

    1. Send the owner's message + the list of tools to Gemini.
    2. If Gemini asks to call tools, run them and send back the results.
    3. Repeat until Gemini answers in plain text (or we hit the step limit).

Every tool call is recorded in `steps`, so the dashboard can show the agent's work.
"""
from datetime import date

from google.genai import types
from sqlalchemy.orm import Session

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOLS, run_tool
from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.services.extractor import make_client
from app.services.settings_service import get_factory_settings

MAX_STEPS = 8   # safety limit on tool-calling rounds


class AgentError(Exception):
    pass


def _declarations() -> list[types.FunctionDeclaration]:
    return [types.FunctionDeclaration(name=name, description=spec["description"],
                                      parameters_json_schema=spec["parameters"])
            for name, (_, spec) in TOOLS.items()]


def _short(result: dict) -> str:
    """One-line summary of a tool result for the steps panel."""
    if "error" in result:
        return f"error: {result['error']}"
    if "saved" in result:
        return f"saved {result.get('quote')} at ₹{result.get('price_per_piece')}/pc"
    if "total_cost" in result:
        return (f"true cost ₹{result['cost_per_piece']}/pc, safe price "
                f"₹{result['recommended_price_per_piece']}/pc, verdict: {result['verdict']}")
    if "summary" in result:
        return str(result["summary"])[:160]
    for key, value in result.items():
        if isinstance(value, list):
            return f"{len(value)} {key.replace('_', ' ')}"
    return str(result)[:160]


def run_agent(db: Session, message: str, history: list[dict] | None = None, client=None) -> dict:
    """history: [{"role": "user"|"assistant", "text": "..."}]. Returns {reply, steps}."""
    if client is None:
        if not GEMINI_API_KEY:
            raise AgentError("GEMINI_API_KEY is missing from .env")
        client = make_client()

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT.format(
            factory_name=get_factory_settings(db).factory_name, today=date.today().isoformat()),
        tools=[types.Tool(function_declarations=_declarations())],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )

    contents = []
    for turn in (history or [])[-10:]:
        role = "model" if turn.get("role") == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=turn.get("text", ""))]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

    steps = []
    for _ in range(MAX_STEPS):
        try:
            response = client.models.generate_content(model=GEMINI_MODEL, contents=contents, config=config)
        except Exception as e:
            raise AgentError(f"Gemini error: {type(e).__name__}: {e}") from e

        calls = response.function_calls or []
        if not calls:
            return {"reply": (response.text or "").strip() or "Sorry, I could not answer that.",
                    "steps": steps}

        # Keep Gemini's own turn exactly as it sent it, then answer each tool call
        contents.append(response.candidates[0].content)
        result_parts = []
        for call in calls:
            args = dict(call.args or {})
            result = run_tool(db, call.name, args)
            steps.append({"tool": call.name, "args": args, "result": _short(result)})
            result_parts.append(types.Part.from_function_response(name=call.name, response={"result": result}))
        contents.append(types.Content(role="user", parts=result_parts))

    return {"reply": "I needed too many steps for that. Please ask a simpler question.", "steps": steps}
