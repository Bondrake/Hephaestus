"""Dummy agent for verifying control channel."""
import sys
import time
import os

# Flush stdout immediately
sys.stdout.reconfigure(line_buffering=True)

print("Dummy agent started")
log_file = "dummy_agent.log"

with open(log_file, "w") as f:
    f.write("Started\n")

try:
    while True:
        line = sys.stdin.readline()
        if line:
            with open(log_file, "a") as f:
                f.write(f"Received: {line}")
            print(f"Processed: {line.strip()}")
        else:
            time.sleep(0.1)
except KeyboardInterrupt:
    print("Dummy agent stopping")
