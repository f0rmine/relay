# Relay Messenger: повний контекст проєкту

Цей документ описує фактичний стан репозиторію Relay Messenger. Він призначений як технічний контекст для розробника або іншої мовної моделі. У документі не заявлено функцій, яких немає у коді.

## 1. Призначення проєкту

Relay Messenger — клієнт-серверний застосунок для приватного обміну повідомленнями між двома користувачами. Основний клієнт орієнтований на Android, але той самий Vue-код запускається у браузері для розробки.

Система підтримує реєстрацію, вхід, профілі, аватари, пошук користувачів, приватні діалоги 1-to-1, текстові повідомлення, файли, зображення, історію повідомлень, unread count, read receipts, typing indicator, online/offline status, last seen, видалення повідомлення для всіх, локальні сповіщення та Firebase push-сповіщення.

Проєкт є робочим MVP для демонстраційного або малого self-hosted розгортання. Він не позиціонується як повністю підготовлений публічний production-сервіс.

## 2. Реалізовані функції

У поточному коді реалізовано:

- реєстрацію за username, display name, email і password;
- вхід за username або email;
- access і refresh JWT;
- rotation refresh token;
- logout і відкликання refresh token;
- серверний password reset token flow;
- отримання та редагування профілю;
- avatar upload або локальний placeholder з ініціалами, який формує frontend;
- пошук інших користувачів за username, display name та email;
- private conversation між двома користувачами;
- запобігання дублюванню одного й того самого private conversation;
- список діалогів, відсортований за останньою активністю;
- preview останнього повідомлення на головному екрані;
- prefix `You:` або його локалізований аналог для власного останнього повідомлення;
- надсилання тексту через WebSocket;
- optimistic message у клієнті до server acknowledgement;
- точне зіставлення optimistic message із серверним через `request_id`;
- видалення pending message після server error або 15-секундного timeout;
- cursor pagination історії;
- стабільну pagination для повідомлень з однаковим timestamp;
- image/file upload;
- image preview і file message у чаті;
- захищене скачування attachment;
- soft delete власного повідомлення для всіх;
- стилізований deleted-message state без оригінального тексту;
- unread count;
- read receipts;
- typing indicator;
- online/offline presence;
- last seen timestamp;
- reconnect WebSocket із exponential backoff;
- повторний join активних чатів після reconnect;
- refresh активної історії після reconnect;
- локальні Android notifications;
- Firebase Cloud Messaging для закритого застосунку;
- відкриття конкретного чату з push notification;
- видалення notification, коли користувач сам відкрив відповідний чат;
- українську та англійську локалізацію;
- темний mobile-first UI;
- browser development mode;
- Android build через Capacitor;
- генерацію Android launcher icon із `mobile/assets/logo.png`;
- server-side AES-256-GCM encryption для текстів повідомлень і attachment bytes.

## 3. Функції, яких немає

У поточній версії не реалізовано:

- групові чати;
- канали;
- message editing;
- reactions;
- voice messages;
- voice/video calls;
- user blocking/reporting;
- admin panel;
- moderation tools;
- email delivery password reset link;
- forgot/reset password screens у mobile client;
- наскрізне шифрування E2EE;
- S3-compatible object storage;
- reverse proxy у Docker Compose;
- автоматичне HTTPS provisioning;
- background job queue;
- automated Android UI/instrumentation tests;
- CI/CD pipeline.

## 4. Загальна архітектура

Архітектура клієнт-серверна.

Ionic Vue client відповідає за UI, route navigation, локальний стан, REST-запити, WebSocket connection, завантаження файлів, локальні notifications і реєстрацію FCM token.

FastAPI backend відповідає за автентифікацію, authorization, validation, бізнес-логіку, роботу з PostgreSQL, шифрування і розшифрування вмісту, WebSocket events, Redis presence/PubSub і FCM HTTP v1 requests.

PostgreSQL є основним джерелом правди. У ньому зберігаються користувачі, сесії, діалоги, повідомлення, read receipts, attachment metadata і device tokens.

Redis використовується лише для тимчасового realtime-стану. Постійні повідомлення у Redis не зберігаються.

Uploads volume містить avatar files і зашифровані attachment files. Метадані цих файлів знаходяться у PostgreSQL.

Firebase Cloud Messaging використовується для Android push delivery, коли отримувач не має активного WebSocket або не знаходиться у відповідному чаті.

## 5. Структура репозиторію

