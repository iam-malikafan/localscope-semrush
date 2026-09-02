import os
import secrets
from dotenv import load_dotenv
from time import time
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Form,Depends,HTTPException
from fastapi.responses import RedirectResponse
import asyncio
from uuid import uuid4
from urllib.parse import urlsplit, quote,unquote
from contextlib import asynccontextmanager
import httpx
from fastapi import (
    FastAPI,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed
from fastapi.responses import JSONResponse, Response, StreamingResponse
from app.proxy.proxy_engine import  prepare_response_headers, open_stream_response
from app.proxy.target_config import (
    TargetConfig,
    build_target_url,
)
from app.proxy.cookie_rewriter import (
    rewrite_set_cookie,
)
from app.proxy.html_rewriter import rewrite_html
from app.proxy.css_rewriter import rewrite_css
from app.proxy.manifest_rewriter import (
    rewrite_manifest,
)
from app.proxy.redirect_rewriter import (
    rewrite_redirect_location,
)
from app.proxy.url_mapper import build_external_target_url,decode_external_proxy_url
from app.proxy.origin_rewriter import (
    rewrite_origin_headers,
)
from app.inspectors.stream_classifier import (
    is_streaming_response,
)

from app.accounts.models import (
    create_account,
)
from app.accounts.cookie_sync import (
    update_account_cookie,
)
from app.accounts.selector import (
    select_account_for_session,
)
from app.accounts.health import (
    update_account_health_from_response,
)
from app.accounts.health_check import (
    check_account_health,
    check_proxy_health,
)
from app.accounts.session_cleanup import (
    cleanup_stale_sessions,
)

from app.policies.access_rules import (
    is_access_blocked,
)


from app.storage.database import (
    initialize_database,
    load_accounts,
    save_account,
    update_account_enabled,
    update_account_cookie as save_account_cookie,
    delete_account_from_database,
    update_account,
)


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.account_clients = {}

    app.state.target = TargetConfig("https://www.semrush.com")


    initialize_database()

    app.state.accounts = (
        load_accounts()
    )


    app.state.account_assignments = {}
    app.state.next_account_index = 0
    app.state.session_last_seen = {}

    app.state.admin_sessions = set()

    app.state.admin_username = os.getenv(
        "LOCALSCOPE_ADMIN_USER",
    )
    
    app.state.admin_password = os.getenv(
        "LOCALSCOPE_ADMIN_PASSWORD",
    )
    if (
        not app.state.admin_username
        or not app.state.admin_password
    ):
        raise RuntimeError(
            "LocalScope admin credentials "
            "are not configured"
        )


    yield

    for client in app.state.account_clients.values():
        await client.aclose()


async def get_account_client(app: FastAPI, account):
    """Return the reusable HTTPX client bound to an account proxy."""
    if not account.proxy_url:
        raise RuntimeError("Account proxy is not configured")

    client = app.state.account_clients.get(account.id)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            proxy=account.proxy_url,
            follow_redirects=False,
            timeout=30.0,
        )
        app.state.account_clients[account.id] = client

    return client


async def close_account_client(app: FastAPI, account_id: str):
    client = app.state.account_clients.pop(account_id, None)
    if client is not None and not client.is_closed:
        await client.aclose()


def build_proxy_url(data: dict) -> str | None:
    scheme = str(data.get("proxy_scheme", "http")).strip().lower()
    host = str(data.get("proxy_host", "")).strip()
    port = data.get("proxy_port")
    username = str(data.get("proxy_username", "")).strip()
    password = str(data.get("proxy_password", ""))

    if scheme not in {"http", "https"}:
        raise ValueError("Proxy scheme must be http or https")
    if not host:
        raise ValueError("Proxy host is required")
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise ValueError("Proxy port must be a number")
    if not 1 <= port <= 65535:
        raise ValueError("Proxy port must be between 1 and 65535")

    auth = ""
    if username or password:
        if not username or not password:
            raise ValueError("Both proxy username and password are required")
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"

    return f"{scheme}://{auth}{host}:{port}"


