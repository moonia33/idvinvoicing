import ipaddress
import socket

ALLOWED_SMTP_PORTS = {25, 465, 587, 2525}


def ensure_public_smtp_host(host: str, port: int) -> None:
    """Neleidžia SMTP jungčių į vidinius/privačius adresus (SSRF)."""
    if port not in ALLOWED_SMTP_PORTS:
        raise ValueError(f"Neleistinas SMTP prievadas {port}")
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise ValueError(f"SMTP serveris {host} nerastas") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise ValueError(f"SMTP serveris {host} nukreiptas į vidinį adresą")
