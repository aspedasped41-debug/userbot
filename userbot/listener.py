from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from telethon import events
from telethon.events import NewMessage
from telethon.tl.custom import Message
from telethon.tl.types import User


logger = logging.getLogger(__name__)
NotifyCallback = Callable[[int, str], Awaitable[None]]


def has_self_destruct_media(message: Message) -> bool:
    media = getattr(message, "media", None)
    if media is None:
        return False

    ttl_seconds = getattr(media, "ttl_seconds", None)
    return ttl_seconds is not None


def build_private_media_handler(
    bot_user_id: int,
    notify: NotifyCallback,
) -> tuple[NewMessage.EventBuilder, Callable[[NewMessage.Event], Awaitable[None]]]:
    event_builder = events.NewMessage(incoming=True)

    async def handler(event: NewMessage.Event) -> None:
        message = event.message
        if not event.is_private or not has_self_destruct_media(message):
            return

        sender = await event.get_sender()
        if getattr(sender, "bot", False):
            return

        try:
            await message.forward_to("me")
        except Exception as exc:
            logger.warning(
                "Could not forward self-destructing media for bot user %s: %s",
                bot_user_id,
                exc.__class__.__name__,
            )
            await _download_and_send_to_saved_messages(event, bot_user_id, notify)

    return event_builder, handler


def _sender_label(sender: User | None) -> str:
    if sender is None:
        return "unknown sender"

    parts: list[str] = []
    full_name = " ".join(
        part
        for part in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)]
        if part
    )
    if full_name:
        parts.append(full_name)

    username = getattr(sender, "username", None)
    if username:
        parts.append(f"@{username}")

    sender_id = getattr(sender, "id", None)
    if sender_id:
        parts.append(f"id={sender_id}")

    return " | ".join(parts) if parts else "unknown sender"


async def _saved_caption(event: NewMessage.Event) -> str:
    sender = await event.get_sender()
    attribution = f"From: {_sender_label(sender)}"
    original_text = event.message.text

    if original_text:
        return f"{attribution}\n\n{original_text}"
    return attribution


async def _download_and_send_to_saved_messages(
    event: NewMessage.Event,
    bot_user_id: int,
    notify: NotifyCallback,
) -> None:
    with tempfile.TemporaryDirectory(prefix=f"userbot_{bot_user_id}_") as temp_dir:
        downloaded_path: str | None = None

        try:
            downloaded = await event.message.download_media(file=temp_dir)
            if not downloaded:
                raise RuntimeError("download_media returned no file")

            downloaded_path = str(downloaded)
            await event.client.send_file(
                "me",
                downloaded_path,
                caption=await _saved_caption(event),
            )
        except Exception as exc:
            logger.warning(
                "Could not download/send self-destructing media for bot user %s: %s",
                bot_user_id,
                exc.__class__.__name__,
            )
            await notify(
                bot_user_id,
                "A private self-destructing media message was detected, but Telegram "
                "did not allow it to be forwarded or saved through the fallback.",
            )
        finally:
            if downloaded_path:
                try:
                    Path(downloaded_path).unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Could not remove temporary media file for bot user %s",
                        bot_user_id,
                    )
