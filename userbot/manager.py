from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import Bot
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config import Settings, normalize_phone
from userbot.listener import build_private_media_handler


logger = logging.getLogger(__name__)
NOT_REGISTERED_TEXT = "Siz ro'yhatdan o'tmagansiz | \u0412\u044b \u043d\u0435 \u0437\u0430\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u044b"
REGISTERED_TEXT = "Siz ro'yhatdan o'tgansiz | \u0412\u044b \u0437\u0430\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0438\u0440\u043e\u0432\u0430\u043b\u0438\u0441\u044c"


class LoginFlowError(RuntimeError):
    pass


@dataclass
class LoginState:
    bot_user_id: int
    step: str
    phone: str | None = None
    phone_code_hash: str | None = None
    client: TelegramClient | None = None


@dataclass(frozen=True)
class ListenerRegistration:
    event_builder: object
    handler: Callable[..., Awaitable[None]]


class UserbotManager:
    def __init__(self, settings: Settings, bot: Bot) -> None:
        self.settings = settings
        self.bot = bot
        self.clients: dict[int, TelegramClient] = {}
        self.phones: dict[int, str] = {}
        self.usernames: dict[int, str] = {}
        self.login_states: dict[int, LoginState] = {}
        self.listeners: dict[int, ListenerRegistration] = {}

    def session_path(self, bot_user_id: int) -> Path:
        return self.settings.sessions_dir / f"{bot_user_id}.session"

    def session_file_exists(self, bot_user_id: int) -> bool:
        return self.session_path(bot_user_id).exists()

    def session_user_ids(self) -> list[int]:
        user_ids: list[int] = []
        for path in sorted(self.settings.sessions_dir.glob("*.session")):
            try:
                user_ids.append(int(path.stem))
            except ValueError:
                logger.warning("Ignoring session file with non-numeric name: %s", path.name)
        return user_ids

    def is_running(self, bot_user_id: int) -> bool:
        client = self.clients.get(bot_user_id)
        return bool(client and client.is_connected())

    def login_step(self, bot_user_id: int) -> str | None:
        state = self.login_states.get(bot_user_id)
        return state.step if state else None

    def _login_status(self, bot_user_id: int) -> str:
        state = self.login_states.get(bot_user_id)
        if state:
            return state.step
        if self.is_running(bot_user_id):
            return "running"
        if self.session_file_exists(bot_user_id):
            return "session file only"
        return "not logged in"

    def _create_client(self, bot_user_id: int) -> TelegramClient:
        return TelegramClient(
            str(self.session_path(bot_user_id)),
            self.settings.api_id,
            self.settings.api_hash,
        )

    async def notify_bot_user(self, bot_user_id: int, text: str) -> None:
        try:
            await self.bot.send_message(bot_user_id, text)
        except Exception as exc:
            logger.warning(
                "Could not notify bot user %s: %s",
                bot_user_id,
                exc.__class__.__name__,
            )

    async def begin_login(self, bot_user_id: int) -> None:
        await self.cancel_login(bot_user_id)
        self.login_states[bot_user_id] = LoginState(bot_user_id=bot_user_id, step="phone")

    async def cancel_login(self, bot_user_id: int) -> None:
        state = self.login_states.pop(bot_user_id, None)
        if state and state.client:
            await state.client.disconnect()

    async def request_code(self, bot_user_id: int, phone: str) -> None:
        normalized_phone = normalize_phone(phone)
        if not normalized_phone:
            raise LoginFlowError("Phone number is empty or invalid.")

        await self.cancel_login(bot_user_id)

        client = self._create_client(bot_user_id)
        try:
            await client.connect()
            sent_code = await client.send_code_request(normalized_phone)
        except Exception:
            await client.disconnect()
            raise

        self.login_states[bot_user_id] = LoginState(
            bot_user_id=bot_user_id,
            step="code",
            phone=normalized_phone,
            phone_code_hash=sent_code.phone_code_hash,
            client=client,
        )

    async def submit_code(self, bot_user_id: int, code: str) -> str:
        state = self.login_states.get(bot_user_id)
        if not state or state.step != "code" or not state.client:
            raise LoginFlowError("No active login code request. Send /login to start again.")

        if not state.client.is_connected():
            await state.client.connect()

        await state.client.sign_in(
            phone=state.phone,
            code=code,
            phone_code_hash=state.phone_code_hash,
        )

        await self._activate_client(bot_user_id, state.client, state.phone)
        return "signed_in"

    async def mark_password_required(self, bot_user_id: int) -> None:
        state = self.login_states.get(bot_user_id)
        if not state:
            raise LoginFlowError("No active login flow. Send /login to start again.")
        state.step = "password"

    async def submit_password(self, bot_user_id: int, password: str) -> str:
        state = self.login_states.get(bot_user_id)
        if not state or state.step != "password" or not state.client:
            raise LoginFlowError("No active 2FA password request. Send /login to start again.")

        if not state.client.is_connected():
            await state.client.connect()

        try:
            await state.client.sign_in(password=password)
        finally:
            password = ""

        await self._activate_client(bot_user_id, state.client, state.phone)
        return "signed_in"

    async def _activate_client(
        self,
        bot_user_id: int,
        client: TelegramClient,
        phone: str | None = None,
    ) -> None:
        existing = self.clients.get(bot_user_id)
        if existing and existing is not client:
            await self.stop_user(bot_user_id, delete_session=False)

        if not client.is_connected():
            await client.connect()

        event_builder, handler = build_private_media_handler(
            bot_user_id=bot_user_id,
            notify=self.notify_bot_user,
        )
        client.add_event_handler(handler, event_builder)

        self.clients[bot_user_id] = client
        self.listeners[bot_user_id] = ListenerRegistration(event_builder, handler)

        resolved_phone = phone or await self._get_client_phone(client)
        if resolved_phone:
            self.phones[bot_user_id] = normalize_phone(resolved_phone)
        resolved_username = await self._get_client_username(client)
        self.usernames[bot_user_id] = resolved_username or ""

        self.login_states.pop(bot_user_id, None)

    async def _get_client_phone(self, client: TelegramClient) -> str | None:
        try:
            me = await client.get_me()
        except Exception as exc:
            logger.warning("Could not read signed-in Telegram user: %s", exc.__class__.__name__)
            return None
        return getattr(me, "phone", None)

    async def _get_client_username(self, client: TelegramClient) -> str | None:
        try:
            me = await client.get_me()
        except Exception as exc:
            logger.warning("Could not read signed-in Telegram username: %s", exc.__class__.__name__)
            return None
        return getattr(me, "username", None)

    async def start_user(self, bot_user_id: int) -> bool:
        if self.is_running(bot_user_id):
            return True

        client = self._create_client(bot_user_id)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return False
            await self._activate_client(bot_user_id, client)
            return True
        except Exception as exc:
            await client.disconnect()
            logger.warning(
                "Could not start userbot for bot user %s: %s",
                bot_user_id,
                exc.__class__.__name__,
            )
            return False

    async def start_existing_sessions(self) -> None:
        for bot_user_id in self.session_user_ids():
            started = await self.start_user(bot_user_id)
            if started:
                logger.info("Started userbot for bot user %s", bot_user_id)
            else:
                logger.warning("Session file exists but is not authorized: %s", bot_user_id)

    async def _logout_client(self, bot_user_id: int, client: TelegramClient) -> None:
        try:
            if not client.is_connected():
                await client.connect()
            if await client.is_user_authorized():
                await client.log_out()
        except Exception as exc:
            logger.warning(
                "Could not log out Telegram session for bot user %s: %s",
                bot_user_id,
                exc.__class__.__name__,
            )
        finally:
            if client.is_connected():
                await client.disconnect()

    async def _logout_session_file(self, bot_user_id: int) -> None:
        if not self.session_file_exists(bot_user_id):
            return

        client = self._create_client(bot_user_id)
        await self._logout_client(bot_user_id, client)

    async def stop_user(self, bot_user_id: int, delete_session: bool = False) -> None:
        await self.cancel_login(bot_user_id)

        client = self.clients.pop(bot_user_id, None)
        registration = self.listeners.pop(bot_user_id, None)
        if client:
            if registration:
                client.remove_event_handler(registration.handler)
            if delete_session:
                await self._logout_client(bot_user_id, client)
            else:
                await client.disconnect()
        elif delete_session:
            await self._logout_session_file(bot_user_id)

        self.phones.pop(bot_user_id, None)
        self.usernames.pop(bot_user_id, None)

        if delete_session:
            for path in self.settings.sessions_dir.glob(f"{bot_user_id}.session*"):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    async def stop_all(self) -> None:
        for bot_user_id in list(self.clients):
            await self.stop_user(bot_user_id, delete_session=False)
        for bot_user_id in list(self.login_states):
            await self.cancel_login(bot_user_id)

    async def status_text(self, bot_user_id: int) -> str:
        state = self.login_states.get(bot_user_id)
        running = self.is_running(bot_user_id)
        session_file = self.session_file_exists(bot_user_id)

        if not running and session_file and not state:
            await self.start_user(bot_user_id)
            running = self.is_running(bot_user_id)

        if state:
            return NOT_REGISTERED_TEXT

        if running:
            return REGISTERED_TEXT

        return NOT_REGISTERED_TEXT

    async def is_admin(self, bot_user_id: int) -> bool:
        phone = self.phones.get(bot_user_id)
        if normalize_phone(phone) == self.settings.admin_phone:
            return True

        client = self.clients.get(bot_user_id)
        if client and client.is_connected():
            phone = await self._get_client_phone(client)
            if phone:
                self.phones[bot_user_id] = normalize_phone(phone)
                return self.phones[bot_user_id] == self.settings.admin_phone

        return False

    async def admin_data_text(self) -> str:
        session_ids = self.session_user_ids()
        lines = [
            "Userbot data",
            f"Total active sessions: {len(self.clients)}",
            f"Session files: {len(session_ids)}",
            "",
        ]

        if not session_ids:
            lines.append("No session files.")

        for index, bot_user_id in enumerate(session_ids, start=1):
            running = self.is_running(bot_user_id)
            status = self._login_status(bot_user_id)
            phone = self.phones.get(bot_user_id, "unknown")
            username = self.usernames.get(bot_user_id, "")
            lines.append(
                f"{index}: bot_user_id={bot_user_id} | phone={phone} | "
                f"running={running} | login_status={status} | username={username}"
            )

        active_login_ids = sorted(set(self.login_states) - set(session_ids))
        if active_login_ids:
            lines.extend(["", "In-memory login flows:"])
            for bot_user_id in active_login_ids:
                state = self.login_states[bot_user_id]
                phone = state.phone or "unknown"
                lines.append(
                    f"- bot_user_id={bot_user_id} | phone={phone} | "
                    f"running={self.is_running(bot_user_id)} | login_status={state.step}"
                )

        return "\n".join(lines)

    async def user_data_text(self, bot_user_id: int) -> str:
        if not self.is_running(bot_user_id) and self.session_file_exists(bot_user_id):
            await self.start_user(bot_user_id)

        running = self.is_running(bot_user_id)
        session_file = self.session_file_exists(bot_user_id)
        lines = [
            "Userbot user data",
            f"bot_user_id={bot_user_id}",
            f"phone={self.phones.get(bot_user_id, 'unknown')}",
            f"username={self.usernames.get(bot_user_id, '')}",
            f"running={running}",
            f"session_file={session_file}",
            f"login_status={self._login_status(bot_user_id)}",
            f"generated_at={datetime.now().isoformat(timespec='seconds')}",
            "",
        ]

        client = self.clients.get(bot_user_id)
        if not client or not client.is_connected():
            lines.append("No running authorized client is available for this user.")
            return "\n".join(lines)

        try:
            dialogs = await client.get_dialogs(limit=None)
        except Exception as exc:
            logger.warning(
                "Could not export dialogs for bot user %s: %s",
                bot_user_id,
                exc.__class__.__name__,
            )
            lines.append(f"Could not read dialogs: {exc.__class__.__name__}")
            return "\n".join(lines)

        categories: dict[str, list[Any]] = {
            "Private chats": [],
            "Bots": [],
            "Groups": [],
            "Channels": [],
            "Other dialogs": [],
        }
        for dialog in dialogs:
            categories[self._dialog_category(dialog)].append(dialog)

        lines.extend(
            [
                f"Total dialogs: {len(dialogs)}",
                f"Private chats: {len(categories['Private chats'])}",
                f"Bots: {len(categories['Bots'])}",
                f"Groups: {len(categories['Groups'])}",
                f"Channels: {len(categories['Channels'])}",
                f"Other dialogs: {len(categories['Other dialogs'])}",
                "",
            ]
        )

        for category, category_dialogs in categories.items():
            lines.append(category)
            if not category_dialogs:
                lines.append("- none")
                lines.append("")
                continue

            for index, dialog in enumerate(category_dialogs, start=1):
                lines.append(self._dialog_report_line(index, dialog))
            lines.append("")

        return "\n".join(lines).rstrip()

    def _dialog_category(self, dialog: Any) -> str:
        entity = getattr(dialog, "entity", None)
        if getattr(entity, "bot", False):
            return "Bots"
        if getattr(dialog, "is_user", False):
            return "Private chats"
        if getattr(dialog, "is_group", False):
            return "Groups"
        if getattr(dialog, "is_channel", False):
            return "Channels"
        return "Other dialogs"

    def _dialog_report_line(self, index: int, dialog: Any) -> str:
        entity = getattr(dialog, "entity", None)
        message = getattr(dialog, "message", None)
        entity_id = getattr(entity, "id", getattr(dialog, "id", "unknown"))
        title = self._dialog_title(dialog, entity)
        username = getattr(entity, "username", "") or ""
        phone = normalize_phone(getattr(entity, "phone", None)) or ""
        participants_count = getattr(entity, "participants_count", None)
        verified = getattr(entity, "verified", False)
        scam = getattr(entity, "scam", False)
        fake = getattr(entity, "fake", False)
        unread_count = getattr(dialog, "unread_count", 0)
        unread_mentions = getattr(dialog, "unread_mentions_count", 0)
        pinned = getattr(dialog, "pinned", False)
        archived = getattr(dialog, "archived", False)
        last_message_id = getattr(message, "id", "")
        last_message_date = getattr(message, "date", None)
        if last_message_date:
            last_message_date = last_message_date.isoformat()
        else:
            last_message_date = ""

        fields = [
            f"{index}: id={entity_id}",
            f"title={title}",
            f"username={username}",
            f"phone={phone}",
            f"participants_count={participants_count if participants_count is not None else ''}",
            f"unread_count={unread_count}",
            f"unread_mentions={unread_mentions}",
            f"pinned={pinned}",
            f"archived={archived}",
            f"verified={verified}",
            f"scam={scam}",
            f"fake={fake}",
            f"last_message_id={last_message_id}",
            f"last_message_date={last_message_date}",
        ]
        return " | ".join(fields)

    def _dialog_title(self, dialog: Any, entity: Any) -> str:
        name = getattr(dialog, "name", None) or getattr(entity, "title", None)
        if name:
            return str(name)

        first_name = getattr(entity, "first_name", None) or ""
        last_name = getattr(entity, "last_name", None) or ""
        full_name = " ".join(part for part in [first_name, last_name] if part)
        return full_name or "unknown"
