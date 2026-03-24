"""Utilitaires communs pour les parsers XML de l'Assemblée nationale."""

import html
import re
from datetime import datetime

from lxml import etree

NS = "http://schemas.assemblee-nationale.fr/referentiel"
NSMAP = {"an": NS}


def tag(name: str) -> str:
    return f"{{{NS}}}{name}"


def findtext(element, path: str, default: str = "") -> str:
    parts = path.split("/")
    current = element
    for part in parts[:-1]:
        current = current.find(tag(part))
        if current is None:
            return default
    result = current.findtext(tag(parts[-1]))
    return result.strip() if result else default


def find(element, path: str):
    parts = path.split("/")
    current = element
    for part in parts:
        current = current.find(tag(part))
        if current is None:
            return None
    return current


def findall(element, path: str) -> list:
    parts = path.split("/")
    current = element
    for part in parts[:-1]:
        current = current.find(tag(part))
        if current is None:
            return []
    return current.findall(tag(parts[-1]))


def clean_html(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_datetime(text: str) -> datetime | None:
    if not text:
        return None
    for fmt in [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
        "%Y-%m-%d%z",
    ]:
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_bool(text: str) -> bool | None:
    if not text:
        return None
    return text.lower() == "true"


def parse_xml(filepath: str) -> etree._Element:
    return etree.parse(filepath).getroot()
