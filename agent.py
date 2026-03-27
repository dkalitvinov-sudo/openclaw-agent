from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db import get_user_memories
from tools import TOOL_SCHEMAS, dump_tool_result, run_tool


settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)


SYSTEM_PROMPT = """
You are a Telegram personal agent.
Speak naturally in Russian unless the user clearly uses another language.
Be concise, useful, and action oriented.
Use tools when they genuinely help.
When a user asks to remember something durable, use save_memory.
When a user asks to save or find notes, use note tools.
When a user asks for a reminder, use create_reminder and interpret time in Europe/Kiev unless specified.
When a user sends a public URL and asks what it says, use fetch_url_summary.
Do not pretend you completed external side effects that do not exist.
If a request is risky, irreversible, or payment related, explain that a confirmation layer should be added first.
""".strip()


async def transcribe_audio(file_path: str) -> str:
    with open(file_path, 'rb') as audio_file:
        transcript = await client.audio.transcriptions.create(
            model=settings.openai_transcription_model,
            file=audio_file,
        )
    text = getattr(transcript, 'text', None)
    if not text:
        raise RuntimeError('Empty transcript returned from OpenAI transcription API')
    return text.strip()


async def synthesize_speech(text: str, output_path: str) -> str:
    speech = await client.audio.speech.create(
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        input=text[:4000],
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    await speech.write_to_file(output_path)
    return output_path


async def run_agent(session: AsyncSession, *, user_id: int, chat_id: int, text: str) -> str:
    memories = await get_user_memories(session, user_id=user_id)
    input_payload: list[dict[str, Any]] = [
        {
            'role': 'user',
            'content': [
                {
                    'type': 'input_text',
                    'text': (
                        f"User memory:\n- " + "\n- ".join(memories)
                        if memories
                        else 'User memory: none yet.'
                    )
                    + f"\n\nUser message:\n{text}",
                }
            ],
        }
    ]

    response = await client.responses.create(
        model=settings.openai_model,
        instructions=SYSTEM_PROMPT,
        input=input_payload,
        tools=TOOL_SCHEMAS,
        parallel_tool_calls=True,
    )

    while True:
        function_calls = [item for item in response.output if item.type == 'function_call']
        if not function_calls:
            return response.output_text.strip()

        tool_outputs = []
        for call in function_calls:
            args = json.loads(call.arguments)
            result = await run_tool(session, call.name, args, user_id=user_id, chat_id=chat_id)
            tool_outputs.append(
                {
                    'type': 'function_call_output',
                    'call_id': call.call_id,
                    'output': dump_tool_result(result),
                }
            )

        response = await client.responses.create(
            model=settings.openai_model,
            instructions=SYSTEM_PROMPT,
            previous_response_id=response.id,
            input=tool_outputs,
            tools=TOOL_SCHEMAS,
            parallel_tool_calls=True,
        )
