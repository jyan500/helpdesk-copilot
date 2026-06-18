"""
The hand-rolled agent loop (Phase 2) — SCAFFOLD. Fill in the TODOs.

This is your Phase 1 scratch_tools.py loop, grown up and moved into the app.
You already wrote the core handshake there (dispatch a tool call, feed the result
back, repeat). Port that logic here, then adapt it for what's NEW in Phase 2:

  NEW vs Phase 1:
    1. MANY tools, not one  -> pass a list of FunctionDeclarations; dispatch by
       name through the TOOLS registry.
    2. ASYNC tools that hit the DB -> `result = await TOOLS[name](session, **args)`.
       Note the injected `session` (first arg) — the model never sees it.
    3. A SYSTEM PROMPT that tells the model it's the Account agent and how to
       behave (e.g. "look up the customer by email first to get their id").
    4. Return the final text (the endpoint will send it to the browser) instead
       of just printing.

Keep from Phase 1: the MAX_ITERS cap, and logging each step so you can watch the
loop work (this is also the seed of the Phase 6 "agent thoughts" panel).

Still deliberately by hand — no agent framework (see the build plan's framework note).
"""
from __future__ import annotations

from google import genai
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from tools.account import ACCOUNT_TOOL_DECLS, TOOLS
from utils.constants import GEMINI_FLASH_LITE_MODEL

MAX_ITERS = 6  # cost guardrail: never loop forever (CLAUDE.md cost rule)

ACCOUNT_SYSTEM_PROMPT = (
    # TODO: write the Account-agent instructions. Things worth telling it:
    #  - It answers questions about customers, their orders, and subscriptions.
    #  - To find anything for a customer, FIRST call get_customer(email) to get
    #    the id, THEN call get_orders / get_subscription with that id.
    #  - If get_customer returns found=false, say you couldn't find that customer
    #    instead of inventing data.
    #  - Be concise; answer the actual question asked.
    """
    You are a helpdesk agent that answers questions about customers, their orders and subscriptions.
    To answer questions about a customer, you must first call get_customer(email) to get the id,
    then call get_orders/get_subscription with that id.
    If get_customer returns found=false, say you couldn't find the customer instead of inventing data.
    Be concise, and answer the actual question asked.
    """
)


async def run_account_agent(message: str, session: AsyncSession) -> str:
    """Run the tool-calling loop until the model gives a final text answer.

    Returns the final answer string. Raises nothing fancy yet — keep it simple.
    """
    client = genai.Client()

    config = types.GenerateContentConfig(
        # TODO: wire up the config:
        #   - tools=[types.Tool(function_declarations=ACCOUNT_TOOL_DECLS)]
        #   - automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        #       (we run the loop by hand — don't let the SDK do it for us)
        #   - max_output_tokens=1000  (cost guardrail)
        #   - system_instruction=ACCOUNT_SYSTEM_PROMPT
        tools=[types.Tool(function_declarations=ACCOUNT_TOOL_DECLS)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=1000,
        system_instruction=ACCOUNT_SYSTEM_PROMPT
    )

    # Conversation history we GROW each turn (same idea as Phase 1's `contents`).
    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=message)]),
    ]

    for i in range(MAX_ITERS):
        # TODO (port from Phase 1, now ASYNC):
        #   response = await client.aio.models.generate_content(
        #       model=GEMINI_FLASH_LITE_MODEL, contents=contents, config=config)
        #   (note client.aio.* is the async API — you used the sync client in the
        #    scratch script; here we're inside an async endpoint.)
        response = await client.aio.models.generate_content(
            model=GEMINI_FLASH_LITE_MODEL, contents=contents,
            config=config
        )

        # TODO: pull out the model's turn and scan its parts for a function_call
        #   (and log any text). Remember a turn can contain text AND a call.
        model_turn = response.candidates[0].content

        # TODO: if there is NO function call -> the model answered. Return the
        #   final text (join any text parts) and stop.
        function_call = None
        final_text = []
        for part in model_turn.parts:
            if part.function_call:
                print(f"function call: name {part.function_call.name} args: {part.function_call.args}")
                function_call = part.function_call
            elif part.text:
                print(f"text:  {part.text}")
                final_text.append(part.text)

        if not function_call:
            print("No tool call - model answered directly, nothing to run.")
            return "\n".join(final_text)

        # TODO: DISPATCH — the Phase 2 twist is async + injected session:
        #   fn = TOOLS[function_call.name]
        #   result = await fn(session, **function_call.args)
        #   print(f"[iter {i}] {function_call.name}({dict(function_call.args)}) -> {result}")
        fn = TOOLS[function_call.name]
        result = await fn(session, **function_call.args)
        print(f"[iter {i}] {function_call.name}({dict(function_call.args)}) -> {result}")

        # TODO: FEED THE RESULT BACK — same two-append pattern as Phase 1:
        # both the model turn, and the result of the function
        #   contents.append(model_turn)
        #   fr = types.Part.from_function_response(
        #       name=function_call.name, response={"result": result})
        #   contents.append(types.Content(role="user", parts=[fr]))
        contents.append(model_turn)
        fr = types.Part.from_function_response(
            name=function_call.name, response={"result": result})
        contents.append(types.Content(role="user", parts=[fr]))

    # Hit the cap without the model settling on an answer.
    return "Sorry — I couldn't complete that within the step limit."


