"""
Orchestrator agent (Phase 4) — SCAFFOLD. Fill in the TODOs.

This is the new concept for Phase 4: a TRIAGE step. Before any specialist runs,
the orchestrator looks at the user's message, decides what KIND of request it is
(account / knowledge / action), and routes it to the right agent. We chose the
simplest pattern from the build plan — an LLM CLASSIFIER:

    intent = await classify(message)          # one cheap, tool-less LLM call
    async for ev in stream_agent(AGENTS[intent], message, session):
        yield ev                              # delegate to that specialist

Two pieces to build:
  1. classify(message) -> one of INTENTS. A tiny LLM call: no tools, a tight
     system prompt, a hard cap on output tokens. It returns a LABEL, nothing else.
  2. stream_orchestrator(message, session) -> the generator the endpoint streams.
     It classifies, tells the UI where it routed (a new "route" event), then either
     delegates to a specialist or — for "action" — says that's coming in Phase 5.

Cost note (CLAUDE.md): classify() adds one LLM call per request, so keep it cheap —
max_output_tokens tiny, thinking off. It's classifying, not writing prose.

Event contract — same as the specialists, PLUS one new event so the UI/logs can
show the routing decision:
    {"type": "route", "intent": str}   # NEW: which specialist we picked
    {"type": "tool",  "name": str, "args": dict}
    {"type": "delta", "text": str}
    {"type": "done"}
"""
from __future__ import annotations

from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from agent.agents import AGENTS
from agent.loop import stream_agent
from utils.constants import GEMINI_FLASH_LITE_MODEL

# The labels classify() is allowed to produce. "account" and "knowledge" must
# match keys in AGENTS; "action" is recognized now but not yet served (Phase 5).
INTENTS = ("account", "knowledge", "action")
DEFAULT_INTENT = "knowledge"  # safe fallback if the model returns something off-list

CLASSIFIER_SYSTEM_PROMPT = (
    """
    You are a triage classifier for a customer-support assistant. Read the user's
    message and decide which specialist should handle it. Reply with EXACTLY ONE
    word, lowercase, no punctuation, from this list:

      account    - questions about a specific customer's data: their orders,
                   order status, subscriptions, billing records, account details.
      knowledge  - "how do I..." and general policy questions answered from the
                   help center: refund policy, shipping times, support hours, etc.
      action     - requests to DO something with side effects: issue a refund,
                   cancel a subscription, send an email, open a ticket.

    Output only the single word. Do not explain.
    """
)


async def classify(message: str) -> str:
    """Return one of INTENTS for `message`. A cheap, tool-less classification call.

    Pointers:
      - Build a genai.Client() and a GenerateContentConfig with:
          system_instruction=CLASSIFIER_SYSTEM_PROMPT,
          max_output_tokens=...        # tiny — it's one word (e.g. 5)
          thinking_config=types.ThinkingConfig(thinking_budget=0),
          # NO tools here — classification doesn't call functions.
      - One non-streaming call is fine (it's short):
          resp = await client.aio.models.generate_content(
              model=GEMINI_FLASH_LITE_MODEL,
              contents=[types.Content(role="user", parts=[types.Part(text=message)])],
              config=config)
      - Pull the text out (resp.text, or join the parts), then NORMALIZE it:
          label = (resp.text or "").strip().lower()
        The model may add stray whitespace/quotes/a period — be defensive.
      - VALIDATE against INTENTS. If the label isn't one of them, fall back to
        DEFAULT_INTENT instead of trusting a bad label. (Tip: `if "account" in
        label ... elif "action" in label ...` is a forgiving way to map a slightly
        chatty reply onto a clean intent.)
      - print(f"[orchestrator] classified -> {label}") so you can watch routing.
    """
    # TODO: implement per the pointers above.
    client = genai.Client()

    config = types.GenerateContentConfig(
        max_output_tokens=10,
        system_instruction=CLASSIFIER_SYSTEM_PROMPT,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    resp = await client.aio.models.generate_content(
        model=GEMINI_FLASH_LITE_MODEL,
        contents=[types.Content(role="user", parts=[types.Part(text=message)])],
        config=config
    )

    label = (resp.text or "").strip().lower()
    intent = DEFAULT_INTENT 
    # we do substring checing in case the returned string from the LLM contains more than just the label
    # i.e if the LLM returns the string "this is an account classification", 
    # we check for the substring "account"
    if "account" in label:
        intent = "account"
    elif "knowledge" in label:
        intent = "knowledge"
    elif "action" in label:
        intent = "action"

    print(f"[orchestrator] classified -> {label}")
    return intent

async def stream_orchestrator(message: str, session: AsyncSession):
    """Async generator: classify, announce the route, then delegate (or stub action).

    Pointers:
      1. intent = await classify(message)
      2. yield {"type": "route", "intent": intent}        # let the UI show it
      3. Branch:
           - if intent == "action":  the Action agent doesn't exist until Phase 5.
             yield a {"type":"delta", ...} explaining that, then {"type":"done"};
             return.
           - else: look up AGENTS[intent] and DELEGATE by re-yielding every event
             the specialist produces:
                 async for event in stream_agent(AGENTS[intent], message, session):
                     yield event
             (stream_agent already emits the tool/delta/done events AND the final
              "done", so you don't add your own here.)
      Defensive touch: if intent somehow isn't in AGENTS, fall back to
      AGENTS[DEFAULT_INTENT] so a bad label can't crash the stream.
    """
    # TODO: implement per the pointers above.
    intent = await classify(message)
    # yield so that it gets returned to the UI over SSE
    yield {"type": "route", "intent": intent}

    # TODO: implement action agent in phase 5
    if intent == "action":
        yield {"type": "delta", "text": "Sorry, we cannot process this action right now."}
        yield {"type": "done"}
        return
    else:
        agent_config = AGENTS[intent] if intent in AGENTS else AGENTS[DEFAULT_INTENT]
        async for event in stream_agent(agent_config, message, session):
            yield event
