from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Optional

import requests

from src.config import Settings


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int | None
    content: str
    content_type: str
    error: str | None = None
    retry_count: int = 0
    rendered: bool = False


class Fetcher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
        self._last_request_at = 0.0

    async def polite_delay(self) -> None:
        delay = random.uniform(self.settings.request_delay_min_ms, self.settings.request_delay_max_ms) / 1000
        await asyncio.sleep(delay)

    async def fetch(self, url: str, render: bool = False) -> FetchResult:
        if render and self.settings.enable_playwright:
            rendered = await self.fetch_with_playwright(url)
            if rendered.status_code and rendered.content:
                return rendered
        await self.polite_delay()
        last_error = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self.session.get(url, timeout=self.settings.request_timeout, allow_redirects=True)
                text = response.text if "text" in response.headers.get("content-type", "") or "xml" in response.headers.get("content-type", "") or not response.headers.get("content-type") else ""
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.settings.max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                return FetchResult(
                    url=url,
                    final_url=response.url,
                    status_code=response.status_code,
                    content=text,
                    content_type=response.headers.get("content-type", ""),
                    retry_count=attempt,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                if attempt < self.settings.max_retries:
                    await asyncio.sleep(2**attempt)
        return FetchResult(url=url, final_url=url, status_code=None, content="", content_type="", error=last_error, retry_count=self.settings.max_retries)

    async def fetch_with_playwright(self, url: str) -> FetchResult:
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            return FetchResult(url=url, final_url=url, status_code=None, content="", content_type="", error=f"playwright_import_error: {exc}", rendered=True)
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(user_agent=self.settings.user_agent)
                response = await page.goto(url, wait_until="commit", timeout=self.settings.request_timeout * 1000)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=min(self.settings.request_timeout * 1000, 15000))
                except Exception:
                    pass
                await page.wait_for_timeout(2500)
                content = await page.content()
                final_url = page.url
                status = response.status if response else None
                await browser.close()
                return FetchResult(url=url, final_url=final_url, status_code=status, content=content, content_type="text/html; rendered", rendered=True)
        except Exception as exc:
            return FetchResult(url=url, final_url=url, status_code=None, content="", content_type="", error=f"playwright_error: {exc}", rendered=True)
