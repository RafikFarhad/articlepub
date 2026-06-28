from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from urllib.error import HTTPError

from articlepub.models import CalibreConfig
from articlepub.upload import CalibreWebUploader, UploadError


LOGIN_FORM = """
<form method="POST">
  <input type="hidden" name="csrf_token" value="login-csrf">
  <input type="hidden" name="next" value="">
  <input type="text" name="username">
  <input type="password" name="password">
  <input type="checkbox" name="remember_me" checked>
</form>
"""

UPLOAD_FORM = """
<form id="form-upload" action="/calibre-web/upload" method="post" enctype="multipart/form-data">
  <input type="hidden" name="csrf_token" value="upload-csrf">
  <input id="btn-upload" name="btn-upload" type="file" multiple>
</form>
"""

DETAIL_PAGE = """
<form id="have_read_form">
  <input type="hidden" name="csrf_token" value="detail-csrf">
</form>
<ul id="add-to-shelves">
  <li>
    <a data-href="/calibre-web/shelf/add/7/35" data-shelf-action="add">Long Reads</a>
  </li>
</ul>
"""


class FakeUploadResponse:
    def __init__(self, status: int = 200, body: str = "ok", url: str | None = None) -> None:
        self.status = status
        self.body = body
        self.url = url

    def __enter__(self) -> "FakeUploadResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.body.encode("utf-8")

    def geturl(self) -> str:
        return self.url or ""