app = FastAPI(lifespan=lifespan)



@app.middleware("http")
async def localscope_session_middleware(
    request: Request,
    call_next,
):

    path = request.url.path


    # LocalScope admin/internal routes
    # should not create user sessions.
    if (
        path.startswith("/localscope/")
        or path == "/localscope"
    ):
        return await call_next(
            request
        )


    session_id = request.cookies.get(
        "localscope_session"
    )


    if not session_id:

        session_id = str(
            uuid4()
        )


    request.state.localscope_session = (
        session_id
    )


    request.app.state.session_last_seen[
        session_id
    ] = time()


    response = await call_next(
        request
    )


    if (
        request.cookies.get(
            "localscope_session"
        )
        is None
    ):

        response.set_cookie(
            key="localscope_session",
            value=session_id,
            httponly=True,
            samesite="lax",
            path="/",
        )


    return response
 
app.mount(
    "/localscope/static",
    StaticFiles(directory="static"),
    name="localscope-static",
)
templates = Jinja2Templates(directory="templates")


@app.get("/localscope/")
async def home(
    request: Request,
):

    if not is_admin_authenticated(
        request
    ):

        return RedirectResponse(
            url="/localscope/login",
            status_code=302,
        )


    return templates.TemplateResponse(
        request=request,
        name="index.html",
    )





