#!/usr/bin/env python3

import asyncio
import datetime
import json
import logging
import string
import sys

from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / Path(".config") / Path("yubikey-gpg-notifier.json")

logging.basicConfig(
    filename="/tmp/yubikey-gpg-notifier.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
logger.info(("-" * 27) + str(datetime.datetime.now()) + ("-" * 27))


class ConfigError(ValueError):
    pass


class Config:
    scdaemon: str
    notify_command: str
    cancel_command: str
    auth_wait_time: float
    sign_wait_time: float
    decrypt_wait_time: float
    log_level: str

    @classmethod
    def load(cls, path: Path) -> "Config":
        with open(path, "r") as file:
            config_dict = json.load(file)

        if not isinstance(config_dict, dict):
            raise ConfigError("Config should be a dictionary")

        config = cls()

        def get_expected_value(key, expected_type):
            value = config_dict.get(key)
            if value is None:
                raise ConfigError(f"Missing {key}")
            if not isinstance(value, expected_type):
                raise ConfigError(f"{key} should be type {expected_type}")
            return value

        config.scdaemon = get_expected_value("scdaemon", str)
        config.notify_command = get_expected_value("notify_command", str)
        config.cancel_command = get_expected_value("cancel_command", str)
        config.auth_wait_time = get_expected_value("auth_wait_time", (int, float))
        config.sign_wait_time = get_expected_value("sign_wait_time", (int, float))
        config.decrypt_wait_time = get_expected_value("decrypt_wait_time", (int, float))

        log_level = config_dict.get("log_level")
        if log_level is not None:
            if not isinstance(log_level, str):
                raise ConfigError(f"log_level should be type {str}")

            log_level = log_level.upper()

            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if log_level not in valid_levels:
                valid_level_list = "', '".join(valid_levels)
                raise ConfigError(f"log_level should be one of '{valid_level_list}'")

            config.log_level = log_level
        else:
            config.log_level = "INFO"

        return config


async def get_stdin_reader() -> asyncio.StreamReader:
    loop = asyncio.get_event_loop()

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    return reader


async def get_stdout_writer() -> asyncio.StreamWriter:
    loop = asyncio.get_event_loop()

    w_transport, w_protocol = await loop.connect_write_pipe(
        protocol_factory=asyncio.streams.FlowControlMixin, pipe=sys.stdout
    )

    writer = asyncio.StreamWriter(
        transport=w_transport, protocol=w_protocol, reader=None, loop=loop
    )

    return writer


async def tee_stream(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    queue: asyncio.Queue[tuple[str, bytes]],
    key: str,
) -> None:
    """Forward data from reader to writer while pushing it to a queue.

    Queue items are a tuple of (key, data) where key is the passed parameter.
    data is None when EOF was reached.
    """
    while data := await reader.readline():
        writer.write(data)
        await queue.put((key, data))
    await queue.put((key, None))


async def notify(logger: logging.Logger, config: Config, operation: dict[str, Any]) -> None:
    command = string.Template(config.notify_command).safe_substitute(operation)
    logger.debug("Sending notification with %s", command)
    await asyncio.create_subprocess_shell(
        command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def cancel_notification(logger: logging.Logger, config: Config) -> None:
    logger.debug("Cancelling notification with %s", config.cancel_command)
    await asyncio.create_subprocess_shell(
        config.cancel_command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def launch_scdaemon(config: Config) -> asyncio.subprocess.Process:
    passed_args = sys.argv[1:]

    scdaemon = await asyncio.create_subprocess_exec(
        config.scdaemon,
        *passed_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    return scdaemon


async def process_events(
    logger: logging.Logger, config: Config, queue: asyncio.Queue[tuple[str, bytes]]
) -> None:
    operations = {
        b"PKAUTH": {
            "description": "authentication",
            "wait_time": config.auth_wait_time,
        },
        b"PKSIGN": {
            "description": "signing",
            "wait_time": config.sign_wait_time,
        },
        b"PKDECRYPT": {
            "description": "encryption",
            "wait_time": config.decrypt_wait_time,
        },
    }

    current_operation = None
    waiting = False
    notified = False
    while True:
        key, data = await queue.get()

        if data is None:
            logger.debug("Empty input, exiting (%s)", key)
            break

        if key == "STDIN":
            logger.debug("STDIN:  %s", data)

            waiting = False

            for command, operation in operations.items():
                if data.startswith(command):
                    logger.debug("Detected %s command (%s)", operation["description"], command)
                    current_operation = operation

            if data.startswith(b"RESTART"):
                current_operation = None

        if key == "STDOUT":
            logger.debug("STDOUT: %s", data)

            if current_operation and data.startswith(b"S PINCACHE_PUT") and queue.empty():
                await asyncio.sleep(current_operation["wait_time"])

                if queue.empty():
                    waiting = True
                    await notify(logger, config, current_operation)
                    notified = True
            else:
                waiting = False

        if notified and not waiting:
            await cancel_notification(logger, config)
            notified = False


async def async_main():
    try:
        logger.info("Attempting to load config from %s", CONFIG_PATH)
        config = Config.load(path=CONFIG_PATH)
        logger.info("Config loaded successfully")
    except ConfigError as exc:
        logger.error("Config error: %s", exc)
        exit(1)
    except FileNotFoundError:
        logger.error("Config file not found")
        exit(1)
    except Exception as exc:
        logger.error("Error loading config file")
        logger.error(exc)
        exit(1)

    logger.setLevel(config.log_level)

    scdaemon = await launch_scdaemon(config)

    queue = asyncio.Queue()

    stdin_reader = await get_stdin_reader()
    asyncio.create_task(
        tee_stream(reader=stdin_reader, writer=scdaemon.stdin, queue=queue, key="STDIN")
    )

    stdout_writer = await get_stdout_writer()
    asyncio.create_task(
        tee_stream(
            reader=scdaemon.stdout, writer=stdout_writer, queue=queue, key="STDOUT"
        )
    )

    await process_events(logger, config, queue)

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
