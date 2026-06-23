**English** | [Українська](README.uk.md)

# Relay Messenger

Relay is a real-time messenger built around a FastAPI backend and an Android-first frontend based on Ionic Vue + Capacitor. It brings together database persistence, JWT authentication, private one-to-one chats, message history, attachments, read receipts, online status, typing indicators, avatars, local and FCM notifications, Docker-based deployment, and backend tests. Quite a lot for a compact messenger, but that is exactly the point here.

## Tech Stack

- Backend: Python, FastAPI, Pydantic v2, SQLAlchemy 2.0 async, Alembic
- Database: PostgreSQL as the persistent source of truth
- Realtime: native FastAPI WebSockets
- Realtime helper: Redis for presence, typing state, temporary connection/pubsub fanout
- Mobile: Ionic Vue, Vue 3 Composition API, TypeScript, Vite, Pinia, Vue Router
- Android: Capacitor
- Deployment: Docker Compose with PostgreSQL, Redis, backend, and persistent uploads

## Features

- Register/login/logout, access tokens, refresh tokens, protected routes
- Password reset token generation API
- User search by username, display name, or email
- Generated placeholder avatars and avatar upload
- Private one-to-one conversations only for v1
- Conversation list with latest message and unread count
- Message history with cursor pagination
- Realtime send/delete/read/typing/presence events over WebSockets
- File/image upload with MIME and size validation
- AES-256-GCM encryption at rest for new message text and chat attachments
- Versioned encryption keys for rotation without invalidating older encrypted records
- Local notifications for realtime messages outside the active chat
- Firebase Cloud Messaging push-token support for closed-app message notifications
- English/Ukrainian interface with a persisted in-app language selector
- Android double-back exit from the conversations screen
- Soft delete for everyone
- Dark, mobile-first Telegram-like UI

## Project Structure

```text
backend/              FastAPI app, Alembic, tests, Dockerfile
mobile/               Ionic Vue + Capacitor app
README.uk.md           Ukrainian version of this README
docker-compose.yml    PostgreSQL, Redis, backend, volumes
docker-compose.firebase.yml optional Firebase service account mount for FCM
.env.example          Root Docker environment template
```

## Architecture

FastAPI exposes the REST APIs and the WebSocket gateway. PostgreSQL keeps the permanent application data: users, conversations, participants, encrypted message payloads, read receipts, refresh tokens, password reset tokens, and attachment metadata. New message text and chat attachment bytes are encrypted with AES-256-GCM before they are written to storage, then decrypted only after participant authorization. Simple enough on the surface. Under the hood, though, this separation matters.

Files live in a persistent local uploads volume. Avatars are served publicly so profiles can render them, while encrypted chat attachments are delivered through authenticated download routes. Redis is deliberately limited to temporary realtime state: online presence, typing indicators, and pub/sub fanout for future multi-instance backend deployment. Permanent chat data never goes to Redis.

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Generate a 32-byte encryption key and place its Base64 value in `ENCRYPTION_KEYS` before starting the backend:

```bash
python3 -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Example configuration shape. The value below is intentionally only a placeholder:

```env
ENCRYPTION_ACTIVE_KEY_ID=v1
ENCRYPTION_KEYS={"v1":"REPLACE_WITH_BASE64_ENCODED_32_BYTE_KEY"}
```

Run migrations:

```bash
alembic upgrade head
```

Start the backend:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --no-access-log
```

Optional seed users:

```bash
python -m app.scripts_seed
```

## Docker Setup

From the repository root:

```bash
cp .env.example .env
docker compose up -d postgres redis
docker compose build backend
docker compose run --rm backend alembic upgrade head
docker compose up backend
```

Backend API: `http://localhost:8000`

PostgreSQL and Redis host ports are bound to `127.0.0.1` for local diagnostics only. Containers talk through the private Compose network, so ports `5432` and `6379` should not be exposed to the LAN or the internet.

On startup, the backend validates the active encryption key. Missing keys, unknown active key IDs, invalid Base64, and keys that are not exactly 32 bytes stop the app instead of quietly storing plaintext. A small check, but a very useful one.

