# yubikey-gpg-notifier

This tool creates notifications when it detects gpg operations are waiting for a YubiKey touch.

It acts as a proxy between gpg and scdaemon and watches for certain commands being passed to the YubiKey.

When it detects one of these commands and the YubiKey has not responded for a configured period of time, a notification is shown to remind the user to touch the key.

## Installation

Download the yubikey-gpg-notifier file somewhere suitable and ensure it is executable.

> [!IMPORTANT]
> Python 3.11 is currently required due to the tomllib requirement. If not available on your PATH, amend the shebang to point to a Python 3.11+ interpreter.

Create a config file at `~/.config/yubikey-gpg-notifier.toml` - the tool will refuse to start without this.
Example using [terminal-notifier](https://github.com/julienXX/terminal-notifier):
```toml
scdaemon = "/path/to/gnupg/libexec/scdaemon"
notify_command = "terminal-notifier -group yubikey-gpg-notifier -title YubiKey -message 'Touch to release %operation operation'"
cancel_command = "terminal-notifier -remove yubikey-gpg-notifier"
wait_time = 0.1
```

Amend (or create) your `~/.gnupg/gpg-agent.conf` with the line `scdaemon-program /path/to/yubikey-gpg-notifier`

It may be necessary on first run and on config changes to restart the gpg-agent process:
```shell
gpgconf --kill gpg-agent
gpgconf --launch gpg-agent
```

## Configuration examples

Using terminal-notifier:
```toml
scdaemon = "/path/to/gnupg/libexec/scdaemon"
notify_command = "terminal-notifier -group yubikey-gpg-notifier -title YubiKey -message 'Touch to release %operation operation'"
cancel_command = "terminal-notifier -remove yubikey-gpg-notifier"
wait_time = 0.1
```

Using terminal-notifier, masquerading as Yubico Authenticator:
```toml
scdaemon = "/path/to/gnupg/libexec/scdaemon"
notify_command = "terminal-notifier -group yubikey-gpg-notifier -sender com.yubico.yubioath -title YubiKey -message 'Touch to release %operation operation'"
cancel_command = "terminal-notifier -remove yubikey-gpg-notifier -sender com.yubico.yubioath"
wait_time = 0.1
```

Using libnotify's notify-send:
```toml
scdaemon = "/path/to/gnupg/libexec/scdaemon"
notify_command = "notify-send --transient YubiKey 'Touch to release %operation operation'"
cancel_command = ""
wait_time = 0.1
```

## Links

Inspired by:
- https://github.com/klali/scdaemon-proxy
- https://github.com/maximbaz/yubikey-touch-detector
- https://github.com/palantir/gpg-tap-notifier-macos
