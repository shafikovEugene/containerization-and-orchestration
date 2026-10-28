import pyseccomp as seccomp
import os
import sys


f = seccomp.SyscallFilter(defaction=seccomp.ALLOW)

f.add_rule(seccomp.ERRNO(1), "mount")
f.add_rule(seccomp.ERRNO(1), "umount2")
f.add_rule(seccomp.ERRNO(1), "reboot")

f.load()

os.execv(sys.executable, [sys.executable, './api/main.py'])