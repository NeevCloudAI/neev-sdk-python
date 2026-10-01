"""Chunked, resumable file upload and streamed download over the sandbox runtime.

A file larger than one request body is sent with the tus 1.0.0 resumable-upload
endpoints: create the upload, PATCH it chunk by chunk, and on a dropped or refused
chunk ask the sandbox how much arrived (HEAD) and continue from there.
"""

from __future__ import annotations

import base64
import io
import os
import secrets
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from typing import IO, Any
from urllib.parse import urlsplit

import httpx

from neevai.errors import APIConnectionError, APIError, NeevAIError, NotFoundError
from neevai.transport.runtime import AsyncRuntimeTransport, RuntimeTransport

TUS_VERSION = "1.0.0"
# The largest body the sandbox accepts in one request; bigger writes go through upload.
SINGLE_WRITE_MAX_BYTES = 1 << 20
DEFAULT_CHUNK_SIZE = SINGLE_WRITE_MAX_BYTES
# A chunk is one request, so it can be no larger than a single request body;
# smaller chunks lose less on a flaky link.
MIN_CHUNK_SIZE = 64 << 10
MAX_CHUNK_SIZE = SINGLE_WRITE_MAX_BYTES
# Consecutive chunk attempts that make no progress before the upload gives up.
MAX_STALLED_ATTEMPTS = 5
# Statuses on a chunk that mean "check the offset and try again" rather than fail.
_RETRYABLE_STATUSES = (409, 500, 502, 503, 504)

UploadData = bytes | bytearray | memoryview | str | IO[bytes]
ProgressCallback = Callable[[int, int], None]
WriteResult = dict[str, int]


class _Source:
    """Random-access view over upload data, read one chunk at a time."""

    def __init__(self, data: UploadData):
        if isinstance(data, str):
            data = data.encode("utf-8")
        if isinstance(data, (bytes, bytearray, memoryview)):
            self._buf: memoryview | None = memoryview(data).cast("B")
            self._file: IO[bytes] | None = None
            self._base = 0
            self.length = len(self._buf)
            return
        seekable = getattr(data, "seekable", None)
        if (
            not hasattr(data, "seek")
            or not hasattr(data, "tell")
            or (callable(seekable) and not seekable())
        ):
            raise NeevAIError(
                "upload needs bytes, str, or a seekable binary file object; "
                "read a non-seekable stream into bytes first."
            )
        self._buf = None
        self._file = data
        self._base = data.tell()
        self.length = data.seek(0, io.SEEK_END) - self._base
        data.seek(self._base)

    def read_at(self, offset: int, size: int) -> bytes:
        """Returns exactly ``size`` bytes starting ``offset`` bytes into the data."""
        if self._buf is not None:
            return bytes(self._buf[offset : offset + size])
        assert self._file is not None
        self._file.seek(self._base + offset)
        parts: list[bytes] = []
        remaining = size
        while remaining > 0:
            part = self._file.read(remaining)
            if not part:
                raise NeevAIError(
                    f"upload source ended at byte {offset + size - remaining} of {self.length}; "
                    "it changed while uploading."
                )
            parts.append(part)
            remaining -= len(part)
        return b"".join(parts)


def validate_chunk_size(chunk_size: object) -> int:
    """Returns the chunk size to use, rejecting one outside 64 KiB..1 MiB."""
    if chunk_size is None:
        return DEFAULT_CHUNK_SIZE
    if (
        isinstance(chunk_size, bool)
        or not isinstance(chunk_size, int)
        or not MIN_CHUNK_SIZE <= chunk_size <= MAX_CHUNK_SIZE
    ):
        raise NeevAIError(
            f"chunk_size must be between {MIN_CHUNK_SIZE} and {MAX_CHUNK_SIZE} bytes "
            f"(64 KiB to 1 MiB), got {chunk_size!r}."
        )
    return chunk_size


