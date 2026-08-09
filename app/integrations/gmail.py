from __future__ import annotations

import asyncio
import base64
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from app.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


class GmailConfigurationError(RuntimeError):
    pass


class GmailClient:
    """Local OAuth Gmail integration using user-supplied credentials."""

    def credentials_exist(self) -> bool:
        return Path(settings.gmail_credentials_path).exists()

    def connected(self) -> bool:
        try:
            creds = self._credentials(interactive=False)
            return bool(creds and creds.valid)
        except Exception:
            return False

    async def connect(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._connect_sync)

    def _connect_sync(self) -> dict[str, Any]:
        creds = self._credentials(interactive=True)
        return {"connected": bool(creds and creds.valid)}

    def _credentials(self, interactive: bool):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        token_path = Path(settings.gmail_token_path)
        creds = None
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        if (not creds or not creds.valid) and interactive:
            cred_path = Path(settings.gmail_credentials_path)
            if not cred_path.exists():
                raise GmailConfigurationError(
                    f"Download a Google OAuth Desktop client file and save it locally as {settings.gmail_credentials_path}."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), SCOPES)
            creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def _service(self):
        from googleapiclient.discovery import build
        creds = self._credentials(interactive=False)
        if not creds or not creds.valid:
            raise GmailConfigurationError("Gmail is not connected. Use Connect Gmail first.")
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    async def recent(self, max_results: int = 5, query: str | None = None) -> list[dict[str, str]]:
        return await asyncio.to_thread(self._recent_sync, max_results, query)

    def _recent_sync(self, max_results: int, query: str | None) -> list[dict[str, str]]:
        service = self._service()
        params: dict[str, Any] = {"userId": "me", "maxResults": max_results}
        if query:
            params["q"] = query
        result = service.users().messages().list(**params).execute()
        rows = []
        for item in result.get("messages", []):
            msg = service.users().messages().get(
                userId="me",
                id=item["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            rows.append({
                "id": item["id"],
                "from": headers.get("from", ""),
                "subject": headers.get("subject", "(no subject)"),
                "date": headers.get("date", ""),
                "snippet": msg.get("snippet", ""),
            })
        return rows

    async def send(self, to: str, subject: str, body: str) -> dict[str, str]:
        return await asyncio.to_thread(self._send_sync, to, subject, body)

    def _send_sync(self, to: str, subject: str, body: str) -> dict[str, str]:
        service = self._service()
        message = EmailMessage()
        message.set_content(body)
        message["To"] = to
        message["Subject"] = subject
        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = service.users().messages().send(userId="me", body={"raw": encoded}).execute()
        return {"id": sent.get("id", ""), "threadId": sent.get("threadId", "")}
