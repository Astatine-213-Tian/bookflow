"""Caller-owned authenticated REST transport; no automatic write retries."""

import base64
import os
from pathlib import Path

import httpx

from src.runtime.paths import repo_root

TOKEN = "NOTION_API_TOKEN"


def configured_token() -> str:
    """The token from the environment, else from the checkout's git-ignored .env.

    A variable present in the environment wins, even when empty.
    """
    if TOKEN in os.environ:
        return os.environ[TOKEN].strip()
    return dotenv_value(repo_root() / ".env", TOKEN)


def dotenv_value(path: Path, key: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return ""
    for line in lines:
        name, separator, value = line.strip().removeprefix("export ").partition("=")
        if separator and name.strip() == key:
            value = value.strip()
            if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value.strip()
    return ""


def api_token() -> str:
    token = configured_token()
    if not token:
        raise ValueError(
            "Notion manuscript access requires NOTION_API_TOKEN in the environment or the checkout's .env"
        )
    return token


async def api_request(
    client: httpx.AsyncClient, request: dict, *, headers: dict | None = None
) -> dict:
    kwargs = {"headers": headers} if headers else {}
    if "json" in request:
        kwargs["json"] = request["json"]
    if "file" in request:
        file = request["file"]
        kwargs["files"] = {
            "file": (
                file["filename"],
                base64.b64decode(file["data"]),
                file["content_type"],
            )
        }
    response = await client.request(
        request["method"], "https://api.notion.com/v1/" + request["path"], **kwargs
    )
    try:
        body = response.json()
    except ValueError:
        if response.is_success:
            raise
        body = {}
    return {
        "status": response.status_code,
        "body": body,
        "request_id": response.headers.get("x-request-id", ""),
        "retry_after": response.headers.get("retry-after", ""),
    }
