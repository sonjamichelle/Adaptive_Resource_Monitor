"""Windows performance data and adapter identity."""
import ctypes as ct
from ctypes import wintypes as w
import logging
from mmap import PAGESIZE
import uuid
import winreg

LOG = logging.getLogger(__name__)


class _Double(ct.Structure):
    _fields_ = [("status", w.DWORD), ("value", ct.c_double)]


class _Item(ct.Structure):
    _fields_ = [("name", w.LPWSTR), ("data", _Double)]


class Pdh:
    MORE_DATA = 0x800007D2

    def __init__(self, paths):
        self.dll = ct.WinDLL("pdh")
        hndl = w.HANDLE
        for name, args in {
            "PdhOpenQueryW": [w.LPCWSTR, ct.c_size_t, ct.POINTER(hndl)],
            "PdhAddEnglishCounterW": [hndl, w.LPCWSTR, ct.c_size_t, ct.POINTER(hndl)],
            "PdhCollectQueryData": [hndl],
            "PdhGetFormattedCounterArrayW": [
                hndl, w.DWORD, ct.POINTER(w.DWORD), ct.POINTER(w.DWORD), ct.c_void_p],
            "PdhCloseQuery": [hndl],
        }.items():
            fn = getattr(self.dll, name)
            fn.argtypes = args
            fn.restype = w.DWORD
        self.query = hndl()
        result = self.dll.PdhOpenQueryW(None, 0, ct.byref(self.query))
        if result:
            raise OSError(f"PdhOpenQuery returned {result:#x}")
        self.counters = {}
        for key, path in paths.items():
            counter = hndl()
            result = self.dll.PdhAddEnglishCounterW(self.query, path, 0, ct.byref(counter))
            if result:
                LOG.info("Windows counter unavailable %s (%#x)", key, result)
            else:
                self.counters[key] = counter

    def collect(self):
        result = self.dll.PdhCollectQueryData(self.query)
        if result and self.counters:
            LOG.debug("Windows query unavailable (%#x)", result)
        return {key: self._array(counter) for key, counter in self.counters.items()}

    def _array(self, counter):
        length, count = w.DWORD(), w.DWORD()
        getter = self.dll.PdhGetFormattedCounterArrayW
        for _ in range(3):
            result = getter(counter, 0x200, ct.byref(length), ct.byref(count), None)
            if result != self.MORE_DATA or not 0 < length.value <= 32 * 1024 * 1024:
                return {}
            data = ct.create_string_buffer(length.value)
            result = getter(counter, 0x200, ct.byref(length), ct.byref(count), data)
            if not result:
                rows = ct.cast(data, ct.POINTER(_Item))
                return {rows[i].name: rows[i].data.value for i in range(count.value)
                        if rows[i].data.status in (0, 1) and rows[i].name}
            if result != self.MORE_DATA:
                break
        return {}

    def close(self):
        if self.query:
            self.dll.PdhCloseQuery(self.query)
            self.query = None


class _Luid(ct.Structure):
    _fields_ = [("low", w.DWORD), ("high", w.LONG)]


class Adapter(ct.Structure):
    _fields_ = [("name", w.WCHAR * 128), ("vendor", w.UINT), ("device", w.UINT),
                ("subsystem", w.UINT), ("revision", w.UINT), ("dedicated", ct.c_size_t),
                ("system", ct.c_size_t), ("shared", ct.c_size_t), ("luid", _Luid),
                ("flags", w.UINT)]

    @property
    def identifier(self):
        return f"luid_0x{self.luid.high & 0xffffffff:08x}_0x{self.luid.low:08x}"


class _OpenAdapter(ct.Structure):
    _fields_ = [("luid", _Luid), ("handle", w.UINT)]


class _QueryAdapter(ct.Structure):
    _fields_ = [("handle", w.UINT), ("kind", w.UINT), ("data", ct.c_void_p), ("size", w.UINT)]


def adapter_identity(adapter):
    gdi = ct.WinDLL("gdi32")
    opened = _OpenAdapter(adapter.luid)
    create = gdi.D3DKMTOpenAdapterFromLuid
    create.argtypes = [ct.POINTER(_OpenAdapter)]
    if create(ct.byref(opened)):
        return None, None
    close = gdi.D3DKMTCloseAdapter
    close.argtypes = [ct.POINTER(w.UINT)]
    try:
        result = (w.UINT * 3)()
        query = gdi.D3DKMTQueryAdapterInfo
        query.argtypes = [ct.POINTER(_QueryAdapter)]
        args = _QueryAdapter(opened.handle, 6, ct.addressof(result), ct.sizeof(result))
        location = (tuple(result) if not query(ct.byref(args)) and result[0] <= 255
                    and result[1] <= 31 and result[2] <= 7 else None)
        flags = w.UINT()
        args = _QueryAdapter(opened.handle, 15, ct.addressof(flags), ct.sizeof(flags))
        return location, flags.value if not query(ct.byref(args)) else None
    finally:
        close(ct.byref(w.UINT(opened.handle)))


