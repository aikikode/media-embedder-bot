import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,!?;:"


@dataclass(frozen=True)
class Service:
    name: str
    source: re.Pattern[str]
    target: str


def load_services(path: Path) -> list[Service]:
    with path.open(encoding="utf-8") as file:
        entries = json.load(file)

    services = []
    for entry in entries:
        targets = entry.get("targets", [])
        if not targets:
            raise ValueError(f"Service {entry.get('name', '<unnamed>')} has no targets")
        services.append(
            Service(
                name=entry["name"],
                source=re.compile(entry["source"], re.IGNORECASE),
                target=targets[0],
            )
        )
    return services


def _trim_url(url: str) -> str:
    url = url.rstrip(TRAILING_PUNCTUATION)
    for opening, closing in (("(", ")"), ("[", "]"), ("{", "}")):
        while url.endswith(closing) and url.count(closing) > url.count(opening):
            url = url[:-1]
    return url


def transform_url(url: str, services: list[Service]) -> str | None:
    candidate = _trim_url(url)
    if candidate.lower().startswith("www."):
        candidate = f"https://{candidate}"

    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        if not hostname:
            return None
    except ValueError:
        return None

    for service in services:
        if service.source.fullmatch(hostname):
            return urlunsplit(
                (parsed.scheme, service.target, parsed.path, parsed.query, parsed.fragment)
            )
    return None


def transformed_urls(text: str, services: list[Service]) -> list[str]:
    transformed = []
    for match in URL_PATTERN.finditer(text):
        result = transform_url(match.group(), services)
        if result:
            transformed.append(result)
    return transformed
