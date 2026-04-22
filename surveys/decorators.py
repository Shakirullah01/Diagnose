"""
Framing rules for Yandex Metrika Webvisor / click map / scroll map.

Those tools load the site inside an iframe from Yandex origins. The default
``X-Frame-Options: DENY`` from ``XFrameOptionsMiddleware`` blocks that.

We use ``@xframe_options_exempt`` only on selected public views so the middleware
does not set ``X-Frame-Options``, and we add ``Content-Security-Policy: frame-ancestors``
so only this site and Yandex can embed the page (stricter than fully open framing).

Admin, specialist panel, and other private views keep the default DENY behaviour.
"""

from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.views.decorators.clickjacking import xframe_options_exempt

# Yandex.Metrica CSP for click map / scroll map / Webvisor (see install-counter-csp).
# frame-ancestors must include blob: and https://mc.yandex.ru (and regional mc hosts as needed).
_METRIKA_FRAME_ANCESTORS = (
    "frame-ancestors 'self' blob: "
    "https://mc.yandex.ru "
    "https://mc.yandex.com "
    "https://mc.yandex.by "
    "https://mc.yandex.kz "
    "https://webvisor.com "
    "http://webvisor.com "
    "https://mc.webvisor.com "
    "https://mc.webvisor.org"
)


def _merge_frame_ancestors_csp(response) -> None:
    if getattr(response, "streaming", False):
        return
    code = getattr(response, "status_code", 200)
    if code in (301, 302, 303, 307, 308):
        return
    existing = (response.get("Content-Security-Policy") or "").strip()
    if not existing:
        response["Content-Security-Policy"] = _METRIKA_FRAME_ANCESTORS
        return
    if "frame-ancestors" in existing.lower():
        return
    response["Content-Security-Policy"] = f"{existing}; {_METRIKA_FRAME_ANCESTORS}"


def allow_yandex_metrika_frames(view_func):
    """
    Public pages that should work inside Yandex Metrika session replay / maps:
    skip ``X-Frame-Options: DENY`` and restrict embedding via CSP ``frame-ancestors``.
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        # For temporary diagnostics, allow open framing on selected public pages.
        # X-Frame-Options is already exempted for this view by the decorator below.
        if not getattr(settings, "METRIKA_IFRAME_TEST_MODE", False):
            _merge_frame_ancestors_csp(response)
        return response

    return xframe_options_exempt(_wrapped_view)
