# FileLocker

Encrypted vault manager for Linux. Create password-protected vaults whose
contents and filenames are encrypted at rest using
[gocryptfs](https://nuetzlich.net/gocryptfs/). Each vault mounts as a normal
folder via FUSE when unlocked.

![GTK4 / libadwaita UI](.github/screenshot.png)

---

## Features

- Create and manage multiple vaults, each with its own password
- AES-GCM per-file encryption and encrypted filenames via gocryptfs
- Modern GTK4 / libadwaita UI — works on Wayland and X11
- Auto-lock on idle timeout or screen lock (D-Bus)
- Recovery key (24-word mnemonic) shown once at creation
- Stealth mode — hide a vault from the list with a dot-prefix
- No network access, no telemetry, no vendor lock-in
- Open vault format (gocryptfs) — accessible from the command line too

---

## Requirements

| Package | Purpose |
|---|---|
| `gocryptfs` ≥ 2.3 | Encryption engine |
| `fuse3` / `fusermount3` | FUSE mounting |
| `python3` ≥ 3.11 | Runtime |
| `python3-gi` | GTK4 / GObject Python bindings |
| `gir1.2-gtk-4.0` | GTK4 typelib |
| `gir1.2-adw-1` | libadwaita typelib |
| `python3-dbus` | Auto-lock via D-Bus (optional) |

Install all on Ubuntu / Debian:

```bash
sudo apt install gocryptfs fuse3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-dbus
```

---

## Installation

### From tarball (recommended)

```bash
# Download and verify
wget https://github.com/filelocker/filelocker/releases/download/v1.0.0/filelocker-1.0.0.tar.gz
wget https://github.com/filelocker/filelocker/releases/download/v1.0.0/SHA256SUMS
sha256sum -c SHA256SUMS

# Extract and install (no root needed — installs to ~/.local)
tar -xzf filelocker-1.0.0.tar.gz
cd filelocker-1.0.0
bash packaging/install.sh

# Or system-wide (requires root)
sudo bash packaging/install.sh --system
```

### From source

```bash
git clone https://github.com/filelocker/filelocker.git
cd filelocker
bash packaging/check_deps.sh   # verify dependencies
python3 bin/filelocker          # run directly from source
```

---

## Uninstall

```bash
bash packaging/uninstall.sh
```

---

## Quick start

1. Launch FileLocker from your application menu or run `filelocker`.
2. Click **+** (New Vault) to create a vault.
3. Choose a name, location, and password.
4. **Write down your 24-word recovery key** — you will not see it again.
5. Click a vault in the list to unlock it. A file manager window opens.
6. When done, click the lock icon to lock the vault.

---

## Configuration

Settings are stored in `~/.config/filelocker/settings.json` (mode 600).
Vault metadata (names and paths, never passwords) is stored in
`~/.config/filelocker/vaults.json` (mode 600).

---

## Auto-lock

FileLocker can lock all vaults automatically:

- **Idle timeout** — configurable (1, 5, 15, 30 minutes, or never) in Preferences.
- **Screen lock** — locks when the GNOME screen saver activates or when
  `org.freedesktop.login1.Session.Lock` fires (works with KDE, etc.).
- **App quit** — all vaults are locked when FileLocker exits.

---

## Recovery

If you forget your password, use your recovery key:

```bash
# Show the gocryptfs master key from your recovery mnemonic:
# (each word maps to 11 bits of your 256-bit master key)
# Then unlock via CLI:
gocryptfs -masterkey XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX \
          /path/to/vault /path/to/mountpoint
```

The exact master key hex string is derived from your 24-word mnemonic.
See `docs/THREAT_MODEL.md` for details.

---

## Security notes

- Encryption is real; **hiding is cosmetic**. The UI labels these separately.
- A vault that is unlocked (mounted) is accessible to any process running as you.
- Enable encrypted swap and full-disk encryption for complete protection.
- See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for a full threat model.

---

## Project layout

```
filelocker/
  bin/filelocker              Launcher script
  src/filelocker/
    core/                     Vault manager, registry, recovery, auto-lock, utils
    backend/                  gocryptfs adapter (BackendAdapter ABC)
    gui/                      GTK4/libadwaita UI
  data/                       .desktop, icon, metainfo
  packaging/                  install.sh, uninstall.sh, build-tarball.sh
  docs/                       THREAT_MODEL.md
  tests/                      Unit and integration tests
```

---

## Contributing

Bug reports and patches welcome via the issue tracker.
Please read `docs/THREAT_MODEL.md` before proposing cryptography changes.

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).

gocryptfs is © Jakob Unterwurzacher and is licensed under the MIT license.
