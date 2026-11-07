"""Scoped lifecycle for the lab's owned threaded TCP/UDP fixtures."""
from contextlib import contextmanager
import json
import os
import sys
import threading
import time


@contextmanager
def serving(server, owner):
    metadata = dict(owner=owner, pid=os.getpid(), listener_started=time.time(),
                    port=server.server_address[1],
                    cleanup='server.shutdown(); thread.join(); server.server_close()')
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
        closed = server.socket.fileno() == -1
        print(json.dumps(dict(event='owned_listener_closed', **metadata,
                              descriptor_closed=closed, thread_joined=not thread.is_alive())), file=sys.stderr)
        if thread.is_alive() or not closed:
            raise RuntimeError(f'{owner}: owned listener did not close')
