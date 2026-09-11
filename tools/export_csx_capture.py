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
import stat
import struct
import sys
import uuid
import zipfile
import zlib
from dataclasses import dataclass, field
from typing import Any

import compile_dataset as compiler
import validate_repository as validator


TOOL_VERSION = "1.0.8"
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


def _format_exception_diagnostics(error: BaseException) -> str:
    messages = [str(error)]
    seen_exceptions: set[int] = set()
    seen_messages = {messages[0]}
    current: BaseException | None = error
    while current is not None and id(current) not in seen_exceptions:
        seen_exceptions.add(id(current))
        if current is not error:
            cause_message = f"caused by: {current}"
            if cause_message not in seen_messages:
                messages.append(cause_message)
                seen_messages.add(cause_message)
        for note in getattr(current, "__notes__", ()):
            text = str(note)
            if text and text not in seen_messages:
                messages.append(text)
                seen_messages.add(text)
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    return " | ".join(messages)


def _attach_exception_diagnostics(
    target: BaseException, source: BaseException, label: str
) -> None:
    target.add_note(f"{label}: {_format_exception_diagnostics(source)}")


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


def _windows_open_owner_directory(path: pathlib.Path, context: str) -> int:
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
    handle = create_file(
        str(path),
        0x00000001 | 0x00000004 | 0x00000020 | 0x00000040 | 0x00000080,
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,
        0x02000000,
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ExportError(
            f"cannot hold {context}: Windows error {ctypes.get_last_error()}"
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


def _windows_list_directory_entries(
    handle: int, context: str
) -> list[tuple[str, int, int]]:
    class FileIdBothDirectoryInformation(ctypes.Structure):
        _fields_ = [
            ("NextEntryOffset", ctypes.c_uint32),
            ("FileIndex", ctypes.c_uint32),
            ("CreationTime", ctypes.c_int64),
            ("LastAccessTime", ctypes.c_int64),
            ("LastWriteTime", ctypes.c_int64),
            ("ChangeTime", ctypes.c_int64),
            ("EndOfFile", ctypes.c_int64),
            ("AllocationSize", ctypes.c_int64),
            ("FileAttributes", ctypes.c_uint32),
            ("FileNameLength", ctypes.c_uint32),
            ("EaSize", ctypes.c_uint32),
            ("ShortNameLength", ctypes.c_ubyte),
            ("ShortName", ctypes.c_wchar * 12),
            ("FileId", ctypes.c_int64),
            ("FileName", ctypes.c_wchar * 1),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandleEx
    get_information.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    get_information.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(64 * 1024)
    entries: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    information_class = 11
    while True:
        if not get_information(
            ctypes.c_void_p(handle), information_class, buffer, len(buffer)
        ):
            error_number = ctypes.get_last_error()
            if error_number == 18:
                break
            raise ExportError(
                f"cannot enumerate {context}: Windows error {error_number}"
            )
        information_class = 10
        offset = 0
        while True:
            item = FileIdBothDirectoryInformation.from_buffer(buffer, offset)
            name = ctypes.string_at(
                ctypes.addressof(buffer)
                + offset
                + FileIdBothDirectoryInformation.FileName.offset,
                item.FileNameLength,
            ).decode("utf-16-le")
            if name not in {".", ".."}:
                folded = name.casefold()
                if folded in seen:
                    raise ExportError(f"{context} contains a duplicate member name")
                seen.add(folded)
                entries.append(
                    (
                        name,
                        int(item.FileAttributes),
                        int(item.FileId) & 0xFFFFFFFFFFFFFFFF,
                    )
                )
            if item.NextEntryOffset == 0:
                break
            offset += item.NextEntryOffset
            if offset >= len(buffer):
                raise ExportError(f"cannot enumerate {context}: invalid entry offset")
    return sorted(entries, key=lambda item: item[0].casefold())


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


def _windows_final_path(handle: int) -> pathlib.Path:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_name = kernel32.GetFinalPathNameByHandleW
    get_name.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
    ]
    get_name.restype = ctypes.c_uint32
    required = get_name(ctypes.c_void_p(handle), None, 0, 0)
    if not required:
        raise ExportError(
            "cannot resolve owned directory handle: Windows error "
            f"{ctypes.get_last_error()}"
        )
    buffer = ctypes.create_unicode_buffer(required + 1)
    written = get_name(ctypes.c_void_p(handle), buffer, len(buffer), 0)
    if not written or written >= len(buffer):
        raise ExportError(
            "cannot resolve owned directory handle: Windows error "
            f"{ctypes.get_last_error()}"
        )
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return pathlib.Path(value)


def _stream_identity(stream) -> tuple[int, int]:
    if os.name == "nt":
        import msvcrt

        return _windows_handle_identity(msvcrt.get_osfhandle(stream.fileno()))
    return _file_identity(os.fstat(stream.fileno()))


def _windows_nt_status_error(status: int) -> int:
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    convert_status = ntdll.RtlNtStatusToDosError
    convert_status.argtypes = [ctypes.c_long]
    convert_status.restype = ctypes.c_uint32
    return int(convert_status(ctypes.c_long(status)))


def _windows_nt_open_relative(
    parent_handle: int,
    name: str,
    *,
    desired_access: int,
    share_access: int,
    disposition: int,
    create_options: int,
    file_attributes: int,
    context: str,
) -> tuple[int, int]:
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ExportError(f"cannot access {context}: invalid relative member name")

    class UnicodeString(ctypes.Structure):
        _fields_ = [
            ("Length", ctypes.c_ushort),
            ("MaximumLength", ctypes.c_ushort),
            ("Buffer", ctypes.POINTER(ctypes.c_wchar)),
        ]

    class ObjectAttributes(ctypes.Structure):
        _fields_ = [
            ("Length", ctypes.c_uint32),
            ("RootDirectory", ctypes.c_void_p),
            ("ObjectName", ctypes.POINTER(UnicodeString)),
            ("Attributes", ctypes.c_uint32),
            ("SecurityDescriptor", ctypes.c_void_p),
            ("SecurityQualityOfService", ctypes.c_void_p),
        ]

    class IoStatusBlock(ctypes.Structure):
        _fields_ = [
            ("Status", ctypes.c_void_p),
            ("Information", ctypes.c_size_t),
        ]

    name_buffer = ctypes.create_unicode_buffer(name)
    object_name = UnicodeString(
        len(name.encode("utf-16-le")),
        ctypes.sizeof(name_buffer),
        ctypes.cast(name_buffer, ctypes.POINTER(ctypes.c_wchar)),
    )
    attributes = ObjectAttributes(
        ctypes.sizeof(ObjectAttributes),
        parent_handle,
        ctypes.pointer(object_name),
        0x00000040,
        None,
        None,
    )
    status_block = IoStatusBlock()
    returned_handle = ctypes.c_void_p()
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    nt_create_file = ntdll.NtCreateFile
    nt_create_file.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_uint32,
        ctypes.POINTER(ObjectAttributes),
        ctypes.POINTER(IoStatusBlock),
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    nt_create_file.restype = ctypes.c_long
    status = int(
        nt_create_file(
            ctypes.byref(returned_handle),
            desired_access,
            ctypes.byref(attributes),
            ctypes.byref(status_block),
            None,
            file_attributes,
            share_access,
            disposition,
            create_options,
            None,
            0,
        )
    )
    if status < 0:
        error_number = _windows_nt_status_error(status)
        if ctypes.c_uint32(status).value == 0xC0000035:
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), name)
        raise ExportError(f"cannot access {context}: Windows error {error_number}")
    if returned_handle.value is None:
        raise ExportError(f"cannot access {context}: Windows returned no handle")
    return int(returned_handle.value), int(status_block.Information)


