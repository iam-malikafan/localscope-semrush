import httpx


REQUEST_EXCLUDED_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


RESPONSE_EXCLUDED_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding", 
    "content-security-policy",
    "content-security-policy-report-only",
    "cross-origin-embedder-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
    "set-cookie",
    "alt-svc",
}


def prepare_request_headers(headers: dict):
    forwarded_headers = {}

    for name, value in headers.items():
        if name.lower() in REQUEST_EXCLUDED_HEADERS:
            continue

        forwarded_headers[name] = value

    return forwarded_headers


def prepare_response_headers(headers):
    forwarded_headers = {}

    for name, value in headers.items():
        if name.lower() in RESPONSE_EXCLUDED_HEADERS:
            continue

        forwarded_headers[name] = value

    return forwarded_headers


async def forward_request(
    client: httpx.AsyncClient,
    method: str,
    target_url: str,
    headers: dict,
    body: bytes
):
    forwarded_headers = prepare_request_headers(headers)

    try:
        response = await client.request(
            method=method,
            url=target_url,
            headers=forwarded_headers,
            content=body
        )

        return response

    except httpx.TimeoutException as error:
        raise RuntimeError(
            f"Upstream request timed out: {error}"
        ) from error

    except httpx.RequestError as error:
        raise RuntimeError(
            f"Upstream request failed: {error}"
        ) from error


async def open_stream_response(
    client: httpx.AsyncClient,
    method: str,
    target_url: str,
    headers: dict,
    body: bytes,
):
    forwarded_headers = prepare_request_headers(
        headers
    )

    try:
        upstream_request = client.build_request(
            method=method,
            url=target_url,
            headers=forwarded_headers,
            content=body,
        )
        

        response = await client.send(
            upstream_request,
            stream=True,
        )

        return response

    except httpx.TimeoutException as error:
        raise RuntimeError(
            f"Upstream request timed out: {error}"
        ) from error

    except httpx.RequestError as error:
        raise RuntimeError(
            f"Upstream request failed: {error}"
        ) from error