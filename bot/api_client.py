from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from bot.config import get_settings


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class DjangoApiClient:
    """HTTP client for the Django REST API. No download logic here."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.api_base_url.rstrip("/")
        self.token = settings.internal_api_token
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=15.0),
            headers={"Authorization": f"Bearer {self.token}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        r = await self._client.get(f"{self.base_url}/health/")
        r.raise_for_status()
        return r.json()

    async def create_job(
        self,
        *,
        url: str,
        telegram_user_id: int,
        chat_id: int,
        preferred_format: str = "best",
        username: str = "",
        first_name: str = "",
        last_name: str = "",
        language_code: str = "",
    ) -> dict[str, Any]:
        payload = {
            "url": url,
            "telegram_user_id": telegram_user_id,
            "chat_id": chat_id,
            "preferred_format": preferred_format,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "language_code": language_code,
        }
        r = await self._client.post(f"{self.base_url}/jobs/", json=payload)
        if r.status_code >= 400:
            detail = _extract_detail(r)
            raise ApiError(detail, r.status_code)
        return r.json()

    async def get_job(self, job_id: int) -> dict[str, Any]:
        last_error: ApiError | None = None
        for attempt in range(4):
            try:
                r = await self._client.get(f"{self.base_url}/jobs/{job_id}/")
            except httpx.HTTPError as exc:
                last_error = ApiError(f"ارتباط با API قطع شد: {exc}")
                await asyncio.sleep(0.7 * (attempt + 1))
                continue
            if r.status_code == 404:
                raise ApiError("جاب پیدا نشد.", 404)
            if r.status_code >= 500:
                last_error = ApiError(_extract_detail(r), r.status_code)
                await asyncio.sleep(0.7 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise ApiError(_extract_detail(r), r.status_code)
            return r.json()
        raise last_error or ApiError("خطا در دریافت وضعیت جاب.")

    async def ack_job(self, job_id: int) -> dict[str, Any]:
        r = await self._client.post(f"{self.base_url}/jobs/{job_id}/ack/")
        if r.status_code >= 400:
            raise ApiError(_extract_detail(r), r.status_code)
        return r.json()

    async def cancel_job(self, job_id: int) -> dict[str, Any]:
        r = await self._client.post(f"{self.base_url}/jobs/{job_id}/cancel/")
        if r.status_code >= 400:
            raise ApiError(_extract_detail(r), r.status_code)
        return r.json()

    async def probe(self, url: str, telegram_user_id: int = 0) -> dict[str, Any]:
        r = await self._client.post(
            f"{self.base_url}/probes/",
            json={"url": url, "telegram_user_id": telegram_user_id},
        )
        if r.status_code >= 400:
            raise ApiError(_extract_detail(r), r.status_code)
        return r.json()


def _extract_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            if "detail" in data:
                return str(data["detail"])
            # DRF field errors
            parts = []
            for key, val in data.items():
                parts.append(f"{key}: {val}")
            if parts:
                return "; ".join(parts)
    except Exception:  # noqa: BLE001
        pass
    text = (response.text or "").strip()
    if "<html" in text.lower() or "<!doctype" in text.lower():
        return f"خطای داخلی سرور (HTTP {response.status_code})"
    cleaned = re.sub(r"<[^>]+>", "", text).strip()
    return (cleaned[:240] if cleaned else "") or f"HTTP {response.status_code}"