async def handle_proxy_request(
    request: Request,
    target_url: str,
):
    body = await request.body()

    original_headers = dict(request.headers)

    session_id = (
        request.state.localscope_session
    )

    account = select_account_for_session(
        app=request.app,
        session_id=session_id,
    )


    # On real browser page navigation, verify that
    # the assigned Semrush account is still authenticated.
    if (
        account
        and is_document_request(request)
    ):
        checked_account_ids = set()

        while (
            account
            and account.id not in checked_account_ids
        ):
            checked_account_ids.add(
                account.id
            )

            health, status_code = (
                await check_account_health(
                    client=await get_account_client(request.app, account),
                    cookie=account.cookie,
                )
            )

            account.health = health
            account.last_status_code = (
                status_code
            )

            # Account is still valid.
            if health == "healthy":
                break

            # The cookie is genuinely expired.
            if health == "expired":

                # Remove the stale sticky assignment.
                request.app.state.account_assignments.pop(
                    session_id,
                    None,
                )

                # Try another available account.
                account = select_account_for_session(
                    app=request.app,
                    session_id=session_id,
                )

                continue

            # "error" could just mean Semrush/network trouble.
            # Do not permanently treat the account as expired.
            break


    if not account:
        return templates.TemplateResponse(
            request=request,
            name="unavailable.html",
            status_code=503,
        )

    browser_headers = dict(
        original_headers
    )

    browser_headers.pop(
        "cookie",
        None,
    )
    
    target_host = urlsplit(
        target_url
    ).hostname or ""


    is_semrush_host = (
        target_host == "semrush.com"
        or target_host.endswith(
            ".semrush.com"
        )
    )


    if is_semrush_host:

        browser_headers["cookie"] = (
            account.cookie
        )

    else:

        browser_headers.pop(
            "cookie",
            None,
        )

    forward_headers = rewrite_origin_headers(
        headers=browser_headers,
        upstream_url=target_url,
    )


    try:
        client = await get_account_client(request.app, account)
    except RuntimeError as error:
        return JSONResponse(
            status_code=503,
            content={"error": "proxy_not_configured", "message": str(error)},
        )

    try:

        upstream_response = await open_stream_response(
            client=client,
            method=request.method,
            target_url=target_url,
            headers=forward_headers,
            body=body,
        )



    except RuntimeError as error:
        return JSONResponse(
            status_code=502,
            content={
                "error": "upstream_error",
                "message": str(error),
            },
        )

    update_account_health_from_response(
        account=account,
        target_url=target_url,
        status_code=(
            upstream_response.status_code
        ),
    )
    


    response_content_type = upstream_response.headers.get("content-type")

    # Detect responses that must be forwarded as a stream.
    is_streaming = is_streaming_response(
        response_content_type
    )
    if is_streaming:

        response_headers = prepare_response_headers(
            upstream_response.headers
        )

        set_cookies = (
            upstream_response.headers.get_list(
                "set-cookie"
            )
        )


        target_host = urlsplit(
            request.app.state.target.base_url
        ).hostname

        response_host = urlsplit(
            target_url
        ).hostname or ""

        is_semrush_host = (
            response_host == "semrush.com"
            or response_host.endswith(
                ".semrush.com"
            )
        )

        if (
            set_cookies
            and is_semrush_host
        ):

            account.cookie = (
                update_account_cookie(
                    current_cookie=account.cookie,
                    set_cookie_headers=set_cookies,
                )
            )

            save_account_cookie(
                account_id=account.id,
                cookie=account.cookie,
            )
 


        async def stream_generator():

            try:

                async for chunk in (
                    upstream_response.aiter_bytes()
                ):

                    yield chunk

            finally:

                await upstream_response.aclose()

        return StreamingResponse(
            stream_generator(),
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=None,
        )
    
    response_body = await upstream_response.aread()

    await upstream_response.aclose()

    set_cookies = (
        upstream_response.headers.get_list(
            "set-cookie"
        )
    )

    target_host = urlsplit(
        request.app.state.target.base_url
    ).hostname

    response_host = urlsplit(
        target_url
    ).hostname or ""

    is_semrush_host = (
        response_host == "semrush.com"
        or response_host.endswith(
            ".semrush.com"
        )
    )

    if (
        set_cookies
        and is_semrush_host
    ):

        account.cookie = (
            update_account_cookie(
                current_cookie=account.cookie,
                set_cookie_headers=set_cookies,
            )
        )

        save_account_cookie(
            account_id=account.id,
            cookie=account.cookie,
        )

    if response_content_type and "text/html" in response_content_type.lower():
        html = response_body.decode(
            "utf-8",
            errors="replace",
        )

        rewritten_html = rewrite_html(
            html=html,
            upstream_url=target_url,
            target_base_url=(
                request.app.state.target.base_url
            ),
        )

        response_body = rewritten_html.encode("utf-8")

    elif response_content_type and "text/css" in response_content_type.lower():
        css = response_body.decode(
            "utf-8",
            errors="replace",
        )

        rewritten_css = rewrite_css(
            css=css,
            upstream_url=target_url,  
            target_base_url=(
                request.app.state.target.base_url
            ),
        )

        response_body = rewritten_css.encode("utf-8")

    elif (
        response_content_type
        and (
            "application/manifest+json" in response_content_type.lower()
            or "application/x-web-app-manifest+json" in response_content_type.lower()
        )
    ) or "manifest" in target_url.lower():
        response_body = rewrite_manifest(
            body=response_body,
            upstream_url=target_url,
            target_base_url=request.app.state.target.base_url,
        )


    redirect_location = upstream_response.headers.get("location")



    response_headers = prepare_response_headers(upstream_response.headers)
    if upstream_response.is_redirect:

        rewritten_location = rewrite_redirect_location(
            location=redirect_location,
            upstream_url=target_url,
            target_base_url=(request.app.state.target.base_url),
        )

        if rewritten_location:

            response_headers["location"] = rewritten_location

    response = Response(
        content=response_body,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )



    return response

def is_document_request(
    request: Request,
) -> bool:

    fetch_dest = (
        request.headers.get(
            "sec-fetch-dest",
            ""
        ).lower()
    )

    accept = (
        request.headers.get(
            "accept",
            ""
        ).lower()
    )

    return (
        fetch_dest == "document"
        or (
            "text/html" in accept
            and fetch_dest not in {
                "empty",
                "script",
                "style",
                "image",
            }
        )
    )

