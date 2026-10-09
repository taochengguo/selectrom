import json
import socket
import struct
from io import BytesIO
from unittest.mock import patch

from django.test import SimpleTestCase

from sampling.services.tianditu_direct import DirectNetworkError, get_json, parse_a_records


class _Socket:
    def __init__(self, status=200, headers=b"", payload=b'{"status":"0"}'):
        self.status = status
        self.headers = headers
        self.payload = payload
        self.options = []
        self.bound = None
        self.connected = None
        self.sent = b""

    def settimeout(self, value):
        self.timeout = value

    def setsockopt(self, *args):
        self.options.append(args)

    def bind(self, address):
        self.bound = address

    def connect(self, address):
        self.connected = address

    def sendall(self, data):
        self.sent += data

    def makefile(self, _mode):
        return BytesIO(
            f"HTTP/1.1 {self.status} Result\r\n".encode("ascii")
            + self.headers
            + f"Content-Length: {len(self.payload)}\r\n\r\n".encode("ascii")
            + self.payload
        )

    def close(self):
        pass


class _TLSContext:
    def __init__(self):
        self.server_hostname = None

    def wrap_socket(self, connection, server_hostname):
        self.server_hostname = server_hostname
        return connection


class TiandituDirectNetworkTests(SimpleTestCase):
    def test_dns_answer_returns_real_ipv4_addresses(self):
        question = b"\x03api\x08tianditu\x03gov\x02cn\x00\x00\x01\x00\x01"
        answer = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4)
        packet = (
            struct.pack("!HHHHHH", 0xBEEF, 0x8180, 1, 2, 0, 0)
            + question
            + answer + bytes((49, 4, 56, 33))
            + answer + bytes((49, 4, 56, 45))
        )

        self.assertEqual(parse_a_records(packet, 0xBEEF), ["49.4.56.33", "49.4.56.45"])
        with self.assertRaises(DirectNetworkError):
            parse_a_records(packet, 0x1234)
        with self.assertRaises(DirectNetworkError):
            parse_a_records(packet[:-2], 0xBEEF)

    @patch("sampling.services.tianditu_direct._resolve_ipv4", return_value=["49.4.56.33"])
    @patch("sampling.services.tianditu_direct.ssl.create_default_context")
    @patch("sampling.services.tianditu_direct.socket.socket")
    def test_https_uses_physical_interface_and_original_tls_hostname(self, socket_factory, context_factory, _resolve):
        network_socket = _Socket(payload=json.dumps({"status": "0"}).encode("utf-8"))
        context = _TLSContext()
        socket_factory.return_value = network_socket
        context_factory.return_value = context

        result = get_json(
            "https://api.tianditu.gov.cn/geocoder?tk=test-key",
            source_ip="192.168.2.12",
            interface_index=18,
            dns_servers=["61.132.163.68"],
        )

        self.assertEqual(result, {"status": "0"})
        self.assertEqual(network_socket.bound, ("192.168.2.12", 0))
        self.assertEqual(network_socket.connected, ("49.4.56.33", 443))
        self.assertIn((socket.IPPROTO_IP, 31, struct.pack("!I", 18)), network_socket.options)
        self.assertEqual(context.server_hostname, "api.tianditu.gov.cn")
        self.assertIn(b"GET /geocoder?tk=test-key HTTP/1.1\r\n", network_socket.sent)
        self.assertIn(b"Host: api.tianditu.gov.cn\r\n", network_socket.sent)
