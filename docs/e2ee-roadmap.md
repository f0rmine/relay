# Relay end-to-end encryption plan

Status: **Phase 2 in progress.** Phase 1 (key directory) and Phase 2a/2b (protocol
core, encrypted 1:1 text chats as an opt-in preview) have shipped. Regular chats
are still protected by server-side encryption at rest only. Relay must not be
described as end-to-end encrypted until Phase 2 is complete *and* an independent
security review of the protocol code has been done.

## 1. Goal and threat model

End-to-end encryption means the server stores and relays only ciphertext it cannot
decrypt, and it cannot silently insert itself into a conversation.

Protected against:

- A compromised or malicious server operator, including one who modifies server code.
- Theft of the database, uploads volume or backups.
- Passive and active network attackers (TLS is still required as an outer layer).
- "Harvest now, decrypt later" by a future quantum adversary (hybrid key agreement).

Explicitly **not** protected against:

- A compromised, unlocked device (malware, someone holding your phone).
- Metadata the server needs to route messages: who talks to whom, when, message
  sizes, group membership, IP addresses. Minimised where cheap, not hidden.
- A user who never verifies safety numbers *and* is targeted by an operator who
  swaps keys. Key-change warnings make this detectable, not impossible.

## 2. Current model (shipped)

The server holds an AES-256-GCM keyring (`ENCRYPTION_KEYS`) and encrypts message
text and attachment bytes at rest, with AAD bound to object ids. The server can
read all content, which is what makes server-side search, thumbnails, link
previews and chat export possible today. This layer stays as defence in depth
after E2EE ships; it just stops being the only protection.

## 3. Protocol choice

**Signal-style: PQXDH session setup + Double Ratchet for device-to-device
sessions, Sender Keys for groups.** Primitives come from the audited `@noble`
libraries (Ed25519, X25519, SHA-2, HKDF, AES-GCM), plus ML-KEM-768 from
`@noble/post-quantum`.

Why this over the alternatives:

| Option | Verdict |
|---|---|
| `@signalapp/libsignal-client` | Best implementation, but ships native Node bindings only; it cannot run in the Capacitor WebView. |
| MLS (RFC 9420) via `ts-mls` | Strong standard, native multi-device and large groups. But commits need a strictly ordered delivery service, external joins for invite links add complexity, and the TS implementation is young. Revisit for groups > ~100 members. |
| Matrix Olm/Megolm (`matrix-sdk-crypto-wasm`) | Audited, but tied to Matrix event and room semantics; adapting it means carrying a large protocol surface we don't use. |
| Static ECDH + AES-GCM (old plan's "v1") | Rejected: no forward secrecy or post-compromise security. One leaked key would expose every past and future message. |

The specs we implement are public and well analysed (X3DH/PQXDH, Double Ratchet,
Sender Keys). Our code implementing them is **not** audited, hence the review gate.

**Hybrid post-quantum from day one.** PQXDH mixes an ML-KEM-768 shared secret into
the X25519 handshake. If the ML-KEM implementation (not yet audited) were broken,
security falls back to classical X25519; it cannot get weaker than that.

## 4. Keys and the device directory

| Key | Type | Lives on | Purpose |
|---|---|---|---|
| Account identity key (AIK) | Ed25519 | every linked device | Signs the account's device list. This is what safety numbers verify. |
| Device signing key | Ed25519 | one device | Signs that device's prekeys. |
| Device agreement key | X25519 | one device | Long-term DH key in PQXDH. |
| Signed prekey | X25519 | one device | Rotated ~weekly, signed by the device key. |
| Last-resort PQ prekey | ML-KEM-768 | one device | Signed; used when one-time KEM prekeys run out. |
| One-time prekeys | X25519 and ML-KEM-768 | one device | Consumed once per new session, topped up automatically. |

**The server cannot add devices.** The old plan let the server return any key list,
so a malicious operator could quietly add their own "device" to every account
and read everything. Now every device record carries a signature by the account
identity key over its keys; clients verify it and refuse unsigned or mis-signed
devices. The server verifies the same signatures on upload so garbage never
enters the directory, but clients never trust that check.

**Adding a device** requires an already-linked device: the new device shows a QR
code, the old one scans it, then sends the identity key over an encrypted
channel and signs the new device. No server-side key escrow.

**Losing all devices** means generating a new identity key. Contacts see a
"safety number changed" warning, exactly as they should.

## 5. Verification

- **Safety numbers:** Signal's fingerprint construction (5200 iterations of
  SHA-512 over version, identity key and user id; 30 digits per party, 60 total,
  sorted so both sides see the same number). Compared in person or via QR.
