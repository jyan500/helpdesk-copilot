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
        for part in model_turn.parts:
            if part.function_call:
                print(f"function call: name {part.function_call.name} args: {part.function_call.args}")
                function_call = part.function_call
            elif part.text:
                print(f"text:  {part.text}")

        if not function_call:
            print("No tool call - model answered directly, nothing to run.")
            return

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