def blocked_response(
    request: Request,
):

    accept = (
        request.headers.get(
            "accept",
            ""
        )
        .lower()
    )

    content_type = (
        request.headers.get(
            "content-type",
            ""
        )
        .lower()
    )

    is_api_request = (
        "application/json"
        in accept
        or
        "application/json"
        in content_type
    )


    if is_api_request:

        return JSONResponse(
            status_code=403,
            content={
                "error":
                    "access_restricted",

                "message":
                    "This action is not available "
                    "through LocalScope.",
            },
        )


    return templates.TemplateResponse(
        request=request,
        name="blocked.html",
        status_code=403,
    )

@app.api_route("/proxy/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_request(
    request: Request,
    path: str,
):

    if is_access_blocked(
        method=request.method,
        path=path,
        is_document=is_document_request(
            request
        ),
    ):
        return blocked_response(
            request
        )

    target = request.app.state.target

    target_url = build_target_url(
        base_url=target.base_url,
        path=path,
        query_string=request.url.query,
    )

    return await handle_proxy_request(
        request=request,
        target_url=target_url,
    )


@app.api_route(
    "/proxy-external/{scheme}/{encoded_netloc}/{path:path}",
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    ],
)
async def proxy_external(
    request: Request,
    scheme: str,
    encoded_netloc: str,
    path: str,
):

    if scheme not in {
        "http",
        "https",
    }:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_scheme"
            },
        )

    target_url = build_external_target_url(
        scheme=scheme,
        encoded_netloc=encoded_netloc,
        path=path,
        query_string=request.url.query,
    )

    return await handle_proxy_request(
        request=request,
        target_url=target_url,
    )



# =============================
# LOGIN PANEL ROUTES
# =============================
def require_admin(
    request: Request,
):

    if not is_admin_authenticated(
        request
    ):
        raise HTTPException(
            status_code=401,
            detail="Admin authentication required",
        )
    
def is_admin_authenticated(
    request: Request,
) -> bool:

    session_id = request.cookies.get(
        "localscope_admin_session"
    )

    if not session_id:
        return False

    return (
        session_id
        in request.app.state.admin_sessions
    )


@app.get(
    "/localscope/login"
)
async def admin_login_page(
    request: Request,
):

    if is_admin_authenticated(
        request
    ):

        return RedirectResponse(
            url="/localscope/",
            status_code=302,
        )

    return templates.TemplateResponse(
        request=request,
        name="admin_login.html",
        context={
            "error": None,
        },
    )

@app.post(
    "/localscope/login"
)
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):

    correct_user = secrets.compare_digest(
        username,
        request.app.state.admin_username,
    )

    correct_password = secrets.compare_digest(
        password,
        request.app.state.admin_password,
    )

    if not (
        correct_user
        and correct_password
    ):

        return templates.TemplateResponse(
            request=request,
            name="admin_login.html",
            context={
                "error":
                    "Invalid username or password.",
            },
            status_code=401,
        )


    session_id = secrets.token_urlsafe(
        32
    )

    request.app.state.admin_sessions.add(
        session_id
    )


    response = RedirectResponse(
        url="/localscope/",
        status_code=303,
    )

    response.set_cookie(
        key="localscope_admin_session",
        value=session_id,
        httponly=True,
        samesite="strict",
        path="/localscope",
    )

    return response


@app.post(
    "/localscope/logout"
)
async def admin_logout(
    request: Request,
):

    session_id = request.cookies.get(
        "localscope_admin_session"
    )

    if session_id:

        request.app.state.admin_sessions.discard(
            session_id
        )


    response = RedirectResponse(
        url="/localscope/login",
        status_code=303,
    )

    response.delete_cookie(
        "localscope_admin_session",
        path="/localscope",
    )

    return response