def _windows_rename_handle(
    handle: int, target_parent_handle: int, target_name: str, context: str
) -> None:
    if not target_name or target_name in {".", ".."} or any(
        separator in target_name for separator in ("/", "\\")
    ):
        raise ExportError(f"cannot rename {context}: invalid destination name")

    class FileRenameInformation(ctypes.Structure):
        _fields_ = [
            ("Flags", ctypes.c_uint32),
            ("RootDirectory", ctypes.c_void_p),
            ("FileNameLength", ctypes.c_uint32),
            ("FileName", ctypes.c_wchar * 1),
        ]

    encoded_name = target_name.encode("utf-16-le")
    rename_buffer = ctypes.create_string_buffer(
        FileRenameInformation.FileName.offset + len(encoded_name) + 2
    )
    rename = ctypes.cast(
        rename_buffer, ctypes.POINTER(FileRenameInformation)
    ).contents
    rename.Flags = 0
    rename.RootDirectory = target_parent_handle
    rename.FileNameLength = len(encoded_name)
    ctypes.memmove(
        ctypes.addressof(rename_buffer) + FileRenameInformation.FileName.offset,
        encoded_name,
        len(encoded_name),
    )
    class IoStatusBlock(ctypes.Structure):
        _fields_ = [
            ("Status", ctypes.c_void_p),
            ("Information", ctypes.c_size_t),
        ]

    status_block = IoStatusBlock()
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    set_information = ntdll.NtSetInformationFile
    set_information.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(IoStatusBlock),
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
    ]
    set_information.restype = ctypes.c_long
    status = int(
        set_information(
            ctypes.c_void_p(handle),
            ctypes.byref(status_block),
            rename_buffer,
            len(rename_buffer),
            10,
        )
    )
    if status < 0:
        error_number = _windows_nt_status_error(status)
        if ctypes.c_uint32(status).value in {0xC0000035, 0xC00000BA}:
            raise FileExistsError(
                errno.EEXIST, os.strerror(errno.EEXIST), target_name
            )
        raise ExportError(f"cannot rename {context}: Windows error {error_number}")


_UNRESOLVED_WINDOWS_OWNED_TREES: list[Any] = []
_UNRESOLVED_WINDOWS_CLEANUP_OWNERS: list[Any] = []


def _retain_unresolved_handle(
    context: str,
    handle: int,
    identity: tuple[int, int] | None,
    diagnostic_target: BaseException,
) -> None:
    if identity is None:
        try:
            identity = _windows_handle_identity(handle)
        except BaseException as identity_error:
            _attach_exception_diagnostics(
                diagnostic_target,
                identity_error,
                f"cannot identify retained {context}",
            )
    owner = _WindowsHandleOwner(context)
    owner.add(context, handle, identity)
    owner.retain()


@dataclass
class _WindowsHandleOwner:
    context: str
    handles: dict[str, int] = field(default_factory=dict)
    identities: dict[str, tuple[int, int] | None] = field(default_factory=dict)
    _retained: bool = False

    def add(
        self, key: str, handle: int, identity: tuple[int, int] | None
    ) -> None:
        if key in self.handles:
            raise ExportError(f"duplicate retained handle key: {key!r}")
        self.handles[key] = handle
        self.identities[key] = identity

    def retain(self) -> None:
        if not self._retained:
            _UNRESOLVED_WINDOWS_CLEANUP_OWNERS.append(self)
            self._retained = True

    def close(self) -> None:
        failures: list[tuple[str, BaseException]] = []
        for key, handle in list(self.handles.items()):
            try:
                _windows_close_handle(handle)
            except BaseException as error:
                failures.append((key, error))
            else:
                self.handles.pop(key)
                self.identities.pop(key, None)
        if self.handles and not self._retained:
            self.retain()
        elif not self.handles and self._retained:
            try:
                _UNRESOLVED_WINDOWS_CLEANUP_OWNERS.remove(self)
            except ValueError:
                pass
            self._retained = False
        if failures:
            error = ExportError(
                f"cannot release {self.context}; unresolved handles: "
                + ", ".join(repr(key) for key, _ in failures)
            )
            for key, failure in failures:
                _attach_exception_diagnostics(error, failure, f"handle {key!r}")
            raise error from failures[0][1]


