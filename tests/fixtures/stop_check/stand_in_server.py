"""A stand-in for the app's server entry, for the stop check's own tests.

    stand_in_server.py --run-streamlit-server PORT

Run as the check runs the download's server entry (the sentinel and a port
after the program). STAND_IN_SERVER_MODE says how it behaves:

  silent  it listens on 127.0.0.1:PORT, writes the listening mark once it
          does, answers Streamlit's health check ("ok", with an XSRF
          cookie) and opens a WebSocket on the session's route (101, the
          opening's own accept key) under the Host 127.0.0.1, with no Origin
          or that Host's own, refusing (403) one under any other Host or
          from any other Origin, as the app's server does; then it reads
          what the session sends and sends nothing back: a run that never
          starts.
  stalls  as silent, but after the session's first message it sends the
          session's start, a text box and a markdown element, built by
          Streamlit's own classes, then nothing: a run that starts and
          stalls.
  liar    it writes the listening mark for PORT and never listens.
  mute    it listens and answers as silent, but never writes the mark.

It ends at the end of its input (a pipe), or on SIGTERM, as the app's server
does; a test's clean-up ends it otherwise.
"""
import base64
import hashlib
import os
import socket
import sys
import threading
import time

SENTINEL = "--run-streamlit-server"
MARK = "zij-server-listening"
MODE = os.environ.get("STAND_IN_SERVER_MODE", "silent")


def _end_at_the_end_of_input():
    try:
        while os.read(0, 4096):
            pass
    except OSError:
        return
    os._exit(0)


def _frame(payload):
    size = len(payload)
    if size < 126:
        head = bytes([0x82, size])
    elif size < 65536:
        head = bytes([0x82, 126]) + size.to_bytes(2, "big")
    else:
        head = bytes([0x82, 127]) + size.to_bytes(8, "big")
    return head + payload


def _stalled_run():
    from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

    out = []
    start = ForwardMsg()
    start.new_session.SetInParent()
    out.append(start)
    box = ForwardMsg()
    box.delta.new_element.text_input.id = "$$ID-00-location_input_key"
    box.delta.new_element.text_input.label = "City, or latitude, longitude"
    out.append(box)
    words = ForwardMsg()
    words.delta.new_element.markdown.body = "a line of markdown"
    out.append(words)
    return b"".join(_frame(msg.SerializeToString()) for msg in out)


def _read_head(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        got = conn.recv(4096)
        if not got:
            return None, b""
        data += got
    head, rest = data.split(b"\r\n\r\n", 1)
    return head.decode("latin-1").split("\r\n"), rest


def _serve(conn):
    with conn:
        lines, rest = _read_head(conn)
        if not lines:
            return
        path = lines[0].split()[1] if len(lines[0].split()) > 1 else ""
        headers = {name.strip().lower(): value.strip() for name, _, value in
                   (line.partition(":") for line in lines[1:])}
        if path == "/_stcore/health":
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nSet-Cookie: _streamlit_xsrf=2|aa|bb|1; Path=/\r\n"
                         b"Connection: close\r\n\r\nok")
            return
        if path != "/_stcore/stream" or "sec-websocket-key" not in headers:
            conn.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            return
        host, origin = headers.get("host", ""), headers.get("origin")
        if host.rpartition(":")[0] != "127.0.0.1" or origin not in (None, f"http://{host}"):
            conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            return
        accept = base64.b64encode(hashlib.sha1((headers["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                                               .encode("ascii")).digest()).decode("ascii")
        conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Accept: {accept}\r\nSec-WebSocket-Protocol: streamlit\r\n\r\n").encode("ascii"))
        answered = False
        while True:
            got = rest or conn.recv(65536)
            rest = b""
            if not got:
                return
            if MODE == "stalls" and not answered:
                conn.sendall(_stalled_run())
                answered = True


def main():
    port = int(sys.argv[sys.argv.index(SENTINEL) + 1])
    threading.Thread(target=_end_at_the_end_of_input, daemon=True).start()
    if MODE == "liar":
        print(f"{MARK} {port}", flush=True)
        while True:
            time.sleep(1)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", port))
    server.listen(16)
    if MODE != "mute":
        print(f"{MARK} {port}", flush=True)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=_serve, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
