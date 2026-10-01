"""Tests for chunked, resumable uploads and streamed downloads on sandbox files."""

import base64
import io
import json
import os

import httpx
import pytest

from neevai.errors import InternalServerError, NeevAIError
from neevai.runtime.connection import AsyncSandboxConnection, SandboxConnection

MIB = 1 << 20
CONNECT_URL = "https://sbx.example.com"


class FakeSandbox:
    """A sandbox runtime that speaks the resumable-upload protocol, with injectable faults."""

    def __init__(self, *, uploads_supported: bool = True):
        self.uploads_supported = uploads_supported
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.bodies: dict[str, bytes] = {}
        self.files: dict[str, bytes] = {}
        self.staged: dict[str, bytearray] = {}
        self.lengths: dict[str, int] = {}
        self.targets: dict[str, str] = {}
        # Fault scripts, consumed in order of PATCH calls (1-based).
        self.drop_after_accept: set[int] = set()
        self.conflict_on: set[int] = set()
        self.ignore_on: set[int] = set()
        self.fail_commit = False
        # Drop a committed upload, as the real runtime does, so a later HEAD is a 404.
        self.forget_on_commit = False
        self.transient_500_on: set[int] = set()
        self.patches = 0
        self.read_payload = b""
        self.read_fails_midway = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        headers = {k.lower(): v for k, v in request.headers.items()}
        path = request.url.path
        self.requests.append((request.method, path, headers))
        self.bodies[path] = request.content
        if path == "/v1/files/write":
            self.files[request.url.params["path"]] = request.content
            return httpx.Response(200, json={"bytes_written": len(request.content)})
        if path == "/v1/files/read":
            if self.read_fails_midway:
                return httpx.Response(200, stream=_BrokenStream(self.read_payload[:10]))
            return httpx.Response(200, content=self.read_payload)
        if path == "/v1/files/uploads" and request.method == "POST":
            if not self.uploads_supported:
                return httpx.Response(404, text="404 page not found")
            meta = dict(pair.split(" ") for pair in headers["upload-metadata"].split(","))
            upload_id = f"u{len(self.lengths) + 1}"
            self.lengths[upload_id] = int(headers["upload-length"])
            self.staged[upload_id] = bytearray()
            self.targets[upload_id] = base64.b64decode(meta["path"]).decode()
            return httpx.Response(201, headers={"Location": f"/v1/files/uploads/{upload_id}"})
        upload_id = path.rsplit("/", 1)[-1]
        if upload_id not in self.staged:
            return httpx.Response(404, json={"reason_code": "not_found", "message": "no upload"})
        staged = self.staged[upload_id]
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Upload-Offset": str(len(staged))})
        if request.method == "DELETE":
            del self.staged[upload_id]
            return httpx.Response(204)
        # PATCH
        self.patches += 1
        if self.patches in self.conflict_on or int(headers["upload-offset"]) != len(staged):
            return httpx.Response(409)
        if self.patches in self.transient_500_on:
            return httpx.Response(500, text="upstream hiccup")
        if self.patches in self.ignore_on:
            return httpx.Response(204, headers={"Upload-Offset": str(len(staged))})
        staged.extend(request.content)
        if len(staged) == self.lengths[upload_id]:
            if self.fail_commit:
                del self.staged[upload_id]
                return httpx.Response(
                    500, json={"reason_code": "internal", "message": "could not write file"}
                )
            self.files[self.targets[upload_id]] = bytes(staged)
            if self.forget_on_commit:
                del self.staged[upload_id]
        if self.patches in self.drop_after_accept:
            raise httpx.ConnectError("connection dropped", request=request)
        return httpx.Response(204, headers={"Upload-Offset": str(len(staged))})

    def calls(self) -> list[tuple[str, str]]:
        return [(method, path) for method, path, _ in self.requests]


class _BrokenStream(httpx.SyncByteStream, httpx.AsyncByteStream):
    """A response body that fails after its first bytes."""

    def __init__(self, first: bytes):
        self.first = first

    def __iter__(self):
        yield self.first
        raise httpx.ReadError("connection reset")

    async def __aiter__(self):
        yield self.first
        raise httpx.ReadError("connection reset")


def _conn(fake: FakeSandbox) -> SandboxConnection:
    return SandboxConnection(
        connect_url=CONNECT_URL,
        api_key="test",
        client=httpx.Client(transport=httpx.MockTransport(fake.handler)),
    )