@dataclass
class _WindowsOwnedTree:
    parent: pathlib.Path
    parent_handle: int | None
    root: pathlib.Path
    root_identity: tuple[int, int]
    directory_handles: dict[str, int]
    directories: dict[str, tuple[int, int]]
    files: dict[str, tuple[int, int]] = field(default_factory=dict)
    _retained: bool = False

    @classmethod
    def create_unique(
        cls, parent: pathlib.Path, prefix: str, context: str
    ) -> "_WindowsOwnedTree":
        parent_handle = _windows_open_owner_directory(parent, f"{context} parent")
        try:
            parent_information = _windows_handle_information(parent_handle)
            if not parent_information["attributes"] & 0x00000010 or (
                parent_information["attributes"] & 0x00000400
            ):
                raise ExportError(
                    f"cannot create {context}: parent is not an ordinary directory"
                )
            for _ in range(16):
                path = parent / f"{prefix}{uuid.uuid4().hex}"
                handle: int | None = None
                identity: tuple[int, int] | None = None
                try:
                    handle, creation_result = _windows_nt_open_relative(
                        parent_handle,
                        path.name,
                        desired_access=(
                            0x00100000
                            | 0x00010000
                            | 0x00000080
                            | 0x00000020
                            | 0x00000001
                            | 0x00000002
                        ),
                        share_access=0x00000001 | 0x00000002 | 0x00000004,
                        disposition=2,
                        create_options=0x00000001,
                        file_attributes=0x00000010,
                        context=f"{context} at {path}",
                    )
                except FileExistsError:
                    continue
                if creation_result != 2:
                    raise ExportError(
                        f"cannot create {context} at {path}: directory was not newly created"
                    )
                information = _windows_handle_information(handle)
                if not information["attributes"] & 0x00000010 or information[
                    "attributes"
                ] & 0x00000400:
                    raise ExportError(
                        f"cannot create {context} at {path}: member is not a directory"
                    )
                identity = information["identity"]
                return cls(
                    parent,
                    parent_handle,
                    path,
                    identity,
                    {".": handle},
                    {".": identity},
                )
            raise ExportError(f"cannot create unique {context}")
        except BaseException as error:
            if "handle" in locals() and handle is not None:
                try:
                    _windows_mark_delete(handle)
                except BaseException as cleanup_error:
                    _attach_exception_diagnostics(
                        error, cleanup_error, f"failed {context} disposition"
                    )
                try:
                    _windows_close_handle(handle)
                except BaseException as close_error:
                    _retain_unresolved_handle(
                        f"failed {context} handle", handle, identity, error
                    )
                    _attach_exception_diagnostics(
                        error, close_error, f"failed {context} handle"
                    )
            try:
                _windows_close_handle(parent_handle)
            except BaseException as close_error:
                _retain_unresolved_handle(
                    f"failed {context} parent handle",
                    parent_handle,
                    None,
                    error,
                )
                _attach_exception_diagnostics(
                    error, close_error, f"failed {context} parent handle"
                )
            raise

    def _relative(self, path: pathlib.Path | str) -> str:
        candidate = pathlib.Path(path)
        if candidate.is_absolute():
            try:
                candidate = candidate.relative_to(self.root)
            except ValueError as error:
                raise ExportError("owned path is outside the export staging tree") from error
        relative = candidate.as_posix().strip("/")
        if relative in {"", "."}:
            return "."
        parts = pathlib.PurePosixPath(relative).parts
        if any(part in {"", ".", ".."} for part in parts):
            raise ExportError("owned path is not a canonical relative member")
        return "/".join(parts)

    def _parent(self, relative: str) -> tuple[int, str]:
        member = pathlib.PurePosixPath(relative)
        parent = member.parent.as_posix()
        if parent == ".":
            parent = "."
        handle = self.directory_handles.get(parent)
        if handle is None:
            raise ExportError(
                f"owned parent directory {parent!r} is not held for mutation"
            )
        return handle, member.name

    def create_directory(self, path: pathlib.Path | str, context: str) -> None:
        relative = self._relative(path)
        if relative == "." or relative in self.directories or relative in self.files:
            raise ExportError(f"cannot create {context}: member already exists")
        parent_handle, name = self._parent(relative)
        handle: int | None = None
        handle_identity: tuple[int, int] | None = None
        try:
            handle, creation_result = _windows_nt_open_relative(
                parent_handle,
                name,
                desired_access=(
                    0x00100000
                    | 0x00010000
                    | 0x00000080
                    | 0x00000020
                    | 0x00000001
                    | 0x00000002
                ),
                share_access=0x00000001 | 0x00000002 | 0x00000004,
                disposition=2,
                create_options=0x00000001,
                file_attributes=0x00000010,
                context=context,
            )
            if creation_result != 2:
                raise ExportError(f"cannot create {context}: member was not newly created")
            information = _windows_handle_information(handle)
            if not information["attributes"] & 0x00000010 or information[
                "attributes"
            ] & 0x00000400:
                raise ExportError(f"cannot create {context}: member is not a directory")
            self.directory_handles[relative] = handle
            handle_identity = information["identity"]
            self.directories[relative] = handle_identity
            handle = None
        except BaseException as error:
            if handle is not None:
                try:
                    _windows_close_handle(handle)
                except BaseException as close_error:
                    _retain_unresolved_handle(
                        f"failed {context} handle",
                        handle,
                        handle_identity,
                        error,
                    )
                    _attach_exception_diagnostics(
                        error, close_error, f"cannot release failed {context} handle"
                    )
            raise

    def _file_stream(
        self, path: pathlib.Path | str, *, create: bool, context: str
    ):
        import msvcrt

        relative = self._relative(path)
        if relative == ".":
            raise ExportError(f"cannot access {context}: path identifies the root")
        if create and (relative in self.files or relative in self.directories):
            raise ExportError(f"cannot create {context}: member already exists")
        expected_identity = self.files.get(relative)
        if not create and expected_identity is None:
            raise ExportError(f"cannot open {context}: member is not exporter-owned")
        parent_handle, name = self._parent(relative)
        handle: int | None = None
        descriptor: int | None = None
        identity: tuple[int, int] | None = None
        try:
            handle, creation_result = _windows_nt_open_relative(
                parent_handle,
                name,
                desired_access=(
                    0x80000000
                    | 0x40000000
                    | 0x00100000
                    | 0x00010000
                    | 0x00000080
                ),
                share_access=0x00000001 | 0x00000002 | 0x00000004,
                disposition=2 if create else 1,
                create_options=0x00000040 | 0x00000020,
                file_attributes=0x00000080,
                context=context,
            )
            if create and creation_result != 2:
                raise ExportError(f"cannot create {context}: member was not newly created")
            information = _windows_handle_information(handle)
            if information["attributes"] & (0x00000010 | 0x00000400):
                raise ExportError(f"cannot access {context}: member is not an ordinary file")
            identity = information["identity"]
            if expected_identity is not None and identity != expected_identity:
                raise ExportError(f"cannot open {context}: file identity changed")
            descriptor = msvcrt.open_osfhandle(handle, os.O_BINARY | os.O_RDWR)
            handle = None
            stream = os.fdopen(descriptor, "w+b" if create else "r+b")
            descriptor = None
            if create:
                self.files[relative] = identity
            return stream
        except BaseException as error:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except BaseException as close_error:
                    _attach_exception_diagnostics(
                        error, close_error, f"cannot release failed {context} descriptor"
                    )
            if handle is not None:
                try:
                    _windows_close_handle(handle)
                except BaseException as close_error:
                    _retain_unresolved_handle(
                        f"failed {context} handle", handle, identity, error
                    )
                    _attach_exception_diagnostics(
                        error, close_error, f"cannot release failed {context} handle"
                    )
            raise

    def create_file(self, path: pathlib.Path | str, context: str):
        return self._file_stream(path, create=True, context=context)

    def open_file(self, path: pathlib.Path | str, context: str):
        return self._file_stream(path, create=False, context=context)

    def ensure_directory_handles(self, path: pathlib.Path | str = ".") -> None:
        prefix = self._relative(path)
        if "." not in self.directory_handles:
            raise ExportError("publication root owner is no longer retained")
        for relative in sorted(
            self.directories,
            key=lambda value: (value != ".") + value.count("/"),
        ):
            if relative == "." or relative in self.directory_handles:
                continue
            if prefix != "." and not (
                relative == prefix or relative.startswith(prefix + "/")
            ):
                continue
            parent_handle, name = self._parent(relative)
            handle: int | None = None
            try:
                handle, _ = _windows_nt_open_relative(
                    parent_handle,
                    name,
                    desired_access=(
                        0x00100000
                        | 0x00010000
                        | 0x00000080
                        | 0x00000020
                        | 0x00000001
                        | 0x00000002
                    ),
                    share_access=0x00000001 | 0x00000002 | 0x00000004,
                    disposition=1,
                    create_options=0x00000001,
                    file_attributes=0,
                    context=f"owned directory {relative!r}",
                )
                information = _windows_handle_information(handle)
                if not information["attributes"] & 0x00000010 or information[
                    "attributes"
                ] & 0x00000400:
                    raise ExportError(
                        f"owned directory {relative!r} is not an ordinary directory"
                    )
                if information["identity"] != self.directories[relative]:
                    raise ExportError(
                        f"owned directory {relative!r} identity changed"
                    )
                self.directory_handles[relative] = handle
                handle = None
            except BaseException as error:
                if handle is not None:
                    try:
                        _windows_close_handle(handle)
                    except BaseException as close_error:
                        _retain_unresolved_handle(
                            f"failed directory {relative!r}",
                            handle,
                            self.directories[relative],
                            error,
                        )
                        _attach_exception_diagnostics(
                            error,
                            close_error,
                            f"cannot release failed directory {relative!r}",
                        )
                raise

    def inventory(
        self, path: pathlib.Path | str = "."
    ) -> tuple[dict[str, dict], list[str]]:
        prefix = self._relative(path)
        self.ensure_directory_handles(prefix)
        selected_directories, selected_files = self.subtree_ledgers(prefix)
        directory_seals: dict[str, dict] = {}
        actual_directories: set[str] = {"."}
        actual_files: set[str] = set()
        prefix_path = pathlib.PurePosixPath(prefix) if prefix != "." else None

        def global_relative(local: str) -> str:
            if prefix_path is None:
                return local
            if local == ".":
                return prefix
            return (prefix_path / local).as_posix()

        root_relative = global_relative(".")
        root_handle = self.directory_handles[root_relative]
        if root_relative == ".":
            if self.parent_handle is None:
                raise ExportError("publication parent owner is no longer retained")
            watch_parent, watch_name = self.parent_handle, self.root.name
        else:
            watch_parent, watch_name = self._parent(root_relative)
        with _directory_membership_guard(
            self.root,
            owner_parent_handle=watch_parent,
            owner_name=watch_name,
        ):
            for local_relative, expected_identity in sorted(
                selected_directories.items()
            ):
                relative = global_relative(local_relative)
                handle = self.directory_handles.get(relative)
                if handle is None:
                    raise ExportError(
                        f"owned directory {relative!r} is not retained for inspection"
                    )
                information = _windows_handle_information(handle)
                if not information["attributes"] & 0x00000010 or information[
                    "attributes"
                ] & 0x00000400:
                    raise ExportError(
                        f"owned directory {relative!r} is not an ordinary directory"
                    )
                if information["identity"] != expected_identity:
                    raise ExportError(
                        f"owned directory {relative!r} identity changed"
                    )
                directory_seals[local_relative] = {
                    key: information[key]
                    for key in ("identity", "mtimeNs", "ctimeNs", "size", "links")
                }
                for name, attributes, file_id in _windows_list_directory_entries(
                    handle, f"owned directory {relative!r}"
                ):
                    local_child = (
                        name
                        if local_relative == "."
                        else f"{local_relative}/{name}"
                    )
                    if attributes & 0x00000400:
                        raise ExportError(
                            "publication stage contains a reparse-point member"
                        )
                    if attributes & 0x00000010:
                        actual_directories.add(local_child)
                        expected_child = selected_directories.get(local_child)
                    else:
                        actual_files.add(local_child)
                        expected_child = selected_files.get(local_child)
                    if expected_child is not None and expected_child[1] != file_id:
                        raise ExportError(
                            f"owned member {local_child!r} identity changed"
                        )
            if actual_directories != set(selected_directories) or actual_files != set(
                selected_files
            ):
                raise ExportError(
                    "owned tree contains untracked, missing, or mistyped members; "
                    f"directories={sorted(actual_directories)!r}, "
                    f"expectedDirectories={sorted(selected_directories)!r}, "
                    f"files={sorted(actual_files)!r}, "
                    f"expectedFiles={sorted(selected_files)!r}"
                )
            for local_relative, seal in directory_seals.items():
                information = _windows_handle_information(
                    self.directory_handles[global_relative(local_relative)]
                )
                current = {
                    key: information[key]
                    for key in ("identity", "mtimeNs", "ctimeNs", "size", "links")
                }
                if current != seal:
                    raise ExportError(
                        "publication stage membership changed during enumeration"
                    )
        return directory_seals, sorted(actual_files)

    def rename_root(self, destination: pathlib.Path, context: str) -> None:
        destination = destination.resolve()
        if destination.parent != self.parent.resolve():
            raise ExportError(f"cannot rename {context}: destination parent changed")
        if self.parent_handle is None or "." not in self.directory_handles:
            raise ExportError(f"cannot rename {context}: owner handle is unavailable")
        release_failures: list[tuple[str, BaseException]] = []
        for relative in sorted(
            set(self.directory_handles) - {"."},
            key=lambda value: value.count("/"),
            reverse=True,
        ):
            try:
                _windows_close_handle(self.directory_handles[relative])
            except BaseException as error:
                release_failures.append((relative, error))
            else:
                self.directory_handles.pop(relative)
        if release_failures:
            self._update_retention()
            error = ExportError(
                f"cannot rename {context}: cannot release descendant owner handles"
            )
            for relative, failure in release_failures:
                _attach_exception_diagnostics(
                    error, failure, f"directory {relative!r}"
                )
            raise error from release_failures[0][1]
        root_handle = self.directory_handles["."]
        try:
            _windows_rename_handle(
                root_handle, self.parent_handle, destination.name, context
            )
        except BaseException as error:
            try:
                self.root = _windows_final_path(root_handle)
            except BaseException as path_error:
                _attach_exception_diagnostics(
                    error, path_error, f"cannot reconcile {context} destination"
                )
            raise
        self.root = destination

    def move_file(
        self,
        source: pathlib.Path | str,
        destination: pathlib.Path | str,
        context: str,
    ) -> None:
        source_relative = self._relative(source)
        destination_relative = self._relative(destination)
        expected_identity = self.files.get(source_relative)
        if expected_identity is None:
            raise ExportError(f"cannot move {context}: source is not exporter-owned")
        if destination_relative in self.files or destination_relative in self.directories:
            raise ExportError(f"cannot move {context}: destination already exists")
        source_parent, source_name = self._parent(source_relative)
        target_parent, target_name = self._parent(destination_relative)
        handle: int | None = None
        primary_error: BaseException | None = None
        try:
            handle, _ = _windows_nt_open_relative(
                source_parent,
                source_name,
                desired_access=0x00100000 | 0x00010000 | 0x00000080,
                share_access=0x00000001 | 0x00000002 | 0x00000004,
                disposition=1,
                create_options=0x00000040 | 0x00000020,
                file_attributes=0,
                context=context,
            )
            if _windows_handle_identity(handle) != expected_identity:
                raise ExportError(f"cannot move {context}: source identity changed")
            _windows_rename_handle(handle, target_parent, target_name, context)
            self.files[destination_relative] = self.files.pop(source_relative)
        except BaseException as error:
            primary_error = error
        finally:
            if handle is not None:
                try:
                    _windows_close_handle(handle)
                except BaseException as close_error:
                    _retain_unresolved_handle(
                        f"failed {context} handle",
                        handle,
                        expected_identity,
                        primary_error or close_error,
                    )
                    if primary_error is None:
                        primary_error = ExportError(
                            f"cannot release {context} handle: {close_error}"
                        )
                        _attach_exception_diagnostics(
                            primary_error, close_error, f"{context} handle"
                        )
                    else:
                        _attach_exception_diagnostics(
                            primary_error, close_error, f"cannot release {context} handle"
                        )
        if primary_error is not None:
            raise primary_error

    def _update_retention(self) -> None:
        unresolved = self.parent_handle is not None or bool(self.directory_handles)
        if unresolved and not self._retained:
            _UNRESOLVED_WINDOWS_OWNED_TREES.append(self)
            self._retained = True
        elif not unresolved and self._retained:
            try:
                _UNRESOLVED_WINDOWS_OWNED_TREES.remove(self)
            except ValueError:
                pass
            self._retained = False

    def close(self) -> None:
        failures: list[tuple[str, BaseException]] = []
        if self.parent_handle is not None:
            try:
                _windows_close_handle(self.parent_handle)
            except BaseException as error:
                failures.append(("publication parent", error))
            else:
                self.parent_handle = None
        for relative in sorted(
            set(self.directory_handles) - {"."},
            key=lambda value: value.count("/"),
            reverse=True,
        ):
            handle = self.directory_handles[relative]
            try:
                _windows_close_handle(handle)
            except BaseException as error:
                failures.append((f"directory {relative!r}", error))
            else:
                self.directory_handles.pop(relative)
        if "." in self.directory_handles:
            try:
                _windows_close_handle(self.directory_handles["."])
            except BaseException as error:
                failures.append(("publication root", error))
            else:
                self.directory_handles.pop(".")
        self._update_retention()
        if failures:
            error = ExportError(
                "cannot release owned staging tree: "
                + ", ".join(label for label, _ in failures)
            )
            for label, failure in failures:
                _attach_exception_diagnostics(error, failure, label)
            raise error from failures[0][1]

    def delete_subtree(self, path: pathlib.Path | str = ".") -> None:
        prefix = self._relative(path)
        expected_directories, expected_files = self.subtree_ledgers(prefix)
        directories, files = self.inventory(prefix)
        if set(directories) != set(expected_directories) or set(files) != set(
            expected_files
        ):
            raise ExportError(
                "owned cleanup tree contains untracked or missing members"
            )
        for relative, seal in directories.items():
            if seal["identity"] != expected_directories[relative]:
                raise ExportError(
                    f"owned cleanup directory {relative!r} identity changed"
                )

        def global_relative(local: str) -> str:
            if prefix == ".":
                return local
            if local == ".":
                return prefix
            return f"{prefix}/{local}"

        acquired = _WindowsHandleOwner("owned cleanup handles")
        try:
            for local_relative in files:
                relative = global_relative(local_relative)
                parent_handle, name = self._parent(relative)
                handle, _ = _windows_nt_open_relative(
                    parent_handle,
                    name,
                    desired_access=0x00100000 | 0x00010000 | 0x00000080,
                    share_access=0x00000001 | 0x00000002 | 0x00000004,
                    disposition=1,
                    create_options=0x00000040 | 0x00000020,
                    file_attributes=0,
                    context=f"owned cleanup file {relative!r}",
                )
                acquired.add(relative, handle, self.files[relative])
                information = _windows_handle_information(handle)
                if information["attributes"] & (0x00000010 | 0x00000400):
                    raise ExportError(
                        f"owned cleanup file {relative!r} is not an ordinary file"
                    )
                if information["identity"] != self.files[relative]:
                    raise ExportError(
                        f"owned cleanup file {relative!r} identity changed"
                    )

            final_directories, final_files = self.inventory(prefix)
            if final_directories != directories or final_files != files:
                raise ExportError("owned cleanup tree changed before deletion")
        except BaseException as error:
            try:
                acquired.close()
            except BaseException as close_error:
                _attach_exception_diagnostics(
                    error, close_error, "cleanup acquisition rollback"
                )
            raise

        failures: list[tuple[str, BaseException]] = []
        for local_relative in sorted(files):
            relative = global_relative(local_relative)
            handle = acquired.handles[relative]
            try:
                _windows_mark_delete(handle)
                _windows_close_handle(handle)
            except BaseException as error:
                failures.append((f"file {relative!r}", error))
            else:
                acquired.handles.pop(relative)
                acquired.identities.pop(relative, None)
                self.files.pop(relative, None)

        for local_relative in sorted(
            directories,
            key=lambda value: (value != ".") + value.count("/"),
            reverse=True,
        ):
            relative = global_relative(local_relative)
            handle = self.directory_handles[relative]
            try:
                _windows_mark_delete(handle)
                _windows_close_handle(handle)
            except BaseException as error:
                failures.append((f"directory {relative!r}", error))
            else:
                self.directory_handles.pop(relative)
                self.directories.pop(relative, None)

        try:
            acquired.close()
        except BaseException as close_error:
            failures.append(("cleanup handle release", close_error))
        self._update_retention()
        if failures:
            primary = failures[0][1]
            for label, failure in failures[1:]:
                _attach_exception_diagnostics(primary, failure, label)
            raise primary

    def subtree_ledgers(
        self, path: pathlib.Path | str
    ) -> tuple[dict[str, tuple[int, int]], dict[str, tuple[int, int]]]:
        prefix = self._relative(path)

        def select(values: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
            if prefix == ".":
                return dict(values)
            selected = {}
            for relative, identity in values.items():
                if relative == prefix:
                    selected["."] = identity
                elif relative.startswith(prefix + "/"):
                    selected[relative[len(prefix) + 1 :]] = identity
            return selected

        return select(self.directories), select(self.files)

def _windows_open_change_watch_handle(root: pathlib.Path) -> int:
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
    handle = create_file(
        str(root),
        0x00000001,
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,
        0x02000000 | 0x00200000 | 0x40000000,
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ExportError(
            "cannot watch publication membership: Windows error "
            f"{ctypes.get_last_error()}"
        )
    return int(handle)


def _windows_create_event_handle() -> int:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_event = kernel32.CreateEventW
    create_event.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_wchar_p,
    ]
    create_event.restype = ctypes.c_void_p
    event = create_event(None, True, False, None)
    if not event:
        raise ExportError(
            "cannot watch publication membership: Windows error "
            f"{ctypes.get_last_error()}"
        )
    return int(event)


def _windows_start_directory_change_watch(
    handle: int,
    buffer: ctypes.Array,
    overlapped: ctypes.Structure,
) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    read_changes = kernel32.ReadDirectoryChangesW
    read_changes.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    read_changes.restype = ctypes.c_int
    if not read_changes(
        ctypes.c_void_p(handle),
        buffer,
        len(buffer),
        True,
        0x00000001 | 0x00000002,
        None,
        ctypes.byref(overlapped),
        None,
    ) and ctypes.get_last_error() != 997:
        raise ExportError(
            "cannot watch publication membership: Windows error "
            f"{ctypes.get_last_error()}"
        )


_UNRESOLVED_WINDOWS_WATCHES: list[Any] = []


class _WindowsDirectoryChangeWatch:
    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_void_p),
            ("InternalHigh", ctypes.c_void_p),
            ("Offset", ctypes.c_uint32),
            ("OffsetHigh", ctypes.c_uint32),
            ("hEvent", ctypes.c_void_p),
        ]

    def __init__(
        self,
        root: pathlib.Path | None = None,
        *,
        owner_parent_handle: int | None = None,
        owner_name: str | None = None,
    ):
        self.handle: int | None = None
        self.event: int | None = None
        self.overlapped = self.Overlapped()
        self.buffer = ctypes.create_string_buffer(64 * 1024)
        self._retained = False
        self._start_may_be_pending = False
        try:
            if owner_parent_handle is not None and owner_name is not None:
                self.handle, _ = _windows_nt_open_relative(
                    owner_parent_handle,
                    owner_name,
                    desired_access=0x00000001,
                    share_access=0x00000001 | 0x00000002 | 0x00000004,
                    disposition=1,
                    create_options=0x00000001,
                    file_attributes=0,
                    context="publication membership watch",
                )
            elif root is not None:
                self.handle = _windows_open_change_watch_handle(root)
            else:
                raise ExportError("publication membership watch requires an owner")
            self.event = _windows_create_event_handle()
            self.overlapped.hEvent = self.event
            self._start_may_be_pending = True
            try:
                _windows_start_directory_change_watch(
                    self.handle, self.buffer, self.overlapped
                )
            except ExportError:
                self._start_may_be_pending = False
                raise
            self._start_may_be_pending = False
        except BaseException as error:
            if self._start_may_be_pending:
                self._retain_unresolved_resources()
                error.add_note(
                    "publication membership watch start is unresolved; "
                    "native state was retained"
                )
                raise
            close_errors = self._release_handles()
            if close_errors:
                self._retain_unresolved_resources()
            for attribute, close_error in close_errors:
                _attach_exception_diagnostics(
                    error,
                    close_error,
                    f"cannot release change-watch {attribute}",
                )
            raise

    def _release_handles(self) -> list[tuple[str, BaseException]]:
        errors: list[tuple[str, BaseException]] = []
        for attribute in ("event", "handle"):
            handle = getattr(self, attribute)
            if handle is None:
                continue
            try:
                _windows_close_handle(handle)
            except BaseException as error:
                errors.append((attribute, error))
            else:
                setattr(self, attribute, None)
        return errors

    def _retain_unresolved_resources(self) -> None:
        if not self._retained:
            _UNRESOLVED_WINDOWS_WATCHES.append(self)
            self._retained = True

    def _release_retention(self) -> None:
        if self._retained:
            try:
                _UNRESOLVED_WINDOWS_WATCHES.remove(self)
            except ValueError:
                pass
            self._retained = False

    def finish(self) -> bool:
        if self.handle is None or self.event is None:
            raise ExportError("publication membership watch is not active")
        completion_established = False
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            wait = kernel32.WaitForSingleObject
            wait.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            wait.restype = ctypes.c_uint32
            cancel = kernel32.CancelIoEx
            cancel.argtypes = [ctypes.c_void_p, ctypes.POINTER(self.Overlapped)]
            cancel.restype = ctypes.c_int
            get_result = kernel32.GetOverlappedResult
            get_result.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(self.Overlapped),
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.c_int,
            ]
            get_result.restype = ctypes.c_int
            initial_wait = wait(self.event, 0)
            changed = initial_wait == 0
            errors = []
            if initial_wait == 0xFFFFFFFF:
                errors.append(
                    "change-watch wait failed with Windows error "
                    f"{ctypes.get_last_error()}"
                )
            if not changed and not cancel(self.handle, ctypes.byref(self.overlapped)):
                error_number = ctypes.get_last_error()
                if error_number != 1168:
                    errors.append(f"cancel failed with Windows error {error_number}")
            completion_wait = wait(self.event, 5000)
            if completion_wait != 0:
                if completion_wait == 0xFFFFFFFF:
                    errors.append(
                        "change-watch completion wait failed with Windows error "
                        f"{ctypes.get_last_error()}"
                    )
                else:
                    errors.append("change-watch cancellation did not complete")
                raise ExportError(
                    "cannot finish publication membership watch: "
                    + "; ".join(errors)
                )
            completion_established = True
            transferred = ctypes.c_uint32()
            if get_result(
                self.handle,
                ctypes.byref(self.overlapped),
                ctypes.byref(transferred),
                False,
            ):
                changed = changed or transferred.value > 0
            else:
                error_number = ctypes.get_last_error()
                if error_number != 995:
                    errors.append(
                        f"change-watch result failed with Windows error {error_number}"
                    )
            release_errors = self._release_handles()
            if self.handle is not None or self.event is not None:
                self._retain_unresolved_resources()
            else:
                self._release_retention()
            if errors or release_errors:
                message = "cannot finish publication membership watch"
                if errors:
                    message += ": " + "; ".join(errors)
                failure = ExportError(message)
                for attribute, release_error in release_errors:
                    _attach_exception_diagnostics(
                        failure,
                        release_error,
                        f"cannot release change-watch {attribute}",
                    )
                if release_errors:
                    raise failure from release_errors[0][1]
                raise failure
            return changed
        except BaseException as error:
            if not completion_established or self.handle is not None or self.event is not None:
                self._retain_unresolved_resources()
            if not completion_established:
                error.add_note(
                    "publication membership watch completion is unresolved; "
                    "native state was retained"
                )
            elif self.handle is not None or self.event is not None:
                error.add_note(
                    "publication membership watch release is unresolved; "
                    "native state was retained"
                )
            raise