### Encryption key rotation

Generate a new 32-byte key, keep the previous key in the JSON map, and change only the active ID:

```env
ENCRYPTION_ACTIVE_KEY_ID=v2
ENCRYPTION_KEYS={"v1":"OLD_BASE64_KEY","v2":"NEW_BASE64_KEY"}
```

After restart, new messages and attachments use `v2`; existing `v1` records remain decryptable. Do not remove `v1` until every record that references it has been re-encrypted or deleted. Also back up the key map separately from PostgreSQL and the uploads volume. Why so strict? Because losing a referenced key permanently loses access to the encrypted content that depends on it.

Persistent volumes:

- `postgres_data`: PostgreSQL data
- `redis_data`: Redis append-only data
- `uploads`: uploaded avatars and attachments

## Utility Scripts

Run these from anywhere inside the repository:

```bash
./scripts/backend-start.sh     # build backend, start Postgres/Redis, run migrations, start API
./scripts/backend-stop.sh      # stop Docker Compose services
./scripts/backend-logs.sh      # follow backend container logs
./scripts/backend-migrate.sh   # run Alembic migrations
./scripts/backend-test.sh      # run backend pytest suite
./scripts/mobile-dev.sh        # start Ionic/Vite browser dev server
./scripts/android-build.sh     # build and copy latest debug APK
./scripts/smoke-messages.sh    # dummy users, all-to-all WebSocket messages, and one image attachment check
./scripts/firebase-check.sh    # print safe Firebase service-account/IAM diagnostics
./scripts/rotate-jwt-secrets.sh # rotate ignored local .env JWT secrets without printing them
./scripts/health.sh            # check http://localhost:8000/health
./scripts/health.sh http://100.106.107.54:8000
./scripts/smoke-messages.sh http://100.106.107.54:8000
```

## Backend Tests

```bash
cd backend
pip install -e ".[dev]"
pytest
ruff check app
```

The tests use an async SQLite database and fake Redis for the core behavior: registration, login, protected route access, user search, private conversation creation, message service persistence, read receipts, soft delete, and upload validation.

## Mobile Tests

```bash
cd mobile
npm install
npm test
```

The mobile tests verify translation dictionary parity and the reconciliation of optimistic messages with server acknowledgements or errors.

## Mobile Setup

Requires Node.js 20.19+ or 22.12+ and npm.

```bash
cd mobile
npm install
cp .env.example .env
npm run dev
```

Browser development uses:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```

Production HTTPS/WSS uses the same variables, without changing application code:

```env
VITE_API_BASE_URL=https://relay.example.com
VITE_WS_BASE_URL=wss://relay.example.com
```

Terminate TLS at Caddy, Nginx, Tailscale Serve, or another trusted reverse proxy, then forward both REST and `/ws` traffic to FastAPI on port `8000`. Keep `http/ws` for local development or for a trusted encrypted tunnel only.

Add the public frontend origin, for example `https://relay.example.com`, to backend `CORS_ORIGINS`. During frontend startup, the API and WebSocket URLs reject unsupported schemes, query strings, and fragments.

Android emulator usually needs:

```env
VITE_API_BASE_URL=http://10.0.2.2:8000
VITE_WS_BASE_URL=ws://10.0.2.2:8000
```

A real Android phone on the same Wi-Fi/LAN needs the host LAN IP, for example:

```env
VITE_API_BASE_URL=http://192.168.1.50:8000
VITE_WS_BASE_URL=ws://192.168.1.50:8000
```

## Android Build

```bash
cd mobile
npm install
npm run build
npx cap add android
npx cap sync android
npx cap open android
```

Build a debug APK from Android Studio or from `mobile/android` with Gradle after the Android platform has been generated:

```bash
cd mobile/android
./gradlew assembleDebug
```

The APK is written to `mobile/android/app/build/outputs/apk/debug/app-debug.apk`.

### Android token storage