def _aconn(fake: FakeSandbox) -> AsyncSandboxConnection:
    return AsyncSandboxConnection(
        connect_url=CONNECT_URL,
        api_key="test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)),
    )


def _payload(size: int) -> bytes:
    return bytes(i % 251 for i in range(size))


def test_upload_sends_chunks_with_tus_headers_and_reports_progress():
    fake = FakeSandbox()
    data = _payload(2 * MIB + 5)
    progress: list[tuple[int, int]] = []
    result = _conn(fake).files.upload(
        "big.bin", data, cwd="sub", on_progress=lambda s, t: progress.append((s, t))
    )

    assert result == {"bytes_written": len(data)}
    assert fake.files["big.bin"] == data
    assert fake.calls() == [
        ("POST", "/v1/files/uploads"),
        ("PATCH", "/v1/files/uploads/u1"),
        ("PATCH", "/v1/files/uploads/u1"),
        ("PATCH", "/v1/files/uploads/u1"),
    ]
    create = fake.requests[0][2]
    assert create["tus-resumable"] == "1.0.0"
    assert create["upload-length"] == str(len(data))
    assert create["upload-metadata"] == (
        f"path {base64.b64encode(b'big.bin').decode()},cwd {base64.b64encode(b'sub').decode()}"
    )
    assert create["authorization"] == "Bearer test"
    patches = [h for m, _, h in fake.requests if m == "PATCH"]
    assert [h["upload-offset"] for h in patches] == ["0", str(MIB), str(2 * MIB)]
    assert all(h["content-type"] == "application/offset+octet-stream" for h in patches)
    assert all(h["tus-resumable"] == "1.0.0" for h in patches)
    assert progress == [(MIB, len(data)), (2 * MIB, len(data)), (len(data), len(data))]


def test_upload_streams_a_seekable_file_object_from_its_position():
    fake = FakeSandbox()
    data = _payload(MIB + 3)
    handle = io.BytesIO(b"skip" + data)
    handle.seek(4)
    _conn(fake).files.upload("f.bin", handle)
    assert fake.files["f.bin"] == data


def test_upload_resumes_after_a_dropped_chunk_via_head():
    fake = FakeSandbox()
    fake.drop_after_accept = {1}
    data = _payload(2 * MIB)
    _conn(fake).files.upload("d.bin", data)
    assert fake.files["d.bin"] == data
    assert fake.calls() == [
        ("POST", "/v1/files/uploads"),
        ("PATCH", "/v1/files/uploads/u1"),
        ("HEAD", "/v1/files/uploads/u1"),
        ("PATCH", "/v1/files/uploads/u1"),
    ]
    assert [h["upload-offset"] for m, _, h in fake.requests if m == "PATCH"] == ["0", str(MIB)]


def test_upload_heads_and_continues_after_a_409():
    fake = FakeSandbox()
    fake.conflict_on = {2}
    data = _payload(2 * MIB)
    _conn(fake).files.upload("c.bin", data)
    assert fake.files["c.bin"] == data
    assert fake.calls()[1:] == [
        ("PATCH", "/v1/files/uploads/u1"),
        ("PATCH", "/v1/files/uploads/u1"),
        ("HEAD", "/v1/files/uploads/u1"),
        ("PATCH", "/v1/files/uploads/u1"),
    ]


def test_upload_gives_up_after_repeated_no_progress_and_discards_it():
    fake = FakeSandbox()
    fake.conflict_on = set(range(1, 50))
    with pytest.raises(NeevAIError):
        _conn(fake).files.upload("x.bin", _payload(MIB + 1))
    assert fake.calls()[-1] == ("DELETE", "/v1/files/uploads/u1")
    # Five attempts in all, matching the JS SDK.
    assert fake.patches == 5
    assert "x.bin" not in fake.files


def test_upload_chunk_that_does_not_advance_ends_with_an_error():
    fake = FakeSandbox()
    fake.ignore_on = {1}
    with pytest.raises(NeevAIError, match="stalled at byte 0"):
        _conn(fake).files.upload("s.bin", _payload(MIB + 1))
    assert fake.calls()[-1] == ("DELETE", "/v1/files/uploads/u1")


