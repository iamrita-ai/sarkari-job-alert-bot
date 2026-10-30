"""Optional branded stickers - the closest thing a bot has to premium emoji.

Telegram does not let a bot use the $ (custom) emoji of a pack it does not
own, but it *can* own a sticker set. So the bot ships with a SERENA sticker
and sends it with the welcome message.

Two ways to configure it:

  1. ``WELCOME_STICKER_FILE_ID`` - one sticker, sent every time.
  2. ``STICKER_SET_NAME`` - a sticker set the bot owns; a random sticker of
     that set is sent (``python scripts/create_sticker_set.py <user_id>``).
"""
from __future__ import annotations

import logging
import random

from telegram.error import TelegramError

from bot import config

logger = logging.getLogger(__name__)


async def _pick_from_set(bot, set_name: str) -> str | None:  # noqa: ANN001
    """A random sticker (file id) of a sticker set."""
    try:
        sticker_set = await bot.get_sticker_set(set_name)
    except TelegramError:
        logger.exception("Sticker set '%s' is not reachable", set_name)
        return None
    stickers = list(getattr(sticker_set, "stickers", []) or [])
    if not stickers:
        return None
    return random.choice(stickers).file_id


async def welcome_sticker(bot, chat_id: int) -> str | None:  # noqa: ANN001
    """Send the branded sticker - returns the file id that was sent."""
    file_id = config.WELCOME_STICKER_FILE_ID
    if not file_id and config.STICKER_SET_NAME:
        file_id = await _pick_from_set(bot, config.STICKER_SET_NAME)
    if not file_id:
        return None
    try:
        await bot.send_sticker(chat_id=chat_id, sticker=file_id)
    except TelegramError:
        logger.exception("Could not send the welcome sticker")
        return None
    return file_id


async def send_sticker_by_id(bot, chat_id: int, file_id: str) -> bool:  # noqa: ANN001
    """Send a sticker by its file id (used by the /sticker command)."""
    try:
        await bot.send_sticker(chat_id=chat_id, sticker=file_id)
    except TelegramError:
        logger.exception("Could not send the sticker")
        return False
    return True