# =============================
# WEBSOCKET ROUTES
# =============================

@app.websocket(
    "/ws-proxy/{encoded_url:path}"
)
async def websocket_proxy(
    websocket: WebSocket,
    encoded_url: str,
):

    target_url = (
        decode_external_proxy_url(
            encoded_url
        )
    )

    session_id = websocket.cookies.get("localscope_session")
    if not session_id:
        session_id = str(uuid4())

    websocket.state.localscope_session = session_id
    websocket.app.state.session_last_seen[session_id] = time()

    account = select_account_for_session(
        app=websocket.app,
        session_id=session_id,
    )

    if not account:
        await websocket.close(code=1013, reason="No Semrush account available")
        return

    if not account.proxy_url:
        await websocket.close(code=1013, reason="Account proxy is not configured")
        return

    requested_protocols = (
        websocket.headers.get(
            "sec-websocket-protocol"
        )
    )

    subprotocols = []

    if requested_protocols:

        subprotocols = [
            protocol.strip()
            for protocol
            in requested_protocols.split(",")
            if protocol.strip()
        ]


    parsed_target = urlsplit(
        target_url
    )

    if parsed_target.scheme == "wss":

        upstream_origin = (
            f"https://{parsed_target.netloc}"
        )

    else:

        upstream_origin = (
            f"http://{parsed_target.netloc}"
        )


    try:

        async with connect(
            target_url,
            origin=upstream_origin,
            proxy=account.proxy_url,
            subprotocols=(
                subprotocols
                if subprotocols
                else None
            ),
        ) as upstream_ws:

            await websocket.accept(
                subprotocol=(
                    upstream_ws.subprotocol
                )
            )


            async def client_to_upstream():

                try:

                    while True:

                        message = (
                            await websocket.receive()
                        )

                        if (
                            message["type"]
                            == "websocket.disconnect"
                        ):
                            break


                        if (
                            message.get("text")
                            is not None
                        ):

                            await upstream_ws.send(
                                message["text"]
                            )


                        elif (
                            message.get("bytes")
                            is not None
                        ):

                            await upstream_ws.send(
                                message["bytes"]
                            )

                except WebSocketDisconnect:
                    pass


            async def upstream_to_client():

                try:

                    async for message in upstream_ws:

                        if isinstance(
                            message,
                            str
                        ):

                            await websocket.send_text(
                                message
                            )

                        else:

                            await websocket.send_bytes(
                                message
                            )

                except ConnectionClosed:
                    pass


            await asyncio.gather(
                client_to_upstream(),
                upstream_to_client(),
            )


    except Exception as error:

        print(
            "WebSocket proxy error:",
            error
        )

    finally:

        try:
            await websocket.close()

        except RuntimeError:
            pass


# =============================
# ACCOUNTS ROUTES
# =============================
@app.post(
    "/localscope/api/accounts"
)
async def add_account(
    request: Request,
    _: None = Depends(require_admin)
):

    data = await request.json()

    name = (
        data.get("name", "")
        .strip()
    )

    cookie = (
        data.get("cookie", "")
        .strip()
    )

    try:
        proxy_url = build_proxy_url(data)
    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={"error": str(error)},
        )


    if not name:

        return JSONResponse(
            status_code=400,
            content={
                "error":
                    "Account name is required"
            },
        )


    if not cookie:

        return JSONResponse(
            status_code=400,
            content={
                "error":
                    "Cookie is required"
            },
        )

    if not proxy_url:
        return JSONResponse(
            status_code=400,
            content={"error": "Proxy configuration is required"},
        )

    account = create_account(
        name=name,
        cookie=cookie,
        proxy_url=proxy_url,
    )

    request.app.state.accounts.append(
        account
    )

    save_account(
        account
    )



    return {
        "id": account.id,
        "name": account.name,
        "enabled": account.enabled
    }