On native Android, access and refresh tokens plus the cached user profile are stored by the Capacitor secure-storage plugin with an Android Keystore-backed AES-GCM key. Browser development keeps a `localStorage` fallback because the browser cannot access Android Keystore. On the first native launch after upgrading, legacy auth values are migrated out of `localStorage` into secure storage.

Manual verification:

1. Build and install the Android app, log in, close it, and reopen it; the session must restore.
2. Inspect the WebView storage through Chrome DevTools; `accessToken`, `refreshToken`, and `authUser` must not exist in `localStorage` on Android.
3. Log out and verify that reopening the app requires login.
4. Run the browser build and verify login/refresh still works through the documented web fallback.

## Notifications

The app has two notification paths:

- Local notifications: when the app is running and receives a WebSocket `message:new` outside the currently open chat.
- FCM push notifications: when the recipient app is closed/disconnected and the backend persists a new message.

For closed-app Android notifications:

1. Create a Firebase project and Android app with package name `com.relay.messenger`.
2. Download `google-services.json` from Firebase and place it at `mobile/android/app/google-services.json` after running `npx cap add android`.
3. Create a Firebase service account JSON in Firebase Console, place it outside git, for example `firebase-service-account.json`.
4. In backend `.env`, set:

```env
PUSH_NOTIFICATIONS_ENABLED=true
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_SERVICE_ACCOUNT_FILE=/absolute/path/to/firebase-service-account.json
```

For Docker, place the ignored service account file at `backend/firebase-service-account.json`, set `FIREBASE_SERVICE_ACCOUNT_FILE=/app/firebase-service-account.json`, and include the Firebase override:

```bash
docker compose -f docker-compose.yml -f docker-compose.firebase.yml up -d backend
```

`./scripts/backend-start.sh` includes this override automatically when `backend/firebase-service-account.json` exists. Keep the real JSON file out of git.

If backend logs show `cloudmessaging.messages.create` permission denied, grant the service account the Firebase Cloud Messaging API Admin role (`roles/firebasecloudmessaging.admin`) in Google Cloud IAM.

To verify which service account and Firebase project your backend is using:

```bash
./scripts/firebase-check.sh
```

The script prints only safe metadata such as `project_id` and `client_email`, plus the exact `gcloud` IAM command. If Google Cloud IAM does not list the service account yet, use **Grant access**, paste the printed `client_email` as the new principal, and assign **Firebase Cloud Messaging API Admin**.

## REST API Summary

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`
- `GET /users/search?q=`
- `GET /users/me/profile`
- `PATCH /users/me/profile`
- `POST /users/me/avatar`
- `GET /conversations`
- `POST /conversations`
- `GET /conversations/{conversation_id}`
- `GET /conversations/{conversation_id}/messages?cursor=&limit=`
- `POST /conversations/{conversation_id}/read`
- `DELETE /messages/{message_id}`
- `POST /attachments/upload`
- `GET /attachments/{attachment_id}`
- `GET /attachments/{attachment_id}/download`
- `POST /devices/push-token`
- `DELETE /devices/push-token`

## WebSocket Events

Connect with `ws://HOST:8000/ws` in local development or `wss://relay.example.com/ws` in production, then send the first frame as:

```json
{"type":"auth","payload":{"token":"ACCESS_TOKEN"}}
```

Client to server:

- `auth`
- `conversation:join`
- `conversation:leave`
- `message:send`
- `message:delete`
- `message:read`
- `typing:start`
- `typing:stop`

Server to client:

- `message:new`
- `message:deleted`
- `message:read`
- `conversation:updated`
- `user:online`
- `user:offline`
- `typing:update`
- `error`

Attachments are uploaded first and then delivered to participants inside `message:new` after the sender sends the message. Orphan uploads are not broadcast.
Attachment previews and downloads use authenticated `/attachments/{attachment_id}/download` requests; raw attachment files are not exposed through the public static uploads route.

## Database Schema

Main tables:

- `users`: identity, email, password hash, avatar, last seen
- `refresh_tokens`: hashed persisted refresh tokens
- `password_reset_tokens`: hashed reset tokens
- `conversations`: private one-to-one chat records
- `conversation_participants`: participant rows and conversation-level read timestamp
- `messages`: legacy plaintext compatibility plus AES-GCM ciphertext, nonce, key ID, encryption version, timestamps, and soft-delete metadata
- `message_reads`: per-message read receipts
- `attachments`: uploaded file metadata, encrypted storage path, AES-GCM nonce, key ID, and encryption version
- `device_tokens`: Android/FCM device tokens and their selected locales for closed-app notifications

The app uses UUID strings as IDs. PostgreSQL remains the source of truth for all permanent data.

## Redis Keys

- `presence:user:{user_id}`: short-lived online marker
- `typing:conversation:{conversation_id}:user:{user_id}`: short-lived typing marker
- `pubsub:broadcast`: WebSocket event fanout channel

Redis data is temporary and safe to lose.

## Security Notes

- Passwords are hashed with Argon2.
- Access and refresh tokens use separate secrets.
- Refresh tokens are stored hashed in PostgreSQL.
- Native Android stores access and refresh tokens in Android Keystore-backed secure storage. Browser development uses a `localStorage` fallback; a public browser deployment should move refresh tokens to HttpOnly secure cookies for stronger XSS isolation.
- New message text and attachment bytes are encrypted at rest with AES-256-GCM using a unique random nonce per record.
- Encryption keys are versioned. New records use `ENCRYPTION_ACTIVE_KEY_ID`; old key IDs must remain in `ENCRYPTION_KEYS` until their records are re-encrypted.
- Auth-sensitive endpoints have a simple in-process per-IP rate limiter.
- Routes and WebSocket actions validate the current user.
- Only conversation participants can read, send, delete, or mark messages as read.
- Uploads use generated filenames and allow only images plus common document MIME types/extensions.
- Avatar files are public so profiles can render them; chat attachment files require authenticated route access.
- Message text is rendered as plain text in Vue, not unsafe HTML.
- Docker runs Uvicorn with access logging disabled so WebSocket JWT query tokens are not printed in normal container logs.
- For public deployments, run the backend behind HTTPS/WSS and rotate JWT and data-encryption keys.

This is server-side encryption at rest, not end-to-end encryption: the running backend can decrypt authorized responses and push previews. Database dumps and copied upload volumes do not contain plaintext for newly stored messages/files, but compromise of both the backend and its encryption keys can expose content.

## Selfhosting

Windows PC with Docker Desktop:

1. Install Docker Desktop.
2. Copy `.env.example` to `.env`.
3. Run the Docker commands above.
4. Use `localhost` for browser testing, `10.0.2.2` for Android emulator, or the PC LAN IP for a real phone.

Linux server with Docker Engine:

1. Install Docker Engine and Compose plugin.
2. Copy `.env.example` to `.env` and set strong secrets.
3. Run migrations and start the stack.
4. Use a domain with Caddy/Nginx and HTTPS, or use a VPN such as Tailscale for private access.

Back up PostgreSQL regularly and keep uploaded files on persistent storage.

## Known Limitations

- Password reset returns a token through the API instead of sending email over SMTP.
- FCM push notifications require Firebase project setup and are disabled by default in `.env`.
- Closed-app notifications require Android/Firebase credentials; local WebSocket notifications work without Firebase.
- Group chats, voice messages, message editing, reactions, blocking/reporting, and admin moderation are not implemented.
- Local uploads are suitable for local or small self-hosted setups; S3-compatible object storage is a better upgrade for larger deployments.
- Full end-to-end encryption is intentionally left as a future improvement.
- Migration `0003_content_encryption` adds nullable encryption metadata, so legacy plaintext records/files remain readable without breaking history. It does not rewrite existing content; perform a controlled backfill before claiming that every historical row/file is encrypted.

## Suggested Improvements

- Full E2EE with audited protocol design
- Rich notification actions and notification grouping
- Group chats and roles
- Message editing and reactions
- User blocking/reporting
- Admin moderation tools
- S3-compatible object storage
- Reverse proxy with automatic HTTPS
- More complete frontend tests
