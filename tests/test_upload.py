from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from articlepub.models import CalibreConfig
from articlepub.upload import CalibreWebUploader


class FakeUploadResponse:
    def __init__(self, status: int = 200, body: str = "ok") -> None:
        self.status = status
        self.body = body

    def __enter__(self) -> "FakeUploadResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.body.encode("utf-8")


class FakeOpener:
    def __init__(self) -> None:
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        return FakeUploadResponse()


class UploadTest(TestCase):
    def test_login_then_uploads_epub_multipart(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            path.write_bytes(b"epub")
            uploader = CalibreWebUploader(
                CalibreConfig(
                    base_url="https://calibre.example.com",
                    username="user",
                    password="pass",
                    api_key="api-token",
                )
            )
            opener = FakeOpener()
            uploader.opener = opener

            response = uploader.upload(path)

        self.assertEqual(response, "ok")
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(opener.requests[0].full_url, "https://calibre.example.com/login")
        self.assertEqual(opener.requests[1].full_url, "https://calibre.example.com/upload")
        self.assertIn(b'name="btn-upload"; filename="book.epub"', opener.requests[1].data)
        self.assertEqual(opener.requests[1].headers["Authorization"], "Bearer api-token")

    def test_upload_supports_calibre_web_base_path_without_login(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            path.write_bytes(b"epub")
            uploader = CalibreWebUploader(CalibreConfig(base_url="http://calibre.example.test/calibre-web/"))
            opener = FakeOpener()
            uploader.opener = opener

            response = uploader.upload(path)

        self.assertEqual(response, "ok")
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(opener.requests[0].full_url, "http://calibre.example.test/calibre-web/upload")
        self.assertIn(b'name="btn-upload"; filename="book.epub"', opener.requests[0].data)
