from urllib.parse import urlsplit, urlunsplit


class TargetConfig:
    def __init__(self, base_url: str):
        self.base_url = self._validate_base_url(base_url)

    def _validate_base_url(self, base_url: str) -> str:
        parsed = urlsplit(base_url)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError(
                "Target URL must use http or https"
            )

        if not parsed.netloc:
            raise ValueError(
                "Target URL must contain a host"
            )

        return base_url.rstrip("/")


def build_target_url(
    base_url: str,
    path: str,
    query_string: str
) -> str:
    parsed_base = urlsplit(base_url)

    base_path = parsed_base.path.rstrip("/")

    requested_path = path.lstrip("/")

    if requested_path:
        final_path = f"{base_path}/{requested_path}"
    else:
        final_path = base_path or "/"

    return urlunsplit(
        (
            parsed_base.scheme,
            parsed_base.netloc,
            final_path,
            query_string,
            ""
        )
    )