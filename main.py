from __future__ import annotations

import logging
import os
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from agent import run_agent, synthesize_speech, transcribe_audio
from config import get_settings
from db import SessionLocal, init_db
from scheduler import start_scheduler
from telegram_api import TelegramAPI