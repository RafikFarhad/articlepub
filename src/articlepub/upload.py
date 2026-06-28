from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
import mimetypes
import re
from typing import Callable
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .models import CalibreConfig


class UploadError(RuntimeError):
    pass


ProgressLog = Callable[[str, str], None]


class CalibreWebUploader:
    def __init__(
        self,
        config: CalibreConfig,
        timeout: int = 60,
        log: Callable[[str], None] | None = None,
        progress: ProgressLog | None = None,
    ) -> None:
        self.config = config
        self.timeout = timeout
        self.opener = build_opener(HTTPCookieProcessor())
        self.log = log or (lambda _message: None)
        self.progress = progress or (lambda _level, _message: None)

    def upload(self, epub_path: Path) -> str:
        return self.upload_result(epub_path).response_text

    def upload_result(self, epub_path: Path) -> "UploadResult":
        if not epub_path.exists():
            raise UploadError(f"EPUB does not exist: {epub_path}")
        if self.config.username and self.config.password:
            self._login()
            self._success("Login succeeded")
        else:
            self._info("Login skipped (anonymous mode)")
        upload_form = self._get_upload_form()
        response_text = self._upload_file(epub_path, upload_form)
        result = _upload_result(response_text, self.config.base_url)
        self._success("Book uploaded")
        if result.book_url:
            self._info(f"Book: {result.book_url}")
        else:
            self.log("calibre upload: response did not include a book URL")
        if self.config.shelf_names:
            self._add_to_shelves(result, self.config.shelf_names)
        else:
            self.log("calibre shelf: skipped; no shelf requested")
        return result

    def _login(self) -> None:
        login_url = urljoin(_base(self.config.base_url), "login")
        self.log("calibre login: fetching login form")
        login_page = self._read_text(Request(login_url, method="GET"), "login form")
        login_form = _find_login_form(login_page.text)
        data = dict(login_form.fields) if login_form else {}
        data.update({"username": self.config.username, "password": self.config.password})
        if "remember_me" in data and not data["remember_me"]:
            data["remember_me"] = "on"
        self.log("calibre login: posting credentials")
        request = Request(
            _form_url(login_page.url, login_form, login_url),
            data=urlencode(data).encode("utf-8"),
            headers={"content-type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        response = self._read_text(request, "login")
        if _find_login_form(response.text):
            raise UploadError("Calibre-Web login did not complete; check username/password and CSRF settings")
        self.log("calibre login: authenticated session established")

    def _get_upload_form(self) -> "_ResolvedUploadForm":
        self.log("calibre upload: fetching upload form")
        response = self._read_text(Request(_base(self.config.base_url), method="GET"), "upload form")
        upload_form = _find_upload_form(response.text)
        if not upload_form:
            if self.config.username and self.config.password:
                raise UploadError("Calibre-Web upload form was not available after login; check upload permission")
            raise UploadError("Calibre-Web upload form was not available; anonymous upload is disabled or lacks upload permission")
        return _ResolvedUploadForm(
            url=_form_url(response.url, upload_form, urljoin(_base(self.config.base_url), "upload")),
            csrf_token=upload_form.fields.get("csrf_token"),
        )

    def _upload_file(self, epub_path: Path, upload_form: "_ResolvedUploadForm") -> str:
        self.log(f"calibre upload: posting {epub_path.name}")
        boundary = "----articlepub-" + uuid.uuid4().hex
        body = _multipart_body(boundary, epub_path, csrf_token=upload_form.csrf_token)
        headers = {
            "content-type": f"multipart/form-data; boundary={boundary}",
            "content-length": str(len(body)),
        }
        if self.config.api_key:
            headers["authorization"] = f"Bearer {self.config.api_key}"
            headers["x-api-key"] = self.config.api_key
        request = Request(upload_form.url, data=body, headers=headers, method="POST")
        text = self._read_text(request, "upload").text
        self.log("calibre upload: upload accepted")
        return text

    def _add_to_shelves(self, result: "UploadResult", shelf_names: list[str]) -> None:
        if result.book_id is None:
            message = "Calibre-Web upload response did not include a book id; cannot add shelves"
            result.shelf_errors.append(message)
            self._warning(f"Shelf update failed: {message}")
            return

        detail_url = urljoin(_base(self.config.base_url), f"book/{result.book_id}")
        self._info("Fetching shelves")
        self.log(f"calibre shelf: fetching book detail for book {result.book_id}")
        try:
            detail = self._read_text(Request(detail_url, method="GET"), "book detail")
        except UploadError as exc:
            message = str(exc)
            result.shelf_errors.append(message)
            self._warning(f"Shelf update failed: {message}")
            return
        csrf_token = _find_csrf_token(detail.text)
        shelf_links = _find_shelf_links(detail.text)
        if shelf_links:
            available = ", ".join(f"{link.label} ({link.action})" for link in shelf_links)
            self.log(f"calibre shelf: exposed shelf actions: {available}")
        if not shelf_links:
            message = _missing_shelf_actions_message(detail.text, bool(self.config.username and self.config.password))
            result.shelf_errors.append(message)
            self._warning(f"Shelf update failed: {message}")
            return

        for shelf_name in shelf_names:
            present_link = _match_shelf_link(shelf_name, shelf_links, action="remove", required=False)
            if present_link:
                result.shelves_present.append(present_link.label)
                self.log(f"calibre shelf: already on shelf {present_link.label}")
                self._info(f"Already on shelf: {present_link.label}")
                continue

            try:
                shelf_link = _match_shelf_link(shelf_name, shelf_links, action="add")
            except UploadError as exc:
                message = str(exc)
                result.shelf_errors.append(message)
                self._warning(f"Shelf update failed: {message}")
                continue
            data = {}
            if csrf_token is not None:
                data["csrf_token"] = csrf_token
            request = Request(
                urljoin(detail.url, shelf_link.url),
                data=urlencode(data).encode("utf-8"),
                headers={
                    "content-type": "application/x-www-form-urlencoded",
                    "x-requested-with": "XMLHttpRequest",
                },
                method="POST",
            )
            try:
                self.log(f"calibre shelf: adding to shelf {shelf_link.name}")
                self._read_text(request, f"add to shelf {shelf_link.name}")
                result.shelves_added.append(shelf_link.label)
                self._success(f"Added to shelf: {shelf_link.label}")
            except UploadError as exc:
                message = str(exc)
                result.shelf_errors.append(message)
                self._warning(f"Shelf update failed: {message}")

    def _info(self, message: str) -> None:
        self.progress("info", message)

    def _success(self, message: str) -> None:
        self.progress("success", message)

    def _warning(self, message: str) -> None:
        self.progress("warning", message)

    def _read_text(self, request: Request, action: str) -> "_TextResponse":
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
                status = getattr(response, "status", 200)
                if status >= 400:
                    raise UploadError(_http_error_message(action, status, getattr(response, "reason", ""), text))
                get_url = getattr(response, "geturl", None)
                return _TextResponse(text=text, url=get_url() if get_url else request.full_url)
        except HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise UploadError(_http_error_message(action, exc.code, exc.reason, text)) from exc


def _multipart_body(boundary: str, epub_path: Path, csrf_token: str | None = None) -> bytes:
    filename = epub_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/epub+zip"
    chunks = []
    if csrf_token is not None:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                b'Content-Disposition: form-data; name="csrf_token"\r\n\r\n',
                csrf_token.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="btn-upload"; filename="{filename}"\r\n'.encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            epub_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks)


def _base(base_url: str) -> str:
    return base_url.rstrip("/") + "/"


def _upload_result(response_text: str, base_url: str) -> "UploadResult":
    location = _upload_location(response_text)
    book_id = _book_id(location)
    book_url = urljoin(_base(base_url), f"book/{book_id}") if book_id is not None else None
    return UploadResult(response_text=response_text, location=location, book_id=book_id, book_url=book_url)


def _upload_location(response_text: str) -> str | None:
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    location = data.get("location")
    return location if isinstance(location, str) else None


def _book_id(location: str | None) -> int | None:
    if not location:
        return None
    match = re.search(r"(?:^|/)(?:admin/)?book/(\d+)(?:[/?#]|$)", location)
    return int(match.group(1)) if match else None


def _form_url(page_url: str, form: "_ParsedForm | None", fallback: str) -> str:
    if form and form.action is not None:
        return urljoin(page_url, form.action)
    return fallback


def _find_upload_form(html: str) -> "_ParsedForm | None":
    for form in _parse_forms(html):
        if "btn-upload" in form.file_fields or form.form_id == "form-upload":
            return form
    return None


def _find_login_form(html: str) -> "_ParsedForm | None":
    for form in _parse_forms(html):
        if "username" in form.fields and "password" in form.fields:
            return form
    return None


def _find_csrf_token(html: str) -> str | None:
    for form in _parse_forms(html):
        token = form.fields.get("csrf_token")
        if token:
            return token
    return None


def _find_shelf_links(html: str) -> list["_ShelfLink"]:
    parser = _ShelfLinkParser()
    parser.feed(html)
    return parser.links


def _match_shelf_link(
    name: str,
    links: list["_ShelfLink"],
    action: str | None = None,
    required: bool = True,
) -> "_ShelfLink | None":
    candidates = [link for link in links if action is None or link.action == action]
    requested_label = _clean_text(name)
    exact = [link for link in candidates if link.label.casefold() == requested_label.casefold()]
    if len(exact) == 1:
        return exact[0]
    normalized = [link for link in candidates if link.name.casefold() == _shelf_name(requested_label).casefold()]
    if len(normalized) == 1:
        return normalized[0]
    if len(normalized) > 1:
        choices = ", ".join(link.label for link in normalized)
        raise UploadError(f"Calibre-Web shelf name is ambiguous: {name}. Use one of: {choices}")
    if not required:
        return None
    available = ", ".join(link.label for link in links) or "none"
    raise UploadError(f"Calibre-Web shelf not found or unavailable: {name}. Available shelves: {available}")


def _parse_forms(html: str) -> list["_ParsedForm"]:
    parser = _FormParser()
    parser.feed(html)
    return parser.forms


def _http_error_message(action: str, status: int, reason: str, body: str) -> str:
    detail = body.strip()
    suffix = f": {reason}" if reason else ""
    if detail:
        suffix += f": {detail}"
    return f"Calibre-Web {action} failed with status {status}{suffix}"


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _shelf_name(label: str) -> str:
    return re.sub(r"\s*\(Public\)$", "", _clean_text(label)).strip()


def _missing_shelf_actions_message(html: str, login_attempted: bool) -> str:
    if login_attempted and _find_login_form(html):
        return "Calibre-Web returned an anonymous book page after login; login cookie was not accepted"
    if login_attempted:
        return "Calibre-Web did not expose shelf actions for this book; confirm this user can see and edit the requested shelf"
    return "Calibre-Web did not expose shelf actions for this book; shelf changes require login or shelf permissions"


@dataclass(slots=True)
class UploadResult:
    response_text: str
    location: str | None = None
    book_id: int | None = None
    book_url: str | None = None
    shelves_added: list[str] = field(default_factory=list)
    shelves_present: list[str] = field(default_factory=list)
    shelf_errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _TextResponse:
    text: str
    url: str


@dataclass(slots=True)
class _ResolvedUploadForm:
    url: str
    csrf_token: str | None


@dataclass(slots=True)
class _ParsedForm:
    action: str | None
    form_id: str | None
    fields: dict[str, str] = field(default_factory=dict)
    file_fields: set[str] = field(default_factory=set)


@dataclass(slots=True)
class _ShelfLink:
    label: str
    name: str
    url: str
    action: str


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[_ParsedForm] = []
        self._current: _ParsedForm | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "form":
            self._current = _ParsedForm(action=attr.get("action"), form_id=attr.get("id"))
            return
        if tag != "input" or self._current is None:
            return
        name = attr.get("name")
        if not name:
            return
        input_type = (attr.get("type") or "").casefold()
        if input_type == "file":
            self._current.file_fields.add(name)
        else:
            self._current.fields[name] = attr.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._current is not None:
            self.forms.append(self._current)
            self._current = None


class _ShelfLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[_ShelfLink] = []
        self._href: str | None = None
        self._action: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        action = attr.get("data-shelf-action")
        if tag == "a" and action in {"add", "remove"} and attr.get("data-href"):
            self._href = attr["data-href"]
            self._action = action
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            label = _clean_text("".join(self._text))
            if label:
                self.links.append(
                    _ShelfLink(label=label, name=_shelf_name(label), url=self._href, action=self._action or "add")
                )
            self._href = None
            self._action = None
            self._text = []