Корінь репозиторію містить `backend`, `mobile`, `scripts`, `docs`, Docker Compose files, env examples і README.

`backend/app/main.py` є точкою входу FastAPI.

`backend/app/api/routes` містить REST routes для auth, users, conversations, messages, attachments і devices.

`backend/app/api/deps.py` містить dependency для async database session та отримання current user із Bearer token.

`backend/app/core` містить конфігурацію, database engine, Redis client, security helpers, encryption, rate limiting та exception handling.

`backend/app/models` містить SQLAlchemy models.

`backend/app/schemas` містить Pydantic request, response та WebSocket schemas.

`backend/app/services` містить основну бізнес-логіку. Routes не повинні дублювати цю логіку.

`backend/app/websocket` містить WebSocket endpoint, serialization helpers та connection manager.

`backend/app/tests` містить backend tests.

`backend/alembic` містить Alembic migrations.

`mobile/src/views` містить application screens.

`mobile/src/components` містить reusable UI components.

`mobile/src/stores` містить Pinia stores.

`mobile/src/api` містить HTTP client та shared TypeScript interfaces.

`mobile/src/services` містить auth storage, notifications, push і navigation helpers.

`mobile/src/i18n` містить English/Ukrainian dictionaries та locale setup.

`mobile/src/config/env.ts` нормалізує API і WebSocket URLs.

`mobile/android` є native Android project, створеним Capacitor.

`mobile/scripts/generate-android-icons.mjs` генерує Android launcher resources.

`scripts` містить команди запуску, зупинки, migration, tests, healthcheck, smoke test, Firebase check та Android build.

## 6. Backend technology stack

Backend написаний на Python 3.11+.

FastAPI використовується для REST API, dependency injection, OpenAPI, middleware та native WebSocket endpoint.

Uvicorn запускає ASGI application.

Pydantic v2 перевіряє request/response/WebSocket payloads.

`pydantic-settings` завантажує конфігурацію з environment variables і `.env`.

SQLAlchemy 2.0 async style використовується для ORM та database queries.

`asyncpg` є PostgreSQL driver.

Alembic керує migrations.

`redis.asyncio` використовується для Redis operations.

`argon2-cffi` використовується для password, refresh token і reset token hashes.

PyJWT створює і перевіряє JWT.

`cryptography` реалізує AES-GCM encryption.

`aiofiles` використовується для async file operations.

HTTPX і Google Auth використовуються для Firebase HTTP v1.

## 7. Backend lifecycle

Під час імпорту application backend перевіряє encryption key configuration і створює uploads/avatar directories.

Під час startup backend виконує Redis `PING` і запускає Redis Pub/Sub subscriber.

Якщо Redis недоступний або encryption keys неправильні, backend повинен завершити запуск із явною помилкою, а не працювати з частково зламаним realtime.

Під час shutdown backend припиняє приймати нові з'єднання, очікує завершення вже запланованих push tasks, скасовує Redis subscriber і закриває Redis connection.

Окремого Celery, RQ або іншого background worker немає.

## 8. Authentication і session security

Паролі хешуються Argon2. Password hash ніколи не повертається через API.

JWT підписуються алгоритмом HS256.

Access token і refresh/password-reset token використовують різні secrets.

Access token за замовчуванням діє 30 хвилин.

Refresh token за замовчуванням діє 14 днів.

Refresh token зберігається у PostgreSQL тільки як Argon2 hash.

`POST /auth/refresh` відкликає попередній refresh token і видає нову пару. Повторне використання старого token відхиляється.

Password reset token також зберігається як hash. Після reset він позначається використаним, а active refresh sessions користувача відкликаються.

Password recovery реалізовано частково: backend генерує reset token, але email не надсилається. За замовчуванням endpoint повертає однакову generic response незалежно від існування email, а поле `reset_token` має значення `null`. Для локальної демонстрації token можна явно дозволити через `PASSWORD_RESET_TOKEN_IN_RESPONSE=true`; production-конфігурація забороняє цей режим.

Auth endpoints мають Redis-backed fixed-window rate limit: 20 attempts за 60 секунд на комбінацію IP і route. Atomic Lua operation робить limiter спільним для кількох backend processes або instances.

REST authentication використовує `Authorization: Bearer <access_token>`.

WebSocket не передає token у query string. Після відкриття `/ws` першим JSON frame надсилається event `auth` із access token.

## 9. Server-side encryption

Проєкт використовує server-side encryption at rest. Це не E2EE.