@contextlib.contextmanager
def _directory_membership_guard(
    root: pathlib.Path,
    *,
    owner_parent_handle: int | None = None,
    owner_name: str | None = None,
):
    if os.name != "nt":
        yield
        return
    watch = _WindowsDirectoryChangeWatch(
        root,
        owner_parent_handle=owner_parent_handle,
        owner_name=owner_name,
    )
    try:
        yield
    except BaseException as error:
        try:
            if watch.finish():
                error.add_note(
                    "publication stage membership changed during enumeration"
                )
        except BaseException as watch_error:
            _attach_exception_diagnostics(
                error, watch_error, "publication membership watch teardown"
            )
        raise
    else:
        if watch.finish():
            message = "publication stage membership changed during enumeration"
            raise ExportError(message)


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
    before_identity = _stream_identity(stream)
    if (
        before_identity != _stream_identity(stream)
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


def _read_sealed_file(
    path: pathlib.Path,
    retain_bytes: bool = False,
    owned_tree: _WindowsOwnedTree | None = None,
) -> tuple[bytes, dict]:
    try:
        if owned_tree is None and path.is_symlink():
            raise ExportError(f"publication stage contains a symbolic link: {path.name!r}")
        stream_context = (
            owned_tree.open_file(path, f"staged file {path.name!r}")
            if owned_tree is not None
            else path.open("r+b")
        )
        with stream_context as stream, _exclusive_stream_lock(stream):
            return _read_sealed_stream(stream, path, retain_bytes=retain_bytes)
    except ExportError:
        raise
    except OSError as error:
        raise ExportError(f"cannot seal staged file {path.name!r}: {error}") from error


def _inventory_stage(
    root: pathlib.Path, owned_tree: _WindowsOwnedTree | None = None
) -> tuple[dict[str, dict], list[str]]:
    if owned_tree is not None:
        return owned_tree.inventory()
    with _directory_membership_guard(root):
        directories: dict[str, dict] = {
            ".": _directory_seal(root, "publication stage")
        }
        files: list[str] = []
        for current, names, filenames in os.walk(root, followlinks=False):
            current_path = pathlib.Path(current)
            for name in sorted(names):
                directory = current_path / name
                if directory.is_symlink():
                    raise ExportError(
                        "publication stage contains a symbolic-link directory"
                    )
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
            if (
                _directory_seal(
                    path, f"publication stage directory {relative!r}"
                )
                != seal
            ):
                raise ExportError(
                    "publication stage membership changed during enumeration"
                )
    return directories, sorted(files)


def _snapshot_stage(
    root: pathlib.Path,
    scan_public: bool = False,
    owned_tree: _WindowsOwnedTree | None = None,
) -> dict:
    if owned_tree is not None:
        root = owned_tree.root
    directories, filenames = _inventory_stage(root, owned_tree=owned_tree)
    files: dict[str, dict] = {}
    with contextlib.ExitStack() as stack:
        streams = {}
        for relative in filenames:
            path = root / relative
            try:
                stream = stack.enter_context(
                    owned_tree.open_file(path, f"staged file {relative!r}")
                    if owned_tree is not None
                    else path.open("r+b")
                )
                stack.enter_context(_exclusive_stream_lock(stream))
            except OSError as error:
                raise ExportError(f"cannot seal staged file {relative!r}: {error}") from error
            streams[relative] = stream
        locked_directories, locked_filenames = _inventory_stage(
            root, owned_tree=owned_tree
        )
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
                _stream_identity(stream) != seal["identity"]
                or current.st_size != seal["bytes"]
                or current.st_mtime_ns != seal["mtimeNs"]
            ):
                raise ExportError("publication stage changed during coherent verification")
        final_directories, final_filenames = _inventory_stage(
            root, owned_tree=owned_tree
        )
        if final_directories != directories or final_filenames != filenames:
            raise ExportError("publication stage changed during coherent verification")
    return {"directories": directories, "files": files}


