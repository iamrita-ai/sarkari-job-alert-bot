"""Create the SERENA sticker set (run once, as the bot owner).

    python scripts/create_sticker_set.py 123456789

Arguments:
    user_id   your Telegram user id (the owner of the set)

The script uploads ``assets/serena_sticker.png`` as a sticker set that the
bot owns and prints the name to put into your environment:

    STICKER_SET_NAME=serena_by_your_bot

From then on the bot greets every new user with a sticker - the closest
thing to "premium emoji" a Telegram bot can do (custom $ emoji may only be
used by the pack owner).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Bot, StickerFormat, StickerSet  # noqa: E402
from telegram.error import TelegramError  # noqa: E402

from bot import config  # noqa: E402

STICKER_FILE = Path(__file__).resolve().parent.parent / "assets" / "serena_sticker.png"
SET_NAME = "serena_by_serena_bot"
SET_TITLE = "SERENA"


async def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    try:
        user_id = int(sys.argv[1])
    except ValueError:
        print("The user id must be a number")
        return 1
    if not config.BOT_TOKEN:
        print("BOT_TOKEN is missing - put it into your .env")
        return 1
    if not STICKER_FILE.exists():
        print(f"Missing sticker file: {STICKER_FILE}")
        return 1

    bot = Bot(config.BOT_TOKEN)
    try:
        await bot.delete_sticker_set(SET_NAME)
    except TelegramError:
        pass  # the set does not exist yet - that is the normal case
    try:
        with STICKER_FILE.open("rb") as photo:
            await bot.create_new_sticker_set(
                user_id=user_id,
                name=SET_NAME,
                title=SET_TITLE,
                png_sticker=photo,
                format=StickerFormat.STATIC,
                emojis=["⭐️", "✨", "🔔", "🎫", "🏁"],
            )
    except TelegramError as exc:
        print(f"Could not create the sticker set: {exc}")
        return 1

    sticker_set: StickerSet = await bot.get_sticker_set(SET_NAME)
    print(f"Sticker set ready: {sticker_set.name} ({len(sticker_set.stickers)} sticker(s))")
    print("Add this to your environment:")
    print(f"STICKER_SET_NAME={sticker_set.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
