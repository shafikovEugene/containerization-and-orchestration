import os
import time
import threading

CPU_WORKERS = int(os.getenv("CPU_WORKERS", "1"))
MEM_STEP_MB = int(os.getenv("MEM_STEP_MB", "10"))
MEM_INTERVAL_S = float(os.getenv("MEM_INTERVAL_S", "5"))
MEM_MAX_MB = int(os.getenv("MEM_MAX_MB", "0"))  # 0 = без ограничения


def cpu_burner():
    x = 0
    while True:
        x = (x + 1) % 1_000_000
        _ = x * x % 7


def memory_burner():
    chunks = []
    total_mb = 0

    while MEM_MAX_MB == 0 or total_mb < MEM_MAX_MB:
        chunk = bytearray(MEM_STEP_MB * 1024 * 1024)
        # Записываем в память, чтобы страницы действительно выделялись
        for i in range(0, len(chunk), 4096):
            chunk[i] = 1

        chunks.append(chunk)
        total_mb += MEM_STEP_MB
        time.sleep(MEM_INTERVAL_S)

    while True:
        time.sleep(60)


def main():
    for _ in range(CPU_WORKERS):
        threading.Thread(target=cpu_burner, daemon=True).start()

    memory_burner()


if __name__ == "__main__":
    main()