def _require_stage_snapshot(
    root: pathlib.Path,
    expected: dict,
    owned_tree: _WindowsOwnedTree | None = None,
) -> None:
    if _snapshot_stage(root, owned_tree=owned_tree) != expected:
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
    source: pathlib.Path,
    destination: pathlib.Path,
    context: str,
    declared_digest: str,
    owned_tree: _WindowsOwnedTree | None = None,
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
        output_context = (
            owned_tree.create_file(destination, context)
            if owned_tree is not None
            else destination.open("xb")
        )
        with output_context as output_stream:
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
    owned_tree: _WindowsOwnedTree | None = None,
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
    ) = _copy_and_inspect_png(
        path,
        spool_path,
        context,
        declared_digest,
        owned_tree=owned_tree,
    )
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
    owned_tree: _WindowsOwnedTree | None = None,
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
            owned_tree=owned_tree,
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


def _inspect_manifest(
    manifest_path: pathlib.Path,
    spool_directory: pathlib.Path,
    owned_tree: _WindowsOwnedTree | None = None,
) -> dict:
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
                manifest_path,
                capture,
                child,
                context,
                spool_directory,
                owned_tree=owned_tree,
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


def _zip_info_signature(
    info: zipfile.ZipInfo,
    *,
    extra: bytes | None = None,
    create_version: int | None = None,
    extract_version: int | None = None,
) -> tuple:
    return (
        info.filename,
        info.orig_filename,
        info.date_time,
        info.compress_type,
        info.comment,
        info.extra if extra is None else extra,
        info.create_system,
        info.create_version if create_version is None else create_version,
        info.extract_version if extract_version is None else extract_version,
        info.flag_bits,
        info.volume,
        info.internal_attr,
        info.external_attr,
        info.header_offset,
        info.CRC,
        info.compress_size,
        info.file_size,
    )


