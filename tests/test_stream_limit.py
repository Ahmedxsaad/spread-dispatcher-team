"""A stream whose server accepts the connection and then says nothing must give up after seconds, not minutes."""
import socket
import threading
import time
import unittest

import spread.stream

import desk.live as live


class StreamLimitTest(unittest.TestCase):
    def setUp(self):
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(5)
        self.held = []
        threading.Thread(target=self.accept, daemon=True).start()
        self.before = spread.stream.QUIET_LIMIT

    def accept(self):
        while True:
            try:
                self.held.append(self.server.accept()[0])  # accepted, and never answered
            except OSError:
                return

    def tearDown(self):
        spread.stream.QUIET_LIMIT = self.before
        self.server.close()
        for connection in self.held:
            connection.close()

    def test_a_silent_handshake_times_out_within_the_limit(self):
        self.assertEqual(live.STREAM, 5.0)
        spread.stream.QUIET_LIMIT = 0.5  # the same switch that play_live sets, shorter for the test
        began = time.monotonic()
        with self.assertRaises(OSError):
            next(spread.stream.websocket(f"http://127.0.0.1:{self.server.getsockname()[1]}", "/v1/worlds/w/stream", "key", 0.4))
        self.assertLess(time.monotonic() - began, 3.0)

    def test_a_frame_that_stops_half_way_times_out_within_the_limit(self):
        port = self.server.getsockname()[1]
        spread.stream.QUIET_LIMIT = 0.5
        stream = spread.stream.websocket(f"http://127.0.0.1:{port}", "/v1/worlds/w/stream", "key", 0.4)
        result = {}

        def read():
            began = time.monotonic()
            try:
                result["event"] = next(stream)
            except OSError as error:
                result["error"] = error
            result["seconds"] = time.monotonic() - began

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        while not self.held:
            time.sleep(0.01)
        connection = self.held[0]
        connection.recv(4096)
        connection.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n")
        connection.sendall(bytes([0x81, 20]) + b'{"seq": 1, "at"')  # a text frame of 20 bytes, of which 15 arrive
        reader.join(5)
        self.assertIn("error", result)
        self.assertLess(result["seconds"], 3.0)


if __name__ == "__main__":
    unittest.main()
