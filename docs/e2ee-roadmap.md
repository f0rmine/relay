# Relay E2EE Roadmap (Foundation)

Status: foundation only. Server-side encrypt-at-rest remains the shipped model;
this document describes the path to true end-to-end encryption and the
groundwork already merged.

## Current model (shipped)

- The server holds AES-256-GCM keys (`ENCRYPTION_KEYS` keyring) and encrypts
  message text + attachment bytes before writing to disk (AAD binds ciphertext
  to object ids).
- Implication: the server can read content. This enables server-side search,
  thumbnail generation, push preview labels, and bounded-decrypt search.

## Threat model target

Protect against: server operator compromise, database theft, passive network
observers. Not protected against: compromised client devices.

## Why full E2EE is deferred

Enabling client-side E2EE today would permanently break, without replacement:

1. Global message search (server can no longer decrypt).
2. Server-side thumbnails.
3. Push previews beyond fixed labels (already label-only).
4. Bounded-scan moderation tooling.

A migration must ship replacements (client-side local index search, pre-uploaded
thumbnails generated on-device before encryption) in the same release window.

## Protocol sketch (target)

- Identity: Ed25519 signing key + X25519 agreement key per device,
  registered via `PUT /devices/keys` (groundwork shipped; table `user_devices`).
- Discovery: `GET /devices/keys/{user_id}` returns member device keys so
  senders can seal to every device of every participant.
- Sessions: double-ratchet (or initial static-ECDH + AES-GCM v1) per
  (sender device, recipient device) pair; group chats fan out per member pair
  (sender-keys style) — no sender anonymity in v1.
- Verification: safety numbers = SHA-256 of sorted identity public keys,
  rendered as 60-digit groups; QR compare in GroupInfo later.
- Multi-device: each device has its own ratchet; adding a device requires
  re-keying from an authorized device (no server-side key escrow).

## Groundwork shipped in this release

- `user_devices` table `(user_id, public_key, device_label)` unique per pair.
- `PUT /devices/keys`, `GET /devices/keys/{user_id}` endpoints (unauthenticated
  crypto is NOT active; payloads stored verbatim).

## Migration plan (when activated)

1. Ship client key generation + registration behind a flag.
2. Dual-write period: messages carry both encrypted-at-rest body and E2EE
   envelope; old clients keep working.
3. Flip search/thumbnails to client-generated variants.
4. Remove server-side plaintext path for new messages; keep decrypt for legacy
   rows until retention window passes.
