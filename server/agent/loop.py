"""
The hand-rolled agent loop.

Phases 2–3 left this file with three near-identical loops (run_account_agent,
stream_account_agent, stream_knowledge_agent). The only things that EVER differed
between the two streaming ones were:
    (a) the system prompt,
    (b) the tool declarations passed to the model,
    (c) the tool registry the loop dispatches through.

Phase 4 cashes in the promise those functions kept making ("Phase 4 is where we
factor the shared loop out"). Your job in this file:

    1. Describe a specialist agent as DATA  -> fill in `AgentConfig`.
    2. Write the ONE generic streaming loop -> fill in `stream_agent`, by PORTING
       your existing stream_account_agent and swapping the 3 hard-coded bits for
       fields off `agent`.
    3. Once stream_agent works, the two old streaming functions below become dead
       code — delete them (they're kept now ONLY as the thing you port from).

Still by hand — no agent framework (see the build plan's framework note).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from tools.account import ACCOUNT_TOOL_DECLS, TOOLS
from tools.knowledge import KNOWLEDGE_TOOL_DECLS
from tools.knowledge import TOOLS as KNOWLEDGE_TOOLS
from utils.constants import GEMINI_FLASH_LITE_MODEL

MAX_ITERS = 6  # cost guardrail: never loop forever (CLAUDE.md cost rule)
EMPTY_RETRY_LIMIT = 2 # if the LLM client comes back with an empty response, allow for retries

ACCOUNT_SYSTEM_PROMPT = (
    """
    You are a helpdesk agent that answers questions about customers, their orders and subscriptions.
    To answer questions about a customer, you must first call get_customer(email) to get the id,
    then call get_orders/get_subscription with that id.
    If get_customer returns found=false, say you couldn't find the customer instead of inventing data.
    Be concise, and answer the actual question asked.
    """
)

# The whole point of RAG is grounding: the model must answer from RETRIEVED text,
# not its own memory, and tell the user WHERE the answer came from.
KNOWLEDGE_SYSTEM_PROMPT = (
    """
    You are a helpdesk knowledge agent. You answer "how do I..." and policy
    questions (refunds, shipping, billing, account/login, support hours) using the
    company's help-center articles.

    Always call search_docs first to retrieve relevant article chunks, then answer
    using ONLY the information in those chunks. Do not rely on prior knowledge or
    invent details. If the retrieved chunks don't contain the answer, say you
    couldn't find it in the help center rather than guessing.

    Cite your source: end your answer with the title of the article you used,
    e.g. (Source: Refunds & Returns). Be concise and answer the actual question.
    """
)


# ===========================================================================
# PHASE 4 — STEP 1: AgentConfig — a specialist agent described as DATA.
#
# This is the heart of the refactor. Instead of one streaming function per agent,
# each specialist becomes an instance of this dataclass; the generic loop reads
# its fields. Adding Phase 5's Action agent later then becomes "make one more
# AgentConfig", not "copy the whole loop again".
#
# TODO: declare the four fields the loop needs. Look at what stream_account_agent
#   and stream_knowledge_agent below ACTUALLY differ on — those differences ARE
#   the fields:
#       name: str                                    # "account"/"knowledge" — for logs + routing
#       system_prompt: str                           # -> goes to config.system_instruction
#       tool_decls: list[types.FunctionDeclaration]  # -> goes to types.Tool(function_declarations=...)
#       tools: dict[str, Callable[..., Awaitable[dict]]]  # name -> async callable to dispatch to
#   (Awaitable/Callable are imported up top so you can type `tools` precisely.)
# ===========================================================================
@dataclass(frozen=True)
class AgentConfig:
    # TODO: add the four fields described above.
    name: str
    system_prompt: str
    tool_decls: list[types.FunctionDeclaration]
    tools: dict[str, Callable[..., Awaitable[dict]]]


# ===========================================================================
# PHASE 4 — STEP 2: stream_agent — the ONE streaming loop, parameterized.
#
# Port your stream_account_agent (below) almost verbatim. The ONLY changes:
#   - config.system_instruction      = agent.system_prompt   (was the constant)
#   - types.Tool(function_declarations=agent.tool_decls)     (was ACCOUNT_TOOL_DECLS)
#   - dispatch: await agent.tools[function_call.name](...)   (was TOOLS[...])
# Everything else — the chunk-by-chunk consume, the None guards, the two-append
# feed-back, the empty-retry + iteration-cap handling — is IDENTICAL. Don't
# re-derive it; move it.
#
# Event contract stays the same so the SAME frontend can render ANY agent:
#     {"type": "tool",  "name": str, "args": dict}
#     {"type": "delta", "text": str}
#     {"type": "done"}
# ===========================================================================
async def stream_agent(agent: AgentConfig, message: str, session: AsyncSession):
    """Async generator: drives `agent`'s tool-calling loop, yielding SSE events."""
    # TODO: build the genai client + GenerateContentConfig, but read prompt/decls
    #   from `agent` instead of hard-coding them.
    #
    # TODO: run the same for-loop over MAX_ITERS you already wrote in
    #   stream_account_agent: open the stream, consume chunks (yield deltas as
    #   they arrive), and on a function_call -> yield a {"type":"tool",...} event,
    #   dispatch via agent.tools[...], append the model turn + function response,
    #   then continue. On a text-only turn yield {"type":"done"} and return.
    #
    # TODO: keep the empty-retry guard and the post-loop iteration-cap fallback.
    #
    # TIP while testing: print(f"[{agent.name} iter {i}] ...") so the logs tell you
    #   WHICH agent ran — handy once the orchestrator is picking for you.
    """Async generator: yields {type: tool|delta|done} events (see contract above)."""
    client = genai.Client()

    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=agent.tool_decls)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=1000,
        system_instruction=agent.system_prompt,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=message)]),
    ]

    empty_retries = 0
    for i in range(MAX_ITERS):
        stream = await client.aio.models.generate_content_stream(
        model=GEMINI_FLASH_LITE_MODEL, contents=contents, config=config)

        function_call = None
        produced_text = False
        async for chunk in stream:
            # some chunks have no candidates
            if not chunk.candidates:
                continue
            content = chunk.candidates[0].content
            # some chunks contain only metadata (i.e finish reason, usage, etc) but no parts
            if content is None or content.parts is None:
                continue
            for part in content.parts:
                if part.function_call:
                    function_call = part.function_call
                elif part.text:
                    produced_text = True
                    yield {"type": "delta", "text": part.text}

        # there IS a tool call => tell the UI, then run it (async + session):
        if function_call is not None:
            yield {"type": "tool", "name": function_call.name, "args": dict(function_call.args)}
            result = await agent.tools[function_call.name](session, **function_call.args)
            print(f"{agent.name} [iter {i}] {function_call.name}({dict(function_call.args)}) -> {result}")

            contents.append(types.Content(
                role="model",
                parts=[types.Part(function_call=function_call)]
            ))
            contents.append(types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name=function_call.name, response={"result": result}
                    )
                ]
            ))
            continue

        if produced_text:
            yield {"type": "done"}
            return

        empty_retries += 1
        if empty_retries <= EMPTY_RETRY_LIMIT:
            print(f"{agent.name} [iter {i}] empty turn - retrying ({empty_retries})")
            continue
        yield {"type": "delta", "text": "Sorry, I couldn't generate a response. Please try again."}
        yield {"type": "done"}
        return

    yield {"type": "delta", "text": "Sorry — I couldn't complete that within the step limit."}
    yield {"type": "done"}