def _tus_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Headers every resumable-upload request carries, plus ``extra``."""
    headers = {"Tus-Resumable": TUS_VERSION}
    if extra:
        headers.update(extra)
    return headers


def _create_headers(path: str, cwd: str | None, length: int) -> dict[str, str]:
    """Headers for starting an upload of ``length`` bytes to ``path``."""
    meta = [("path", path)] + ([("cwd", cwd)] if cwd else [])
    encoded = ",".join(f"{k} {base64.b64encode(v.encode()).decode()}" for k, v in meta)
    return _tus_headers({"Upload-Length": str(length), "Upload-Metadata": encoded})


def _patch_headers(offset: int) -> dict[str, str]:
    """Headers for a chunk that starts at ``offset``."""
    return _tus_headers(
        {"Content-Type": "application/offset+octet-stream", "Upload-Offset": str(offset)}
    )


def _upload_path(response: httpx.Response) -> str:
    """The upload's path relative to the sandbox, from the create response's Location."""
    location = response.headers.get("Location")
    if not location:
        raise NeevAIError("the sandbox started an upload but did not say where to send it.")
    parts = urlsplit(str(location))
    return str(parts.path) + (f"?{parts.query}" if parts.query else "")


def _offset(response: httpx.Response, length: int) -> int:
    """The Upload-Offset the sandbox reported, checked to lie within the upload."""
    raw = response.headers.get("Upload-Offset")
    try:
        offset = int(raw) if raw is not None else -1
    except ValueError:
        offset = -1
    if not 0 <= offset <= length:
        raise NeevAIError(f"the sandbox reported an invalid upload offset {raw!r}.")
    return offset


def _is_retryable(exc: BaseException, is_last: bool) -> bool:
    """Whether a failed chunk is worth resuming: the connection dropped or the sandbox
    refused the offset or was briefly unavailable. A 500 carrying the sandbox's error
    on the last chunk means the file could not be written, so it is final."""
    if isinstance(exc, APIConnectionError):
        return True
    if not isinstance(exc, APIError) or exc.status_code not in _RETRYABLE_STATUSES:
        return False
    return not (exc.status_code == 500 and is_last and exc.code is not None)


def _is_missing_route(exc: APIError) -> bool:
    """A 404 without the sandbox's error envelope: the runtime has no upload endpoints."""
    return exc.status_code == 404 and exc.code is None


def _stalled_error(offset: int, length: int) -> NeevAIError:
    return NeevAIError(f"upload stalled at byte {offset} of {length}.")


def upload(
    transport: RuntimeTransport,
    write_once: Callable[[str, bytes, str | None], WriteResult],
    path: str,
    data: UploadData,
    chunk_size: int | None,
    cwd: str | None,
    on_progress: ProgressCallback | None,
) -> WriteResult:
    """Uploads ``data`` to ``path`` in chunks, resuming dropped chunks from the sandbox's
    offset. Falls back to ``write_once`` for empty data or a runtime without uploads."""
    size = validate_chunk_size(chunk_size)
    source = _Source(data)
    if source.length == 0:
        return write_once(path, b"", cwd)
    try:
        created = transport.request(
            "POST", "/v1/files/uploads", headers=_create_headers(path, cwd, source.length)
        )
    except APIError as exc:
        if _is_missing_route(exc):
            return write_once(path, source.read_at(0, source.length), cwd)
        raise
    upload_path = _upload_path(created)
    try:
        _send_chunks(transport, upload_path, source, size, on_progress)
    except BaseException:
        # Discard the staged bytes; the original failure is what the caller needs.
        try:
            transport.request("DELETE", upload_path, headers=_tus_headers())
        except Exception:
            pass
        raise
    return {"bytes_written": source.length}


def _send_chunks(
    transport: RuntimeTransport,
    upload_path: str,
    source: _Source,
    chunk_size: int,
    on_progress: ProgressCallback | None,
) -> None:
    """PATCHes every chunk from offset 0, asking the sandbox for its offset after a
    retryable failure and continuing from there."""
    offset, stalled = 0, 0
    while offset < source.length:
        chunk = source.read_at(offset, min(chunk_size, source.length - offset))
        is_last = offset + len(chunk) >= source.length
        try:
            response = transport.request(
                "PATCH", upload_path, headers=_patch_headers(offset), content=chunk
            )
        except Exception as exc:
            if not _is_retryable(exc, is_last):
                raise
            stalled += 1
            if stalled >= MAX_STALLED_ATTEMPTS:
                raise
            try:
                head = transport.request("HEAD", upload_path, headers=_tus_headers())
            except NotFoundError:
                # A final chunk that landed but lost its response leaves no upload to query.
                if not is_last:
                    raise exc from None
                if on_progress is not None:
                    on_progress(source.length, source.length)
                return
            except Exception:
                raise exc from None
            resumed = _offset(head, source.length)
            if resumed > offset:
                stalled = 0
                if on_progress is not None:
                    on_progress(resumed, source.length)
            offset = resumed
            continue
        accepted = _offset(response, source.length)
        if accepted <= offset:
            raise _stalled_error(offset, source.length)
        offset, stalled = accepted, 0
        if on_progress is not None:
            on_progress(offset, source.length)


