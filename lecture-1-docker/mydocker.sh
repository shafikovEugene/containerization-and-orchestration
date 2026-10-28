#!/usr/bin/env bash
set -euo pipefail

# Параметры
CGROUP_NAME="lab1-api"
PID_LIMIT=5
MEMORY_LIMIT="67108864"  # 64 МБ
CPU_LIMIT="50000 100000" # 0.5 CPU
SCRIPT_PATH="$(realpath ./api/seccomp-filter-main.py)"

# Cgroupv2
CGROUP_DIR="/sys/fs/cgroup/$CGROUP_NAME"

echo "+cpu +memory +pids" | sudo tee /sys/fs/cgroup/cgroup.subtree_control > /dev/null || true

sudo mkdir -p "$CGROUP_DIR"
echo "$MEMORY_LIMIT" | sudo tee "$CGROUP_DIR/memory.max" > /dev/null
echo "$CPU_LIMIT" | sudo tee "$CGROUP_DIR/cpu.max" > /dev/null
echo "$PID_LIMIT" | sudo tee "$CGROUP_DIR/pids.max" > /dev/null
echo $$ | sudo tee "$CGROUP_DIR/cgroup.procs" > /dev/null

# Запуск процесса с namespace'ами и seccomp-профилем
exec unshare --pid --mount --uts --ipc --user --net --fork --map-root-user --mount-proc \
  bash -c "
    hostname my-docker
    ip link set lo up
    exec setpriv --inh-caps=-all --bounding-set=-all python3 $SCRIPT_PATH
  "