@app.put("/localscope/api/accounts/{account_id}")
async def edit_account(
    request: Request,
    account_id: str,
    _: None = Depends(require_admin),
):
    data = await request.json()

    account = next(
        (
            account
            for account in request.app.state.accounts
            if account.id == account_id
        ),
        None,
    )

    if account is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Account not found"},
        )

    name = str(data.get("name", "")).strip()

    if not name:
        return JSONResponse(
            status_code=400,
            content={"error": "Account name is required"},
        )

    cookie = data.get("cookie")
    if cookie is not None:
        cookie = str(cookie).strip()

        if not cookie:
            return JSONResponse(
                status_code=400,
                content={"error": "Cookie cannot be empty when provided"},
            )

    proxy_url = None

    proxy_fields_present = any(
        field in data
        for field in (
            "proxy_scheme",
            "proxy_host",
            "proxy_port",
            "proxy_username",
            "proxy_password",
        )
    )

    if proxy_fields_present:
        proxy_username = str(data.get("proxy_username", "")).strip()
        proxy_password = str(data.get("proxy_password", ""))

        existing_proxy = urlsplit(account.proxy_url) if account.proxy_url else None

        # If credentials are left blank during editing,
        # keep the existing proxy credentials.
        if existing_proxy and not proxy_username and not proxy_password:
            proxy_username = existing_proxy.username or ""
            proxy_password = (
                unquote(existing_proxy.password)
                if existing_proxy.password
                else ""
            )

        proxy_data = {
            "proxy_scheme": data.get("proxy_scheme", "http"),
            "proxy_host": data.get("proxy_host", ""),
            "proxy_port": data.get("proxy_port"),
            "proxy_username": proxy_username,
            "proxy_password": proxy_password,
        }

        try:
            proxy_url = build_proxy_url(proxy_data)
        except ValueError as error:
            return JSONResponse(
                status_code=400,
                content={"error": str(error)},
            )

    old_proxy_url = account.proxy_url

    if proxy_url is not None and proxy_url != old_proxy_url:
        await close_account_client(request.app, account.id)

    account.name = name

    if cookie is not None:
        account.cookie = cookie

    if proxy_url is not None:
        account.proxy_url = proxy_url

    update_account(
        account_id=account.id,
        name=account.name,
        cookie=cookie,
        proxy_url=proxy_url,
    )

    return {
        "id": account.id,
        "name": account.name,
        "enabled": account.enabled,
    }

@app.get(
    "/localscope/api/accounts"
)
async def list_accounts(
    request: Request,
    _: None = Depends(require_admin)
):

    cleanup_stale_sessions(
        request.app
    )

    assignments = (
        request.app.state
        .account_assignments
    )

    return [
        {
            "id": account.id,
            "name": account.name,
            "enabled": account.enabled,

            "assigned_users": sum(
                1
                for assigned_account_id
                in assignments.values()
                if assigned_account_id
                == account.id
            ),
            "health": account.health,
            "has_proxy": bool(account.proxy_url),
            "proxy_host": (urlsplit(account.proxy_url).hostname if account.proxy_url else None),
            "proxy_port": (urlsplit(account.proxy_url).port if account.proxy_url else None),
            "proxy_scheme": (urlsplit(account.proxy_url).scheme if account.proxy_url else None),
            "proxy_has_auth": bool(
                account.proxy_url
                and urlsplit(account.proxy_url).username
            ),
            "proxy_health": getattr(account, "proxy_health", "unknown"),
            "proxy_status_code": getattr(account, "proxy_status_code", None),
            "last_status_code":
                account.last_status_code,
        }

        for account
        in request.app.state.accounts
    ]