# ===========================================================================
# STREAMING version (Phase 2, step 7) — SCAFFOLD. Fill in the TODOs.
#
# Same loop as run_account_agent above, but instead of RETURNING one string it's
# an async GENERATOR that YIELDS events as they happen, so the browser can show
# progress and a typewriter answer over SSE. Keep run_account_agent above as your
# non-streaming reference — this is its streaming sibling.
#
# The event contract (each yielded dict becomes one SSE message; the endpoint
# passes it straight through, the frontend switches on event["type"]):
#     {"type": "tool",  "name": str, "args": dict}   # a tool is being run (loading)
#     {"type": "delta", "text": str}                 # a chunk of the answer
#     {"type": "done"}                               # finished
#
# TWO things change vs the non-streaming loop:
#   1. await client.aio.models.generate_content_stream(...) instead of
#      generate_content(...). It returns an ASYNC ITERATOR of partial chunks, so
#      you consume it with `async for chunk in stream:`.
#   2. You don't have a tidy `model_turn` object handed to you anymore. For a
#      tool-call turn, rebuild the history turn yourself from the function_call:
#          types.Content(role="model", parts=[types.Part(function_call=fc)])
#
# Caveat to know (fine to ignore for Phase 2): if a turn streams some "thinking"
# text AND then a tool call, you'll have already yielded that text as deltas.
# For this app the model almost always either answers OR calls a tool, so it's
# rarely an issue; cleanly separating "thoughts" from "answer" is a Phase 6 job.
# ===========================================================================
async def stream_account_agent(message: str, session: AsyncSession):
    """Async generator: yields {type: tool|delta|done} events (see contract above)."""
    client = genai.Client()

    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=ACCOUNT_TOOL_DECLS)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=1000,
        system_instruction=ACCOUNT_SYSTEM_PROMPT,
    )

    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=message)]),
    ]

    for i in range(MAX_ITERS):
        # TODO: open the streaming call (note: generate_content_STREAM, and it's
        #   awaited because we're on the async client):
        stream = await client.aio.models.generate_content_stream(
        model=GEMINI_FLASH_LITE_MODEL, contents=contents, config=config)

        function_call = None
        # TODO: consume the stream chunk by chunk:
        #     async for chunk in stream:
        #         for part in chunk.candidates[0].content.parts:
        #             if part.function_call:
        #                 function_call = part.function_call
        #             elif part.text:
        #                 yield {"type": "delta", "text": part.text}   # live token
        #   (yielding text as it arrives is what gives the typewriter effect.)
        async for chunk in stream:
            for part in chunk.candidates[0].content.parts:
                if part.function_call:
                    function_call = part.function_call
                elif part.text:
                    yield {"type": "delta", "text": part.text}

        # TODO: no tool call this turn => the model answered. Signal completion
        #   and stop the generator:
        #     if function_call is None:
        #         yield {"type": "done"}
        #         return
        if function_call is None:
            yield {"type": "done"}
            return

        # TODO: there IS a tool call => tell the UI, then run it (async + session):
        #     yield {"type": "tool", "name": function_call.name,
        #            "args": dict(function_call.args)}
        #     result = await TOOLS[function_call.name](session, **function_call.args)
        #     print(f"[iter {i}] {function_call.name}({dict(function_call.args)}) -> {result}")
        yield {"type": "tool", "name": function_call.name, "args": dict(function_call.args)}
        result = await TOOLS[function_call.name](session, **function_call.args)
        print(f"[iter {i}] {function_call.name}({dict(function_call.args)}) -> {result}")

        # TODO: feed the result back — same two-append pattern, but REBUILD the
        #   model turn yourself (streaming didn't hand you one):
        #     contents.append(types.Content(
        #         role="model", parts=[types.Part(function_call=function_call)]))
        #     contents.append(types.Content(role="user", parts=[
        #         types.Part.from_function_response(
        #             name=function_call.name, response={"result": result})]))

        # NOTE: single-call only — see Phase 4 
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

    # Hit the iteration cap without a final answer.
    yield {"type": "delta", "text": "Sorry — I couldn't complete that within the step limit."}
    yield {"type": "done"}


if __name__ == "__main__":
    import asyncio

    from db.session import AsyncSessionLocal, engine

    async def _smoke():
        async with AsyncSessionLocal() as session:
            # print("prompt: what is the latest subscription for notfound@example.com?")
            # res = await run_account_agent("what is the latest subscription for notfound@example.com?", session)
            print("prompt: what is the latest subscription for alice@example.com?")
            res = await run_account_agent("what is the latest subscription for alice@example.com?", session)
            print("res: ", res)
        await engine.dispose()

    asyncio.run(_smoke())