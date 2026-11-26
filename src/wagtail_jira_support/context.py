from urllib.parse import urlsplit, urlunsplit


def sanitize_source_url(url):
    """Remove potentially sensitive components from a source URL."""
    if not isinstance(url, str) or not url.strip():
        return ""

    try:
        parsed = urlsplit(url.strip())

        if parsed.scheme not in ("http", "https"):
            return ""

        if not parsed.hostname:
            return ""

        if parsed.username is not None or parsed.password is not None:
            return ""

        # Accessing port also validates its format.
        _ = parsed.port

        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path or "/",
                "",
                "",
            )
        )
    except ValueError:
        return ""


def build_description(
    description,
    application_name,
    environment="",
    source_url="",
):
    """Append application context to a support request description."""
    lines = [
        description.strip(),
        "",
        "---",
        "Application context",
        "",
        f"Application: {application_name}",
    ]

    if environment:
        lines.append(f"Environment: {environment}")

    source_url = sanitize_source_url(source_url)

    if source_url:
        lines.append(f"Source URL: {source_url}")

    return "\n".join(lines)
