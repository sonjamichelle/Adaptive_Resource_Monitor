"""Loopback-only test endpoint with a fixed synthetic telemetry frame."""
import socket
import threading

import paramiko

from arm.providers.ssh import probe_command

SECRET = "arm-fixture-only"
COMMAND = probe_command().encode()
FRAME = (
    "os\tLinux fixture\nboot\t{boot}\nuptime\t12345.67\ncpu\tcpu\t{busy} 0 200 500 0 0 0 0 0 0\n"
    "cpu\tcpu0\t{busy} 0 200 500 0 0 0 0 0 0\n"
    "ram\tMemTotal\t16384\nram\tMemAvailable\t12000\n"
    "ram\tSwapTotal\t2024\nram\tSwapFree\t1024\n"
    "disk\tnvme0n1\t1 0 {busy} 3 4 0 {busy} 3 0 50 99\n"
    "net\teth0\t1\tup\t10000\t{busy} 0 0 0 0 0 0 0 {busy} 0 0 0 0 0 0 0\n"
    "net\tvpn0\t0\tup\t\t{busy} 0 0 0 0 0 0 0 {busy} 0 0 0 0 0 0 0\n"
    "drm\t0000:01:00.0\t0x1002\t0x1234\t80\t128\t512\t40000\t1500\t800\t10000000,50000000\n"
)


class Secret:
    def __init__(self, secret=SECRET):
        self.secret = secret

    def read(self, reference):
        return self.secret


class Auth(paramiko.ServerInterface):
    def __init__(self, key=None):
        self.exec = threading.Event()
        self.command = None
        self.key = key

    def check_auth_password(self, username, password):
        return (paramiko.AUTH_SUCCESSFUL if (username, password) == ("tester", SECRET)
                else paramiko.AUTH_FAILED)

    def check_auth_publickey(self, username, key):
        return paramiko.AUTH_SUCCESSFUL if username == "tester" and key == self.key else paramiko.AUTH_FAILED

    def check_channel_request(self, kind, channel_id):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel, command):
        self.command = command
        self.exec.set()
        return command == COMMAND


class Fixture:
    def __init__(self, *, key=None, drop_first=False, public=None, gate=None):
        self.key = key or paramiko.RSAKey.generate(2048)
        self.drop_first, self.public = drop_first, public
        self.gate = gate
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.listener.settimeout(.25)
        self.port = self.listener.getsockname()[1]
        self.connections = 0
        self.samples = 0
        self.commands = []
        self.errors = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.listener.close()
        self.thread.join(5)
        if self.thread.is_alive():
            raise TimeoutError("SSH test fixture did not stop")
        if self.errors:
            raise AssertionError(self.errors)

    def run(self):
        while not self.stop.is_set():
            try:
                sock, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.connections += 1
            transport = paramiko.Transport(sock)
            transport.add_server_key(self.key)
            server = Auth(self.public)
            try:
                transport.start_server(server=server)
                channel = transport.accept(timeout=2)
                if channel is None or not server.exec.wait(1):
                    continue
                self.commands.append(server.command)
                channel.settimeout(.2)
                buf = b""
                while not self.stop.is_set():
                    try:
                        data = channel.recv(32768)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if line != b".":
                            continue
                        self.samples += 1
                        if self.drop_first and self.samples == 1:
                            transport.close()
                            break
                        if self.gate is not None:
                            while not self.stop.is_set() and not self.gate.wait(.05):
                                pass
                            if self.stop.is_set():
                                break
                        frame = FRAME.format(boot=102, busy=100 + self.samples * 10)
                        channel.sendall(b"@arm-begin\n" + frame.encode() + b"@arm-end\n")
            except (OSError, EOFError, paramiko.SSHException):
                pass
            except Exception as exc:
                self.errors.append(exc)
            finally:
                transport.close()