Текст повідомлення перед записом у PostgreSQL шифрується AES-256-GCM.

Для кожного message генерується окремий випадковий 12-byte nonce.

Ciphertext прив’язаний до конкретного message ID через associated data.

У таблиці `messages` зберігаються `text_ciphertext`, `text_nonce`, `text_key_id` та `encryption_version`.

Поле `text` для нових повідомлень залишається `NULL`.

Attachment bytes також шифруються AES-256-GCM перед записом на диск. У PostgreSQL зберігаються nonce, key ID, version і encrypted file path.

`ENCRYPTION_ACTIVE_KEY_ID` вказує ключ для нових записів.

`ENCRYPTION_KEYS` є JSON object, де key ID відповідає Base64-encoded 32-byte key.

Keyring підтримує rotation: новий active key використовується для нових записів, старі keys залишаються для читання старих records.

Legacy plaintext message/attachment records можуть читатися без encryption metadata.

Soft delete очищає message ciphertext, nonce, key ID і version.

Backend володіє encryption keys і розшифровує дані перед відправленням клієнту. Тому оператор сервера технічно має доступ до plaintext. Це забезпечує захист даних на диску або у database dump, але не конфіденційність від сервера.

Аватари, usernames, emails, conversation metadata, sender IDs, timestamps, MIME types та file sizes не шифруються.

Втрата encryption keyring робить зашифровані дані невідновними.

## 10. Database models

Усі основні IDs є UUID strings довжиною 36 символів.

`User` зберігає ID, username, email, display name, avatar URL, password hash, created/updated timestamps і last seen.

Username та email мають unique constraints та indexes.

`RefreshToken` зберігає user ID, indexed unique JWT ID (`jti`), token hash, created time, expiry та revoked time.

`PasswordResetToken` зберігає user ID, indexed unique JWT ID (`jti`), token hash, expiry та used time.

`Conversation` зберігає ID, kind, private key, created time та updated time.

Private key формується з двох відсортованих user UUID. Він unique та indexed.

`ConversationParticipant` зв’язує user і conversation. Комбінація conversation/user unique. Модель також зберігає joined time та last read time.

`Message` зберігає conversation ID, sender ID, encrypted text fields, timestamps, future edited timestamp, deleted timestamp і deleted-by user ID.

Для message history існує composite index за conversation ID та created time.

`MessageRead` зберігає message ID, reader user ID і read timestamp. Комбінація message/user unique.

`Attachment` зберігає message ID, uploader ID, original filename, generated stored filename, MIME type, original file size, paths, public/download URL, encryption metadata та created time.

`DeviceToken` зберігає user ID, unique FCM token, platform, locale, optional device ID, enabled state та timestamps.

## 11. Database migrations

`0001_initial` створює основні users, auth, conversations, messages, read receipts та attachments tables.

`0002_device_tokens` додає FCM device tokens.

`0003_content_encryption` додає message і attachment encryption columns.

`0004_device_token_locale` додає locale для локалізованого push preview.

`0005_token_jti` додає indexed unique `jti` для refresh і password-reset tokens. Старі rows без `jti` залишаються сумісними та перевіряються через legacy fallback.

Міграції запускаються командою `./scripts/backend-migrate.sh` або `docker compose run --rm --build backend alembic upgrade head`.

## 12. REST API

FastAPI автоматично надає Swagger UI за `/docs`, ReDoc за `/redoc` і OpenAPI JSON за `/openapi.json`.

`GET /health` є простим liveness endpoint і повертає status `ok` без перевірки зовнішніх залежностей.

`GET /health/ready` перевіряє PostgreSQL, Redis та стан Pub/Sub subscriber. Саме цей endpoint використовується Docker healthcheck і script `./scripts/health.sh`.

Auth routes:

- `POST /auth/register` створює користувача та token pair;
- `POST /auth/login` виконує вхід;
- `POST /auth/refresh` виконує token rotation;
- `POST /auth/logout` відкликає refresh token;
- `GET /auth/me` повертає current user;
- `POST /auth/forgot-password` створює reset token;
- `POST /auth/reset-password` змінює password.

User routes:

- `GET /users/search?q=` шукає до 20 інших users;
- `GET /users/me/profile` повертає current profile;
- `PATCH /users/me/profile` змінює display name або email;
- `POST /users/me/avatar` приймає multipart avatar.

Conversation routes:

