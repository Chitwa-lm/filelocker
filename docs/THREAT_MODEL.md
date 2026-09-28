# FileLocker Threat Model

Version 1.0.0 — 2026-09-28

---

## What FileLocker protects against

| Threat | Protection |
|---|---|
| Stolen or powered-off laptop | AES-GCM encryption via gocryptfs; data is ciphertext at rest |
| Another user or root browsing your disk | Per-file encryption; filenames also encrypted |
| Cloud sync leaking plaintext | Per-file encryption makes synced files opaque |
| Casual snooping | Stealth mode hides vault directories with a dot-prefix |
| Weak passwords | Scrypt KDF (N=2^18) makes brute-force expensive; strength meter in UI |
| Password in process list | Passwords passed only via stdin, never in argv |
| Password in logs or crash reports | Backend sanitises gocryptfs stderr before forwarding |
| Stale FUSE mounts after a crash | Stale-mount scan and cleanup at every app start |
| Password-change key exposure | Uses gocryptfs -passwd; old key is re-wrapped, not re-encrypted |

---

## What FileLocker does NOT protect against

| Threat | Why |
|---|---|
| Malware running as you while a vault is unlocked | The attacker has the same filesystem access you do |
| Shoulder surfing / keyloggers | Password entry is visible to anyone watching the screen |
| Live memory dump while unlocked | The decryption key is in kernel FUSE memory while mounted |
| Forgotten password | By design — no backdoor. Recovery key is your only fallback |
| Physical coercion | Encryption cannot protect against "rubber-hose cryptanalysis" |
| Thumbnails and recent-files leakage | Your file manager may have cached previews outside the vault |
| Swap / hibernation leakage | Enable encrypted swap and full-disk encryption for full coverage |
| SSD "secure erase" of originals | SSDs remap sectors; rely on encryption from the start, not deletion |

---

## Hiding vs Encryption

FileLocker uses two distinct mechanisms and labels them clearly in the UI:

- **Encrypted** — cryptographic protection. Contents unreadable without the password, even to root. This is the real protection.
- **Hidden** — obscurity. The vault directory is dot-prefixed and omitted from the FileLocker list. It is still visible with `ls -la`. Hiding alone is not security.

Both can be enabled independently. For sensitive data, encryption is mandatory; hiding is optional convenience.

---

## Key derivation

gocryptfs uses scrypt with N=2^18, r=8, p=1 by default. On a modern desktop this takes approximately 0.5–1 second per unlock attempt, making offline brute-force attacks expensive. The derived key wraps a random 256-bit master key stored in `gocryptfs.conf`. Changing the password re-wraps the master key without re-encrypting vault contents.

---

## Recovery key

The recovery key is a 24-word mnemonic encoding 256 bits of entropy with an 8-bit checksum. It is generated at vault creation, shown once, and must be written down by the user. It maps to the gocryptfs master key. Anyone with the recovery key can reconstruct the vault config and unlock the vault without the password.

**Store your recovery key separately from your device.**

---

## Supply-chain considerations

- All runtime dependencies are system packages (`apt`), not pip packages, reducing exposure to PyPI supply-chain attacks.
- The tarball ships `SHA256SUMS` and an optional GPG signature for verification.
- gocryptfs itself is an audited open-source project. FileLocker does not modify or re-implement its cryptography.

---

## Reporting security issues

Please report security vulnerabilities privately via the project issue tracker with the "security" label, or by email if a private disclosure address is published.