- **Trust on first use with loud key-change warnings:** the first identity key
  seen for a contact is pinned locally. A different key later shows a warning in
  the chat and clears the "verified" mark until the user re-verifies.

## 6. What changes for existing features

Turning on E2EE removes the server's ability to read content, so each
server-side feature needs a client-side replacement in the same release window:

| Feature | Today | Under E2EE |
|---|---|---|
| Message search | server decrypts and scans | on-device index over the local message store |
| Thumbnails | server generates from plaintext | sender generates before encrypting; sent inside the envelope |
| Link previews | server fetches the URL (and learns it) | off in E2EE chats (see decisions) |
| Reply quotes | server embeds the quoted text | client resolves from its local store |
| Chat export | server builds a zip | client builds it from local data |
| Attachments | server encrypts uploads | client encrypts with a random per-file key; key and digest travel in the message envelope |
| Push previews | fixed labels | unchanged (already label-only) |
| Reactions, edits, deletes | plaintext operations | encrypted control messages inside the session |
| Scheduled and disappearing messages | server-timed | unchanged: the server times opaque ciphertext |

## 7. Rollout (no plaintext dual-write)

The old plan dual-wrote a plaintext-readable copy next to the E2EE envelope
during migration, which would have left the server able to read every "E2EE"
message for the whole transition. Instead:

- E2EE is a **per-conversation** property, fixed once set.
- New conversations become E2EE when every participant has a registered device.
- Existing conversations keep their history under server-side encryption and show
  a banner offering to continue in a new E2EE conversation.
- Clients that predate E2EE cannot read E2EE conversations; a minimum app version
  is enforced for them rather than weakening the format.

## 8. Phases

1. **Identity and key directory** *(done, v1.9.0)*: key generation on device, private
   keys in the platform keystore, signed device records, signed and one-time
   prekeys with atomic claim, safety numbers screen, key-change detection.
2. **1:1 E2EE:**
   - 2a *(done, v1.9.1)*: PQXDH + Double Ratchet core, envelope format, padding.
   - 2b *(done, v1.10.0)*: opt-in encrypted 1:1 chats (text). One envelope per
     recipient device; the server rejects sends that don't cover exactly the
     active devices; each device fetches only its own envelope; decrypted text
     lives only in an on-device store (ratchet keys are single-use).
   - 2c: client-encrypted attachments and voice notes.
   - 2d: device linking via QR, encrypted edits.
   - Known metadata in 2b: reply targets and reactions are visible to the server.
3. **Groups:** Sender Keys with rotation on every membership change; invite-link
   joins receive keys from existing members.
4. **Feature replacements:** on-device search, client thumbnails, client export,
   sender-side link previews.
5. **Recovery and launch:** optional encrypted backup keyed by a recovery
   passphrase (Argon2id, client-side), independent security review, then E2EE on
   by default.

## 9. Decisions

- **Encrypted backup is opt-in.** Default is privacy: nothing leaves the device
  unless the user turns backup on and sets a recovery passphrase.
- **Link previews are off in E2EE conversations.** Sender-side fetching would leak
  the sender's IP address to the linked site; server-side fetching would leak the URL.
- Open: group size ceiling for Sender Keys before considering MLS.
