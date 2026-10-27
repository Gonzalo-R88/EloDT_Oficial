"""Resolver del challenge de AWS WAF de Transfermarkt con un navegador real.

Cuando CloudFront/AWS WAF marca la IP como sospechosa ya no devuelve 403 sino
una página de *challenge* JavaScript (HTTP 202 con `awswaf.com/challenge.js`).
`curl_cffi` no ejecuta JavaScript, así que nunca obtiene la cookie
`aws-waf-token` y todas las peticiones quedan bloqueadas.

Este módulo lanza un Chromium headless (Playwright) contra la home del sitio,
espera a que el reto se resuelva y devuelve las cookies de sesión para
inyectarlas en la sesión HTTP (`curl_cffi`). Playwright se importa de forma
perezosa para que el resto del proyecto y los tests funcionen sin él.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Nombre de la cookie que emite el reto. Sin ella, el resto da igual.
_WAF_COOKIE = "aws-waf-token"


class WafChallengeSolver:
    """Resuelve el challenge de AWS WAF con Playwright/Chromium headless."""

    def __init__(
        self,
        domain: str = "www.transfermarkt.com",
        *,
        headless: bool = True,
        user_agent: Optional[str] = None,
        locale: str = "es-AR",
        timeout_ms: int = 60_000,
        wait_seconds: float = 15.0,
    ) -> None:
        self.domain = domain
        self.headless = headless
        self.user_agent = user_agent or _DEFAULT_USER_AGENT
        self.locale = locale
        self.timeout_ms = timeout_ms
        self.wait_seconds = wait_seconds

    def solve(self) -> dict[str, str]:
        """Devuelve las cookies de sesión tras resolver el challenge.

        Lanza Chromium, navega a la home y espera a que aparezca
        `aws-waf-token`. Si no lo consigue, registra un warning y devuelve lo
        que haya (el llamador reintentará o fallará más adelante).
        """
        from playwright.sync_api import sync_playwright  # import perezoso

        url = f"https://{self.domain}/"
        deadline = time.monotonic() + self.wait_seconds
        cookies: list[dict] = []

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.headless)
            try:
                context = browser.new_context(
                    user_agent=self.user_agent, locale=self.locale
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                while time.monotonic() < deadline:
                    cookies = context.cookies()
                    if any(c.get("name") == _WAF_COOKIE and c.get("value") for c in cookies):
                        break
                    page.wait_for_timeout(1000)
                cookies = context.cookies()
            finally:
                browser.close()

        result = {
            c["name"]: c["value"]
            for c in cookies
            if c.get("name") and c.get("value")
        }
        if result.get(_WAF_COOKIE):
            logger.info(
                "Challenge AWS WAF resuelto (%s); %d cookies obtenidas.",
                self.domain, len(result),
            )
        else:
            logger.warning(
                "No se obtuvo %s tras %.0fs en %s; se continúa igual.",
                _WAF_COOKIE, self.wait_seconds, self.domain,
            )
        return result
