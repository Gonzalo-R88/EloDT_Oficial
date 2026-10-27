"""Cliente HTTP con reintentos, backoff y rate limiting para Transfermarkt.

Para esquivar el WAF de CloudFront (AWS WAF / Bot Control) el cliente:

* **Impersona la huella TLS/HTTP de Chrome** vía `curl_cffi`, de modo que la
  petición no se distinga de la de un navegador real (la huella TLS de
  `requests`/OpenSSL es un patrón clásico de bot).
* Envía headers de navegador (incluido `Referer`) y mantiene las cookies de
  sesión; conviene llamar a `warm_up()` una vez antes de scrapear para que la
  sesión arranque con cookies.
* Aplica un delay aleatorio (jitter) antes de cada request para no generar un
  ritmo constante y "robótico".
* Un HTTP 403 se interpreta como bloqueo temporal de la IP: espera
  `blocked_wait` segundos y reintenta hasta `blocked_retries` veces, en vez de
  abortar, para que un backfill desatendido se reanude solo.
* Si el WAF responde con un *challenge* JavaScript (HTTP 202 con
  `awswaf.com/challenge.js`), delega en `waf_solver` (Chromium headless) para
  resolverlo y reinyecta las cookies resultantes antes de reintentar.

Si `curl_cffi` no está instalado, cae a `requests` (con headers de navegador)
para no romper tests ni entornos mínimos.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional

try:  # pragma: no cover - depende del entorno
    from curl_cffi import requests as http_requests
    from curl_cffi.requests.exceptions import RequestException as _RequestException
    from curl_cffi.requests import RequestsError as _RequestsError

    _HAS_CURL_CFFI = True
except ImportError:  # pragma: no cover
    import requests as http_requests  # type: ignore

    _RequestException = http_requests.RequestException
    _RequestsError = http_requests.RequestException
    _HAS_CURL_CFFI = False

logger = logging.getLogger(__name__)

_NETWORK_ERRORS = (_RequestException, _RequestsError)

# Marcadores de la página de challenge de AWS WAF (no del HTML real).
_WAF_MARKERS = ("awswaf", "gokuprops", "challenge-container", "awswafcookiedomainlist")


def _is_waf_challenge(status_code: int, body: str) -> bool:
    """Detecta si la respuesta es el challenge JS de AWS WAF."""
    if status_code not in (200, 202, 403):
        return False
    head = body[:5000].lower()
    return any(marker in head for marker in _WAF_MARKERS)


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}


class TransfermarktClient:
    """Cliente sencillo y respetuoso para Transfermarkt."""

    def __init__(
        self,
        delay_min: float = 6.0,
        delay_max: float = 12.0,
        max_retries: int = 4,
        timeout: int = 30,
        blocked_wait: float = 1800.0,
        blocked_retries: int = 24,
        max_waf_solves: int = 5,
        impersonate: str = "chrome124",
        domain: str = "www.transfermarkt.com",
        session: Optional[object] = None,
        waf_solver: Optional[object] = None,
    ) -> None:
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.max_retries = max_retries
        self.timeout = timeout
        self.blocked_wait = blocked_wait
        self.blocked_retries = blocked_retries
        self.max_waf_solves = max_waf_solves
        self.impersonate = impersonate
        self.domain = domain
        self.waf_solver = waf_solver
        if session is not None:
            self.session = session
        elif _HAS_CURL_CFFI:
            self.session = http_requests.Session(impersonate=impersonate)
        else:
            self.session = http_requests.Session()
            self.session.headers.update(_BROWSER_HEADERS)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _sleep(self) -> None:
        time.sleep(random.uniform(self.delay_min, self.delay_max))

    def _apply_cookies(self, cookies: dict[str, str]) -> None:
        """Inyecta las cookies del navegador en la sesión HTTP."""
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain=self.domain)

    def _solve_waf(self, url: str) -> bool:
        """Pide al solver que resuelva el challenge y aplica las cookies.

        Devuelve `True` si se obtuvieron cookies nuevas. Si no hay solver
        configurado, devuelve `False` (el llamador decidirá si abortar).
        """
        if self.waf_solver is None:
            return False
        logger.warning(
            "Challenge AWS WAF detectado en %s; resolviendo con navegador headless.",
            url,
        )
        cookies = self.waf_solver.solve()
        if not cookies:
            return False
        self._apply_cookies(cookies)
        logger.info("Cookies del challenge inyectadas; se reintenta la request.")
        return True

    def warm_up(self, url: Optional[str] = None) -> None:
        """Visita una página del sitio para obtener cookies de sesión.

        Un scraper "frío" que sólo pide URLs profundas es un patrón sospechoso;
        entrar primero por la home reduce ese riesgo. Es best-effort: un solo
        intento, sin el ciclo largo de reintentos, para que un bloqueo no deje
        al worker colgado antes de empezar. Si la home devuelve el challenge de
        AWS WAF, se resuelve con el navegador antes de seguir.
        """
        target = url or f"https://{self.domain}/"
        try:
            response = self.session.get(target, timeout=self.timeout)
            if response.status_code == 200 and not _is_waf_challenge(
                response.status_code, response.text
            ):
                logger.info("Sesión calentada con %s.", target)
                return
            if _is_waf_challenge(response.status_code, response.text):
                self._solve_waf(target)
            else:
                logger.warning(
                    "Warm-up devolvió HTTP %s en %s; se continúa.",
                    response.status_code, target,
                )
        except _NETWORK_ERRORS as exc:
            logger.warning("Warm-up falló en %s (%s); se continúa.", target, exc)

    def _headers(self, referer: Optional[str]) -> Optional[dict[str, str]]:
        # Con impersonación, curl_cffi ya manda los headers del navegador;
        # sólo agregamos el Referer cuando corresponde.
        if referer:
            return {"Referer": referer}
        return None

    # ------------------------------------------------------------------
    # GET con reintentos
    # ------------------------------------------------------------------
    def get(
        self,
        url: str,
        *,
        use_delay: bool = True,
        referer: Optional[str] = None,
    ) -> str:
        """Descarga una URL devolviendo el HTML, con reintentos y backoff.

        Un HTTP 403 se interpreta como bloqueo temporal de la IP (Transfermarkt
        lo usa como rate limit). En ese caso se espera `blocked_wait` segundos y
        se reintenta hasta `blocked_retries` veces, en vez de abortar: así un
        backfill desatendido se reanuda solo cuando el bloqueo se levanta.
        Un challenge de AWS WAF se resuelve con el navegador (si hay solver).
        """
        last_error: Optional[Exception] = None
        retries = 0
        blocked = 0
        waf_solves = 0
        headers = self._headers(referer)
        while True:
            if use_delay:
                self._sleep()
            try:
                response = self.session.get(
                    url, timeout=self.timeout, headers=headers
                )
                if _is_waf_challenge(response.status_code, response.text):
                    waf_solves += 1
                    last_error = RuntimeError(f"challenge AWS WAF en {url}")
                    if self.waf_solver is None:
                        logger.error(
                            "Challenge AWS WAF en %s y no hay solver configurado "
                            "(TM_WAF_SOLVER). Abortando.",
                            url,
                        )
                        break
                    if waf_solves > self.max_waf_solves:
                        break
                    if self._solve_waf(url):
                        continue
                    time.sleep(min(60.0, 5.0 * waf_solves))
                    continue
                if response.status_code == 200:
                    return response.text
                if response.status_code == 403:
                    blocked += 1
                    last_error = RuntimeError(f"HTTP 403 (bloqueo de IP) para {url}")
                    if blocked > self.blocked_retries:
                        break
                    logger.warning(
                        "HTTP 403 en %s (posible bloqueo de IP, intento %s/%s). "
                        "Esperando %.0fs antes de reintentar.",
                        url, blocked, self.blocked_retries, self.blocked_wait,
                    )
                    time.sleep(self.blocked_wait)
                    continue
                if response.status_code in (429, 500, 502, 503, 504):
                    retries += 1
                    last_error = RuntimeError(f"HTTP {response.status_code} para {url}")
                    if retries > self.max_retries:
                        break
                    wait = min(60.0, (2 ** retries) + random.uniform(0, 1))
                    logger.warning(
                        "HTTP %s en %s (intento %s/%s). Reintentando en %.1fs.",
                        response.status_code, url, retries, self.max_retries, wait,
                    )
                    time.sleep(wait)
                    continue
                response.raise_for_status()
            except _NETWORK_ERRORS as exc:
                retries += 1
                last_error = exc
                if retries > self.max_retries:
                    break
                wait = min(60.0, (2 ** retries) + random.uniform(0, 1))
                logger.warning(
                    "Error de red en %s (intento %s/%s): %s. Reintentando en %.1fs.",
                    url, retries, self.max_retries, exc, wait,
                )
                time.sleep(wait)

        raise RuntimeError(f"No se pudo descargar {url}: {last_error}")
