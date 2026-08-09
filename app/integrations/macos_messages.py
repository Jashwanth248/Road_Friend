from __future__ import annotations

import asyncio
import platform
import subprocess

from app.config import settings


class MacMessagesClient:
    """Optional macOS Messages sender with one-time confirmation handled upstream."""

    def available(self) -> bool:
        return platform.system() == "Darwin" and settings.allow_macos_messages

    async def send(self, recipient: str, body: str) -> dict[str, str]:
        if not self.available():
            return {
                "status": "disabled",
                "message": "macOS Messages sending is disabled. Set ALLOW_MACOS_MESSAGES=true locally to enable it.",
            }
        return await asyncio.to_thread(self._send_sync, recipient, body)

    def _send_sync(self, recipient: str, body: str) -> dict[str, str]:
        script = '''
on run argv
    set targetAddress to item 1 of argv
    set messageText to item 2 of argv
    tell application "Messages"
        set targetService to first service whose service type = iMessage
        set targetBuddy to buddy targetAddress of targetService
        send messageText to targetBuddy
    end tell
end run
'''
        subprocess.run(["osascript", "-e", script, recipient, body], check=True, capture_output=True, text=True)
        return {"status": "sent", "recipient": recipient}
