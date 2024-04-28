# yubikey-gpg-notifier

This tool creates notifications when it detects gpg operations are waiting for a YubiKey touch.
This tool acts as a proxy between gpg and scdaemon and watches for certain commands being passed to the YubiKey.
When it detects one of these commands and the YubiKey has not responded for a configured period of time, a notification is shown to remind the user to touch the key.

## Requirements

scdaemon and terminal-notifier must be installed and available on the path.
