import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from media_urls import load_services, transformed_urls


LOGGER = logging.getLogger("media_embedder_bot")
API_ROOT = "https://api.telegram.org"
POLL_TIMEOUT = 30


class TelegramAPIError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str) -> None:
        self.base_url = f"{API_ROOT}/bot{token}"

    def call(self, method: str, **parameters: Any) -> Any:
        body = json.dumps(parameters).encode("utf-8")
        request = Request(
            f"{self.base_url}/{method}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=POLL_TIMEOUT + 10) as response:
                payload = json.load(response)
        except HTTPError as error:
            try:
                details = json.load(error)
                description = details.get("description", str(error))
            except (json.JSONDecodeError, AttributeError):
                description = str(error)
            raise TelegramAPIError(description) from error
        except (URLError, socket.timeout, TimeoutError) as error:
            raise TelegramAPIError(str(error)) from error

        if not payload.get("ok"):
            raise TelegramAPIError(payload.get("description", "Unknown Telegram API error"))
        return payload["result"]

    def updates(self, offset: int | None) -> list[dict[str, Any]]:
        parameters: dict[str, Any] = {
            "timeout": POLL_TIMEOUT,
            "allowed_updates": ["message", "channel_post"],
        }
        if offset is not None:
            parameters["offset"] = offset
        return self.call("getUpdates", **parameters)

    def reply(self, message: dict[str, Any], text: str) -> None:
        parameters: dict[str, Any] = {
            "chat_id": message["chat"]["id"],
            "text": text,
            "link_preview_options": {"is_disabled": False},
            "reply_parameters": {
                "message_id": message["message_id"],
                "allow_sending_without_reply": True,
            },
        }
        if thread_id := message.get("message_thread_id"):
            parameters["message_thread_id"] = thread_id
        self.call("sendMessage", **parameters)


def handle_update(
    client: TelegramClient, update: dict[str, Any], services: list[Any]
) -> None:
    message = update.get("message") or update.get("channel_post")
    if not message or message.get("from", {}).get("is_bot"):
        return

    text = message.get("text") or message.get("caption")
    if not text:
        return

    for url in transformed_urls(text, services):
        try:
            client.reply(message, url)
        except TelegramAPIError:
            LOGGER.exception("Could not reply with transformed URL in chat %s", message["chat"]["id"])


def run(client: TelegramClient, services: list[Any]) -> None:
    offset = None
    LOGGER.info("Listening for Telegram messages")
    while True:
        try:
            updates = client.updates(offset)
            for update in updates:
                if not isinstance(update, dict):
                    LOGGER.error("Ignoring malformed Telegram update")
                    continue
                update_id = update.get("update_id")
                if not isinstance(update_id, int):
                    LOGGER.error("Ignoring Telegram update without a valid update_id")
                    continue
                try:
                    handle_update(client, update, services)
                except Exception:
                    LOGGER.exception("Could not process Telegram update %s", update_id)
                finally:
                    # Skip a bad update instead of crashing on it after every restart.
                    offset = update_id + 1
        except TelegramAPIError:
            LOGGER.exception("Telegram polling failed; retrying in 5 seconds")
            time.sleep(5)


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        LOGGER.error("TELEGRAM_BOT_TOKEN is required")
        return 1

    services_path = Path(__file__).with_name("media_services.json")
    try:
        services = load_services(services_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        LOGGER.exception("Could not load %s", services_path)
        return 1

    try:
        run(TelegramClient(token), services)
    except KeyboardInterrupt:
        LOGGER.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
