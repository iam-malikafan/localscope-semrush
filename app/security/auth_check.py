import os
from urllib.parse import quote, urlsplit

import httpx
from fastapi import Request


AUTH_CHECK_URL = os.getenv(
    "AUTH_CHECK_URL",
    "https://authcheck.rankytools.com",
)

APP_NAME = os.getenv(
    "APP_NAME",
    "wh",
)

LOGIN_URL = os.getenv(
    "LOGIN_URL",
    "https://member.rankytools.com",
)

NO_ACCESS_URL = os.getenv(
    "NO_ACCESS_URL",
    "https://member.rankytools.com/member",
)

CURRENT_HOST = os.getenv(
    "CURRENT_HOST",
    "sem.rankytools.com",
)


async def verify_user(request: Request):
    cookie_string = request.headers.get("cookie", "")

    if not cookie_string or len(cookie_string) < 10:
        print("[AUTH] No cookies found")

        return {
            "authenticated": False,
            "allowed": False,
            "status": "not_logged_in",
            "reason": "no_cookies",
        }

    auth_url = f"{AUTH_CHECK_URL}/?app={APP_NAME}"

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                auth_url,
                headers={
                    "Cookie": cookie_string,
                    "User-Agent": request.headers.get(
                        "user-agent",
                        "Mozilla/5.0",
                    ),
                    "Accept": "application/json",
                    "Host": urlsplit(AUTH_CHECK_URL).hostname,
                },
            )

        if 300 <= response.status_code < 400:
            return {
                "authenticated": False,
                "allowed": False,
                "status": "not_logged_in",
                "reason": "auth_redirect",
            }

        try:
            data = response.json()
        except ValueError:
            return {
                "authenticated": False,
                "allowed": False,
                "status": "error",
                "reason": "invalid_response",
            }

        if not isinstance(data, dict):
            return {
                "authenticated": False,
                "allowed": False,
                "status": "error",
                "reason": "invalid_response",
            }

        if data.get("status") == "ok" and data.get("allowed") is True:
            return {
                "authenticated": True,
                "allowed": True,
                "status": "ok",
                "user": {
                    "uid": data.get("uid"),
                    "email": data.get("email"),
                    "username": data.get("username"),
                    "name": data.get("name"),
                    "token": data.get("token"),
                    "ts": data.get("ts"),
                    "app": data.get("app"),
                    "folderId": data.get("folderId"),
                },
            }

        if data.get("status") == "ok" and data.get("allowed") is False:
            return {
                "authenticated": True,
                "allowed": False,
                "status": "no_access",
                "reason": "no_app_access",
                "user": {
                    "uid": data.get("uid"),
                    "email": data.get("email"),
                    "username": data.get("username"),
                },
            }

        if data.get("status") in {"not_logged_in", "error"}:
            return {
                "authenticated": False,
                "allowed": False,
                "status": data.get("status"),
                "reason": "not_logged_in",
            }

        return {
            "authenticated": False,
            "allowed": False,
            "status": data.get("status", "unknown"),
            "reason": "unknown_status",
        }

    except Exception as error:
        print(f"[AUTH] Auth check failed: {type(error).__name__}")

        return {
            "authenticated": False,
            "allowed": False,
            "status": "error",
            "reason": "auth_check_failed",
        }


def build_auth_redirect(request: Request, auth_result: dict) -> str:
    if (
        not auth_result["authenticated"]
        or auth_result["status"] == "not_logged_in"
    ):
        requested_url = request.url.path

        if request.url.query:
            requested_url += f"?{request.url.query}"

        return (
            f"{LOGIN_URL}"
            f"?return_url="
            f"{quote(f'https://{CURRENT_HOST}{requested_url}', safe='')}"
        )

    if (
        not auth_result["allowed"]
        or auth_result["status"] == "no_access"
    ):
        return NO_ACCESS_URL

    return LOGIN_URL