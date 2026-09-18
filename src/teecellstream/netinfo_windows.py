"""The beacon's interface list on Windows, where there is no `ip addr` (see netinfo.py for the why).

Windows answers this through the IP Helper API: GetAdaptersAddresses hands back a linked list of
adapters, each with its own linked list of unicast addresses, and each address carries the prefix
length. Broadcast address = address | ~mask, exactly as netinfo does it for a Linux link that
printed no broadcast of its own.

Shelling out to PowerShell's Get-NetIPAddress would have been three lines, but it costs half a
second of process start-up every time the beacon refreshes its targets.
"""

import ctypes
import ipaddress
from ctypes import POINTER, Structure, byref, c_void_p, c_wchar_p

# spelled out rather than imported from ctypes.wintypes, which exists only on Windows - this module
# must stay importable on Linux so the test suite can check the layout arithmetic there
# fixed widths, not c_ulong: a Windows ULONG is 32 bits, a Linux c_ulong is 64, and with the exact
# widths the struct sizes come out the same on both, so the layout can be checked by a Linux test
BYTE = ctypes.c_ubyte
DWORD = ctypes.c_uint32
ULONG = ctypes.c_uint32
USHORT = ctypes.c_uint16

AF_INET = 2
AF_UNSPEC = 0

# leave out what we do not read, so the buffer stays small
GAA_FLAG_SKIP_ANYCAST = 0x0002
GAA_FLAG_SKIP_MULTICAST = 0x0004
GAA_FLAG_SKIP_DNS_SERVER = 0x0008
GAA_FLAGS = GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER

ERROR_SUCCESS = 0
ERROR_BUFFER_OVERFLOW = 111

IF_TYPE_SOFTWARE_LOOPBACK = 24
IF_OPER_STATUS_UP = 1

MAX_TRIES = 3            # the adapter list can grow between asking the size and asking for the data
MAX_ADAPTER_ADDRESS_LENGTH = 8


class SOCKET_ADDRESS(Structure):
    _fields_ = [("lpSockaddr", c_void_p), ("iSockaddrLength", ctypes.c_int)]


class SOCKADDR_IN(Structure):
    _fields_ = [("sin_family", USHORT), ("sin_port", USHORT),
                ("sin_addr", ctypes.c_ubyte * 4), ("sin_zero", ctypes.c_char * 8)]


class IP_ADAPTER_UNICAST_ADDRESS(Structure):
    pass


IP_ADAPTER_UNICAST_ADDRESS._fields_ = [
    ("Length", ULONG), ("Flags", DWORD),
    ("Next", POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
    ("Address", SOCKET_ADDRESS),
    ("PrefixOrigin", ctypes.c_int), ("SuffixOrigin", ctypes.c_int), ("DadState", ctypes.c_int),
    ("ValidLifetime", ULONG), ("PreferredLifetime", ULONG), ("LeaseLifetime", ULONG),
    ("OnLinkPrefixLength", ctypes.c_ubyte),
]


class IP_ADAPTER_ADDRESSES(Structure):
    pass


IP_ADAPTER_ADDRESSES._fields_ = [
    # the header is a union with a ULONGLONG for alignment; two ULONGs occupy the same eight bytes
    ("Length", ULONG), ("IfIndex", ULONG),
    ("Next", POINTER(IP_ADAPTER_ADDRESSES)),
    ("AdapterName", ctypes.c_char_p),
    ("FirstUnicastAddress", POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
    ("FirstAnycastAddress", c_void_p),
    ("FirstMulticastAddress", c_void_p),
    ("FirstDnsServerAddress", c_void_p),
    ("DnsSuffix", c_wchar_p), ("Description", c_wchar_p), ("FriendlyName", c_wchar_p),
    ("PhysicalAddress", BYTE * MAX_ADAPTER_ADDRESS_LENGTH), ("PhysicalAddressLength", ULONG),
    ("Flags", ULONG), ("Mtu", ULONG), ("IfType", ULONG), ("OperStatus", ctypes.c_int),
    # everything past this point (Ipv6IfIndex, ZoneIndices, prefixes, speeds...) goes unread, but the
    # buffer is sized by the API itself, so the trailing fields are there - we simply never look
]


def broadcast_for(address: str, prefix_length: int) -> str | None:
    """`192.0.2.10/24` -> `192.0.2.255`. None for a host route (/32) or nonsense."""
    try:
        network = ipaddress.IPv4Interface((address, prefix_length)).network
    except (ValueError, TypeError):
        return None
    if network.prefixlen >= 31:      # /31 and /32 have no broadcast address worth the name
        return None
    return str(network.broadcast_address)


def _adapter_buffer():
    """The raw GetAdaptersAddresses answer, or None. Asks once for the size, then for the data."""
    iphlpapi = ctypes.WinDLL("Iphlpapi.dll")
    size = ULONG(0)
    buffer = None
    for _attempt in range(MAX_TRIES):
        result = iphlpapi.GetAdaptersAddresses(ULONG(AF_INET), ULONG(GAA_FLAGS), None, buffer, byref(size))
        if result == ERROR_SUCCESS:
            return buffer
        if result != ERROR_BUFFER_OVERFLOW:
            raise OSError("GetAdaptersAddresses returned %d" % result)
        buffer = ctypes.cast(ctypes.create_string_buffer(size.value),
                             POINTER(IP_ADAPTER_ADDRESSES))
    raise OSError("GetAdaptersAddresses kept asking for a bigger buffer")


def _address_of(unicast) -> str | None:
    """The IPv4 address behind one unicast entry's sockaddr, or None if it is not IPv4."""
    socket_address = unicast.Address
    if not socket_address.lpSockaddr or socket_address.iSockaddrLength < ctypes.sizeof(SOCKADDR_IN):
        return None
    sockaddr = ctypes.cast(socket_address.lpSockaddr, POINTER(SOCKADDR_IN)).contents
    if sockaddr.sin_family != AF_INET:
        return None
    return ".".join(str(octet) for octet in sockaddr.sin_addr)


def interface_broadcasts() -> list[str]:
    """Every live, non-loopback adapter's own broadcast address. Raises OSError if Windows will not say."""
    broadcasts: list[str] = []
    adapter_pointer = _adapter_buffer()
    while adapter_pointer:
        adapter = adapter_pointer.contents
        usable = adapter.OperStatus == IF_OPER_STATUS_UP and adapter.IfType != IF_TYPE_SOFTWARE_LOOPBACK
        unicast_pointer = adapter.FirstUnicastAddress if usable else None
        while unicast_pointer:
            unicast = unicast_pointer.contents
            address = _address_of(unicast)
            if address is not None:
                broadcast = broadcast_for(address, unicast.OnLinkPrefixLength)
                if broadcast is not None and broadcast not in broadcasts:
                    broadcasts.append(broadcast)
            unicast_pointer = unicast.Next
        adapter_pointer = adapter.Next
    return broadcasts
