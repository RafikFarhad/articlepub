from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .models import CalibreConfig


class UploadError(RuntimeError):
    pass


class CalibreWebUploader:
    def __init__(self, config: CalibreConfig, timeout: int = 60) -> None:
        self.config = config
        self.timeout = timeout
        self.opener = build_opener(HTTPCookieProcessor())

    def upload(self, epub_path: Path) -> str:
        if not epub_path.exists():
            raise UploadError(f"EPUB does not exist: {epub_path}")
        if self.config.username and self.config.password:
            self._login()
        return self._upload_file(epub_path)

    def _login(self) -> None:
        data = urlencode({"username": self.config.username, "password": self.config.password}).encode("utf-8")
        request = Request(
            urljoin(_base(self.config.base_url), "login"),
            data=data,
            headers={"content-type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with self.opener.open(request, timeout=self.timeout) as response:
            if response.status >= 400:
                raise UploadError(f"Calibre-Web login failed with status {response.status}")

    def _upload_file(self, epub_path: Path) -> str:
        boundary = "----articlepub-" + uuid.uuid4().hex
        body = _multipart_body(boundary, epub_path)
        headers = {
            "content-type": f"multipart/form-data; boundary={boundary}",
            "content-length": str(len(body)),
        }
        if self.config.api_key:
            headers["authorization"] = f"Bearer {self.config.api_key}"
            headers["x-api-key"] = self.config.api_key
        request = Request(urljoin(_base(self.config.base_url), "upload"), data=body, headers=headers, method="POST")
        with self.opener.open(request, timeout=self.timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            if response.status >= 400:
                raise UploadError(f"Calibre-Web upload failed with status {response.status}: {text}")
            return text


def _multipart_body(boundary: str, epub_path: Path) -> bytes:
    filename = epub_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/epub+zip"
    chunks = [
        f"--{boundary}\r\n".encode("utf-8"),
        f'Content-Disposition: form-data; name="btn-upload"; filename="{filename}"\r\n'.encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        epub_path.read_bytes(),
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(chunks)


def _base(base_url: str) -> str:
    return base_url.rstrip("/") + "/"