- `GET /conversations` повертає список, participants, latest message, unread count і presence;
- `POST /conversations` створює або повертає private chat;
- `GET /conversations/{conversation_id}` повертає доступний chat;
- `GET /conversations/{conversation_id}/messages` повертає paginated history;
- `POST /conversations/{conversation_id}/read` позначає messages прочитаними.

Message route:

- `DELETE /messages/{message_id}` виконує soft delete власного message.

Attachment routes:

- `POST /attachments/upload` завантажує file та опційно перевіряє `conversation_id`;
- `GET /attachments/{attachment_id}` повертає metadata;
- `GET /attachments/{attachment_id}/download` перевіряє доступ, розшифровує і повертає bytes.

Device routes:

- `POST /devices/push-token` реєструє або оновлює FCM token;
- `DELETE /devices/push-token` відключає token поточного користувача.

## 13. Conversation і message logic

Користувач не може створити conversation із самим собою.

Перед читанням, надсиланням, read action, typing action, attachment access або delete backend перевіряє participation.

Conversation list сортується за `updated_at` у descending order.

Unread count враховує лише чужі, не видалені повідомлення після `last_read_at`.

Read action оновлює `last_read_at` і створює missing `MessageRead` rows.

History використовує opaque URL-safe Base64 cursor. Cursor містить created timestamp і message ID. ID є tie-breaker для однакових timestamps.

Message може містити text, attachments або обидва. Повністю порожній message відхиляється.

Attachment перед прив’язкою повинен належати sender і не бути прив’язаним до іншого message.

Delete дозволений тільки sender. Він не видаляє database row, а встановлює deleted metadata та очищає encrypted text.

Frontend delete використовує REST endpoint і отримує realtime broadcast через backend.

## 14. File і avatar storage

Default maximum upload size — 10 MB.

Upload читається chunks, тому backend припиняє читання після перевищення limit замість необмеженого завантаження у RAM.

Дозволені attachment formats: JPEG, PNG, WebP, GIF, PDF, TXT, DOC і DOCX.

Backend перевіряє MIME type, extension і size. Для image files також перевіряються magic bytes.

Stored filename генерується через UUID. Raw user filename не використовується як disk path.

Original filename залишається у metadata та `Content-Disposition` download response.

Attachment bytes на диску зашифровані.

До прив’язки attachment доступний uploader. Після прив’язки доступ мають тільки conversation participants. Attachment видаленого message не повертається користувачу.

Avatar formats: JPEG, PNG, WebP і GIF. Avatar validation також перевіряє extension, MIME, magic bytes і size.

Avatar files не шифруються та роздаються через `/uploads/avatars`.

Якщо avatar не завантажений, `avatar_url` залишається `null`, а frontend локально показує placeholder з ініціалами. Реєстрація не залежить від зовнішнього avatar service.

## 15. WebSocket protocol

WebSocket endpoint — `/ws`.

Перший client event повинен бути `auth` із access token. Backend відповідає `auth:ok`.

Client events:

- `conversation:join`;
- `conversation:leave`;
- `message:send`;
- `message:delete`;
- `message:read`;
- `typing:start`;
- `typing:stop`.

Server events:

- `auth:ok`;
- `conversation:joined`;
- `conversation:left`;
- `message:new`;
- `message:deleted`;
- `message:read`;
- `conversation:updated`;
- `user:online`;
- `user:offline`;
- `typing:update`;
- `error`.

`message:send` використовує optional top-level `request_id`. Backend повертає цей ID у `message:new`. Frontend використовує його як acknowledgement для точного видалення optimistic placeholder.

Malformed JSON не завершує connection. Backend повертає safe error і продовжує приймати events.

Validation або internal processing errors не повертають sensitive exception details.

## 16. Redis behavior

Presence key має формат `presence:user:{user_id}` і є Redis sorted set з окремою lease для кожного backend instance. Key має TTL 45 секунд.

Backend оновлює presence heartbeat кожні 15 секунд.

Typing key має формат `typing:conversation:{conversation_id}:user:{user_id}` і TTL 5 секунд.

Realtime fanout використовує Redis channel `pubsub:broadcast`.

Connection manager зберігає local sockets per user та local room membership у пам’яті backend process.

Кожен process має instance ID. Event спочатку надсилається local sockets, потім публікується у Redis. Subscriber іншого process надсилає event своїм local sockets. Origin process ігнорує власну Pub/Sub копію.

Redis Pub/Sub не є durable queue. Після reconnect клієнт перечитує активний chat із PostgreSQL.