class FakeOpener:
    def __init__(self, responses=None) -> None:
        self.requests = []
        self.responses = list(responses or [])

    def open(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0) if self.responses else FakeUploadResponse()
        if isinstance(response, BaseException):
            raise response
        if response.url is None:
            response.url = request.full_url
        return response


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
            opener = FakeOpener(
                [
                    FakeUploadResponse(body=LOGIN_FORM, url="https://calibre.example.com/login"),
                    FakeUploadResponse(body="logged in", url="https://calibre.example.com/"),
                    FakeUploadResponse(body=UPLOAD_FORM.replace("/calibre-web/upload", "/upload"),
                                       url="https://calibre.example.com/"),
                    FakeUploadResponse(body="ok", url="https://calibre.example.com/upload"),
                ]
            )
            uploader.opener = opener

            response = uploader.upload(path)

        self.assertEqual(response, "ok")
        self.assertEqual(len(opener.requests), 4)
        self.assertEqual(opener.requests[0].full_url, "https://calibre.example.com/login")
        self.assertEqual(opener.requests[1].full_url, "https://calibre.example.com/login")
        self.assertIn(b"csrf_token=login-csrf", opener.requests[1].data)
        self.assertIn(b"username=user", opener.requests[1].data)
        self.assertIn(b"password=pass", opener.requests[1].data)
        self.assertEqual(opener.requests[2].full_url, "https://calibre.example.com/")
        self.assertEqual(opener.requests[3].full_url, "https://calibre.example.com/upload")
        self.assertIn(b'name="csrf_token"\r\n\r\nupload-csrf', opener.requests[3].data)
        self.assertIn(b'name="btn-upload"; filename="book.epub"', opener.requests[3].data)
        self.assertEqual(opener.requests[3].headers["Authorization"], "Bearer api-token")

    def test_upload_supports_calibre_web_base_path_without_login(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            path.write_bytes(b"epub")
            uploader = CalibreWebUploader(CalibreConfig(base_url="http://calibre.example.test/calibre-web/"))
            opener = FakeOpener(
                [
                    FakeUploadResponse(body=UPLOAD_FORM, url="http://calibre.example.test/calibre-web/"),
                    FakeUploadResponse(body="ok", url="http://calibre.example.test/calibre-web/upload"),
                ]
            )
            uploader.opener = opener

            response = uploader.upload(path)

        self.assertEqual(response, "ok")
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(opener.requests[0].full_url, "http://calibre.example.test/calibre-web/")
        self.assertEqual(opener.requests[1].full_url, "http://calibre.example.test/calibre-web/upload")
        self.assertIn(b'name="csrf_token"\r\n\r\nupload-csrf', opener.requests[1].data)
        self.assertIn(b'name="btn-upload"; filename="book.epub"', opener.requests[1].data)

    def test_anonymous_upload_fails_before_post_when_form_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            path.write_bytes(b"epub")
            uploader = CalibreWebUploader(CalibreConfig(base_url="http://calibre.example.test/calibre-web/"))
            opener = FakeOpener([FakeUploadResponse(body="<form><input name='username'></form>")])
            uploader.opener = opener

            with self.assertRaisesRegex(UploadError, "anonymous upload is disabled"):
                uploader.upload(path)

        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(opener.requests[0].full_url, "http://calibre.example.test/calibre-web/")

    def test_http_error_includes_response_body(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            path.write_bytes(b"epub")
            uploader = CalibreWebUploader(CalibreConfig(base_url="http://calibre.example.test/calibre-web/"))
            opener = FakeOpener(
                [
                    FakeUploadResponse(body=UPLOAD_FORM, url="http://calibre.example.test/calibre-web/"),
                    HTTPError(
                        "http://calibre.example.test/calibre-web/upload",
                        400,
                        "BAD REQUEST",
                        {},
                        BytesIO(b"CSRF token is missing"),
                    ),
                ]
            )
            uploader.opener = opener

            with self.assertRaisesRegex(UploadError, "CSRF token is missing"):
                uploader.upload(path)

    def test_upload_result_can_add_book_to_requested_shelf(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            path.write_bytes(b"epub")
            uploader = CalibreWebUploader(
                CalibreConfig(base_url="http://calibre.example.test/calibre-web/", shelf_names=["Long Reads"])
            )
            opener = FakeOpener(
                [
                    FakeUploadResponse(body=UPLOAD_FORM, url="http://calibre.example.test/calibre-web/"),
                    FakeUploadResponse(body='{"location": "/calibre-web/book/35"}',
                                       url="http://calibre.example.test/calibre-web/upload"),
                    FakeUploadResponse(body=DETAIL_PAGE, url="http://calibre.example.test/calibre-web/book/35"),
                    FakeUploadResponse(status=204, body="", url="http://calibre.example.test/calibre-web/shelf/add/7/35"),
                ]
            )
            uploader.opener = opener

            result = uploader.upload_result(path)

        self.assertEqual(result.book_id, 35)
        self.assertEqual(result.book_url, "http://calibre.example.test/calibre-web/book/35")
        self.assertEqual(result.shelves_added, ["Long Reads"])
        self.assertEqual(len(opener.requests), 4)
        self.assertEqual(opener.requests[2].full_url, "http://calibre.example.test/calibre-web/book/35")
        self.assertEqual(opener.requests[3].full_url, "http://calibre.example.test/calibre-web/shelf/add/7/35")
        self.assertEqual(opener.requests[3].data, b"csrf_token=detail-csrf")

    def test_shelf_failure_keeps_successful_upload_result(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.epub"
            path.write_bytes(b"epub")
            uploader = CalibreWebUploader(
                CalibreConfig(base_url="http://calibre.example.test/calibre-web/", shelf_names=["Story Books"])
            )
            opener = FakeOpener(
                [
                    FakeUploadResponse(body=UPLOAD_FORM, url="http://calibre.example.test/calibre-web/"),
                    FakeUploadResponse(body='{"location": "/calibre-web/book/35"}',
                                       url="http://calibre.example.test/calibre-web/upload"),
                    FakeUploadResponse(body="<html>No shelf actions</html>",
                                       url="http://calibre.example.test/calibre-web/book/35"),
                ]
            )
            uploader.opener = opener

            result = uploader.upload_result(path)

        self.assertEqual(result.book_url, "http://calibre.example.test/calibre-web/book/35")
        self.assertEqual(result.shelves_added, [])
        self.assertEqual(
            result.shelf_errors,
            ["Calibre-Web did not expose shelf actions for this book; shelf changes may require login"],
        )
