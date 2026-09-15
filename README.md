# Telegram Multi-User Userbot

One Python app runs both:

- an aiogram Telegram bot control panel
- Telethon user sessions stored as files in `sessions/`
- private-chat listeners that forward detected self-destructing media to the same account's Saved Messages

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Fill `.env`:

```env
BOT_TOKEN=your_bot_token
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash
ADMIN_PHONE=phone_number
```

4. Run:

```bash
python main.py
```

## Commands

- `/start` shows the bot intro and available commands
- `/privacy` explains why phone number, Telegram login code, and 2FA may be required
- `/login` starts the phone-code login flow
- `/logout` disconnects the running client and deletes `sessions/{bot_user_id}.session`
- `/status` shows this user's login/session status
- `/data` shows summary session data for the admin account only
- `/data <bot_user_id>` sends an admin-only detailed `.txt` report with that user's dialog metadata

## Notes

- Temporary login data is memory-only. If the app restarts mid-login, send `/login` again.
- Session files are not stored in a database. Each bot user gets one file: `sessions/{bot_user_id}.session`.
- Admin access is verified by the signed-in Telegram account phone number. The bot cannot read a Telegram user's phone number until that account logs in through Telethon.
- Telegram may block forwarding one-time or self-destructing media. The app catches those errors and notifies the bot user without crashing.
- Login codes and 2FA passwords are never logged or persisted by this app.
