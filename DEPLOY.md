# Deploy

This app uses Telegram polling, so it does not need an open web port.

## VPS With Docker Compose

1. Copy the project to your server.

2. Create `.env` from the example:

```bash
cp .env.example .env
nano .env
```

3. Fill:

```env
BOT_TOKEN=...
API_ID=...
API_HASH=...
ADMIN_PHONE=...
```

4. Start:

```bash
docker compose up -d --build
```

5. Check logs:

```bash
docker compose logs -f userbot
```

6. Stop:

```bash
docker compose down
```

## Important

- `sessions/` is mounted as a persistent folder on the server.
- Do not delete `sessions/` unless you want users to log in again.
- Keep `.env` private.
- If a user sends `/logout`, the app logs out from Telegram and deletes that user's local session files.

## Update Deployment

After changing code on the server:

```bash
docker compose up -d --build
```

## Backup Sessions

To back up session files:

```bash
tar -czf sessions-backup.tar.gz sessions/
```

Store the backup securely because session files authorize Telegram accounts.
