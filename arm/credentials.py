"""Application-owned generic credentials in Windows Credential Manager."""
import ctypes as ct
from ctypes import wintypes as w
from uuid import uuid4

PREFIX = "AdaptiveResourceMonitor:"
NOT_FOUND = 1168


class _Credential(ct.Structure):
    _fields_ = [("flags", w.DWORD), ("type", w.DWORD), ("target", w.LPWSTR),
                ("comment", w.LPWSTR), ("written", w.FILETIME), ("size", w.DWORD),
                ("blob", ct.POINTER(ct.c_ubyte)), ("persist", w.DWORD),
                ("attribute_count", w.DWORD), ("attributes", ct.c_void_p),
                ("alias", w.LPWSTR), ("username", w.LPWSTR)]


class CredentialStore:
    def __init__(self):
        dll = ct.WinDLL("advapi32", use_last_error=True)
        self._write = dll.CredWriteW
        self._write.argtypes = (ct.POINTER(_Credential), w.DWORD)
        self._write.restype = w.BOOL
        self._read = dll.CredReadW
        self._read.argtypes = (w.LPCWSTR, w.DWORD, w.DWORD, ct.POINTER(ct.POINTER(_Credential)))
        self._read.restype = w.BOOL
        self._delete = dll.CredDeleteW
        self._delete.argtypes = (w.LPCWSTR, w.DWORD, w.DWORD)
        self._delete.restype = w.BOOL
        self._free = dll.CredFree
        self._free.argtypes = (ct.c_void_p,)
        self._free.restype = None

    @staticmethod
    def _target(reference):
        if reference.startswith(PREFIX) and len(reference) == len(PREFIX) + 32:
            if all(char in "0123456789abcdef" for char in reference[len(PREFIX):]):
                return reference
        raise ValueError("Invalid ARM credential reference")

    def save(self, username, secret):
        reference = PREFIX + uuid4().hex
        payload = bytearray(secret, "utf-16-le")
        if not 0 < len(payload) <= 2560:
            raise ValueError("Credential length is unsupported")
        blob = (ct.c_ubyte * len(payload)).from_buffer(payload)
        item = _Credential()
        item.type, item.target, item.username = 1, reference, username
        item.persist, item.size, item.blob = 2, len(blob), blob
        try:
            if not self._write(ct.byref(item), 0):
                raise ct.WinError(ct.get_last_error())
        finally:
            ct.memset(blob, 0, len(blob))
        return reference

    def read(self, reference):
        if not reference:
            return None
        pointer = ct.POINTER(_Credential)()
        if not self._read(self._target(reference), 1, 0, ct.byref(pointer)):
            error = ct.get_last_error()
            if error == NOT_FOUND:
                return None
            raise ct.WinError(error)
        try:
            item = pointer.contents
            return ct.string_at(item.blob, item.size).decode("utf-16-le")
        finally:
            self._free(pointer)

    def delete(self, reference):
        if reference and not self._delete(self._target(reference), 1, 0):
            error = ct.get_last_error()
            if error != NOT_FOUND:
                raise ct.WinError(error)
