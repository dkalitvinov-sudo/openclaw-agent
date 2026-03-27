from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db import SessionLocal


settings = get_settings()
TZ = ZoneInfo(settings.scheduler_timezone)


async def save_memory(session: AsyncSession, *, user_id: int, chat_id: int, fact: str) -> dict[str, Any]:
    item = UserMemory(user_id=user_id, chat_id=chat_id, fact=fact.strip())
    session.add(item)
    await session.commit()
    return {'status': 'ok', 'saved_fact': fact.strip()}


async def create_note(session: AsyncSession, *, user_id: int, chat_id: int, text: str, tags: list[str] | None = None) -> dict[str, Any]:
    note = Note(user_id=user_id, chat_id=chat_id, text=text.strip(), tags=','.join(tags or []))
    session.add(note)
    await session.commit()
    return {'status': 'ok', 'note_id': note.id, 'text': note.text, 'tags': tags or []}


async def search_notes(session: AsyncSession, *, user_id: int, query: str, limit: int = 5) -> dict[str, Any]:
    stmt = (
        select(Note)
        .where(Note.user_id == user_id, Note.text.ilike(f'%{query}%'))
        .order_by(Note.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        'items': [
            {
                'id': row.id,
                'text': row.text,
                'tags': [tag for tag in row.tags.split(',') if tag],
                'created_at': row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


async def create_reminder(session: AsyncSession, *, user_id: int, chat_id: int, text: str, due_at_iso: str) -> dict[str, Any]:
    due_at = datetime.fromisoformat(due_at_iso)
    if due_at.tzinfo is not None:
        due_at = due_at.astimezone(TZ).replace(tzinfo=None)
    reminder = Reminder(user_id=user_id, chat_id=chat_id, text=text.strip(), due_at=due_at)
    session.add(reminder)
    await session.commit()
    return {'status': 'ok', 'reminder_id': reminder.id, 'due_at': due_at.isoformat(), 'text': reminder.text}


async def get_weather(location: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        geo = await client.get(
            'https://geocoding-api.open-meteo.com/v1/search',
            params={'name': location, 'count': 1, 'language': settings.default_weather_language},
        )
        geo.raise_for_status()
        results = geo.json().get('results') or []
        if not results:
            return {'status': 'not_found', 'location': location}
        place = results[0]
        weather = await client.get(
            'https://api.open-meteo.com/v1/forecast',
            params={
                'latitude': place['latitude'],
                'longitude': place['longitude'],
                'current': 'temperature_2m,apparent_temperature,weather_code,wind_speed_10m',
                'timezone': 'auto',
            },
        )
        weather.raise_for_status()
        current = weather.json().get('current', {})
    return {
        'status': 'ok',
        'resolved_location': f"{place['name']}, {place.get('country', '')}".strip(', '),
        'temperature_c': current.get('temperature_2m'),
        'feels_like_c': current.get('apparent_temperature'),
        'wind_kmh': current.get('wind_speed_10m'),
        'weather_code': current.get('weather_code'),
    }


async def fetch_url_summary(url: str) -> dict[str, Any]:
    if not settings.allow_url_fetch:
        return {'status': 'disabled'}
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        response = await client.get(url, headers={'User-Agent': 'TelegramRailwayAgent/1.0'})
        response.raise_for_status()
        text = response.text[:12000]
    return {'status': 'ok', 'url': url, 'content_excerpt': text}


async def list_pending_reminders(session: AsyncSession, *, user_id: int, limit: int = 10) -> dict[str, Any]:
    stmt = (
        select(Reminder)
        .where(Reminder.user_id == user_id, Reminder.sent.is_(False))
        .order_by(Reminder.due_at.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        'items': [
            {'id': row.id, 'text': row.text, 'due_at': row.due_at.isoformat()} for row in rows
        ]
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        'type': 'function',
        'name': 'save_memory',
        'description': 'Save a durable user fact or preference that may be helpful later.',
        'parameters': {
            'type': 'object',
            'properties': {
                'fact': {'type': 'string', 'description': 'The durable fact to remember.'},
            },
            'required': ['fact'],
            'additionalProperties': False,
        },
        'strict': True,
    },
    {
        'type': 'function',
        'name': 'create_note',
        'description': 'Save a note for the user.',
        'parameters': {
            'type': 'object',
            'properties': {
                'text': {'type': 'string'},
                'tags': {'type': 'array', 'items': {'type': 'string'}},
            },
            'required': ['text'],
            'additionalProperties': False,
        },
        'strict': True,
    },
    {
        'type': 'function',
        'name': 'search_notes',
        'description': 'Search previously saved notes.',
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string'},
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 10},
            },
            'required': ['query'],
            'additionalProperties': False,
        },
        'strict': True,
    },
    {
        'type': 'function',
        'name': 'create_reminder',
        'description': 'Create a reminder. Use ISO 8601 local time like 2026-03-26T18:30:00.',
        'parameters': {
            'type': 'object',
            'properties': {
                'text': {'type': 'string'},
                'due_at_iso': {'type': 'string'},
            },
            'required': ['text', 'due_at_iso'],
            'additionalProperties': False,
        },
        'strict': True,
    },
    {
        'type': 'function',
        'name': 'list_pending_reminders',
        'description': 'List upcoming reminders.',
        'parameters': {
            'type': 'object',
            'properties': {
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 10},
            },
            'additionalProperties': False,
        },
        'strict': True,
    },
    {
        'type': 'function',
        'name': 'get_weather',
        'description': 'Get current weather for a city or place name.',
        'parameters': {
            'type': 'object',
            'properties': {
                'location': {'type': 'string'},
            },
            'required': ['location'],
            'additionalProperties': False,
        },
        'strict': True,
    },
    {
        'type': 'function',
        'name': 'fetch_url_summary',
        'description': 'Fetch and read the contents of a public web page when the user sends a URL.',
        'parameters': {
            'type': 'object',
            'properties': {
                'url': {'type': 'string'},
            },
            'required': ['url'],
            'additionalProperties': False,
        },
        'strict': True,
    },
]


async def run_tool(session: AsyncSession, name: str, args: dict[str, Any], *, user_id: int, chat_id: int) -> dict[str, Any]:
    if name == 'save_memory':
        return await save_memory(session, user_id=user_id, chat_id=chat_id, **args)
    if name == 'create_note':
        return await create_note(session, user_id=user_id, chat_id=chat_id, **args)
    if name == 'search_notes':
        return await search_notes(session, user_id=user_id, **args)
    if name == 'create_reminder':
        return await create_reminder(session, user_id=user_id, chat_id=chat_id, **args)
    if name == 'list_pending_reminders':
        return await list_pending_reminders(session, user_id=user_id, **args)
    if name == 'get_weather':
        return await get_weather(**args)
    if name == 'fetch_url_summary':
        return await fetch_url_summary(**args)
    raise ValueError(f'Unknown tool: {name}')


def dump_tool_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False)