def _generated_zip_info_signature(info: zipfile.ZipInfo) -> tuple:
    zip64_values = []
    for value in (info.file_size, info.compress_size, info.header_offset):
        if value > zipfile.ZIP64_LIMIT:
            zip64_values.append(value)
    if not zip64_values:
        return _zip_info_signature(info)
    zip64_extra = struct.pack(
        "<HH" + "Q" * len(zip64_values),
        1,
        len(zip64_values) * 8,
        *zip64_values,
    )
    return _zip_info_signature(
        info,
        extra=info.extra + zip64_extra,
        create_version=max(info.create_version, 45),
        extract_version=max(info.extract_version, 45),
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


def _write_bundle(
    path: pathlib.Path,
    inspected: dict,
    owned_tree: _WindowsOwnedTree | None = None,
) -> tuple[int, int, dict]:
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
        bundle_context = (
            owned_tree.create_file(path, "capture bundle")
            if owned_tree is not None
            else path.open("xb+")
        )
        with bundle_context as bundle_stream, _exclusive_stream_lock(bundle_stream):
            generated_identity = _stream_identity(bundle_stream)
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
                        source_context = (
                            owned_tree.open_file(source, "staged frame")
                            if owned_tree is not None
                            else source.open("rb")
                        )
                        with source_context as stream:
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
            if _stream_identity(bundle_stream) != generated_identity:
                raise ExportError("capture bundle identity changed during generation")
            expected_info_signatures = [
                _generated_zip_info_signature(info) for info in generated_infos
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
                _stream_identity(bundle_stream) != generated_identity
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
    owned_tree: _WindowsOwnedTree | None = None,
) -> tuple[dict, dict, dict, dict]:
    manifest_path = _resolve_plan_path(plan_path, plan["source"]["manifestPath"])
    inspected = _inspect_manifest(
        manifest_path, spool_directory, owned_tree=owned_tree
    )
    byte_length, expanded_length, bundle_seal = _write_bundle(
        bundle_path, inspected, owned_tree=owned_tree
    )
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
    owned_tree: _WindowsOwnedTree,
    expected_root_identity: tuple[int, int],
    expected_directories: dict[str, tuple[int, int]],
    expected_files: dict[str, tuple[int, int]],
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
    snapshot = _snapshot_stage(
        staging, scan_public=True, owned_tree=owned_tree
    )
    if snapshot["directories"]["."]["identity"] != expected_root_identity:
        raise ExportError("publication stage root identity changed before sealing")
    if set(snapshot["directories"]) != {".", "artifacts", "content"}:
        raise ExportError("publication stage has an unexpected directory set")
    if set(snapshot["files"]) != expected_paths:
        raise ExportError("publication stage has an unexpected member set")
    if {
        relative: seal["identity"]
        for relative, seal in snapshot["directories"].items()
    } != expected_directories:
        raise ExportError("publication stage directory ownership changed before sealing")
    if {
        relative: seal["identity"] for relative, seal in snapshot["files"].items()
    } != expected_files:
        raise ExportError("publication stage file ownership changed before sealing")
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


def _publication_snapshot(snapshot: dict) -> dict:
    return {
        "directories": {
            relative: seal["identity"]
            for relative, seal in snapshot["directories"].items()
        },
        "files": snapshot["files"],
    }


def _publish_no_clobber(
    staging: pathlib.Path,
    output: pathlib.Path,
    expected_snapshot: dict,
    expected_identity: tuple[int, int],
    owned_tree: _WindowsOwnedTree,
) -> None:
    """Atomically publish a directory while refusing an existing destination."""
    _require_stage_snapshot(staging, expected_snapshot, owned_tree=owned_tree)
    if expected_snapshot["directories"]["."]["identity"] != expected_identity:
        raise ExportError("validated stage does not have its creation-time identity")
    try:
        owned_tree.rename_root(output, "publication stage")
        published_snapshot = _snapshot_stage(output, owned_tree=owned_tree)
        if (
            published_snapshot["directories"]["."]["identity"] != expected_identity
            or _publication_snapshot(published_snapshot)
            != _publication_snapshot(expected_snapshot)
        ):
            raise ExportError("published output differs from the validated stage")
    except BaseException as error:
        if owned_tree.root == output:
            try:
                owned_tree.rename_root(staging, "failed publication withdrawal")
            except BaseException as withdrawal_error:
                wrapped = ExportError(
                    "publication transition failed and the owned output "
                    "could not be withdrawn"
                )
                _attach_exception_diagnostics(wrapped, error, "publication")
                _attach_exception_diagnostics(
                    wrapped, withdrawal_error, "withdrawal"
                )
                raise wrapped from error
            raise
        if owned_tree.root == staging:
            if isinstance(error, FileExistsError) or (
                isinstance(error, OSError)
                and error.errno in {errno.EEXIST, errno.ENOTEMPTY, errno.EACCES}
                and output.exists()
            ):
                raise ExportError(f"output already exists: {output}") from error
            if isinstance(error, OSError):
                raise ExportError(f"cannot publish export: {error}") from error
            raise
        wrapped = ExportError(
            "publication transition failed with uncertain pathname custody; "
            "the generated root remains retained by handle"
        )
        _attach_exception_diagnostics(wrapped, error, "publication")
        raise wrapped from error


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


def export_plan(plan_path: pathlib.Path, output: pathlib.Path) -> dict:
    staging: pathlib.Path | None = None
    staging_identity: tuple[int, int] | None = None
    owned_tree: _WindowsOwnedTree | None = None
    publication_owner: _WindowsHandleOwner | None = None
    try:
        if os.name != "nt":
            raise ExportError(
                "capture export requires Windows identity-bound cleanup"
            )
        plan_path = plan_path.resolve()
        plan_document, plan_sha256 = _load_json_document(
            plan_path, "capture export plan"
        )
        plan = _validate_plan(plan_document)
        output = output.resolve()
        if output.exists():
            raise ExportError(f"output already exists: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        owned_tree = _WindowsOwnedTree.create_unique(
            output.parent,
            f".{output.name}.staging-",
            "export staging",
        )
        staging = owned_tree.root
        staging_identity = owned_tree.root_identity
        spool_directory = staging / ".private-source"
        owned_tree.create_directory(
            spool_directory, "private source staging"
        )
        spool_identity = owned_tree.directories[".private-source"]
        temporary_bundle = staging / "capture-bundle.zip"
        artifact, capture, receipt, bundle_seal = _build_records(
            plan_path,
            plan,
            plan_sha256,
            temporary_bundle,
            spool_directory,
            owned_tree=owned_tree,
        )
        owned_tree.delete_subtree(spool_directory)
        artifact_directory = staging / "artifacts"
        owned_tree.create_directory(artifact_directory, "artifact staging")
        final_bundle = artifact_directory / f"{artifact['artifactSha256']}.zip"
        owned_tree.move_file(
            temporary_bundle, final_bundle, "capture bundle into artifact staging"
        )
        _, relocated_bundle_seal = _read_sealed_file(
            final_bundle, owned_tree=owned_tree
        )
        if relocated_bundle_seal != bundle_seal:
            raise ExportError("capture bundle identity changed during staging")
        content = staging / "content"
        owned_tree.create_directory(content, "public record staging")
        expected_public_bytes = {
            "content/artifacts.jsonl": _jsonl_bytes([artifact]),
            "content/visual-captures.jsonl": _jsonl_bytes([capture]),
            "public-preview.json": _canonical_json_bytes(
                {"artifacts": [artifact], "visualCaptures": [capture]}
            ),
            "export-receipt.json": _canonical_json_bytes(receipt),
        }
        for relative, data in expected_public_bytes.items():
            path = staging / relative
            with owned_tree.create_file(path, f"public record {relative!r}") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        stage_snapshot = _seal_public_stage(
            staging,
            owned_tree,
            staging_identity,
            owned_tree.directories,
            owned_tree.files,
            artifact["artifactSha256"],
            bundle_seal,
            expected_public_bytes,
        )
        _publish_no_clobber(
            staging, output, stage_snapshot, staging_identity, owned_tree
        )
        publication_owner = _WindowsHandleOwner("published output observation")
        publication_handle = _windows_open_owner_directory(
            output, "published output"
        )
        publication_identity = _windows_handle_identity(publication_handle)
        publication_owner.add(".", publication_handle, publication_identity)
        if publication_identity != staging_identity:
            raise ExportError("published output identity changed before release")
        owned_tree.close()
        publication_owner.close()
        staging = None
        staging_identity = None
        owned_tree = None
        publication_owner = None
    except BaseException as error:
        cleanup_errors: list[BaseException] = []
        if publication_owner is not None:
            try:
                publication_owner.close()
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
        if owned_tree is not None and "." in owned_tree.directory_handles:
            try:
                owned_tree.delete_subtree(".")
            except BaseException as cleanup_error:
                cleanup_errors.append(cleanup_error)
                if "." in owned_tree.directory_handles:
                    owned_tree._update_retention()
        if owned_tree is not None and "." not in owned_tree.directory_handles:
            try:
                owned_tree.close()
            except BaseException as close_error:
                cleanup_errors.append(close_error)
        if cleanup_errors:
            wrapped = ExportError(f"{error}; cleanup failed")
            _attach_exception_diagnostics(wrapped, error, "primary")
            for cleanup_error in cleanup_errors:
                _attach_exception_diagnostics(wrapped, cleanup_error, "cleanup")
            raise wrapped from error
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
        print(
            f"export failed: {_format_exception_diagnostics(error)}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