async def aupload(
    transport: AsyncRuntimeTransport,
    write_once: Callable[[str, bytes, str | None], Awaitable[WriteResult]],
    path: str,
    data: UploadData,
    chunk_size: int | None,
    cwd: str | None,
    on_progress: ProgressCallback | None,
) -> WriteResult:
    """Asynchronous ``upload``: same protocol, resume, and fallback rules."""
    size = validate_chunk_size(chunk_size)
    source = _Source(data)
    if source.length == 0:
        return await write_once(path, b"", cwd)
    try:
        created = await transport.request(
            "POST", "/v1/files/uploads", headers=_create_headers(path, cwd, source.length)
        )
    except APIError as exc:
        if _is_missing_route(exc):
            return await write_once(path, source.read_at(0, source.length), cwd)
        raise
    upload_path = _upload_path(created)
    try:
        await _asend_chunks(transport, upload_path, source, size, on_progress)
    except BaseException:
        # Discard the staged bytes; the original failure is what the caller needs.
        try:
            await transport.request("DELETE", upload_path, headers=_tus_headers())
        except Exception:
            pass
        raise
    return {"bytes_written": source.length}


async def _asend_chunks(
    transport: AsyncRuntimeTransport,
    upload_path: str,
    source: _Source,
    chunk_size: int,
    on_progress: ProgressCallback | None,
) -> None:
    """Asynchronous ``_send_chunks``."""
    offset, stalled = 0, 0
    while offset < source.length:
        chunk = source.read_at(offset, min(chunk_size, source.length - offset))
        is_last = offset + len(chunk) >= source.length
        try:
            response = await transport.request(
                "PATCH", upload_path, headers=_patch_headers(offset), content=chunk
            )
        except Exception as exc:
            if not _is_retryable(exc, is_last):
                raise
            stalled += 1
            if stalled >= MAX_STALLED_ATTEMPTS:
                raise
            try:
                head = await transport.request("HEAD", upload_path, headers=_tus_headers())
            except NotFoundError:
                # A final chunk that landed but lost its response leaves no upload to query.
                if not is_last:
                    raise exc from None
                if on_progress is not None:
                    on_progress(source.length, source.length)
                return
            except Exception:
                raise exc from None
            resumed = _offset(head, source.length)
            if resumed > offset:
                stalled = 0
                if on_progress is not None:
                    on_progress(resumed, source.length)
            offset = resumed
            continue
        accepted = _offset(response, source.length)
        if accepted <= offset:
            raise _stalled_error(offset, source.length)
        offset, stalled = accepted, 0
        if on_progress is not None:
            on_progress(offset, source.length)


def _read_body(path: str, cwd: str | None) -> dict[str, Any]:
    """JSON body for a file read."""
    return {"path": path, "cwd": cwd}


_READ_HEADERS = {"Content-Type": "application/json", "Accept": "application/octet-stream"}


def _open_temp_beside(local_path: str | os.PathLike[str]) -> tuple[IO[bytes], str]:
    """Opens a temporary file in ``local_path``'s directory, so the final rename is atomic."""
    target = os.fspath(local_path)
    directory = os.path.dirname(os.path.abspath(target))
    temp = os.path.join(directory, f".{os.path.basename(target)}.{secrets.token_hex(6)}.part")
    # Mode 0o666 under O_EXCL lets the umask decide permissions, as a plain open() would.
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    return os.fdopen(fd, "wb"), temp


def _finish(handle: IO[bytes], temp: str, local_path: str | os.PathLike[str], ok: bool) -> None:
    """Closes the temp file, then moves it into place on success or removes it on failure."""
    handle.close()
    if ok:
        os.replace(temp, os.fspath(local_path))
    else:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass


def download(
    transport: RuntimeTransport,
    remote_path: str,
    local_path: str | os.PathLike[str],
    cwd: str | None,
) -> int:
    """Streams ``remote_path`` to ``local_path`` and returns the bytes written. The
    file appears only once complete; a failed download leaves nothing behind."""
    chunks: Generator[bytes, None, None] = transport.stream_bytes(
        "POST", "/v1/files/read", headers=_READ_HEADERS, body=_read_body(remote_path, cwd)
    )
    handle, temp = _open_temp_beside(local_path)
    written, ok = 0, False
    try:
        for chunk in chunks:
            handle.write(chunk)
            written += len(chunk)
        ok = True
    finally:
        chunks.close()  # releases the response if the loop stopped early
        _finish(handle, temp, local_path, ok)
    return written


async def adownload(
    transport: AsyncRuntimeTransport,
    remote_path: str,
    local_path: str | os.PathLike[str],
    cwd: str | None,
) -> int:
    """Asynchronous ``download``: same atomic, no-partial-file rule."""
    chunks: AsyncGenerator[bytes, None] = transport.stream_bytes(
        "POST", "/v1/files/read", headers=_READ_HEADERS, body=_read_body(remote_path, cwd)
    )
    handle, temp = _open_temp_beside(local_path)
    written, ok = 0, False
    try:
        async for chunk in chunks:
            handle.write(chunk)
            written += len(chunk)
        ok = True
    finally:
        await chunks.aclose()  # releases the response if the loop stopped early
        _finish(handle, temp, local_path, ok)
    return written
