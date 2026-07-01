import threading
import time
from sidecar.clipboard_mutex import CLIPBOARD_LOCK


def test_clipboard_lock_prevents_interleaving():
    shared_history = []

    def worker(worker_id: int):
        with CLIPBOARD_LOCK:
            shared_history.append(f"start-{worker_id}")
            # Simulate copy + paste delay
            time.sleep(0.05)
            shared_history.append(f"end-{worker_id}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Check that for each worker_id, start and end are contiguous in history (no interleaving!)
    # E.g. ["start-0", "end-0", "start-1", "end-1", ...] and NOT ["start-0", "start-1", "end-0", ...]
    for idx in range(0, len(shared_history), 2):
        start_item = shared_history[idx]
        end_item = shared_history[idx + 1]
        assert start_item.replace("start-", "") == end_item.replace("end-", "")