Коли останній local connection користувача закривається, backend видаляє lease лише свого instance. `user:offline` і оновлення `last_seen_at` відбуваються тільки тоді, коли у sorted set не залишилося активних leases інших instances.

Auth rate-limit key має формат `rate_limit:auth:{sha256}` і короткий TTL, рівний fixed-window interval. Hash не розкриває raw IP або route у назві Redis key.

## 17. Firebase push notifications

Client-side Firebase config знаходиться у `mobile/android/app/google-services.json`.

Backend service account очікується у `backend/firebase-service-account.json` для Docker deployment.

`docker-compose.firebase.yml` монтує service account read-only як `/app/firebase-service-account.json`.

Необхідні variables:

- `PUSH_NOTIFICATIONS_ENABLED=true`;
- `FIREBASE_PROJECT_ID=<project-id>`;
- `FIREBASE_SERVICE_ACCOUNT_FILE=/app/firebase-service-account.json`.

Service account JSON містить private key і ніколи не повинен комітитися.

Backend використовує FCM HTTP v1 та OAuth access token із service account. Надсилання планується як окрема відстежувана `asyncio` task з власною database session, тому HTTP-запит до FCM не блокує WebSocket receive loop. Це не durable job queue: аварійне завершення process може втратити ще не відправлений push.

Push title містить display name або username sender.

Push body містить plaintext message preview або локалізоване `Image`, `Attachment`, `Message deleted` чи generic `Message`.

Device token зберігає locale, тому Ukrainian client отримує Ukrainian attachment labels, а English client — English labels.

FCM request містить conversation ID, message ID і sender ID у data payload.

Android channel має ID `messages` і high importance.

Після натискання notification client відкриває відповідний conversation.

Коли conversation відкрито вручну, delivered notifications цього conversation видаляються.

Під час logout frontend намагається disable token на backend і викликає native unregister.

FCM 400/404 вимикає invalid token. Permission/config errors ставлять FCM delivery на cooldown 300 секунд.

`./scripts/firebase-check.sh` перевіряє metadata service account та env configuration без друку private key.

## 18. Frontend technology stack

Frontend написаний на Vue 3 Composition API та TypeScript.

Ionic Vue надає mobile UI components, navigation behavior, safe areas та Android-friendly layout.

Pinia керує state.

Vue Router разом з Ionic Router керує routes.

Vite запускає dev server і збирає production web bundle.

`vue-tsc` виконує type checking.

`vue-i18n` забезпечує English/Ukrainian localization.

Capacitor загортає web bundle у Android application.

Capacitor Secure Storage зберігає credentials на Android.

Capacitor Push Notifications працює з FCM.

Capacitor Local Notifications показує foreground notifications.

Ionicons використовується для UI icons.

Sharp використовується тільки під час development/build для launcher icon generation.

## 19. Frontend routes і screens

`/login` відкриває `LoginView.vue`.

`/register` відкриває `RegisterView.vue`.

`/conversations` відкриває `ConversationsView.vue`.

`/chat/:id` відкриває `ChatView.vue`.

`/search` відкриває `UserSearchView.vue`.

`/profile` відкриває `ProfileView.vue`.

Login і register routes позначені guest-only.

Conversations, chat, search і profile routes позначені authenticated.

Router guard викликає auth restore перед navigation.

Guest перенаправляється на login. Authenticated user із guest route перенаправляється на conversations.

## 20. Frontend state

`auth.ts` відповідає за register, login, restore, current user, logout, token synchronization, push init та reset інших stores.

`conversations.ts` відповідає за conversation list, latest message, unread count і presence state.

`messages.ts` відповідає за history, cursors, has-more state, durable outbox, automatic retry, confirmed-message cache, upload, optimistic send, read, delete і typing state.

`socket.ts` відповідає за WebSocket lifecycle, auth frame, event queue, active rooms, reconnect і dispatch server events у stores.

Після explicit logout conversations, messages та локальні IndexedDB records цього user повністю очищаються. Після тимчасового завершення session outbox зберігається окремо за user ID, щоб запити можна було продовжити після повторного входу в той самий account.

## 21. Frontend API і token handling

`mobile/src/api/client.ts` автоматично додає Bearer token до REST requests.

Для FormData client не задає JSON content type вручну.

Якщо REST request отримує 401, client запускає один shared refresh request і не дублює одночасні refresh operations.

Після успішного refresh початковий request повторюється з новим access token.

Після невдалого refresh tokens і current user очищаються, а application отримує auth-expired event.