# ===========================================================================
# run_account_agent — Phase 2 NON-streaming reference (kept unchanged).
#
# Returns one final string instead of yielding events. The simplest readable
# version of the tool-calling handshake; keep it as a teaching reference.
# ===========================================================================
async def run_account_agent(message: str, session: AsyncSession) -> str:
    """Run the tool-calling loop until the model gives a final text answer."""
    client = genai.Client()

    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=ACCOUNT_TOOL_DECLS)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=1000,
        system_instruction=ACCOUNT_SYSTEM_PROMPT,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=message)]),
    ]
    empty_retries = 0
    for i in range(MAX_ITERS):
        response = await client.aio.models.generate_content(
            model=GEMINI_FLASH_LITE_MODEL, contents=contents, config=config
        )

        model_turn = response.candidates[0].content
        parts = model_turn.parts if (model_turn and model_turn.parts) else []

        function_call = None
        final_text = []
        for part in parts:
            if part.function_call:
                function_call = part.function_call
            elif part.text:
                final_text.append(part.text)

        if not function_call:
            if final_text:
                return "\n".join(final_text)
            empty_retries += 1
            if empty_retries <= EMPTY_RETRY_LIMIT:
                continue
            return "Sorry, I couldn't generate a response. Please try again."

        fn = TOOLS[function_call.name]
        result = await fn(session, **function_call.args)

        contents.append(model_turn)
        fr = types.Part.from_function_response(
            name=function_call.name, response={"result": result})
        contents.append(types.Content(role="user", parts=[fr]))

    return "Sorry — I couldn't complete that within the step limit."


if __name__ == "__main__":
    import asyncio

    from db.session import AsyncSessionLocal, engine

    async def _smoke():
        ACCOUNT_AGENT = AgentConfig(
            name="account",
            system_prompt=ACCOUNT_SYSTEM_PROMPT,
            tool_decls=ACCOUNT_TOOL_DECLS,
            tools=ACCOUNT_TOOLS,
        )
        async with AsyncSessionLocal() as session:
            # Once stream_agent + agent/agents.py are filled in, switch this to:
            #   from agent.agents import AGENTS
            #   async for event in stream_agent(AGENTS["account"], "...", session):
            async for event in stream_agent(
                ACCOUNT_AGENT,
                "what is the latest subscription for alice@example.com?",
                session
            ):
                print("EVENT: ", event)
        await engine.dispose()

    asyncio.run(_smoke())
