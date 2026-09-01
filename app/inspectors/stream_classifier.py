def is_streaming_response(
    content_type: str | None,
) -> bool:

    if not content_type:
        return False

    content_type = content_type.lower()

    if "text/event-stream" in content_type:
        return True

    return False