Known backend errors локалізуються через translation dictionary.

Authenticated download використовує окремий blob request helper.

На Android access token, refresh token і cached user зберігаються у Secure Storage.

Legacy native values автоматично мігруються з localStorage у Secure Storage, після чого plaintext localStorage values видаляються.

У browser build tokens залишаються у localStorage. Це відоме security limitation web-версії.

Transient network error під час `/auth/me` не видаляє локальну session. Credentials очищаються тільки після підтвердженого authentication failure.

## 22. Frontend realtime behavior

WebSocket reconnect використовує exponential delay від 1 до 30 секунд.

Manual logout/disconnect вимикає reconnect.

Після `auth:ok` queued events надсилаються, active conversations повторно join-яться, а після reconnect active history оновлюється.

Text/file input очищається тільки після успішного durable запису request у IndexedDB outbox.

Кожне outgoing message отримує стабільний `client_message_id`. Backend має unique constraint за sender і client ID, тому повторний REST або WebSocket request повертає вже створене повідомлення без дублювання fanout та push.

Optimistic message отримує ID `pending-{client_message_id}` та delivery state `queued`, `sending` або `failed`.

Attachment до відправлення зберігається як Blob в IndexedDB. Після відновлення мережі client спочатку завантажує attachment, зберігає server attachment ID у тому самому outbox record, а потім створює message через `POST /messages`.

Після REST response або `message:new` із відповідним client ID pending message замінюється persistent message, а outbox record і локальний attachment Blob видаляються.

Transient network/server failures використовують exponential backoff із jitter. Permanent 4xx failure залишається у chat із діями retry та remove.

Flush запускається після login restore, WebSocket `auth:ok`, browser online event, Capacitor network status recovery та application resume. Android не гарантує довільне background execution після повного завершення process, тому durable outbox гарантує збереження request, а delivery продовжується у наступне дозволене lifecycle window.

Останні 200 confirmed messages кожної відкритої conversation кешуються окремо від outbox для offline reading. Локальний cache ізольований app/WebView sandbox, але не є E2EE.

Typing events не накопичуються у stale queue.

Під час прямого переходу з одного `/chat/:id` на інший старий conversation залишає room, а новий завантажується та join-иться.

User search захищений request sequence, тому повільна відповідь старого query не перезаписує нові результати.

## 23. Localization

Підтримуються тільки locales `en` та `uk`.

English є fallback locale.

Initial locale береться зі збереженого `relay.locale`. Якщо значення немає, client перевіряє device/browser languages і вибирає Ukrainian лише для `uk`, інакше English.

Language selector оновлює Vue locale, HTML `lang`, localStorage, Android notification channel та locale FCM token.

Translation tests перевіряють, що English та Ukrainian dictionaries мають однакові keys.

## 24. Android build

Capacitor application ID — `com.relay.messenger`.

Application name — `Relay`.

Web output directory — `dist`.

Capacitor має secure default: cleartext HTTP вимкнений, Android backup і full-backup вимкнені. `./scripts/android-build.sh` явно встановлює `CAPACITOR_ALLOW_CLEARTEXT=true` за замовчуванням для локального LAN/Tailscale debug APK. Для HTTPS/WSS build потрібно запускати `CAPACITOR_ALLOW_CLEARTEXT=false ./scripts/android-build.sh`.

Потрібні Node.js 20.19+ або 22.12+, npm, Android SDK, accepted SDK licenses та Java/JDK. Build script використовує Java 21 path, якщо він є у стандартному Linux location.

Source launcher icon знаходиться у `mobile/assets/logo.png`.

Logo повинен бути square PNG не менше 1024x1024.

`npm run assets:android` генерує square, round та adaptive foreground resources для mdpi, hdpi, xhdpi, xxhdpi та xxxhdpi.

Artwork займає 55% canvas, щоб Android adaptive masks не обрізали logo.

`./scripts/android-build.sh` виконує npm install, TypeScript/Vite build, Vitest, icon generation, Capacitor sync і Gradle assembleDebug.

Capacitor CLI 6.2.1 очікує старий CommonJS export `tar`, але безпечна версія `tar@7.5.16` змінила форму export. `mobile/package.json` залишає security override на 7.5.16, а `postinstall` запускає вузький script `mobile/scripts/patch-capacitor-cli.mjs`, який адаптує один import call у встановленому CLI. Script fail-fast завершується помилкою, якщо структура майбутньої версії Capacitor зміниться. Цей workaround можна видалити після узгодженого major upgrade Capacitor і native plugins.

