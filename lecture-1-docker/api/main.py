from threading import Lock, Thread

from flask import Flask, request

app = Flask(__name__)

# Keep allocated blocks reachable so Python cannot release them.
allocations: list[bytearray] = []
allocations_lock = Lock()


@app.get("/health")
def health():
    return "ok\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.get("/eat")
def eat():
    try:
        mb = int(request.args.get("mb", ""))
    except ValueError:
        return "mb must be an integer\n", 400

    # Touch each 4 KiB page so the kernel backs the allocation with memory.
    block = bytearray(mb * 1024 * 1024)
    for offset in range(0, len(block), 4096):
        block[offset] = 1
    with allocations_lock:
        allocations.append(block)
    return f"allocated and holding {mb} MiB\n", 200


@app.get("/burn")
def burn():
    def burn_cpu():
        n = 0
        while True:
            n += 1
            if n == 1_000_000:
                n = 0
    Thread(target=burn_cpu, daemon=True).start()
    return "CPU burner started\n", 200


if __name__ == "__main__":
    # Disable the reloader so one stable process owns the service and PID.
    app.run(host="0.0.0.0", port=8080, threaded=True, use_reloader=False)