def test_upload_raises_when_the_file_cannot_be_written():
    fake = FakeSandbox()
    fake.fail_commit = True
    with pytest.raises(InternalServerError) as exc:
        _conn(fake).files.upload("w.bin", _payload(MIB + 1))
    assert exc.value.code == "internal"
    assert fake.calls()[-1] == ("DELETE", "/v1/files/uploads/u1")


def test_upload_falls_back_to_one_write_without_upload_endpoints():
    fake = FakeSandbox(uploads_supported=False)
    data = _payload(1000)
    assert _conn(fake).files.upload("old.bin", data) == {"bytes_written": 1000}
    assert fake.calls() == [("POST", "/v1/files/uploads"), ("POST", "/v1/files/write")]
    assert fake.files["old.bin"] == data


def test_upload_of_empty_data_is_a_plain_write():
    fake = FakeSandbox()
    assert _conn(fake).files.upload("empty.txt", b"") == {"bytes_written": 0}
    assert fake.calls() == [("POST", "/v1/files/write")]


def test_write_routes_large_content_through_upload():
    fake = FakeSandbox()
    files = _conn(fake).files
    files.write("small.bin", _payload(MIB))
    files.write("large.bin", _payload(MIB + 1))
    assert fake.calls() == [
        ("POST", "/v1/files/write"),
        ("POST", "/v1/files/uploads"),
        ("PATCH", "/v1/files/uploads/u1"),
        ("PATCH", "/v1/files/uploads/u1"),
    ]
    assert fake.files["large.bin"] == _payload(MIB + 1)


@pytest.mark.parametrize("chunk_size", [(64 << 10) - 1, MIB + 1, 0, True, 1.5])
def test_upload_rejects_chunk_size_outside_range(chunk_size):
    fake = FakeSandbox()
    with pytest.raises(NeevAIError, match="chunk_size"):
        _conn(fake).files.upload("a.bin", b"abc", chunk_size=chunk_size)
    assert fake.requests == []


