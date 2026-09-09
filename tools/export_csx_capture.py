#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Treatid2 and contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export a finalized CSX screenshot sequence into neutral capture evidence."""

from __future__ import annotations

import argparse
import binascii
import contextlib
import ctypes
import datetime as dt
import decimal
import errno
import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import struct
import sys
import tempfile
import uuid
import zipfile
import zlib
from typing import Any

import compile_dataset as compiler
import validate_repository as validator


TOOL_VERSION = "1.0.4"
PLAN_SCHEMA = {
    "name": "skyrim-render-map.csx-capture-export-plan",
    "major": 1,
    "minor": 0,
}
PLAN_KEYS = {
    "schema",
    "submissionId",
    "artifactId",
    "captureId",
    "recordedAt",
    "source",
    "artifact",
    "map",
    "runtime",
    "environment",
    "scenario",
    "treatment",
    "protocol",
    "privacy",
    "notes",
}
SOURCE_KEYS = {"kind", "manifestPath"}
ARTIFACT_PLAN_KEYS = {"locationTemplate", "license", "retentionClass"}
PRODUCER_RETENTION_CLASSES = {
    "release-asset",
    "oci-artifact",
    "object-storage",
    "external",
}
PROTOCOL_PLAN_KEYS = {
    "name",
    "version",
    "artifactSha256",
    "frameRateHz",
    "timingMode",
}
SUCCESS_STATES = {"completed", "completed_with_warnings"}
DROPPED_STATES = {"dropped"}
FAILED_STATES = {"failed", "failed_partial"}
CANCELLED_STATES = {"cancelled", "cancelled_partial"}
SHA256_PATTERN = re.compile(r"^[A-Fa-f0-9]{64}$")
TERMINAL_CODES = {
    "cancelled",
    "capacity_exhausted",
    "composition_failed",
    "cursor_expired",
    "device_changed",
    "encode_failed",
    "encoder_backpressure",
    "feature_disabled",
    "feature_unavailable",
    "gpu_stage_failed",
    "idempotency_conflict",
    "internal_error",
    "invalid_option",
    "invalid_request",
    "manifest_failed",
    "packager_unavailable",
    "packaging_failed",
    "readback_timeout",
    "request_not_found",
    "source_busy",
    "source_timeout",
    "source_unavailable",
    "unsafe_output_collision",
    "unsafe_path",
    "unsupported_capability",
    "unsupported_contract_version",
    "write_failed",
}
VIEW_ALIASES = {
    "left": "left",
    "left_eye": "left",
    "right": "right",
    "right_eye": "right",
    "combined": "mono",
    "desktop_mirror": "mono",
    "mirror": "mono",
    "source_native": "mono",
}
PNG_COLOUR_TYPES = {
    0: "grayscale",
    2: "rgb",
    4: "grayscale-alpha",
    6: "rgba",
}
PNG_BIT_DEPTHS = {
    0: {1, 2, 4, 8, 16},
    2: {8, 16},
    4: {8, 16},
    6: {8, 16},
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_SAFE_ANCILLARY = {
    b"bKGD",
    b"cHRM",
    b"gAMA",
    b"hIST",
    b"pHYs",
    b"sBIT",
    b"sRGB",
    b"tRNS",
}
PNG_PRIVATE_ANCILLARY = {b"eXIf", b"iCCP", b"iTXt", b"tEXt", b"zTXt"}
MAX_PNG_FILE_BYTES = 512 * 1024 * 1024
MAX_PNG_DECOMPRESSED_BYTES = 512 * 1024 * 1024


class ExportError(RuntimeError):
    pass


def _strict_keys(value: Any, expected: set[str], context: str) -> dict:
    if not isinstance(value, dict):
        raise ExportError(f"{context} must be an object")
    actual = set(value)
    if actual != expected:
        raise ExportError(
            f"{context} keys mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def _load_json_document(path: pathlib.Path, context: str) -> tuple[Any, str]:
    try:
        data = path.read_bytes()
        text = data.decode("utf-8")
        return validator.parse_json(text, context), hashlib.sha256(data).hexdigest()
    except (OSError, UnicodeError, validator.ValidationError) as error:
        raise ExportError(f"cannot read {context}: {error}") from error


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _file_identity(value: os.stat_result) -> tuple[int, int]:
    identity = (value.st_dev, value.st_ino)
    if value.st_ino == 0:
        raise ExportError("filesystem does not expose stable file identities")
    return identity


def _windows_open_path_handle(
    path: pathlib.Path, *, delete: bool, deny_delete_sharing: bool
) -> int:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    desired_access = 0x00000080 | (0x00010000 if delete else 0)
    share_mode = 0x00000001 | 0x00000002
    if not deny_delete_sharing:
        share_mode |= 0x00000004
    handle = create_file(
        str(path),
        desired_access,
        share_mode,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ExportError(
            f"cannot open owned path {path.name!r}: Windows error "
            f"{ctypes.get_last_error()}"
        )
    return int(handle)


def _windows_handle_information(handle: int) -> dict:
    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = [
            ("FileAttributes", ctypes.c_uint32),
            ("CreationTimeLow", ctypes.c_uint32),
            ("CreationTimeHigh", ctypes.c_uint32),
            ("LastAccessTimeLow", ctypes.c_uint32),
            ("LastAccessTimeHigh", ctypes.c_uint32),
            ("LastWriteTimeLow", ctypes.c_uint32),
            ("LastWriteTimeHigh", ctypes.c_uint32),
            ("VolumeSerialNumber", ctypes.c_uint32),
            ("FileSizeHigh", ctypes.c_uint32),
            ("FileSizeLow", ctypes.c_uint32),
            ("NumberOfLinks", ctypes.c_uint32),
            ("FileIndexHigh", ctypes.c_uint32),
            ("FileIndexLow", ctypes.c_uint32),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = [ctypes.c_void_p, ctypes.POINTER(ByHandleFileInformation)]
    get_information.restype = ctypes.c_int
    information = ByHandleFileInformation()
    if not get_information(ctypes.c_void_p(handle), ctypes.byref(information)):
        raise ExportError(
            "cannot identify owned path handle: Windows error "
            f"{ctypes.get_last_error()}"
        )
    file_index = (information.FileIndexHigh << 32) | information.FileIndexLow
    if file_index == 0:
        raise ExportError("filesystem does not expose stable file identities")
    creation_time = (information.CreationTimeHigh << 32) | information.CreationTimeLow
    write_time = (information.LastWriteTimeHigh << 32) | information.LastWriteTimeLow
    return {
        "identity": (information.VolumeSerialNumber, file_index),
        "attributes": information.FileAttributes,
        "ctimeNs": creation_time * 100,
        "mtimeNs": write_time * 100,
        "size": (information.FileSizeHigh << 32) | information.FileSizeLow,
        "links": information.NumberOfLinks,
    }


def _windows_handle_identity(handle: int) -> tuple[int, int]:
    return _windows_handle_information(handle)["identity"]


def _windows_close_handle(handle: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    if not close_handle(ctypes.c_void_p(handle)):
        raise ExportError(
            f"cannot close owned path handle: Windows error {ctypes.get_last_error()}"
        )


def _windows_path_information(path: pathlib.Path) -> dict:
    handle = _windows_open_path_handle(
        path, delete=False, deny_delete_sharing=False
    )
    try:
        return _windows_handle_information(handle)
    finally:
        _windows_close_handle(handle)


def _windows_path_identity(path: pathlib.Path) -> tuple[int, int]:
    return _windows_path_information(path)["identity"]


def _directory_identity(path: pathlib.Path, context: str) -> tuple[int, int]:
    if os.name == "nt":
        try:
            information = _windows_path_information(path)
        except ExportError as error:
            if not os.path.lexists(path):
                raise ExportError(
                    f"{context} custody is uncertain: owned directory is absent"
                ) from error
            raise ExportError(f"cannot inspect {context}: {error}") from error
        if not information["attributes"] & 0x00000010 or information[
            "attributes"
        ] & 0x00000400:
            raise ExportError(
                f"{context} custody is uncertain: path is not an owned directory"
            )
        return information["identity"]
    try:
        value = path.stat(follow_symlinks=False)
    except FileNotFoundError as error:
        raise ExportError(
            f"{context} custody is uncertain: owned directory is absent"
        ) from error
    except OSError as error:
        raise ExportError(f"cannot inspect {context}: {error}") from error
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
        raise ExportError(f"{context} custody is uncertain: path is not an owned directory")
    return _file_identity(value)


def _directory_seal(path: pathlib.Path, context: str) -> dict:
    if os.name == "nt":
        try:
            information = _windows_path_information(path)
        except ExportError as error:
            raise ExportError(f"cannot inspect {context}: {error}") from error
        if not information["attributes"] & 0x00000010 or information[
            "attributes"
        ] & 0x00000400:
            raise ExportError(f"{context} is not an ordinary directory")
        return {
            key: information[key]
            for key in ("identity", "mtimeNs", "ctimeNs", "size", "links")
        }
    try:
        value = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ExportError(f"cannot inspect {context}: {error}") from error
    if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode):
        raise ExportError(f"{context} is not an ordinary directory")
    return {
        "identity": _file_identity(value),
        "mtimeNs": value.st_mtime_ns,
        "ctimeNs": value.st_ctime_ns,
        "size": value.st_size,
        "links": value.st_nlink,
    }


@contextlib.contextmanager
def _exclusive_stream_lock(stream):
    """Exclude cooperative writers while one accepted byte version is observed."""
    if os.name == "nt":
        import msvcrt

        class Overlapped(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_void_p),
                ("InternalHigh", ctypes.c_void_p),
                ("Offset", ctypes.c_uint32),
                ("OffsetHigh", ctypes.c_uint32),
                ("hEvent", ctypes.c_void_p),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        lock_file = kernel32.LockFileEx
        lock_file.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(Overlapped),
        ]
        lock_file.restype = ctypes.c_int
        unlock_file = kernel32.UnlockFileEx
        unlock_file.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.POINTER(Overlapped),
        ]
        unlock_file.restype = ctypes.c_int
        handle = ctypes.c_void_p(msvcrt.get_osfhandle(stream.fileno()))
        overlapped = Overlapped()
        if not lock_file(
            handle,
            0x00000002 | 0x00000001,
            0,
            0xFFFFFFFF,
            0xFFFFFFFF,
            ctypes.byref(overlapped),
        ):
            raise ExportError(
                f"cannot lock staged file: Windows error {ctypes.get_last_error()}"
            )
        try:
            yield
        finally:
            if not unlock_file(
                handle, 0, 0xFFFFFFFF, 0xFFFFFFFF, ctypes.byref(overlapped)
            ):
                message = (
                    "cannot unlock staged file: Windows error "
                    f"{ctypes.get_last_error()}"
                )
                active_error = sys.exception()
                if active_error is None:
                    raise ExportError(message)
                active_error.add_note(message)
    else:
        import fcntl

        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ExportError(f"cannot lock staged file: {error}") from error
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _hash_stream(stream) -> tuple[int, str]:
    stream.seek(0)
    digest = hashlib.sha256()
    byte_length = 0
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
        byte_length += len(block)
    return byte_length, digest.hexdigest()


def _read_sealed_stream(
    stream, path: pathlib.Path, retain_bytes: bool = False
) -> tuple[bytes, dict]:
    before = os.fstat(stream.fileno())
    stream.seek(0)
    digest = hashlib.sha256()
    retained = bytearray()
    byte_length = 0
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
        byte_length += len(block)
        if retain_bytes:
            retained.extend(block)
    after = os.fstat(stream.fileno())
    before_identity = _file_identity(before)
    if (
        before_identity != _file_identity(after)
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or byte_length != before.st_size
    ):
        raise ExportError(f"staged file changed while it was sealed: {path.name!r}")
    return bytes(retained), {
        "identity": before_identity,
        "bytes": byte_length,
        "sha256": digest.hexdigest(),
        "mtimeNs": before.st_mtime_ns,
    }


def _read_sealed_file(path: pathlib.Path, retain_bytes: bool = False) -> tuple[bytes, dict]:
    try:
        if path.is_symlink():
            raise ExportError(f"publication stage contains a symbolic link: {path.name!r}")
        with path.open("r+b") as stream, _exclusive_stream_lock(stream):
            return _read_sealed_stream(stream, path, retain_bytes=retain_bytes)
    except ExportError:
        raise
    except OSError as error:
        raise ExportError(f"cannot seal staged file {path.name!r}: {error}") from error


def _inventory_stage(root: pathlib.Path) -> tuple[dict[str, dict], list[str]]:
    directories: dict[str, dict] = {
        ".": _directory_seal(root, "publication stage")
    }
    files: list[str] = []
    for current, names, filenames in os.walk(root, followlinks=False):
        current_path = pathlib.Path(current)
        for name in sorted(names):
            directory = current_path / name
            if directory.is_symlink():
                raise ExportError("publication stage contains a symbolic-link directory")
            relative = directory.relative_to(root).as_posix()
            directories[relative] = _directory_seal(
                directory, f"publication stage directory {relative!r}"
            )
        for name in sorted(filenames):
            path = current_path / name
            if path.is_symlink():
                raise ExportError("publication stage contains a symbolic-link file")
            files.append(path.relative_to(root).as_posix())
    for relative, seal in directories.items():
        path = root if relative == "." else root / relative
        if _directory_seal(path, f"publication stage directory {relative!r}") != seal:
            raise ExportError("publication stage membership changed during enumeration")
    return directories, sorted(files)


def _snapshot_stage(root: pathlib.Path, scan_public: bool = False) -> dict:
    directories, filenames = _inventory_stage(root)
    files: dict[str, dict] = {}
    with contextlib.ExitStack() as stack:
        streams = {}
        for relative in filenames:
            path = root / relative
            try:
                stream = stack.enter_context(path.open("r+b"))
                stack.enter_context(_exclusive_stream_lock(stream))
            except OSError as error:
                raise ExportError(f"cannot seal staged file {relative!r}: {error}") from error
            streams[relative] = stream
        locked_directories, locked_filenames = _inventory_stage(root)
        if locked_directories != directories or locked_filenames != filenames:
            raise ExportError("publication stage changed while files were locked")
        for relative in filenames:
            path = root / relative
            retain_bytes = scan_public and path.suffix != ".zip"
            data, seal = _read_sealed_stream(
                streams[relative], path, retain_bytes=retain_bytes
            )
            if retain_bytes:
                try:
                    validator.scan_public_content(pathlib.Path(relative), data)
                except validator.ValidationError as error:
                    raise ExportError(f"public export validation failed: {error}") from error
            files[relative] = seal
        for relative, stream in streams.items():
            current = os.fstat(stream.fileno())
            seal = files[relative]
            if (
                _file_identity(current) != seal["identity"]
                or current.st_size != seal["bytes"]
                or current.st_mtime_ns != seal["mtimeNs"]
            ):
                raise ExportError("publication stage changed during coherent verification")
        final_directories, final_filenames = _inventory_stage(root)
        if final_directories != directories or final_filenames != filenames:
            raise ExportError("publication stage changed during coherent verification")
    return {"directories": directories, "files": files}


def _require_stage_snapshot(root: pathlib.Path, expected: dict) -> None:
    if _snapshot_stage(root) != expected:
        raise ExportError("publication stage changed after validation")


def _parse_time(value: Any, context: str) -> str:
    if not isinstance(value, str):
        raise ExportError(f"{context} must be an RFC 3339 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExportError(f"{context} must be an RFC 3339 timestamp") from error
    if parsed.tzinfo is None:
        raise ExportError(f"{context} must include a timezone")
    return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_plan_path(plan_path: pathlib.Path, value: Any) -> pathlib.Path:
    if not isinstance(value, str) or not value.strip():
        raise ExportError("source.manifestPath must be a non-empty path")
    candidate = pathlib.Path(value)
    if not candidate.is_absolute():
        candidate = plan_path.parent / candidate
    resolved = candidate.resolve()
    if not resolved.is_file():
        raise ExportError("source.manifestPath is not a file")
    return resolved


def _resolve_frame_path(manifest_path: pathlib.Path, value: Any) -> pathlib.Path:
    if not isinstance(value, str) or not value.strip():
        raise ExportError("frame artifact path must be non-empty")
    declared = pathlib.Path(value)
    if declared.is_absolute() and declared.is_file():
        return declared.resolve()
    if not declared.is_absolute():
        relative = (manifest_path.parent / declared).resolve()
        try:
            relative.relative_to(manifest_path.parent.resolve())
        except ValueError as error:
            raise ExportError("relative frame artifact escapes the manifest directory") from error
        if relative.is_file():
            return relative
    promoted = (manifest_path.parent / declared.name).resolve()
    if promoted.is_file():
        return promoted
    raise ExportError(f"frame artifact is unavailable: {declared.name!r}")


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def _sanitize_png(data: bytes, filename: str) -> tuple[bytes, int, int, str]:
    if not data.startswith(PNG_SIGNATURE):
        raise ExportError(f"{filename!r} is not a PNG")
    position = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    idat = bytearray()
    seen_ihdr = False
    seen_plte = False
    seen_idat = False
    ended_idat = False
    seen_iend = False
    seen_ancillary: set[bytes] = set()
    palette_entries = 0
    width = height = bit_depth = colour_type = 0

    while position < len(data):
        if len(data) - position < 12:
            raise ExportError(f"{filename!r} has a truncated PNG chunk")
        length = struct.unpack(">I", data[position : position + 4])[0]
        end = position + 12 + length
        if end > len(data):
            raise ExportError(f"{filename!r} has a truncated PNG chunk")
        kind = data[position + 4 : position + 8]
        payload = data[position + 8 : position + 8 + length]
        expected_crc = struct.unpack(">I", data[position + 8 + length : end])[0]
        if not all(65 <= byte <= 90 or 97 <= byte <= 122 for byte in kind):
            raise ExportError(f"{filename!r} has an invalid PNG chunk type")
        if kind[2] & 0x20:
            raise ExportError(f"{filename!r} uses a reserved PNG chunk type")
        if (binascii.crc32(kind + payload) & 0xFFFFFFFF) != expected_crc:
            raise ExportError(f"{filename!r} has an invalid {kind!r} checksum")
        if seen_iend:
            raise ExportError(f"{filename!r} contains data after PNG IEND")

        if not seen_ihdr:
            if kind != b"IHDR" or length != 13:
                raise ExportError(f"{filename!r} has no canonical PNG IHDR")
            width, height, bit_depth, colour_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            colour_name = PNG_COLOUR_TYPES.get(colour_type)
            if (
                width == 0
                or height == 0
                or colour_name is None
                or bit_depth not in PNG_BIT_DEPTHS[colour_type]
                or compression != 0
                or filtering != 0
                or interlace != 0
            ):
                raise ExportError(f"{filename!r} has unsupported PNG geometry")
            seen_ihdr = True
            chunks.append((kind, payload))
        elif kind == b"IHDR":
            raise ExportError(f"{filename!r} repeats PNG IHDR")
        elif kind == b"PLTE":
            if (
                seen_plte
                or seen_idat
                or colour_type in {0, 4}
                or length == 0
                or length % 3
                or length > 768
            ):
                raise ExportError(f"{filename!r} has an invalid PNG palette")
            seen_plte = True
            palette_entries = length // 3
            chunks.append((kind, payload))
        elif kind == b"IDAT":
            if ended_idat:
                raise ExportError(f"{filename!r} has non-consecutive PNG IDAT chunks")
            seen_idat = True
            idat.extend(payload)
            chunks.append((kind, payload))
        elif kind == b"IEND":
            if length != 0 or not seen_idat:
                raise ExportError(f"{filename!r} has an invalid PNG IEND")
            seen_iend = True
            chunks.append((kind, payload))
        else:
            if seen_idat:
                ended_idat = True
            if kind in PNG_PRIVATE_ANCILLARY:
                pass
            elif kind in PNG_SAFE_ANCILLARY:
                if kind in seen_ancillary:
                    raise ExportError(f"{filename!r} repeats PNG chunk {kind!r}")
                seen_ancillary.add(kind)
                if kind in {b"tRNS", b"bKGD", b"hIST", b"pHYs"} and seen_idat:
                    raise ExportError(f"{filename!r} has invalid PNG chunk ordering")
                if kind in {b"cHRM", b"gAMA", b"sBIT", b"sRGB"} and (
                    seen_plte or seen_idat
                ):
                    raise ExportError(f"{filename!r} has invalid PNG chunk ordering")
                expected_lengths = {
                    b"cHRM": 32,
                    b"gAMA": 4,
                    b"pHYs": 9,
                    b"sRGB": 1,
                }
                if kind in expected_lengths and length != expected_lengths[kind]:
                    raise ExportError(f"{filename!r} has an invalid PNG {kind!r} chunk")
                if kind == b"hIST" and length != 2 * palette_entries:
                    raise ExportError(f"{filename!r} has an invalid PNG histogram")
                if kind == b"hIST" and colour_type != 3:
                    raise ExportError(f"{filename!r} has an invalid PNG histogram")
                if kind == b"tRNS" and colour_type not in {0, 2, 3}:
                    raise ExportError(f"{filename!r} has an invalid PNG transparency chunk")
                transparency_lengths = {0: 2, 2: 6}
                if kind == b"tRNS":
                    if (
                        colour_type in transparency_lengths
                        and length != transparency_lengths[colour_type]
                    ) or (
                        colour_type == 3 and not 1 <= length <= palette_entries
                    ):
                        raise ExportError(
                            f"{filename!r} has an invalid PNG transparency chunk"
                        )
                if kind == b"sBIT" and length != {0: 1, 2: 3, 3: 3, 4: 2, 6: 4}[
                    colour_type
                ]:
                    raise ExportError(f"{filename!r} has an invalid PNG significant-bits chunk")
                if kind == b"bKGD" and length != {0: 2, 2: 6, 3: 1, 4: 2, 6: 6}[
                    colour_type
                ]:
                    raise ExportError(f"{filename!r} has an invalid PNG background chunk")
                if kind == b"gAMA" and payload == b"\0\0\0\0":
                    raise ExportError(f"{filename!r} has an invalid PNG gamma chunk")
                if kind == b"sRGB" and payload[0] > 3:
                    raise ExportError(f"{filename!r} has an invalid PNG rendering intent")
                if kind == b"pHYs" and payload[-1] > 1:
                    raise ExportError(f"{filename!r} has an invalid PNG physical-unit value")
                if kind == b"sBIT" and any(
                    value == 0 or value > bit_depth for value in payload
                ):
                    raise ExportError(f"{filename!r} has an invalid PNG significant-bits value")
                sample_limit = (1 << bit_depth) - 1
                if kind in {b"bKGD", b"tRNS"} and colour_type in {0, 4}:
                    if struct.unpack(">H", payload[:2])[0] > sample_limit:
                        raise ExportError(f"{filename!r} has an invalid PNG sample value")
                if kind in {b"bKGD", b"tRNS"} and colour_type in {2, 6}:
                    if any(
                        struct.unpack(">H", payload[index : index + 2])[0] > sample_limit
                        for index in range(0, len(payload), 2)
                    ):
                        raise ExportError(f"{filename!r} has an invalid PNG sample value")
                chunks.append((kind, payload))
            else:
                category = "critical" if not kind[0] & 0x20 else "ancillary"
                raise ExportError(f"{filename!r} has unsupported PNG {category} chunk {kind!r}")
        position = end

    if not seen_iend:
        raise ExportError(f"{filename!r} has no PNG IEND")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour_type]
    row_bytes = (width * channels * bit_depth + 7) // 8
    expected_bytes = height * (row_bytes + 1)
    if expected_bytes > MAX_PNG_DECOMPRESSED_BYTES:
        raise ExportError(f"{filename!r} exceeds the decoded PNG safety limit")
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(bytes(idat), expected_bytes + 1)
        pixels += decoder.flush(expected_bytes + 1 - len(pixels))
    except (zlib.error, ValueError) as error:
        raise ExportError(f"{filename!r} has invalid PNG image data") from error
    if (
        not decoder.eof
        or decoder.unused_data
        or decoder.unconsumed_tail
        or len(pixels) != expected_bytes
    ):
        raise ExportError(f"{filename!r} has invalid PNG image data length")
    for row in range(height):
        if pixels[row * (row_bytes + 1)] > 4:
            raise ExportError(f"{filename!r} has an invalid PNG row filter")

    sanitized = PNG_SIGNATURE + b"".join(_png_chunk(kind, payload) for kind, payload in chunks)
    colour_name = PNG_COLOUR_TYPES[colour_type]
    return sanitized, width, height, f"png-{colour_name}-{bit_depth}bit"


def _copy_and_inspect_png(
    source: pathlib.Path, destination: pathlib.Path, context: str, declared_digest: str
) -> tuple[int, str, int, str, int, int, str]:
    source_digest = hashlib.sha256()
    size = 0
    copied = bytearray()
    try:
        with source.open("rb") as input_stream:
            for block in iter(lambda: input_stream.read(1024 * 1024), b""):
                copied.extend(block)
                source_digest.update(block)
                size += len(block)
                if size > MAX_PNG_FILE_BYTES:
                    raise ExportError(f"{context} exceeds the encoded PNG safety limit")
        sanitized, width, height, pixel_format = _sanitize_png(bytes(copied), source.name)
        with destination.open("xb") as output_stream:
            output_stream.write(sanitized)
            output_stream.flush()
            os.fsync(output_stream.fileno())
    except ExportError:
        raise
    except OSError as error:
        raise ExportError(f"cannot stage {context}: {error}") from error
    digest = source_digest.hexdigest()
    if digest != declared_digest.lower():
        raise ExportError(f"{context} SHA-256 differs from the file")
    return (
        size,
        digest,
        len(sanitized),
        hashlib.sha256(sanitized).hexdigest(),
        width,
        height,
        pixel_format,
    )


def _normalize_view(value: Any, filename: str) -> str:
    if value is not None:
        if not isinstance(value, str) or value.lower() not in VIEW_ALIASES:
            raise ExportError(f"unsupported view for frame artifact {filename!r}")
        return VIEW_ALIASES[value.lower()]
    stem = pathlib.Path(filename).stem.lower()
    for suffix, view in sorted(
        VIEW_ALIASES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if stem.endswith("_" + suffix):
            return view
    raise ExportError(f"cannot identify view for frame artifact {filename!r}")


def _filename_view(filename: str) -> str:
    return _normalize_view(None, filename)


def _resolve_artifact_view(artifact: dict, actual: dict, filename: str) -> str:
    authorities = []
    for value in (artifact.get("view"), actual.get("view")):
        if value is not None:
            authorities.append(_normalize_view(value, filename))
    try:
        filename_view = _filename_view(filename)
    except ExportError:
        filename_view = None
    if filename_view is not None:
        authorities.append(filename_view)
    if not authorities:
        raise ExportError(f"cannot identify view for frame artifact {filename!r}")
    if len(set(authorities)) != 1:
        raise ExportError(f"conflicting view declarations for frame artifact {filename!r}")
    return authorities[0]


def _declared_outputs(capture: dict) -> dict[str, dict]:
    outputs = capture.get("outputs", [])
    if not isinstance(outputs, list):
        raise ExportError("manifest capture.outputs must be an array")
    declared = {}
    for output in outputs:
        if not isinstance(output, dict):
            raise ExportError("manifest capture.outputs entries must be objects")
        raw_view = output.get("view")
        if not isinstance(raw_view, str) or raw_view.lower() not in VIEW_ALIASES:
            raise ExportError("manifest capture.outputs contains an unsupported view")
        output_view = VIEW_ALIASES[raw_view.lower()]
        suffix = output.get("nameSuffix")
        if not isinstance(suffix, str) or not suffix:
            raise ExportError("manifest capture.outputs contains no valid nameSuffix")
        suffix_view = VIEW_ALIASES.get(suffix.lower())
        if suffix_view != output_view:
            raise ExportError("manifest capture.outputs has conflicting view and suffix")
        if output_view in declared:
            raise ExportError("manifest capture.outputs repeats an output view")
        declared[output_view] = output
    return declared


def _declared_output(capture: dict, filename: str, view: str) -> dict:
    outputs = _declared_outputs(capture)
    if not outputs:
        return {}
    output = outputs.get(view)
    if output is None:
        raise ExportError(f"manifest capture.outputs has no declaration for {filename!r}")
    suffix = output["nameSuffix"].lower()
    if not pathlib.Path(filename).stem.lower().endswith("_" + suffix):
        raise ExportError(f"manifest capture.outputs disagrees with {filename!r}")
    return output


def _artifact_metadata(
    manifest_path: pathlib.Path,
    capture: dict,
    artifact: dict,
    context: str,
    spool_path: pathlib.Path,
) -> tuple[pathlib.Path, dict]:
    if not isinstance(artifact, dict):
        raise ExportError(f"{context} must be an object")
    path = _resolve_frame_path(manifest_path, artifact.get("path"))
    if artifact.get("committed") is not True:
        raise ExportError(f"{context} is not committed")
    declared_digest = artifact.get("sha256")
    if not isinstance(declared_digest, str) or not SHA256_PATTERN.fullmatch(declared_digest):
        raise ExportError(f"{context}.sha256 must be a complete SHA-256")
    (
        source_size,
        source_digest,
        sanitized_size,
        sanitized_digest,
        width,
        height,
        pixel_format,
    ) = _copy_and_inspect_png(path, spool_path, context, declared_digest)
    if artifact.get("bytes") != source_size:
        raise ExportError(f"{context} byte count differs from the file")
    raw_actual = artifact.get("actual")
    if raw_actual is not None and not isinstance(raw_actual, dict):
        raise ExportError(f"{context}.actual must be an object")
    actual = raw_actual or {}
    view = _resolve_artifact_view(artifact, actual, path.name)
    output = _declared_output(capture, path.name, view)
    raw_encoding = output.get("encoding")
    if raw_encoding is not None and not isinstance(raw_encoding, dict):
        raise ExportError(f"{context} has an invalid encoding declaration")
    encoding = raw_encoding or {}
    formats = [path.suffix.lstrip(".").lower()]
    for value in (encoding.get("format"), actual.get("format")):
        if value is not None:
            if not isinstance(value, str):
                raise ExportError(f"{context} has no valid format declaration")
            formats.append(value.lower())
    if len(set(formats)) != 1:
        raise ExportError(f"{context} has conflicting format declarations")
    format_name = formats[0]
    if not format_name:
        raise ExportError(f"{context} has no valid format declaration")
    if format_name != "png":
        raise ExportError(f"{context} uses unsupported format {format_name!r}")
    if actual.get("width", width) != width or actual.get("height", height) != height:
        raise ExportError(f"{context} PNG dimensions differ from manifest metadata")
    colours = [
        value
        for value in (encoding.get("colourContract"), actual.get("colourContract"))
        if value is not None
    ]
    if not colours or any(not isinstance(value, str) or not value for value in colours):
        raise ExportError(f"{context} has no colour contract")
    if len(set(colours)) != 1:
        raise ExportError(f"{context} has conflicting colour declarations")
    colour = colours[0]
    return spool_path, {
        "view": view,
        "bytes": sanitized_size,
        "sha256": sanitized_digest,
        "sourceBytes": source_size,
        "sourceSha256": source_digest,
        "width": width,
        "height": height,
        "format": "png",
        "colourContract": colour,
        "pixelFormat": pixel_format,
    }


def _validate_manifest_counts(counts: Any, child_count: int) -> dict[str, int]:
    if not isinstance(counts, dict):
        raise ExportError("manifest counts are required")
    normalized = {}
    for key in ("requested", "scheduled", "written", "dropped", "failed", "inFlight"):
        value = counts.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ExportError(f"manifest counts.{key} must be a non-negative integer")
        normalized[key] = value
    for key in ("cancelled", "acquired"):
        value = counts.get(key)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise ExportError(f"manifest counts.{key} must be a non-negative integer")
        if value is not None:
            normalized[key] = value
    normalized.setdefault("cancelled", 0)
    if normalized["requested"] < normalized["scheduled"]:
        raise ExportError("manifest scheduled count exceeds requested count")
    if normalized["inFlight"] != 0 or normalized["scheduled"] != child_count:
        raise ExportError("final manifest count reconciliation failed")
    acquired = normalized.get("acquired")
    if acquired is not None and not (
        normalized["written"] <= acquired <= normalized["scheduled"]
    ):
        raise ExportError("manifest counts.acquired is inconsistent")
    return normalized


def _inspect_completed_child(
    manifest_path: pathlib.Path,
    capture: dict,
    child: dict,
    context: str,
    spool_directory: pathlib.Path,
) -> tuple[dict, str, bool, int]:
    raw_actual = child.get("actual")
    if raw_actual is not None and not isinstance(raw_actual, dict):
        raise ExportError(f"{context}.actual must be an object")
    actual = raw_actual or {}
    raw_actual_source = actual.get("source")
    if raw_actual_source is not None and not isinstance(raw_actual_source, dict):
        raise ExportError(f"{context}.actual.source must be an object")
    actual_source = raw_actual_source or {}
    requested = child.get("requested") if isinstance(child.get("requested"), dict) else {}
    effective = child.get("effective") if isinstance(child.get("effective"), dict) else {}
    requested_source = capture.get("source") if isinstance(capture.get("source"), dict) else {}
    for descriptor in (requested, effective):
        source = descriptor.get("source")
        if not requested_source and isinstance(source, dict):
            requested_source = source
    source_kind = actual_source.get("kind", requested_source.get("kind"))
    if not isinstance(source_kind, str) or not source_kind:
        raise ExportError(f"{context} has no actual capture source")
    fallback_value = actual_source.get("fallbackApplied", False)
    if not isinstance(fallback_value, bool):
        raise ExportError(f"{context} has a non-boolean fallback declaration")
    if fallback_value and (
        not isinstance(actual_source.get("kind"), str) or not actual_source["kind"]
    ):
        raise ExportError(f"{context} declares fallback without an actual capture source")
    if (
        actual_source.get("kind") is not None
        and requested_source.get("kind") is not None
        and actual_source["kind"] != requested_source["kind"]
        and not fallback_value
    ):
        raise ExportError(f"{context} changed capture source without declaring fallback")

    declared_capture = capture
    if isinstance(effective.get("outputs"), list):
        declared_capture = {"outputs": effective["outputs"]}
    if fallback_value and actual_source.get("kind") != requested_source.get("kind"):
        declared_capture = {}
    artifacts = child.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ExportError(f"{context} has no committed artifacts")
    frame_artifacts = []
    source_paths = []
    for artifact_index, artifact in enumerate(artifacts):
        path, metadata = _artifact_metadata(
            manifest_path,
            declared_capture,
            artifact,
            f"{context}.artifacts[{artifact_index}]",
            spool_directory / f"{child.get('ordinal', 0):08d}-{artifact_index:04d}.png",
        )
        source_paths.append(path)
        frame_artifacts.append(metadata)
    views = [item["view"] for item in frame_artifacts]
    if len(views) != len(set(views)):
        raise ExportError(f"{context} repeats an output view")
    declared_views = set(_declared_outputs(declared_capture))
    if declared_views and set(views) != declared_views:
        raise ExportError(f"{context} artifacts do not match the complete output declaration")
    engine_frame = child.get("scheduledEngineFrame")
    timestamp_us = child.get("scheduledTimestampUs")
    scheduled_values = (
        (engine_frame, "scheduledEngineFrame"),
        (timestamp_us, "scheduledTimestampUs"),
    )
    for value, name in scheduled_values:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ExportError(f"{context}.{name} must be non-negative")

    warnings = child.get("warnings", [])
    if warnings is not None and not isinstance(warnings, list):
        raise ExportError(f"{context}.warnings must be an array")
    return (
        {
            "scheduledEngineFrame": engine_frame,
            "scheduledTimestampUs": timestamp_us,
            "artifacts": frame_artifacts,
            "_sourcePaths": source_paths,
        },
        source_kind,
        fallback_value,
        max(len(warnings or []), int(child.get("state") == "completed_with_warnings")),
    )


def _inspect_manifest(manifest_path: pathlib.Path, spool_directory: pathlib.Path) -> dict:
    manifest, manifest_sha256 = _load_json_document(
        manifest_path, "CSX sequence manifest"
    )
    if not isinstance(manifest, dict):
        raise ExportError("CSX sequence manifest must be an object")
    contract = manifest.get("contract")
    if not isinstance(contract, dict) or contract.get("name") != "csx.screenshot":
        raise ExportError("source is not a CSX screenshot manifest")
    if contract.get("major") != 1 or contract.get("minor") != 0:
        raise ExportError("unsupported CSX screenshot contract; expected 1.0")
    revision = contract.get("schemaRevision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ExportError("unsupported CSX screenshot schema revision")
    if manifest.get("state") != "final":
        raise ExportError("CSX screenshot manifest is not final")
    children = manifest.get("children")
    capture = manifest.get("capture")
    if not isinstance(children, list):
        raise ExportError("manifest children are required")
    counts = _validate_manifest_counts(manifest.get("counts"), len(children))
    if capture is None:
        capture = {}
    if not isinstance(capture, dict):
        raise ExportError("manifest capture descriptor must be an object or null")
    frames = []
    omissions = []
    warning_count = 0
    source_kinds: set[str] = set()
    fallback_states: set[bool] = set()
    seen_ordinals: set[int] = set()
    seen_engine_frames: set[int] = set()
    duplicated_frames = 0
    for child_index, child in enumerate(children):
        context = f"children[{child_index}]"
        if not isinstance(child, dict):
            raise ExportError(f"{context} must be an object")
        ordinal = child.get("ordinal")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1:
            raise ExportError(f"{context}.ordinal must be positive")
        if ordinal in seen_ordinals:
            raise ExportError("manifest repeats a child ordinal")
        seen_ordinals.add(ordinal)
        state = child.get("state")
        if state not in SUCCESS_STATES:
            if state not in DROPPED_STATES | FAILED_STATES | CANCELLED_STATES:
                raise ExportError(f"{context} has unsupported terminal state {state!r}")
            omissions.append(
                {
                    "sourceOrdinal": ordinal,
                    "state": state,
                    "terminalCode": (
                        child["error"] if child.get("error") in TERMINAL_CODES else "unspecified"
                    ),
                }
            )
            continue
        frame, source_kind, child_fallback, child_warning_count = (
            _inspect_completed_child(
                manifest_path, capture, child, context, spool_directory
            )
        )
        engine_frame = frame["scheduledEngineFrame"]
        if engine_frame in seen_engine_frames:
            duplicated_frames += 1
        seen_engine_frames.add(engine_frame)
        source_kinds.add(source_kind)
        fallback_states.add(child_fallback)
        warning_count += child_warning_count
        frame["sourceOrdinal"] = ordinal
        frames.append(frame)
    frames.sort(key=lambda item: item["sourceOrdinal"])
    if not frames:
        raise ExportError("manifest contains no completed frames")
    if counts["written"] != len(frames):
        raise ExportError("manifest counts.written differs from completed children")
    dropped = sum(item["state"] in DROPPED_STATES for item in omissions)
    failed = sum(item["state"] in FAILED_STATES for item in omissions)
    cancelled = sum(item["state"] in CANCELLED_STATES for item in omissions)
    if (
        counts["dropped"] != dropped
        or counts["failed"] != failed
        or counts["cancelled"] != cancelled
        or counts["written"] + dropped + failed + cancelled != counts["scheduled"]
    ):
        raise ExportError("manifest terminal counts do not reconcile")
    if len(source_kinds) != 1:
        raise ExportError("manifest mixes actual capture sources")
    if len(fallback_states) != 1:
        raise ExportError("manifest mixes fallback and non-fallback captures")
    view_sets = {tuple(sorted(item["view"] for item in frame["artifacts"])) for frame in frames}
    if len(view_sets) != 1:
        raise ExportError("manifest frames do not have a consistent view set")
    views = next(iter(view_sets))
    if views == ("left", "right"):
        media_kind = "stereo-sequence"
    elif views == ("mono",):
        media_kind = "mono-sequence"
    else:
        raise ExportError(f"unsupported capture view set: {views!r}")
    geometry = {
        (item["width"], item["height"], item["pixelFormat"], item["colourContract"])
        for frame in frames
        for item in frame["artifacts"]
    }
    if len(geometry) != 1:
        raise ExportError("manifest artifacts do not share geometry and encoding")
    width, height, pixel_format, colour_contract = next(iter(geometry))
    return {
        "manifest": manifest,
        "manifestSha256": manifest_sha256,
        "contract": {
            "name": "csx.screenshot",
            "major": 1,
            "minor": 0,
            "schemaRevision": revision,
        },
        "counts": {
            "requested": counts["requested"],
            "scheduled": counts["scheduled"],
            "written": counts["written"],
            "dropped": dropped,
            "failed": failed,
            "cancelled": cancelled,
        },
        "frames": frames,
        "omissions": sorted(omissions, key=lambda item: item["sourceOrdinal"]),
        "dropped": dropped,
        "failed": failed,
        "cancelled": cancelled,
        "warningCount": warning_count,
        "duplicatedFrames": duplicated_frames,
        "sourceKind": next(iter(source_kinds)),
        "sourceFallbackApplied": next(iter(fallback_states)),
        "mediaKind": media_kind,
        "viewCount": len(views),
        "width": width,
        "height": height,
        "pixelFormat": pixel_format,
        "colourContract": colour_contract,
    }


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _zip_info_signature(info: zipfile.ZipInfo) -> tuple:
    return (
        info.filename,
        info.orig_filename,
        info.date_time,
        info.compress_type,
        info.comment,
        info.extra,
        info.create_system,
        info.create_version,
        info.extract_version,
        info.flag_bits,
        info.volume,
        info.internal_attr,
        info.external_attr,
        info.header_offset,
        info.CRC,
        info.compress_size,
        info.file_size,
    )


def _zip_has_exact_terminator(stream, byte_length: int) -> bool:
    end_record_size = 22
    stream.seek(max(0, byte_length - (65535 + end_record_size)))
    tail = stream.read()
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or len(tail) - offset != end_record_size:
        return False
    comment_length = struct.unpack_from("<H", tail, offset + 20)[0]
    return comment_length == 0


def _write_bundle(path: pathlib.Path, inspected: dict) -> tuple[int, int, dict]:
    public_frames = []
    entries: list[tuple[str, pathlib.Path]] = []
    for index, frame in enumerate(inspected["frames"]):
        artifacts = []
        paired = sorted(
            zip(frame["artifacts"], frame["_sourcePaths"]),
            key=lambda item: item[0]["view"],
        )
        for metadata, source_path in paired:
            archive_path = f"frames/{index:06d}/{metadata['view']}.png"
            artifacts.append({"path": archive_path, **metadata})
            entries.append((archive_path, source_path))
        public_frames.append(
            {
                "index": index,
                "sourceOrdinal": frame["sourceOrdinal"],
                "scheduledEngineFrame": frame["scheduledEngineFrame"],
                "scheduledTimestampUs": frame["scheduledTimestampUs"],
                "artifacts": artifacts,
            }
        )
    bundle_manifest = {
        "schema": {
            "name": "skyrim-render-map.capture-bundle",
            "major": 1,
            "minor": 0,
        },
        "source": {
            "contract": inspected["contract"],
            "manifestSha256": inspected["manifestSha256"],
            "counts": inspected["counts"],
        },
        "frames": public_frames,
        "omissions": inspected["omissions"],
    }
    manifest_bytes = _canonical_json_bytes(bundle_manifest)
    try:
        validator.scan_public_content(pathlib.Path("bundle-manifest.json"), manifest_bytes)
    except validator.ValidationError as error:
        raise ExportError(f"capture bundle manifest is not publication-safe: {error}") from error
    expanded_bytes = len(manifest_bytes) + sum(
        metadata["bytes"]
        for frame in inspected["frames"]
        for metadata in frame["artifacts"]
    )
    try:
        with path.open("xb+") as bundle_stream, _exclusive_stream_lock(bundle_stream):
            generated_identity = _file_identity(os.fstat(bundle_stream.fileno()))
            generated_infos = []
            with zipfile.ZipFile(bundle_stream, "w", allowZip64=True) as archive:
                manifest_info = _zip_info("bundle-manifest.json")
                archive.writestr(manifest_info, manifest_bytes)
                generated_infos.append(manifest_info)
                metadata_by_path = {
                    artifact["path"]: artifact
                    for frame in public_frames
                    for artifact in frame["artifacts"]
                }
                for archive_path, source in entries:
                    digest = hashlib.sha256()
                    written = 0
                    frame_info = _zip_info(archive_path)
                    with archive.open(
                        frame_info, "w", force_zip64=True
                    ) as target:
                        with source.open("rb") as stream:
                            for block in iter(lambda: stream.read(1024 * 1024), b""):
                                target.write(block)
                                digest.update(block)
                                written += len(block)
                    generated_infos.append(frame_info)
                    expected = metadata_by_path[archive_path]
                    if (
                        written != expected["bytes"]
                        or digest.hexdigest() != expected["sha256"]
                    ):
                        raise ExportError(
                            "staged frame changed while the bundle was written"
                        )
            bundle_stream.flush()
            os.fsync(bundle_stream.fileno())
            if _file_identity(os.fstat(bundle_stream.fileno())) != generated_identity:
                raise ExportError("capture bundle identity changed during generation")
            expected_info_signatures = [
                _zip_info_signature(info) for info in generated_infos
            ]
            expected_names = [info.filename for info in generated_infos]
            if len(expected_names) != len(set(expected_names)):
                raise ExportError("capture bundle generation repeated an entry name")
            before = os.fstat(bundle_stream.fileno())
            byte_length, digest_before = _hash_stream(bundle_stream)
            if not _zip_has_exact_terminator(bundle_stream, byte_length):
                raise ExportError("capture bundle envelope verification failed")
            bundle_stream.seek(0)
            with zipfile.ZipFile(bundle_stream) as archive:
                actual_infos = archive.infolist()
                if archive.comment or [info.filename for info in actual_infos] != expected_names:
                    raise ExportError("capture bundle member verification failed")
                if [
                    _zip_info_signature(info) for info in actual_infos
                ] != expected_info_signatures:
                    raise ExportError("capture bundle envelope verification failed")
                if archive.read("bundle-manifest.json") != manifest_bytes:
                    raise ExportError("capture bundle manifest verification failed")
                for archive_path, _ in entries:
                    digest = hashlib.sha256(archive.read(archive_path)).hexdigest()
                    expected = metadata_by_path[archive_path]
                    if digest != expected["sha256"]:
                        raise ExportError("capture bundle entry digest verification failed")
            verified_length, digest_after = _hash_stream(bundle_stream)
            after = os.fstat(bundle_stream.fileno())
            if (
                _file_identity(before) != generated_identity
                or _file_identity(after) != generated_identity
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or byte_length != before.st_size
                or verified_length != byte_length
                or digest_after != digest_before
            ):
                raise ExportError("capture bundle changed during coherent verification")
            bundle_seal = {
                "identity": generated_identity,
                "bytes": byte_length,
                "sha256": digest_after,
                "mtimeNs": after.st_mtime_ns,
            }
    except ExportError:
        raise
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ExportError(f"cannot write capture bundle: {error}") from error
    return byte_length, expanded_bytes, bundle_seal


def _validate_plan(plan: Any) -> dict:
    plan = _strict_keys(plan, PLAN_KEYS, "plan")
    if plan["schema"] != PLAN_SCHEMA:
        raise ExportError("unsupported capture export plan schema")
    if (
        not isinstance(plan["submissionId"], str)
        or not validator.SUBMISSION_PATTERN.fullmatch(plan["submissionId"])
    ):
        raise ExportError("plan.submissionId is invalid")
    for key in ("artifactId", "captureId"):
        if not isinstance(plan[key], str) or not validator.RECORD_ID_PATTERN.fullmatch(
            plan[key]
        ):
            raise ExportError(f"plan.{key} is invalid")
    if plan["artifactId"] == plan["captureId"]:
        raise ExportError("plan artifactId and captureId must be distinct")
    _strict_keys(plan["source"], SOURCE_KEYS, "plan.source")
    if plan["source"]["kind"] != "csx-screenshot-sequence-v1":
        raise ExportError("unsupported capture source kind")
    artifact = _strict_keys(plan["artifact"], ARTIFACT_PLAN_KEYS, "plan.artifact")
    template = artifact["locationTemplate"]
    if not isinstance(template, str) or template.count("{sha256}") != 1:
        raise ExportError("artifact.locationTemplate requires one {sha256} placeholder")
    if artifact["license"] not in validator.ARTIFACT_LICENSES:
        raise ExportError("plan.artifact.license is unsupported")
    if artifact["retentionClass"] not in PRODUCER_RETENTION_CLASSES:
        raise ExportError("plan.artifact.retentionClass is unsupported")
    protocol = _strict_keys(plan["protocol"], PROTOCOL_PLAN_KEYS, "plan.protocol")
    if protocol["timingMode"] not in validator.VISUAL_CAPTURE_TIMING_MODES:
        raise ExportError("plan.protocol.timingMode is unsupported")
    frame_rate = protocol["frameRateHz"]
    if not isinstance(frame_rate, str) or not validator.DECIMAL_PATTERN.fullmatch(frame_rate):
        raise ExportError("plan.protocol.frameRateHz must be a canonical decimal")
    try:
        parsed_frame_rate = decimal.Decimal(frame_rate)
    except decimal.InvalidOperation as error:
        raise ExportError("plan.protocol.frameRateHz must be a canonical decimal") from error
    if not parsed_frame_rate.is_finite() or parsed_frame_rate <= 0:
        raise ExportError("plan.protocol.frameRateHz must be positive")
    if not isinstance(plan["runtime"], dict) or not isinstance(
        plan["runtime"].get("extensions"), list
    ):
        raise ExportError("plan.runtime.extensions must be an array")
    if not isinstance(plan["privacy"], dict):
        raise ExportError("plan.privacy must be an object")
    treatment = plan["treatment"]
    if not isinstance(treatment, dict):
        raise ExportError("plan.treatment must be an object")
    generated_capture_ref = compiler.visual_capture_ref(
        plan["submissionId"], plan["captureId"]
    )
    generated_artifact_ref = compiler.artifact_ref(
        plan["submissionId"], plan["artifactId"]
    )
    if treatment.get("baselineObservationRef") in {
        generated_capture_ref,
        generated_artifact_ref,
    }:
        raise ExportError(
            "plan treatment cannot use its generated capture or artifact as its baseline"
        )
    _parse_time(plan["recordedAt"], "plan.recordedAt")
    return plan


def _build_records(
    plan_path: pathlib.Path,
    plan: dict,
    plan_sha256: str,
    bundle_path: pathlib.Path,
    spool_directory: pathlib.Path,
) -> tuple[dict, dict, dict, dict]:
    manifest_path = _resolve_plan_path(plan_path, plan["source"]["manifestPath"])
    inspected = _inspect_manifest(manifest_path, spool_directory)
    byte_length, expanded_length, bundle_seal = _write_bundle(bundle_path, inspected)
    bundle_sha = bundle_seal["sha256"]
    location = plan["artifact"]["locationTemplate"].replace("{sha256}", bundle_sha)
    csx_extensions = [
        item
        for item in plan["runtime"].get("extensions", [])
        if isinstance(item, dict) and item.get("namespace") == "csx"
    ]
    if len(csx_extensions) != 1:
        raise ExportError("plan.runtime requires exactly one CSX extension")
    csx_sha = csx_extensions[0].get("artifactSha256")
    artifact = {
        "schema": {"name": "skyrim-render-map.artifact", "major": 1, "minor": 0},
        "artifactId": plan["artifactId"],
        "artifactSha256": bundle_sha,
        "mediaType": "application/zip",
        "contentKind": inspected["mediaKind"],
        "encoding": "zip",
        "byteLength": byte_length,
        "expandedByteLength": expanded_length,
        "license": plan["artifact"]["license"],
        "retentionClass": plan["artifact"]["retentionClass"],
        "locations": [location],
        "notes": "Deterministic uncompressed capture bundle exported from CSX.",
    }
    issues = []
    if inspected["dropped"]:
        issues.append(f"{inspected['dropped']} scheduled frame slots were dropped")
    if inspected["failed"]:
        issues.append(f"{inspected['failed']} scheduled frame slots failed")
    if inspected["cancelled"]:
        issues.append(f"{inspected['cancelled']} scheduled frame slots were cancelled")
    if inspected["duplicatedFrames"]:
        issues.append(f"{inspected['duplicatedFrames']} engine frame identifiers repeat")
    if inspected["warningCount"]:
        issues.append(f"{inspected['warningCount']} child warnings were reported")
    validity_state = "contaminated" if issues else "valid"
    contamination = []
    full_range = {
        "firstFrame": 0,
        "lastFrame": len(inspected["frames"]) - 1,
    }
    missing_frames = inspected["dropped"] + inspected["failed"] + inspected["cancelled"]
    if missing_frames:
        contamination.append(
            {
                "kind": "dropped-frame",
                **full_range,
                "notes": f"{missing_frames} scheduled frame slots have no retained image.",
            }
        )
    if inspected["duplicatedFrames"]:
        contamination.append(
            {
                "kind": "duplicated-frame",
                **full_range,
                "notes": "At least one engine frame identifier was captured more than once.",
            }
        )
    if inspected["warningCount"]:
        contamination.append(
            {
                "kind": "unknown",
                **full_range,
                "notes": "The source manifest reported one or more child warnings.",
            }
        )
    capture = {
        "schema": {
            "name": "skyrim-render-map.visual-capture-observation",
            "major": 1,
            "minor": 0,
        },
        "captureId": plan["captureId"],
        "recordedAt": _parse_time(plan["recordedAt"], "plan.recordedAt"),
        "map": plan["map"],
        "runtime": plan["runtime"],
        "environment": plan["environment"],
        "scenario": plan["scenario"],
        "treatment": plan["treatment"],
        "protocol": {
            "name": plan["protocol"]["name"],
            "version": plan["protocol"]["version"],
            "artifactSha256": plan["protocol"]["artifactSha256"],
            "captureApi": {
                "name": "csx.screenshot",
                "version": (
                    f"{inspected['contract']['major']}.{inspected['contract']['minor']}"
                    f"-schema.{inspected['contract']['schemaRevision']}"
                ),
                "artifactSha256": csx_sha,
            },
            "sourceKind": inspected["sourceKind"],
            "sourceFallbackApplied": inspected["sourceFallbackApplied"],
            "mediaKind": inspected["mediaKind"],
            "frameCount": len(inspected["frames"]),
            "frameRateHz": plan["protocol"]["frameRateHz"],
            "viewCount": inspected["viewCount"],
            "width": inspected["width"],
            "height": inspected["height"],
            "colorSpace": inspected["colourContract"],
            "pixelFormat": inspected["pixelFormat"],
            "timingMode": plan["protocol"]["timingMode"],
            "droppedFrames": inspected["dropped"],
            "duplicatedFrames": inspected["duplicatedFrames"],
        },
        "captureSha256": bundle_sha,
        "artifactRef": compiler.artifact_ref(plan["submissionId"], plan["artifactId"]),
        "validity": {
            "state": validity_state,
            "contamination": contamination,
            "notes": "; ".join(issues) + ("." if issues else ""),
        },
        "privacy": plan["privacy"],
        "notes": plan["notes"],
    }
    try:
        validator.validate_artifact(artifact, "exported artifact")
        validator.validate_visual_capture(capture, "exported visual capture")
    except validator.ValidationError as error:
        raise ExportError(str(error)) from error
    receipt = {
        "schema": {
            "name": "skyrim-render-map.csx-capture-export-receipt",
            "major": 1,
            "minor": 0,
        },
        "generatedBy": {
            "name": "skyrim-render-map.export-csx-capture",
            "version": TOOL_VERSION,
        },
        "planSha256": plan_sha256,
        "sourceManifestSha256": inspected["manifestSha256"],
        "artifactSha256": bundle_sha,
        "artifactFile": f"artifacts/{bundle_sha}.zip",
        "retainedFrameCount": len(inspected["frames"]),
        "droppedFrameCount": inspected["dropped"],
        "validityState": validity_state,
        "containsSourcePaths": False,
    }
    return artifact, capture, receipt, bundle_seal


def _jsonl_bytes(records: list[dict]) -> bytes:
    return "".join(compiler.canonical_json(record) + "\n" for record in records).encode(
        "utf-8"
    )


def _seal_public_stage(
    staging: pathlib.Path,
    expected_root_identity: tuple[int, int],
    artifact_sha256: str,
    bundle_seal: dict,
    expected_public_bytes: dict[str, bytes],
) -> dict:
    expected_paths = {
        f"artifacts/{artifact_sha256}.zip",
        "content/artifacts.jsonl",
        "content/visual-captures.jsonl",
        "export-receipt.json",
        "public-preview.json",
    }
    snapshot = _snapshot_stage(staging, scan_public=True)
    if snapshot["directories"]["."]["identity"] != expected_root_identity:
        raise ExportError("publication stage root identity changed before sealing")
    if set(snapshot["directories"]) != {".", "artifacts", "content"}:
        raise ExportError("publication stage has an unexpected directory set")
    if set(snapshot["files"]) != expected_paths:
        raise ExportError("publication stage has an unexpected member set")
    artifact_path = f"artifacts/{artifact_sha256}.zip"
    if snapshot["files"][artifact_path] != bundle_seal:
        raise ExportError("capture bundle identity changed before publication")
    for relative, expected in expected_public_bytes.items():
        seal = snapshot["files"][relative]
        if (
            seal["bytes"] != len(expected)
            or seal["sha256"] != hashlib.sha256(expected).hexdigest()
        ):
            raise ExportError(
                f"generated public record changed before publication: {relative}"
            )
    return snapshot


def _withdraw_owned_publication(
    output: pathlib.Path,
    staging: pathlib.Path,
    expected_identity: tuple[int, int],
) -> None:
    if _directory_identity(output, "published output") != expected_identity:
        raise ExportError("published output custody is uncertain; root identity changed")
    if staging.exists():
        raise ExportError("published output cannot be withdrawn; staging path is occupied")
    try:
        os.rename(output, staging)
    except OSError as error:
        raise ExportError(f"published output could not be withdrawn: {error}") from error
    if _directory_identity(staging, "withdrawn publication") != expected_identity:
        try:
            if not output.exists():
                os.rename(staging, output)
        except OSError as restore_error:
            raise ExportError(
                "published output custody changed during withdrawal and restoration failed: "
                f"{restore_error}"
            ) from restore_error
        raise ExportError("published output custody changed during withdrawal")


def _observe_directory(path: pathlib.Path, context: str) -> tuple[str, tuple[int, int] | None]:
    try:
        return "present", _directory_identity(path, context)
    except ExportError as error:
        if not os.path.lexists(path):
            return "absent", None
        raise ExportError(f"{context} custody could not be established: {error}") from error


def _publish_no_clobber(
    staging: pathlib.Path,
    output: pathlib.Path,
    expected_snapshot: dict,
    expected_identity: tuple[int, int],
) -> None:
    """Atomically publish a directory while refusing an existing destination."""
    _require_stage_snapshot(staging, expected_snapshot)
    if expected_snapshot["directories"]["."]["identity"] != expected_identity:
        raise ExportError("validated stage does not have its creation-time identity")
    try:
        if os.name == "nt":
            os.rename(staging, output)
        elif sys.platform.startswith("linux"):
            library = ctypes.CDLL(None, use_errno=True)
            renameat2 = getattr(library, "renameat2", None)
            if renameat2 is None:
                raise ExportError("atomic no-clobber publication is unavailable")
            renameat2.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            renameat2.restype = ctypes.c_int
            result = renameat2(
                -100,
                os.fsencode(staging),
                -100,
                os.fsencode(output),
                1,
            )
            if result != 0:
                error_number = ctypes.get_errno()
                if error_number in {errno.ENOSYS, errno.EINVAL}:
                    raise ExportError("atomic no-clobber publication is unavailable")
                raise OSError(error_number, os.strerror(error_number), str(output))
        elif sys.platform == "darwin":
            library = ctypes.CDLL(None, use_errno=True)
            renamex_np = getattr(library, "renamex_np", None)
            if renamex_np is None:
                raise ExportError("atomic no-clobber publication is unavailable")
            renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
            renamex_np.restype = ctypes.c_int
            if renamex_np(os.fsencode(staging), os.fsencode(output), 0x00000004) != 0:
                error_number = ctypes.get_errno()
                raise OSError(error_number, os.strerror(error_number), str(output))
        else:
            raise ExportError("atomic no-clobber publication is unavailable")
        published_snapshot = _snapshot_stage(output)
        if (
            published_snapshot["directories"]["."]["identity"] != expected_identity
            or published_snapshot != expected_snapshot
        ):
            raise ExportError("published output differs from the validated stage")
    except BaseException as error:
        try:
            stage_state, stage_identity = _observe_directory(
                staging, "publication staging"
            )
            output_state, output_identity = _observe_directory(
                output, "published output"
            )
        except ExportError as custody_error:
            raise ExportError(
                f"publication transition failed: {error}; {custody_error}"
            ) from error
        if output_identity == expected_identity and stage_state == "absent":
            try:
                _withdraw_owned_publication(output, staging, expected_identity)
            except ExportError as withdrawal_error:
                raise ExportError(
                    f"publication transition failed: {error}; "
                    f"withdrawal failed: {withdrawal_error}"
                ) from error
            raise
        if stage_identity == expected_identity and output_identity != expected_identity:
            if isinstance(error, FileExistsError) or (
                isinstance(error, OSError)
                and error.errno in {errno.EEXIST, errno.ENOTEMPTY, errno.EACCES}
                and output.exists()
            ):
                raise ExportError(f"output already exists: {output}") from error
            if isinstance(error, OSError):
                raise ExportError(f"cannot publish export: {error}") from error
            raise
        raise ExportError(
            "publication transition failed with uncertain stage/output custody: "
            f"{error}; stage={stage_state}, output={output_state}"
        ) from error


def _windows_mark_delete(handle: int) -> None:
    class FileDispositionInformation(ctypes.Structure):
        _fields_ = [("DeleteFile", ctypes.c_int)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_information = kernel32.SetFileInformationByHandle
    set_information.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    set_information.restype = ctypes.c_int
    information = FileDispositionInformation(1)
    if not set_information(
        ctypes.c_void_p(handle),
        4,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        raise ExportError(
            "cannot delete owned path by handle: Windows error "
            f"{ctypes.get_last_error()}"
        )


def _close_windows_handles(handles: dict[str, int]) -> None:
    first_error = None
    for relative, handle in list(handles.items()):
        try:
            _windows_close_handle(handle)
        except ExportError as error:
            if first_error is None:
                first_error = ExportError(f"cannot close owned path {relative!r}: {error}")
        finally:
            handles.pop(relative, None)
    if first_error is not None:
        raise first_error


def _windows_delete_owned_tree(
    root: pathlib.Path,
    expected_identity: tuple[int, int],
    owned_children: dict[str, tuple[int, int]],
) -> None:
    directory_handles: dict[str, int] = {}
    file_handles: dict[str, int] = {}
    try:
        root_handle = _windows_open_path_handle(
            root, delete=True, deny_delete_sharing=True
        )
        directory_handles["."] = root_handle
        if _windows_handle_identity(root_handle) != expected_identity:
            raise ExportError("owned cleanup root identity changed before deletion")

        directories, files = _inventory_stage(root)
        if directories["."]["identity"] != expected_identity:
            raise ExportError("owned cleanup root identity changed during enumeration")
        file_identities = {
            relative: _windows_path_identity(root / relative) for relative in files
        }
        for relative in sorted(set(directories) - {"."}):
            handle = _windows_open_path_handle(
                root / relative, delete=True, deny_delete_sharing=True
            )
            directory_handles[relative] = handle
            if _windows_handle_identity(handle) != directories[relative]["identity"]:
                raise ExportError(
                    f"owned cleanup directory {relative!r} changed before deletion"
                )
        for relative in files:
            handle = _windows_open_path_handle(
                root / relative, delete=True, deny_delete_sharing=True
            )
            file_handles[relative] = handle
            if _windows_handle_identity(handle) != file_identities[relative]:
                raise ExportError(
                    f"owned cleanup file {relative!r} changed before deletion"
                )

        final_directories, final_files = _inventory_stage(root)
        if final_directories != directories or final_files != files:
            raise ExportError("owned cleanup tree changed before deletion")
        for relative, child_identity in owned_children.items():
            handle = directory_handles.get(relative)
            if handle is None or _windows_handle_identity(handle) != child_identity:
                raise ExportError(
                    f"owned cleanup child {relative!r} custody is uncertain"
                )

        for relative in sorted(file_handles):
            handle = file_handles.pop(relative)
            _windows_mark_delete(handle)
            _windows_close_handle(handle)
        for relative in sorted(
            directory_handles,
            key=lambda value: (value != ".") + value.count("/"),
            reverse=True,
        ):
            handle = directory_handles.pop(relative)
            _windows_mark_delete(handle)
            _windows_close_handle(handle)
    except BaseException as error:
        try:
            _close_windows_handles(file_handles)
            _close_windows_handles(directory_handles)
        except ExportError as close_error:
            error.add_note(str(close_error))
        raise


def _delete_owned_tree(
    root: pathlib.Path,
    expected_identity: tuple[int, int],
    owned_children: dict[str, tuple[int, int]],
) -> None:
    if os.name == "nt":
        _windows_delete_owned_tree(root, expected_identity, owned_children)
        return
    if not shutil.rmtree.avoids_symlink_attacks:
        raise ExportError("object-bound recursive cleanup is unavailable")
    if _directory_identity(root, "owned cleanup root") != expected_identity:
        raise ExportError("owned cleanup root identity changed before deletion")
    for relative, child_identity in owned_children.items():
        if _directory_identity(root / relative, "owned cleanup child") != child_identity:
            raise ExportError(f"owned cleanup child {relative!r} custody is uncertain")
    try:
        shutil.rmtree(root)
    except OSError as error:
        raise ExportError(f"cannot remove owned cleanup tree: {error}") from error


def _remove_private_staging(
    path: pathlib.Path,
    context: str,
    expected_identity: tuple[int, int],
    owned_children: dict[pathlib.Path, tuple[int, int]] | None = None,
) -> None:
    relative_children = {}
    for child, child_identity in (owned_children or {}).items():
        try:
            relative = child.relative_to(path).as_posix()
        except ValueError as error:
            raise ExportError(f"cannot remove {context}: child is outside owner") from error
        if _directory_identity(child, f"{context} child") != child_identity:
            raise ExportError(f"cannot remove {context}: child custody is uncertain")
        relative_children[relative] = child_identity
    quarantine = path.parent / f".{path.name}.cleanup-{uuid.uuid4().hex}"
    if quarantine.exists():
        raise ExportError(f"cannot remove {context}: cleanup path already exists")
    try:
        os.rename(path, quarantine)
    except FileNotFoundError as error:
        raise ExportError(f"cannot remove {context}: owned directory is absent") from error
    except OSError as error:
        raise ExportError(f"cannot remove {context}: {error}") from error
    actual_identity = _directory_identity(quarantine, context)
    if actual_identity != expected_identity:
        try:
            if not path.exists():
                os.rename(quarantine, path)
        except OSError as restore_error:
            raise ExportError(
                f"cannot remove {context}: ownership changed and restoration failed: "
                f"{restore_error}"
            ) from restore_error
        raise ExportError(f"cannot remove {context}: pathname identified another directory")
    _delete_owned_tree(quarantine, expected_identity, relative_children)
    if quarantine.exists():
        raise ExportError(f"cannot remove {context}")


def export_plan(plan_path: pathlib.Path, output: pathlib.Path) -> dict:
    staging: pathlib.Path | None = None
    staging_identity: tuple[int, int] | None = None
    owned_children: dict[pathlib.Path, tuple[int, int]] = {}
    try:
        plan_path = plan_path.resolve()
        plan_document, plan_sha256 = _load_json_document(
            plan_path, "capture export plan"
        )
        plan = _validate_plan(plan_document)
        output = output.resolve()
        if output.exists():
            raise ExportError(f"output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = pathlib.Path(
            tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent)
        )
        staging_identity = _directory_identity(staging, "export staging")
        spool_directory = staging / ".private-source"
        spool_directory.mkdir()
        spool_identity = _directory_identity(spool_directory, "private source staging")
        owned_children[spool_directory] = spool_identity
        temporary_bundle = staging / "capture-bundle.zip"
        artifact, capture, receipt, bundle_seal = _build_records(
            plan_path, plan, plan_sha256, temporary_bundle, spool_directory
        )
        _remove_private_staging(
            spool_directory, "private source staging", spool_identity
        )
        owned_children.pop(spool_directory)
        artifact_directory = staging / "artifacts"
        artifact_directory.mkdir()
        final_bundle = artifact_directory / f"{artifact['artifactSha256']}.zip"
        temporary_bundle.replace(final_bundle)
        _, relocated_bundle_seal = _read_sealed_file(final_bundle)
        if relocated_bundle_seal != bundle_seal:
            raise ExportError("capture bundle identity changed during staging")
        content = staging / "content"
        content.mkdir()
        expected_public_bytes = {
            "content/artifacts.jsonl": _jsonl_bytes([artifact]),
            "content/visual-captures.jsonl": _jsonl_bytes([capture]),
            "public-preview.json": _canonical_json_bytes(
                {"artifacts": [artifact], "visualCaptures": [capture]}
            ),
            "export-receipt.json": _canonical_json_bytes(receipt),
        }
        for relative, data in expected_public_bytes.items():
            (staging / relative).write_bytes(data)
        stage_snapshot = _seal_public_stage(
            staging,
            staging_identity,
            artifact["artifactSha256"],
            bundle_seal,
            expected_public_bytes,
        )
        _publish_no_clobber(
            staging, output, stage_snapshot, staging_identity
        )
        staging = None
        staging_identity = None
    except BaseException as error:
        cleanup_error = None
        if staging is not None and staging_identity is not None:
            try:
                _remove_private_staging(
                    staging,
                    "export staging",
                    staging_identity,
                    owned_children=owned_children,
                )
            except ExportError as caught:
                cleanup_error = caught
        if cleanup_error is not None:
            raise ExportError(f"{error}; cleanup failed: {cleanup_error}") from error
        if isinstance(error, (ExportError, KeyboardInterrupt, SystemExit)):
            raise
        raise ExportError(f"capture export failed: {error}") from error
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = export_plan(args.plan, args.output)
    except (ExportError, validator.ValidationError) as error:
        print(f"export failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
