import unittest

from bot import handle_update, run
from tests.test_media_urls import SERVICES


class FakeClient:
    def __init__(self) -> None:
        self.replies = []

    def reply(self, message, text) -> None:
        self.replies.append((message, text))


class OneBadUpdateClient(FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.poll_count = 0

    def updates(self, offset):
        self.poll_count += 1
        if self.poll_count > 1:
            raise KeyboardInterrupt
        return [
            {
                "update_id": 1,
                "message": {
                    "message_id": 10,
                    "chat": {"id": -1001},
                    "from": {"is_bot": False},
                    "text": "https://instagram.com/p/bad",
                },
            },
            {
                "update_id": 2,
                "message": {
                    "message_id": 11,
                    "chat": {"id": -1001},
                    "from": {"is_bot": False},
                    "text": "https://instagram.com/p/good",
                },
            },
        ]

    def reply(self, message, text) -> None:
        if message["message_id"] == 10:
            raise ValueError("unexpected handler bug")
        super().reply(message, text)


class HandleUpdateTest(unittest.TestCase):
    def test_replies_once_for_each_url_in_text(self) -> None:
        client = FakeClient()
        message = {
            "message_id": 10,
            "chat": {"id": -1001},
            "from": {"is_bot": False},
            "text": "https://instagram.com/p/one https://vm.tiktok.com/two",
        }

        handle_update(client, {"message": message}, SERVICES)

        self.assertEqual(
            [reply[1] for reply in client.replies],
            ["https://kkinstagram.com/p/one", "https://d.tnktok.com/two"],
        )

    def test_reads_urls_from_media_caption(self) -> None:
        client = FakeClient()
        message = {
            "message_id": 11,
            "chat": {"id": -1001},
            "from": {"is_bot": False},
            "caption": "https://instagram.com/reel/one",
        }

        handle_update(client, {"message": message}, SERVICES)

        self.assertEqual(client.replies[0][1], "https://kkinstagram.com/reel/one")

    def test_ignores_messages_from_bots(self) -> None:
        client = FakeClient()
        message = {
            "message_id": 12,
            "chat": {"id": -1001},
            "from": {"is_bot": True},
            "text": "https://instagram.com/reel/one",
        }

        handle_update(client, {"message": message}, SERVICES)

        self.assertEqual(client.replies, [])

    def test_unexpected_error_does_not_block_later_updates(self) -> None:
        client = OneBadUpdateClient()

        with self.assertLogs("media_embedder_bot", level="ERROR"):
            with self.assertRaises(KeyboardInterrupt):
                run(client, SERVICES)

        self.assertEqual(
            [reply[1] for reply in client.replies],
            ["https://kkinstagram.com/p/good"],
        )


if __name__ == "__main__":
    unittest.main()
