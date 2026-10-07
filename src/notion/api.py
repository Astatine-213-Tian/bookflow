"""Caller-owned authenticated REST transport; no automatic write retries."""

import base64
import os
import httpx


def api_token() -> str:
    token = os.environ.get("NOTION_API_TOKEN", "").strip()
    if not token:
        raise ValueError(
            "Notion manuscript access requires NOTION_API_TOKEN in the process environment; .env is not read"
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