def test_upload_honours_a_custom_chunk_size():
    fake = FakeSandbox()
    _conn(fake).files.upload("a.bin", _payload(MIB + 10), chunk_size=MIB // 2)
    patches = [h["upload-offset"] for m, _, h in fake.requests if m == "PATCH"]
    assert patches == ["0", str(MIB // 2), str(MIB)]


def test_upload_rejects_a_non_seekable_stream():
    class Pipe(io.RawIOBase):
        def readable(self):
            return True

        def seekable(self):
            return False

    with pytest.raises(NeevAIError, match="seekable"):
        _conn(FakeSandbox()).files.upload("p.bin", Pipe())


def test_upload_file_and_download_file_round_trip(tmp_path):
    fake = FakeSandbox()
    data = _payload(MIB + 17)
    local = tmp_path / "in.bin"
    local.write_bytes(data)
    files = _conn(fake).files
    assert files.upload_file(local, "remote.bin") == {"bytes_written": len(data)}
    assert fake.files["remote.bin"] == data

    fake.read_payload = data
    out = tmp_path / "out.bin"
    assert files.download_file("remote.bin", str(out)) == {"bytes_written": len(data)}
    assert out.read_bytes() == data
    umask = os.umask(0)
    os.umask(umask)
    assert os.stat(out).st_mode & 0o777 == 0o666 & ~umask
    read = next(h for m, p, h in fake.requests if p == "/v1/files/read")
    assert read["accept"] == "application/octet-stream"
    assert json.loads(fake.bodies["/v1/files/read"]) == {"path": "remote.bin", "cwd": None}
    assert sorted(os.listdir(tmp_path)) == ["in.bin", "out.bin"]


def test_download_file_leaves_no_partial_file_on_failure(tmp_path):
    fake = FakeSandbox()
    fake.read_payload = _payload(100)
    fake.read_fails_midway = True
    out = tmp_path / "out.bin"
    out.write_bytes(b"previous")
    with pytest.raises(NeevAIError):
        _conn(fake).files.download_file("remote.bin", out)
    assert out.read_bytes() == b"previous"
    assert os.listdir(tmp_path) == ["out.bin"]


@pytest.mark.asyncio
async def test_async_upload_resumes_and_reports_progress():
    fake = FakeSandbox()
    fake.drop_after_accept = {1}
    data = _payload(2 * MIB + 1)
    progress: list[int] = []
    result = await _aconn(fake).files.upload(
        "a.bin", data, on_progress=lambda s, t: progress.append(s)
    )
    assert result == {"bytes_written": len(data)}
    assert fake.files["a.bin"] == data
    assert ("HEAD", "/v1/files/uploads/u1") in fake.calls()
    assert progress == [MIB, 2 * MIB, len(data)]


@pytest.mark.asyncio
async def test_async_upload_failure_discards_and_fallback_writes():
    fake = FakeSandbox()
    fake.fail_commit = True
    with pytest.raises(InternalServerError):
        await _aconn(fake).files.upload("w.bin", _payload(MIB + 1))
    assert fake.calls()[-1] == ("DELETE", "/v1/files/uploads/u1")

    old = FakeSandbox(uploads_supported=False)
    assert await _aconn(old).files.write("big.bin", _payload(MIB + 1)) == {"bytes_written": MIB + 1}
    assert old.calls() == [("POST", "/v1/files/uploads"), ("POST", "/v1/files/write")]


@pytest.mark.asyncio
async def test_async_upload_file_and_download_file(tmp_path):
    fake = FakeSandbox()
    data = _payload(MIB + 9)
    local = tmp_path / "in.bin"
    local.write_bytes(data)
    files = _aconn(fake).files
    await files.upload_file(local, "r.bin", chunk_size=MIB)
    assert fake.files["r.bin"] == data

    fake.read_payload = data
    assert await files.download_file("r.bin", tmp_path / "out.bin") == {"bytes_written": len(data)}
    assert (tmp_path / "out.bin").read_bytes() == data

    fake.read_fails_midway = True
    with pytest.raises(NeevAIError):
        await files.download_file("r.bin", tmp_path / "broken.bin")
    assert not (tmp_path / "broken.bin").exists()
    assert sorted(os.listdir(tmp_path)) == ["in.bin", "out.bin"]


def test_dropped_final_chunk_with_head_404_counts_as_written():
    fake = FakeSandbox()
    fake.forget_on_commit = True
    fake.drop_after_accept = {2}
    data = _payload(MIB + 10)
    progress: list[tuple[int, int]] = []
    result = _conn(fake).files.upload(
        "f.bin", data, on_progress=lambda s, t: progress.append((s, t))
    )
    assert result == {"bytes_written": len(data)}
    assert fake.files["f.bin"] == data
    assert [m for m, _ in fake.calls()] == ["POST", "PATCH", "PATCH", "HEAD"]
    assert progress[-1] == (len(data), len(data))


@pytest.mark.asyncio
async def test_async_dropped_final_chunk_with_head_404_counts_as_written():
    fake = FakeSandbox()
    fake.forget_on_commit = True
    fake.drop_after_accept = {1}
    data = _payload(10)
    assert await _aconn(fake).files.upload("f.bin", data) == {"bytes_written": 10}
    assert [m for m, _ in fake.calls()] == ["POST", "PATCH", "HEAD"]


def test_head_404_after_a_dropped_middle_chunk_raises_the_original_error():
    fake = FakeSandbox()
    fake.drop_after_accept = {1}
    original_handler = fake.handler

    def head_404(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            fake.requests.append((request.method, request.url.path, {}))
            return httpx.Response(404, json={"reason_code": "not_found", "message": "gone"})
        return original_handler(request)

    conn = SandboxConnection(
        connect_url=CONNECT_URL,
        api_key="test",
        client=httpx.Client(transport=httpx.MockTransport(head_404)),
    )
    with pytest.raises(NeevAIError, match="connection dropped|reach"):
        conn.files.upload("f.bin", _payload(MIB + 10))
    assert [m for m, _ in fake.calls()][-2:] == ["HEAD", "DELETE"]


def test_transient_500_on_a_middle_chunk_is_retried():
    fake = FakeSandbox()
    fake.transient_500_on = {1}
    data = _payload(MIB + 10)
    assert _conn(fake).files.upload("f.bin", data) == {"bytes_written": len(data)}
    assert [m for m, _ in fake.calls()] == ["POST", "PATCH", "HEAD", "PATCH", "PATCH"]


def test_stops_after_five_attempts_without_progress():
    fake = FakeSandbox()
    fake.transient_500_on = set(range(1, 20))
    with pytest.raises(InternalServerError):
        _conn(fake).files.upload("f.bin", _payload(10))
    assert sum(1 for m, _ in fake.calls() if m == "PATCH") == 5