Основний APK знаходиться у `mobile/android/app/build/outputs/apk/debug/app-debug.apk`.

Build script також створює timestamped `relay-debug-<timestamp>.apk` у тому самому каталозі.

## 25. Environment variables

`POSTGRES_DB`, `POSTGRES_USER` і `POSTGRES_PASSWORD` налаштовують PostgreSQL container.

`ENVIRONMENT` задає режим `development`, `test` або `production`. У production backend відхиляє слабкі default secrets, wildcard CORS, non-PostgreSQL database, incomplete Firebase configuration та повернення reset token у response.

`DATABASE_URL` задає async SQLAlchemy connection URL.

`REDIS_URL` задає Redis URL.

`JWT_SECRET` підписує access tokens.

`JWT_REFRESH_SECRET` підписує refresh і reset tokens.

`ACCESS_TOKEN_EXPIRE_MINUTES` задає access token TTL.

`REFRESH_TOKEN_EXPIRE_DAYS` задає refresh token TTL.

`PASSWORD_RESET_TOKEN_IN_RESPONSE` дозволяє показати reset token тільки для контрольованої локальної демонстрації. У production значення повинно бути `false`.

`CORS_ORIGINS` є comma-separated allowlist.

`UPLOAD_DIR` задає storage path.

`MAX_UPLOAD_SIZE_MB` задає upload limit.

`ENCRYPTION_ACTIVE_KEY_ID` задає active encryption key.

`ENCRYPTION_KEYS` задає JSON keyring.

`PUSH_NOTIFICATIONS_ENABLED` вмикає FCM.

`FIREBASE_PROJECT_ID` задає Firebase project.

`FIREBASE_SERVICE_ACCOUNT_FILE` задає path до private service account JSON.

`VITE_API_BASE_URL` задає mobile/web REST base URL.

`VITE_WS_BASE_URL` опційно задає WebSocket base URL. Якщо його немає, client перетворює API `http` на `ws`, а `https` на `wss`.

`CAPACITOR_ALLOW_CLEARTEXT` є build-time variable для Android. Значення `true` потрібне лише для HTTP/WS backend у локальній мережі; production HTTPS/WSS build повинен використовувати `false`.

URL validation не дозволяє unsupported schemes, query strings або fragments.

## 26. Docker Compose

`docker-compose.yml` запускає `postgres`, `redis` і `backend`.

PostgreSQL image — `postgres:16-alpine`.

Redis image — `redis:7-alpine` з append-only mode.

PostgreSQL port прив’язаний до `127.0.0.1:5432`.

Redis port прив’язаний до `127.0.0.1:6379`.

Backend port exposed як `8000:8000` для browser, Android, LAN або Tailscale clients.

PostgreSQL використовує named volume `postgres_data`.

Redis використовує named volume `redis_data`.

Uploads використовують named volume `uploads`.

Усі три services мають healthchecks.

Backend залежить від healthy PostgreSQL і Redis.

`docker-compose.firebase.yml` є optional override, який додає read-only service account mount.

`docker-compose.production.yml` є production override: вимагає явні database/JWT/CORS/encryption values, встановлює `ENVIRONMENT=production`, вимикає reset-token exposure, додає restart policies та прив'язує backend port до loopback для роботи за reverse proxy або VPN gateway.

Backend image збирається multi-stage Dockerfile. Runtime image не містить compiler toolchain, application запускається від непривілейованого користувача `relay`, а entrypoint коригує ownership persistent uploads volume перед пониженням прав.

Reverse proxy не входить до Compose. Для public access потрібно додати Caddy, Nginx або інший HTTPS/WSS proxy.

## 27. Запуск проєкту

Для першого backend запуску потрібно скопіювати `.env.example` у `.env`, замінити database password, JWT secrets та encryption key, а потім виконати `./scripts/backend-start.sh`.

`backend-start.sh` будує backend image, запускає PostgreSQL/Redis, виконує Alembic migrations і запускає backend.

Якщо `backend/firebase-service-account.json` існує, script автоматично додає Firebase Compose override.

Healthcheck виконується командою `./scripts/health.sh`.

Для суворішого deployment profile використовується `./scripts/backend-production-start.sh`. Script перевіряє обов'язкові production variables, застосовує `docker-compose.production.yml`, виконує build, migrations і запуск services.

Backend logs відкриваються через `./scripts/backend-logs.sh`.