@app.post(
    "/localscope/api/accounts/{account_id}/proxy-health"
)
async def proxy_health(
    request: Request,
    account_id: str,
    _: None = Depends(require_admin),
):
    for account in request.app.state.accounts:
        if account.id == account_id:
            if not account.proxy_url:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Proxy is not configured"},
                )

            health, status_code, message = await check_proxy_health(account.proxy_url)
            account.proxy_health = health
            account.proxy_status_code = status_code

            return {
                "id": account.id,
                "proxy_health": health,
                "proxy_status_code": status_code,
                "message": message,
            }

    return JSONResponse(
        status_code=404,
        content={"error": "Account not found"},
    )


@app.post(
    "/localscope/api/accounts/{account_id}/enable"
)
async def enable_account(
    request: Request,
    account_id: str,
    _: None = Depends(require_admin)
):

    for account in request.app.state.accounts:

        if account.id == account_id:

            account.enabled = True

            update_account_enabled(
                account_id=account.id,
                enabled=True,
            )


            try:
                health, status_code = (
                    await check_account_health(
                        client=await get_account_client(request.app, account),
                        cookie=account.cookie,
                    )
                )
            except RuntimeError as error:
                account.enabled = False
                update_account_enabled(
                    account_id=account.id,
                    enabled=False,
                )
                return JSONResponse(
                    status_code=400,
                    content={"error": str(error)},
                )


            account.health = health
            account.last_status_code = (
                status_code
            )


            return {
                "id": account.id,
                "name": account.name,
                "enabled": account.enabled,
                "health": account.health,
                "last_status_code":
                    account.last_status_code,
            }


    return JSONResponse(
        status_code=404,
        content={
            "error": "Account not found"
        },
    )

@app.post(
    "/localscope/api/accounts/{account_id}/disable"
)
async def disable_account(
    request: Request,
    account_id: str,
    _: None = Depends(require_admin)
):

    for account in request.app.state.accounts:

        if account.id == account_id:

            account.enabled = False

            update_account_enabled(
                account_id=account.id,
                enabled=False,
            )

            return {
                "id": account.id,
                "name": account.name,
                "enabled": account.enabled,
            }


    return JSONResponse(
        status_code=404,
        content={
            "error": "Account not found"
        },
    )

@app.delete(
    "/localscope/api/accounts/{account_id}"
)
async def delete_account(
    request: Request,
    account_id: str,
    _: None = Depends(require_admin)
):

    accounts = request.app.state.accounts

    for index, account in enumerate(
        accounts
    ):

        if account.id == account_id:

            accounts.pop(index)
            await close_account_client(request.app, account_id)
            delete_account_from_database(
                account_id
            )

            # Remove any browser-session
            # assignments using this account.
            assignments = (
                request.app.state
                .account_assignments
            )

            stale_sessions = [
                session_id
                for session_id, assigned_id
                in assignments.items()
                if assigned_id == account_id
            ]

            for session_id in stale_sessions:
                assignments.pop(
                    session_id,
                    None,
                )

            return {
                "success": True,
                "deleted_id": account_id,
            }

    return JSONResponse(
        status_code=404,
        content={
            "error": "Account not found"
        },
    )



# =============================
# MAIN PROXY WEB ROUTES
# =============================
@app.api_route(
    "/",
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    ],
)
async def proxy_root(
    request: Request,
):


    target = (
        request.app.state.target
    )

    target_url = build_target_url(
        base_url=target.base_url,
        path="",
        query_string=request.url.query,
    )

    return await handle_proxy_request(
        request=request,
        target_url=target_url,
    )

@app.api_route(
    "/{path:path}",
    methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
    ],
)
async def proxy_root_path(
    request: Request,
    path: str,
):

    if is_access_blocked(
        method=request.method,
        path=path,
        is_document=is_document_request(
            request
        ),
    ):
        return blocked_response(
            request
        )
    
    target = request.app.state.target

    target_url = build_target_url(
        base_url=target.base_url,
        path=path,
        query_string=request.url.query,
    )

    return await handle_proxy_request(
        request=request,
        target_url=target_url,
    )


