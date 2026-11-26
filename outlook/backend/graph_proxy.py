"""Validation for Graph calls made on behalf of the authenticated user."""
from urllib.parse import unquote, urlsplit


_GRAPH_HOST = "graph.microsoft.com"
_ALLOWED_METHODS = {"GET", "POST", "PATCH", "DELETE"}
_FORBIDDEN_HEADERS = {
    "authorization",
    "host",
    "content-length",
    "proxy-authorization",
}


def _relative_graph_path(endpoint):
    endpoint = str(endpoint or "").strip()
    if not endpoint or len(endpoint) > 8192:
        raise ValueError("Invalid Microsoft Graph endpoint.")

    parsed = urlsplit(endpoint)
    if parsed.scheme or parsed.netloc:
        if (
            parsed.scheme != "https"
            or parsed.hostname != _GRAPH_HOST
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or not parsed.path.startswith("/v1.0/")
            or parsed.fragment
        ):
            raise ValueError("Only Microsoft Graph v1.0 endpoints are allowed.")
        path = parsed.path[len("/v1.0/"):]
    else:
        if parsed.fragment or endpoint.startswith("//"):
            raise ValueError("Invalid Microsoft Graph endpoint.")
        path = parsed.path.lstrip("/")

    decoded_path = unquote(path)
    if "\\" in decoded_path or any(
        part in {".", ".."} for part in decoded_path.split("/")
    ):
        raise ValueError("Invalid Microsoft Graph endpoint.")
    if not decoded_path.startswith(("me/", "me?", "me", "$batch")):
        raise ValueError("Only the signed-in user's Microsoft Graph data is allowed.")
    root = decoded_path.split("/", 1)[0].split("?", 1)[0]
    if root not in {"me", "$batch"}:
        raise ValueError("Only the signed-in user's Microsoft Graph data is allowed.")
    return root


def validate_graph_request(method, endpoint, body=None, headers=None, raw=False):
    method = str(method or "").upper()
    if method not in _ALLOWED_METHODS:
        raise ValueError("Unsupported Microsoft Graph method.")
    root = _relative_graph_path(endpoint)
    for header in (headers or {}):
        if str(header).lower() in _FORBIDDEN_HEADERS:
            raise ValueError("Authentication and transport headers are managed by Ghost.")
    if raw and method != "GET":
        raise ValueError("Raw Graph requests must be GET requests.")

    if root == "$batch":
        if method != "POST":
            raise ValueError("Microsoft Graph batch requests must use POST.")
        if not isinstance(body, dict) or not isinstance(body.get("requests"), list):
            raise ValueError("Invalid Microsoft Graph batch request.")
        if not 1 <= len(body["requests"]) <= 20:
            raise ValueError("Graph batch requests must contain between 1 and 20 operations.")
        for item in body["requests"]:
            if not isinstance(item, dict):
                raise ValueError("Invalid Microsoft Graph batch operation.")
            nested_method = str(item.get("method") or "").upper()
            nested_url = str(item.get("url") or "")
            if nested_method not in _ALLOWED_METHODS or _relative_graph_path(nested_url) != "me":
                raise ValueError("Graph batch operations must target the signed-in user's data.")
