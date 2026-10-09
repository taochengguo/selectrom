"""Send Tianditu HTTPS requests through a selected Windows physical adapter."""

import http.client
import ipaddress
import json
import os
import secrets
import socket
import ssl
import struct
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import urlsplit


class DirectNetworkError(OSError):
    pass


_IP_UNICAST_IF = 31  # Windows ws2tcpip.h; value is a network-order interface index.
_MAX_RESPONSE_BYTES = 1024 * 1024


def _skip_dns_name(packet, position):
    while True:
        if position >= len(packet):
            raise DirectNetworkError("DNS 响应不完整")
        length = packet[position]
        if length & 0xC0 == 0xC0:
            if position + 1 >= len(packet):
                raise DirectNetworkError("DNS 压缩名称不完整")
            pointer = ((length & 0x3F) << 8) | packet[position + 1]
            if pointer >= len(packet):
                raise DirectNetworkError("DNS 压缩名称无效")
            return position + 2
        if length & 0xC0:
            raise DirectNetworkError("DNS 名称无效")
        if length == 0:
            return position + 1
        position += length + 1


def parse_a_records(packet, request_id):
    """Read IPv4 answers from one matching DNS response packet."""
    try:
        response_id, flags, questions, answers, _authority, _additional = struct.unpack_from(
            "!HHHHHH", packet
        )
        if response_id != request_id or not flags & 0x8000 or flags & 0x020F:
            raise DirectNetworkError("DNS 响应标识、状态或长度无效")
        position = 12
        for _ in range(questions):
            position = _skip_dns_name(packet, position)
            position += 4
            if position > len(packet):
                raise DirectNetworkError("DNS 问题区不完整")

        addresses = []
        for _ in range(answers):
            position = _skip_dns_name(packet, position)
            kind, address_class, _ttl, length = struct.unpack_from("!HHIH", packet, position)
            position += 10
            if position + length > len(packet):
                raise DirectNetworkError("DNS 答案区不完整")
            if kind == 1 and address_class == 1 and length == 4:
                address = socket.inet_ntoa(packet[position:position + 4])
                if address not in addresses:
                    addresses.append(address)
            position += length
        return addresses
    except (IndexError, struct.error) as error:
        raise DirectNetworkError("DNS 响应不完整") from error


def _prepare_socket(connection, source_ip, interface_index, timeout):
    if os.name != "nt":
        raise DirectNetworkError("实体网卡直连目前仅支持 Windows")
    try:
        source_ip = str(ipaddress.IPv4Address(source_ip))
        interface_index = int(interface_index)
        if interface_index <= 0:
            raise ValueError
    except (ipaddress.AddressValueError, TypeError, ValueError) as error:
        raise DirectNetworkError("实体网卡 IP 或接口编号无效") from error
    connection.settimeout(timeout)
    connection.setsockopt(socket.IPPROTO_IP, _IP_UNICAST_IF, struct.pack("!I", interface_index))
    connection.bind((source_ip, 0))


def _resolve_ipv4(host, source_ip, interface_index, dns_servers, timeout=3):
    labels = host.encode("idna").split(b".")
    question = b"".join(bytes((len(label),)) + label for label in labels) + b"\0\0\1\0\1"
    for dns_server in dns_servers:
        try:
            dns_server = str(ipaddress.IPv4Address(dns_server))
            request_id = secrets.randbelow(65536)
            packet = struct.pack("!HHHHHH", request_id, 0x0100, 1, 0, 0, 0) + question
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
                _prepare_socket(connection, source_ip, interface_index, timeout)
                connection.sendto(packet, (dns_server, 53))
                response, sender = connection.recvfrom(4096)
            if sender[0] != dns_server:
                continue
            addresses = parse_a_records(response, request_id)
            if addresses:
                return addresses
        except (OSError, ValueError):
            continue
    raise DirectNetworkError("实体网卡 DNS 未能解析天地图域名")


def get_json(url, *, source_ip, interface_index, dns_servers, timeout=8):
    """Fetch Tianditu JSON using physical DNS, interface routing, and verified TLS."""
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "api.tianditu.gov.cn" or parts.port not in (None, 443):
        raise DirectNetworkError("天地图直连地址无效")
    if not dns_servers:
        raise DirectNetworkError("未配置实体网卡 DNS")

    host = parts.hostname
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    addresses = _resolve_ipv4(host, source_ip, interface_index, dns_servers)
    last_error = None
    for address in addresses:
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            _prepare_socket(connection, source_ip, interface_index, timeout)
            connection.connect((address, 443))
            tls_connection = ssl.create_default_context().wrap_socket(connection, server_hostname=host)
            try:
                request = (
                    f"GET {path} HTTP/1.1\r\n"
                    f"Host: {host}\r\n"
                    "Accept: application/json\r\n"
                    "Connection: close\r\n\r\n"
                )
                tls_connection.sendall(request.encode("ascii"))
                response = http.client.HTTPResponse(tls_connection)
                response.begin()
                payload = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(payload) > _MAX_RESPONSE_BYTES:
                    raise DirectNetworkError("天地图响应超过大小限制")
                if response.status >= 400:
                    raise HTTPError(url, response.status, response.reason, response.headers, BytesIO(payload))
                return json.loads(payload.decode("utf-8"))
            finally:
                tls_connection.close()
        except HTTPError:
            raise
        except (OSError, ssl.SSLError) as error:
            last_error = error
        finally:
            connection.close()
    raise DirectNetworkError("实体网卡无法连接天地图") from last_error
