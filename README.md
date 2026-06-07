# Relay Messenger

Relay is a real-time messenger with a FastAPI backend and an Ionic Vue + Capacitor Android-first frontend. It implements database persistence, JWT authentication, private one-to-one chats, message history, attachments, read receipts, online status, typing indicators, avatars, local/FCM notifications, Docker deployment, and backend tests.

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
- Local notifications for realtime messages outside the active chat
- Firebase Cloud Messaging push-token support for closed-app message notifications
- Android double-back exit from the conversations screen
- Soft delete for everyone
- Dark, mobile-first Telegram-like UI

## Project Structure

```text
backend/              FastAPI app, Alembic, tests, Dockerfile
mobile/               Ionic Vue + Capacitor app
docker-compose.yml    PostgreSQL, Redis, backend, volumes
docker-compose.firebase.yml optional Firebase service account mount for FCM
.env.example          Root Docker environment template
```

## Architecture

FastAPI provides REST APIs and the WebSocket gateway. PostgreSQL stores users, conversations, participants, messages, read receipts, refresh tokens, password reset tokens, and attachment metadata. Files are stored in a persistent local uploads volume: avatars are served publicly, while chat attachments are served through authenticated download routes. Redis stores temporary realtime state only: online presence, typing indicators, and pub/sub fanout for future multi-instance backend deployment. Permanent chat data is never stored in Redis.

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
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
```

The tests use an async SQLite database and fake Redis for core behavior: registration, login, protected route access, user search, private conversation creation, message service persistence, read receipts, soft delete, and upload validation.

## Mobile Setup

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

Android emulator usually needs:

```env
VITE_API_BASE_URL=http://10.0.2.2:8000
VITE_WS_BASE_URL=ws://10.0.2.2:8000
```

Real Android phone on the same Wi-Fi/LAN needs the host LAN IP, for example:

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

Build a debug APK from Android Studio, or from `mobile/android` with Gradle after the Android platform has been generated:

```bash
cd mobile/android
./gradlew assembleDebug
```

The APK is written to `mobile/android/app/build/outputs/apk/debug/app-debug.apk`.

## Notifications

The app uses two notification paths:

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

Connect with `ws://HOST:8000/ws`, then send the first frame as:

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

Attachments are uploaded first, then delivered to participants inside `message:new` after the sender sends the message. Orphan uploads are not broadcast.
Attachment previews and downloads use authenticated `/attachments/{attachment_id}/download` requests; raw attachment files are not exposed through the public static uploads route.

## Database Schema

Main tables:

- `users`: identity, email, password hash, avatar, last seen
- `refresh_tokens`: hashed persisted refresh tokens
- `password_reset_tokens`: hashed reset tokens
- `conversations`: private one-to-one chat records
- `conversation_participants`: participant rows and conversation-level read timestamp
- `messages`: text, timestamps, soft delete metadata
- `message_reads`: per-message read receipts
- `attachments`: uploaded file metadata and storage path
- `device_tokens`: Android/FCM device tokens for closed-app notifications

The app uses UUID strings as IDs. PostgreSQL is the source of truth for all permanent data.

## Redis Keys

- `presence:user:{user_id}`: short-lived online marker
- `typing:conversation:{conversation_id}:user:{user_id}`: short-lived typing marker
- `pubsub:broadcast`: WebSocket event fanout channel

Redis data is temporary and safe to lose.

## Security Notes

- Passwords are hashed with Argon2.
- Access and refresh tokens use separate secrets.
- Refresh tokens are stored hashed in PostgreSQL.
- The mobile app stores tokens in local storage for Capacitor/browser simplicity; a web deployment can use httpOnly secure refresh cookies for stronger browser isolation.
- Auth-sensitive endpoints have a simple in-process per-IP rate limiter.
- Routes and WebSocket actions validate the current user.
- Only conversation participants can read, send, delete, or mark messages as read.
- Uploads use generated filenames and allow only images plus common document MIME types/extensions.
- Avatar files are public so profiles can render them; chat attachment files require authenticated route access.
- Message text is rendered as plain text in Vue, not unsafe HTML.
- Docker runs Uvicorn with access logging disabled so WebSocket JWT query tokens are not printed in normal container logs.
- For public deployments, run the backend behind HTTPS and rotate secrets.

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