Backend зупиняється через `./scripts/backend-stop.sh`.

Frontend dev server запускається через `./scripts/mobile-dev.sh`.

Для browser development API зазвичай `http://localhost:8000`.

Для Android emulator API зазвичай `http://10.0.2.2:8000`.

Для фізичного Android використовується LAN/Tailscale IP або DNS backend host.

Якщо frontend завантажений через HTTPS, WebSocket URL повинен використовувати WSS.

## 28. Tests і quality checks

Backend test command — `./scripts/backend-test.sh`.

Script створює `backend/.venv`, встановлює dev dependencies, запускає pytest і Ruff.

У проєкті є 52 backend tests.

Backend tests покривають registration, login, protected API, refresh rotation, legacy token compatibility, password reset, production configuration guards, distributed rate limit, multi-instance presence, profile, search, avatar replacement і validation, private conversation, batched latest-message/unread queries, messages, read receipts, soft delete, pagination, upload cleanup/validation, push token lifecycle, background FCM scheduling, FCM errors, readiness endpoint, WebSocket authentication/broadcast/persistence/delete, stale connection cleanup, seed-script safety та encryption/key rotation.

Backend tests використовують async SQLite і test doubles для Redis/FCM там, де external integration не потрібна.

Frontend test command — `cd mobile` та `npm test`.

У проєкті є 10 frontend tests у чотирьох files.

Frontend tests перевіряють translation key parity, durable enqueue до network attempt, idempotency key reuse, rejected-message retry, restart restoration, IndexedDB attachment bytes, confirmed-history cache filtering і базові security invariants HTML/Capacitor configuration.

Frontend type-check і production build виконуються через `npm run build`.

Dependency та static security checks запускаються через `./scripts/security-audit.sh`. Script виконує `pip-audit`, Bandit і `npm audit`.

Smoke test запускається через `./scripts/smoke-messages.sh http://localhost:8000`.

Smoke script створює test data, входить demo users, створює conversations, автентифікує WebSocket, надсилає повідомлення і перевіряє attachment flow. Його потрібно запускати тільки у development/test environment.

## 29. Security і privacy status

Реалізовано Argon2 password hashing, hashed persistent tokens, indexed token lookup із row locking, JWT expiry/type validation, refresh rotation, access checks, participant-only attachment access, bounded upload, MIME/extension/image signature validation, generated filenames, cleanup partial uploads, AES-GCM encryption at rest, Android Secure Storage, restrictive web CSP, CORS allowlist, Redis-backed auth rate limiting, generic WebSocket errors, Firebase secret exclusion, non-root backend container і localhost-only PostgreSQL/Redis exposure.

Privacy у поточній версії означає контроль доступу між користувачами та захист даних у storage. Вона не означає конфіденційність від сервера.

E2EE відсутнє. Backend може розшифрувати повідомлення та вкладення.

Web tokens зберігаються у localStorage і залежать від захисту від XSS.

Document files не проходять antivirus/malware scanning.

Public deployment без HTTPS/WSS є небезпечним.

Service account JSON, JWT secrets, PostgreSQL password і encryption keys не повинні потрапляти у Git.

Перед production deployment потрібні secret manager, HTTPS, firewall, backups, encryption key backup/rotation, object storage, malware scanning, monitoring, centralized logs, dependency scanning і threat modeling.

## 30. Основні технічні обмеження

Система орієнтована на малу кількість користувачів.

FCM requests виконуються як in-process background tasks без durable queue або окремого worker.

Redis Pub/Sub не гарантує delivery після disconnect.

Uploads volume потрібно резервувати разом із PostgreSQL та encryption keys.

Локальне file storage не підходить для незалежного горизонтального масштабування без shared filesystem.

Немає автоматизованого reverse proxy, TLS certificate management, CI/CD, metrics або alerting.

Немає Android UI tests.

Password reset не завершений на рівні email і frontend UX.

Повноцінне E2EE потребуватиме окремої device-key architecture, identity verification, prekeys, session protocol, multi-device support та recovery strategy. Його не можна коректно додати лише одним AES key у client.

## 31. Рекомендований напрям подальшої роботи

Найближчими практичними покращеннями є SMTP/email password recovery, external HTTPS reverse proxy, object storage, backup automation, CI checks, monitoring і Android UI tests.

Після цього можна розглядати push delivery через background queue, group chats, editing/reactions і повноцінне E2EE на базі перевіреного протоколу, а не власної криптографічної схеми.
