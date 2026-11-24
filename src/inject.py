#!/usr/bin/env python3
"""Янтарь: один CDP-инжектор — русский UI, кнопки аккаунтов, мост команд.

Только стандартная библиотека. Работает на Linux и Windows.
Гарантирует одну копию через lock-файл и повторно внедряет оверлей,
если страница перезагрузилась или кнопки исчезли.
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
BUNDLED = os.path.join(BASE, "src", "ag-accounts")
ACCOUNTS = BUNDLED if os.path.isfile(BUNDLED) else os.path.join(
    os.path.expanduser("~"), ".local", "bin", "ag-accounts")
LOCK = os.path.join(BASE, "injector.lock")


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


def single_instance():
    """Один инжектор на установку: иначе несколько копий мешают внедрению."""
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            pid = int(open(LOCK).read().strip())
            os.kill(pid, 0)
            return False  # живой процесс уже есть
        except Exception:
            os.unlink(LOCK)
            return single_instance()
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


def targets():
    try:
        with OPENER.open(f"http://127.0.0.1:{PORT}/json/list", timeout=2) as r:
            return json.load(r)
    except Exception:
        return []


def is_app(t):
    url = t.get("url", "")
    return (url.startswith("https://127.0.0.1:") or "Antigravity" in t.get("title", ""))


def connect(t):
    path = t["webSocketDebuggerUrl"].split(f"127.0.0.1:{PORT}", 1)[-1]
    return MiniWebSocket(path)


def evaluate(ws, expression, timeout=6):
    res = ws.call("Runtime.evaluate", {"expression": expression, "returnByValue": True},
                  timeout=timeout)
    return (res.get("result") or {}).get("value")


def ready(ws):
    try:
        return evaluate(ws, "document.readyState === 'complete'") is True
    except Exception:
        return False


def installed(ws):
    try:
        return evaluate(ws, "window.__antigravityI18nInstalled === true && "
                            "!!document.querySelector('.amber-acc-btn')") is True
    except Exception:
        return False


def inject(ws, source):
    ws.call("Page.addScriptToEvaluateOnNewDocument", {"source": source})
    ws.call("Runtime.evaluate", {"expression": source, "awaitPromise": False}, timeout=8)


def account_data():
    data = {"current": {}, "profiles": []}
    try:
        data["current"] = json.loads(subprocess.check_output(
            [ACCOUNTS, "current", "--json"], text=True, timeout=6))
    except Exception:
        pass
    try:
        data["profiles"] = json.loads(subprocess.check_output(
            [ACCOUNTS, "list", "--json"], text=True, timeout=6))
    except Exception:
        pass
    return data


def run_command(cmd, label):
    try:
        subprocess.run([ACCOUNTS, cmd, label], timeout=60, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[Amber] команда аккаунта: {cmd} {label}", flush=True)
    except Exception as exc:
        print(f"[Amber] ошибка команды: {exc}", flush=True)


def main():
    if not single_instance():
        print("[Amber] уже запущен другой инжектор", flush=True)
        return
    with open(OVERLAY, "r", encoding="utf-8") as f:
        source = f.read()
    last_accounts = 0.0
    last_try = {}
    print("[Amber] инжектор запущен", flush=True)
    try:
        while True:
            page = None
            for t in targets():
                if t.get("type") != "page" or not is_app(t) or not t.get("webSocketDebuggerUrl"):
                    continue
                tid = t.get("id", "")
                if page is None and "Antigravity" in t.get("title", ""):
                    page = t
                now = time.monotonic()
                if now - last_try.get(tid, 0) < 5:
                    continue
                last_try[tid] = now
                try:
                    ws = connect(t)
                    try:
                        if ready(ws) and not installed(ws):
                            inject(ws, source)
                            if installed(ws):
                                print(f"[Amber] интерфейс готов: {t.get('title','')[:35]}",
                                      flush=True)
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
                            ws.call("Runtime.evaluate", {
                                "expression": "window.__amberAccountData=" +
                                              json.dumps(data, ensure_ascii=False) + ";true",
                                "returnByValue": True,
                            }, timeout=5)
                            last_accounts = time.monotonic()
                        cmd = evaluate(ws, "window.__amberCommand ? "
                                           "JSON.stringify(window.__amberCommand) : null")
                        if cmd:
                            c = json.loads(cmd)
                            ws.call("Runtime.evaluate",
                                    {"expression": "delete window.__amberCommand"}, timeout=5)
                            if c.get("cmd") in ("use", "add") and c.get("label"):
                                run_command(c["cmd"], c["label"])
                    finally:
                        ws.close()
                except Exception as exc:
                    print(f"[Amber] мост аккаунтов: {exc}", flush=True)
            time.sleep(1.5)
    finally:
        try:
            os.unlink(LOCK)
        except OSError:
            pass


if __name__ == "__main__":
    main()
