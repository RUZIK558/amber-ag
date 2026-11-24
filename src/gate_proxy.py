#!/usr/bin/env python3
"""Локальный CONNECT-прокси для Google Antigravity с终止 TLS и conversion SSE.

Гейт-домены идут через рабочий SNI-прокси. Потоковый вызов
`streamGenerateContent?alt=sse` заменяется на обычный `generateContent`,
а его JSON-ответ упаковывается обратно в SSE — это убирает обрывы длинных
потоков, которые SNI-прокси не выдерживают.
"""
import base64
import json
import os
import socket
import ssl
import struct
import subprocess
import threading
import time

LISTEN = ("127.0.0.1", 53190)
DOH = "https://dns.dns-ai.ru/dns-query"
GATES = {
    "cloudcode-pa.googleapis.com": "185.4.64.180",
    "daily-cloudcode-pa.googleapis.com": "185.4.64.180",
    "generativelanguage.googleapis.com": "185.4.64.180",
    "aicode.googleapis.com": "185.4.64.180",
}
BASE = os.environ.get("AMBER_BASE", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TLS_DIR = os.path.join(BASE, "assets", "certs")
LOG = os.path.join(BASE, "gate-proxy.log")

_local_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
_local_ctx.load_cert_chain(TLS_DIR + "/server.crt", TLS_DIR + "/server.key")
_local_ctx.set_alpn_protocols(["http/1.1"])

_up_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_up_ctx.load_verify_locations(cafile=os.path.join(BASE, "assets", "ca-bundle.pem"))
_up_ctx.check_hostname = True
_up_ctx.set_alpn_protocols(["http/1.1"])

_lock = threading.Lock()


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%F %T')} {msg}\n")


def read_headers(fp):
    lines = []
    while True:
        line = fp.readline(8192)
        if not line or line in (b"\r\n", b"\n"):
            break
        lines.append(line.rstrip(b"\r\n"))
    return lines


def parse_headers(lines):
    out = {}
    for line in lines[1:]:
        if b":" in line:
            k, v = line.split(b":", 1)
            out[k.decode("latin1").lower()] = v.decode("latin1").strip()
    return out


def dechunk(data):
    out = b""
    i = 0
    while i < len(data):
        j = data.find(b"\r\n", i)
        if j < 0:
            break
        try:
            n = int(data[i:j].split(b";")[0], 16)
        except ValueError:
            break
        i = j + 2
        if n == 0:
            break
        out += data[i:i + n]
        i += n + 2
    return out


def read_body(fp, headers):
    if headers.get("transfer-encoding", "").lower() == "chunked":
        raw = b""
        while True:
            line = fp.readline(8192)
            if not line:
                break
            n = int(line.strip().split(b";")[0], 16)
            if n == 0:
                fp.readline()
                break
            raw += fp.read(n)
            fp.read(2)
        return raw
    n = int(headers.get("content-length", "0") or 0)
    return fp.read(n) if n else b""


def forward(host, method, path, headers, body):
    primary = GATES.get(host, host)
    ips = [primary, "31.58.216.201", primary]
    ips = list(dict.fromkeys(ips))
    skip = {"proxy-authorization", "proxy-connection", "connection", "transfer-encoding",
            "content-length", "host", "accept-encoding", "te", "keep-alive"}
    parts = [f"{method} {path} HTTP/1.1", f"Host: {host}", "Connection: close",
             f"Content-Length: {len(body)}"]
    for k, v in headers.items():
        if k not in skip:
            parts.append(f"{k}: {v}")
    req = ("\r\n".join(parts) + "\r\n\r\n").encode("latin1") + body

    last_err = None
    for attempt, ip in enumerate(ips, 1):
        up = None
        try:
            raw = socket.create_connection((ip, 443), timeout=30)
            up = _up_ctx.wrap_socket(raw, server_hostname=host)
            up.settimeout(180)
            up.sendall(req)
            fp = up.makefile("rb")
            lines = read_headers(fp)
            if not lines:
                raise RuntimeError("пустой ответ от SNI-прокси")
            resp_headers = parse_headers(lines)
            resp_body = read_body(fp, resp_headers)
            status_line = lines[0].decode("latin1")
            if attempt > 1:
                log(f"успех с {ip} (попытка {attempt})")
            return up, status_line, resp_headers, resp_body
        except Exception as exc:
            last_err = exc
            log(f"попытка {attempt} через {ip}: {exc!r}")
            if up:
                try:
                    up.close()
                except OSError:
                    pass
    raise RuntimeError(f"все SNI-прокси недоступны: {last_err!r}")


def to_sse(body):
    try:
        obj = json.loads(body)
        return ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")
    except Exception:
        return b"data: " + body + b"\n\n"


def handle_gate(conn, host):
    conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    tls = _local_ctx.wrap_socket(conn, server_side=True)
    fp = tls.makefile("rb")
    try:
        while True:
            lines = read_headers(fp)
            if not lines:
                break
            first = lines[0].decode("latin1").split()
            if len(first) < 2:
                break
            method, path = first[0], first[1]
            headers = parse_headers(lines)
            body = read_body(fp, headers)
            stream = "/v1internal:streamGenerateContent" in path
            if stream:
                path = path.replace("/v1internal:streamGenerateContent", "/v1internal:generateContent")
                path = path.replace("alt=sse", "").replace("?&", "?").rstrip("?")
            log(f"{method} {host}{path[:60]} stream={stream}")
            try:
                up, status, resp_headers, resp_body = forward(host, method, path, headers, body)
            except Exception as exc:
                log(f"forward failed: {exc!r}")
                tls.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                break
            try:
                if stream:
                    log(f"upstream {status} len={len(resp_body)} body={resp_body[:160]!r}")
                if stream and " 200" in status:
                    payload = to_sse(resp_body)
                    log(f"SSE answer len={len(payload)}")
                    head = ("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                            "Cache-Control: no-cache\r\nConnection: close\r\n"
                            f"Content-Length: {len(payload)}\r\n\r\n").encode()
                    tls.sendall(head + payload)
                else:
                    out = [status, "Connection: close"]
                    content_type = resp_headers.get("content-type")
                    if content_type:
                        out.append("Content-Type: " + content_type)
                    out.append(f"Content-Length: {len(resp_body)}")
                    tls.sendall(("\r\n".join(out) + "\r\n\r\n").encode("latin1") + resp_body)
            finally:
                up.close()
            break  # Connection: close — клиент откроет новое соединение
    finally:
        try:
            tls.close()
        except OSError:
            pass


def handle_raw(conn, host, port):
    log(f"TUNNEL {host}:{port}")
    up = socket.create_connection((host, port), timeout=10)
    conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

    def pipe(a, b):
        try:
            while True:
                d = a.recv(65536)
                if not d:
                    break
                b.sendall(d)
        except OSError:
            pass
        finally:
            try:
                b.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    t = threading.Thread(target=pipe, args=(conn, up), daemon=True)
    t.start()
    pipe(up, conn)
    t.join(timeout=3)
    conn.close()


def read_request_line(conn):
    """Читает заголовки CONNECT побайтно, чтобы не проглотить ClientHello."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = conn.recv(1)
        if not chunk:
            break
        buf += chunk
        if len(buf) > 8192:
            break
    return buf.split(b"\r\n", 1)[0].decode("latin1", "replace")


def handle(conn):
    try:
        head = read_request_line(conn)
        parts = head.split()
        if len(parts) < 2 or parts[0].upper() != "CONNECT":
            conn.sendall(b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n")
            return
        target = parts[1]
        host, _, port = target.rpartition(":")
        port = int(port)
        # сбросить уже прочитанные байты из bufsize-обёртки обратно в сокет
        # (makefile читает только одну строку, остальное осталось в сокете)
        if host in GATES:
            handle_gate(conn, host)
        else:
            handle_raw(conn, host, port)
    except Exception as exc:
        log(f"ошибка: {exc!r}")
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    log("TLS-прокси запущен")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(LISTEN)
    server.listen(64)
    while True:
        c, _ = server.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
