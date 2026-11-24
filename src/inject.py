#!/usr/bin/env python3
"""Универсальный CDP-инжектор Янтаря: русский UI + кнопки аккаунтов.

Только стандартная библиотека Python, работает на Linux и Windows.
Файлы приложения не изменяются: всё внедряется через локальный CDP-порт.
"""
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request

PORT = int(os.environ.get("AMBER_DEBUG_PORT", "58321"))
BASE = os.environ.get("AMBER_BASE", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OVERLAY = os.path.join(BASE, "assets", "overlay.js")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ACCOUNTS = os.path.join(os.path.expanduser("~"), ".local", "bin", "ag-accounts")


class MiniWebSocket:
    def __init__(self, path, timeout=5):
        self.sock = socket.create_connection(("127.0.0.1", PORT), timeout=timeout)
        self.buf = bytearray()
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode())
        while b"\r\n\r\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("handshake closed")
            self.buf.extend(chunk)
        i = self.buf.index(b"\r\n\r\n") + 4
        head = bytes(self.buf[:i]).decode("latin1")
        del self.buf[:i]
        if " 101 " not in head.splitlines()[0]:
            raise ConnectionError(head.splitlines()[0])

    def _recv(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self.buf)))
            if not chunk:
                raise EOFError
            self.buf.extend(chunk)
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def send(self, payload):
        data = payload.encode()
        mask = os.urandom(4)
        n = len(data)
        head = bytearray([0x81])
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head.extend(struct.pack("!H", n))
        else:
            head.append(0x80 | 127)
            head.extend(struct.pack("!Q", n))
        head.extend(mask)
        head.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        self.sock.sendall(bytes(head))

    def recv(self, timeout=3):
        self.sock.settimeout(timeout)
        while True:
            a, b = self._recv(2)
            opcode = a & 0x0F
            n = b & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._recv(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._recv(8))[0]
            masked = bool(b & 0x80)
            mask = self._recv(4) if masked else None
            data = self._recv(n)
            if masked:
                data = bytes(x ^ mask[i % 4] for i, x in enumerate(data))
            if opcode == 0x8:
                raise EOFError("closed")
            if opcode == 0x9:
                continue
            if opcode in (0x1, 0x2):
                return data.decode("utf-8", "replace")

    def call(self, method, params, req_id=1, timeout=5):
        self.send(json.dumps({"id": req_id, "method": method, "params": params}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = json.loads(self.recv(timeout=max(0.2, deadline - time.monotonic())))
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(str(msg["error"]))
                return msg.get("result") or {}
        raise TimeoutError(method)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def targets():
    try:
        with OPENER.open(f"http://127.0.0.1:{PORT}/json/list", timeout=2) as r:
            return json.load(r)
    except Exception:
        return []


def connect(target):
    path = target["webSocketDebuggerUrl"].split(f"127.0.0.1:{PORT}", 1)[-1]
    return MiniWebSocket(path)


def evaluate(ws, expression, timeout=6):
    res = ws.call("Runtime.evaluate", {"expression": expression, "returnByValue": True},
                  timeout=timeout)
    return (res.get("result") or {}).get("value")


def account_data():
    data = {"current": {}, "profiles": []}
    try:
        out = subprocess.check_output([ACCOUNTS, "current", "--json"], text=True, timeout=6)
        data["current"] = json.loads(out)
    except Exception:
        pass
    try:
        out = subprocess.check_output([ACCOUNTS, "list", "--json"], text=True, timeout=6)
        data["profiles"] = json.loads(out)
    except Exception:
        pass
    return data


def run_command(cmd, label):
    try:
        subprocess.run([ACCOUNTS, cmd, label], timeout=60, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[Amber] команда аккаунта выполнена: {cmd} {label}", flush=True)
    except Exception as exc:
        print(f"[Amber] ошибка команды: {exc}", flush=True)


def main():
    with open(OVERLAY, "r", encoding="utf-8") as f:
        source = f.read()
    seen = set()
    last_accounts = 0.0
    print("[Amber] инжектор запущен", flush=True)
    while True:
        page = None
        for t in targets():
            tid = t.get("id", "")
            if t.get("type") != "page" or not t.get("webSocketDebuggerUrl"):
                continue
            if page is None and "Antigravity" in t.get("title", ""):
                page = t
            if tid in seen:
                continue
            try:
                ws = connect(t)
                try:
                    if evaluate(ws, "window.__antigravityI18nInstalled === true"):
                        seen.add(tid)
                        continue
                    ws.call("Page.addScriptToEvaluateOnNewDocument", {"source": source})
                    ws.call("Runtime.evaluate", {"expression": source, "awaitPromise": False},
                            timeout=8)
                    if evaluate(ws, "window.__antigravityI18nInstalled === true"):
                        seen.add(tid)
                        print(f"[Amber] перевод внедрён: {t.get('title','')[:40]}", flush=True)
                finally:
                    ws.close()
            except Exception as exc:
                print(f"[Amber] пропуск таргета: {exc}", flush=True)

        if page is not None:
            try:
                ws = connect(page)
                try:
                    if time.monotonic() - last_accounts > 4:
                        data = account_data()
                        pending = os.path.join(os.path.expanduser("~"), ".gemini",
                                               "antigravity-accounts", "pending_add")
                        if os.path.isfile(pending) and data["current"].get("email"):
                            known = {p.get("email") for p in data["profiles"]}
                            if data["current"]["email"] not in known:
                                label = open(pending, encoding="utf-8").read().strip()
                                run_command("save", label)
                                os.remove(pending)
                                data = account_data()
                        payload = json.dumps(data, ensure_ascii=False)
                        ws.call("Runtime.evaluate", {
                            "expression": "window.__amberAccountData=" + payload + ";true",
                            "returnByValue": True,
                        }, timeout=5)
                        last_accounts = time.monotonic()
                    cmd = evaluate(ws, "window.__amberCommand ? JSON.stringify(window.__amberCommand) : null")
                    if cmd:
                        c = json.loads(cmd)
                        ws.call("Runtime.evaluate", {"expression": "delete window.__amberCommand"},
                                timeout=5)
                        if c.get("cmd") in ("use", "add") and c.get("label"):
                            run_command(c["cmd"], c["label"])
                finally:
                    ws.close()
            except Exception as exc:
                print(f"[Amber] мост аккаунтов: {exc}", flush=True)
        time.sleep(1.5)


if __name__ == "__main__":
    main()
