from __future__ import annotations

import os
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_env: str = Field(default='development', alias='APP_ENV')
    app_base_url: str | None = Field(default=None, alias='APP_BASE_URL')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')

    telegram_bot_token: str = Field(alias='TELEGRAM_BOT_TOKEN')
    telegram_secret_token: str = Field(alias='TELEGRAM_SECRET_TOKEN')
    telegram_api_base: str = Field(default='https://api.telegram.org', alias='TELEGRAM_API_BASE')

    openai_api_key: str = Field(alias='OPENAI_API_KEY')
    openai_model: str = Field(default='gpt-5-mini', alias='OPENAI_MODEL')
    openai_transcription_model: str = Field(default='gpt-4o-mini-transcribe', alias='OPENAI_TRANSCRIPTION_MODEL')
    openai_tts_model: str = Field(default='gpt-4o-mini-tts', alias='OPENAI_TTS_MODEL')
    openai_tts_voice: str = Field(default='alloy', alias='OPENAI_TTS_VOICE')

    database_url: str = Field(default='sqlite+aiosqlite:///./data.db', alias='DATABASE_URL')
    scheduler_timezone: str = Field(default='Europe/Kiev', alias='SCHEDULER_TIMEZONE')

    default_weather_language: str = Field(default='ru', alias='DEFAULT_WEATHER_LANGUAGE')
    max_file_mb: int = Field(default=20, alias='MAX_FILE_MB')
    allow_url_fetch: bool = Field(default=True, alias='ALLOW_URL_FETCH')
    admin_user_id: int | None = Field(default=None, alias='ADMIN_USER_ID')

    @property
    def telegram_bot_api_url(self) -> str:
        return f"{self.telegram_api_base}/bot{self.telegram_bot_token}"

    @property
    def telegram_file_api_url(self) -> str:
        return f"{self.telegram_api_base}/file/bot{self.telegram_bot_token}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
