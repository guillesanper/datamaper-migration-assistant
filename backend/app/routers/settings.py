from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.utils.cookies import sign_cookie
from app.utils.i18n import SUPPORTED_LOCALES

router = APIRouter()


@router.post("/settings/locale")
def set_locale(request: Request, locale: str = Form(...)):
    # 1) Validate locale (SUPPORTED_LOCALES should include "en-US" and "es-ES")
    if locale not in SUPPORTED_LOCALES:
        referer = request.headers.get("referer") or "/"
        return RedirectResponse(referer, status_code=303)

    # 2) Build redirect URL: replace `lang` in the referer with the selected locale
    referer = request.headers.get("referer") or "/"
    parts = urlsplit(referer)
    q = parse_qs(parts.query)
    q["lang"] = [locale]  # force new lang
    new_query = urlencode(q, doseq=True)
    new_url = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

    # 3) Set signed cookie and redirect
    resp = RedirectResponse(new_url, status_code=303)
    resp.set_cookie(
        key="locale",
        value=sign_cookie(locale),
        max_age=60 * 60 * 24 * 365,
        path="/",
        secure=False,  # True en prod con HTTPS
        httponly=True,
        samesite="lax",
    )
    return resp


@router.post("/settings/locale/clear")
def clear_locale_cookie(request: Request):
    referer = request.headers.get("referer") or "/"
    resp = RedirectResponse(referer, status_code=303)
    resp.delete_cookie("locale", path="/")
    return resp