def _method(ptr, slot, result, *args):
    table = ct.cast(ptr, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
    return ct.WINFUNCTYPE(result, ct.c_void_p, *args)(table[slot])


def adapters():
    create = ct.WinDLL("dxgi").CreateDXGIFactory1
    create.argtypes = [ct.c_void_p, ct.POINTER(ct.c_void_p)]
    create.restype = ct.c_long
    factory = ct.c_void_p()
    identifier = ct.create_string_buffer(uuid.UUID("770aae78-f26f-4dba-a829-253c83d1b387").bytes_le)
    result = create(identifier, ct.byref(factory))
    if result:
        raise OSError(f"DXGI initialization returned {result & 0xffffffff:#x}")
    devices = []
    try:
        enum = _method(factory, 12, ct.c_long, w.UINT, ct.POINTER(ct.c_void_p))
        for index in range(128):
            adapter = ct.c_void_p()
            if enum(factory, index, ct.byref(adapter)):
                break
            try:
                description = Adapter()
                if not _method(adapter, 10, ct.c_long, ct.POINTER(Adapter))(adapter, ct.byref(description)):
                    if not description.flags & 2 and description.vendor in (0x10de, 0x1002, 0x8086):
                        devices.append(description)
            finally:
                _method(adapter, 2, w.ULONG)(adapter)
    finally:
        _method(factory, 2, w.ULONG)(factory)
    return devices


class _Perf(ct.Structure):
    _fields_ = [("size", w.DWORD)] + [(name, ct.c_size_t) for name in (
        "commit", "commit_limit", "commit_peak", "physical", "available", "cache",
        "kernel", "paged", "nonpaged", "page_size")] + [
        (name, w.DWORD) for name in ("handles", "processes", "threads")]


def commit():
    info = _Perf()
    info.size = ct.sizeof(info)
    get = ct.WinDLL("kernel32").K32GetPerformanceInfo
    get.argtypes = [ct.POINTER(_Perf), w.DWORD]
    get.restype = w.BOOL
    if get(ct.byref(info), info.size):
        return info.commit * info.page_size, info.commit_limit * info.page_size
    return None, None


class _PageFile(ct.Structure):
    _fields_ = [("size", w.DWORD), ("reserved", w.DWORD), ("total", ct.c_size_t),
                ("used", ct.c_size_t), ("peak", ct.c_size_t)]


def pagefiles():
    rows = []
    callback = ct.WINFUNCTYPE(w.BOOL, ct.c_void_p, ct.POINTER(_PageFile), w.LPCWSTR)

    @callback
    def collect(_context, info, _filename):
        rows.append((info.contents.used, info.contents.total))
        return True

    enumerate_files = ct.WinDLL("psapi").EnumPageFilesW
    enumerate_files.argtypes = [callback, ct.c_void_p]
    enumerate_files.restype = w.BOOL
    if enumerate_files(collect, None):
        return (sum(used for used, _ in rows) * PAGESIZE,
                sum(total for _, total in rows) * PAGESIZE)
    return None, None


def cpu_identity():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except OSError:
        return "Windows CPU"


def physical_cores():
    get = ct.WinDLL("kernel32").GetLogicalProcessorInformationEx
    get.argtypes = [ct.c_int, ct.c_void_p, ct.POINTER(w.DWORD)]
    get.restype = w.BOOL
    length = w.DWORD()
    get(0, None, ct.byref(length))
    if not length.value:
        return []
    buf = ct.create_string_buffer(length.value)
    if not get(0, buf, ct.byref(length)):
        return []
    offset, cores = 0, []
    while offset + 32 <= length.value:
        size = w.DWORD.from_buffer(buf, offset + 4).value
        groups = w.WORD.from_buffer(buf, offset + 30).value
        if size < 32 + groups * 16 or offset + size > length.value:
            break
        processors = []
        for group_index in range(groups):
            start = offset + 32 + group_index * 16
            mask = ct.c_uint64.from_buffer(buf, start).value
            group = w.WORD.from_buffer(buf, start + 8).value
            processors.extend(group * 64 + bit for bit in range(64) if mask & (1 << bit))
        if processors:
            cores.append(processors)
        offset += size
    return cores


class _InterfaceRow(ct.Structure):
    _fields_ = [("luid", ct.c_uint64), ("index", w.ULONG), ("guid", ct.c_byte * 16),
                ("alias", w.WCHAR * 257), ("description", w.WCHAR * 257),
                ("address_length", w.ULONG), ("address", ct.c_byte * 32),
                ("permanent", ct.c_byte * 32), ("mtu", w.ULONG), ("type", w.ULONG),
                ("tunnel", w.ULONG), ("media", w.ULONG), ("physical_medium", w.ULONG),
                ("access", w.ULONG), ("direction", w.ULONG), ("flags", ct.c_ubyte),
                ("oper_status", w.ULONG), ("admin_status", w.ULONG), ("connect", w.ULONG),
                ("network_guid", ct.c_byte * 16), ("connection_type", w.ULONG),
                ("transmit", ct.c_uint64), ("receive", ct.c_uint64),
                ("counters", ct.c_uint64 * 18)]


def interface_info():
    ip = ct.WinDLL("iphlpapi")
    get = ip.GetIfTable2
    get.argtypes = [ct.POINTER(ct.c_void_p)]
    get.restype = w.ULONG
    free = ip.FreeMibTable
    free.argtypes = [ct.c_void_p]
    free.restype = None
    table = ct.c_void_p()
    if get(ct.byref(table)):
        return {}
    try:
        count = w.ULONG.from_address(table.value).value
        rows = (_InterfaceRow * count).from_address(table.value + ct.alignment(_InterfaceRow))
        return {row.alias: (bool(row.flags & 1) and row.type in (6, 71),
                            row.transmit, row.receive, bytes(row.guid)) for row in rows}
    finally:
        free(table)
