import subprocess
import threading
import time
import os
import signal
import logging

logger = logging.getLogger(__name__)

class MockPane:
    def __init__(self, session_name, start_directory):
        self.session_name = session_name
        self.cwd = start_directory
        self.process = None
        self.output_buffer = []
        self.lock = threading.Lock()

    def send_keys(self, cmd, enter=True):
        print(f"[MOCK_TMUX] send_keys: {cmd}")
        
        if not self.process:
            # If no process is running, assume this is the launch command
            # But wait, send_keys might be setting env vars first (export ...)
            if cmd.startswith("export "):
                # Ignore exports for now or handle them?
                # We can't easily set env vars for a future process unless we store them.
                return

            # Launch the process
            # We expect cmd to be "python3 .../stub_cli.py ..."
            try:
                # Split command into args, respecting quotes?
                # shlex might be needed, but for now simple split or shell=True
                # shell=True is easier for mocking
                
                self.process = subprocess.Popen(
                    cmd,
                    shell=True,
                    cwd=self.cwd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1 # Line buffered
                )
                
                # Start threads to read output
                threading.Thread(target=self._read_stdout, daemon=True).start()
                threading.Thread(target=self._read_stderr, daemon=True).start()
                
            except Exception as e:
                print(f"[MOCK_TMUX] Failed to start process: {e}")
        else:
            # Process is running, write to stdin
            if self.process.stdin:
                try:
                    self.process.stdin.write(cmd)
                    if enter:
                        self.process.stdin.write("\n")
                    self.process.stdin.flush()
                except Exception as e:
                    print(f"[MOCK_TMUX] Failed to write to stdin: {e}")

    def _read_stdout(self):
        if not self.process:
            return
        for line in self.process.stdout:
            print(f"[MOCK_TMUX_STDOUT] {line.strip()}")
            with self.lock:
                self.output_buffer.append(line.strip())
                # Keep buffer size reasonable
                if len(self.output_buffer) > 1000:
                    self.output_buffer.pop(0)

    def _read_stderr(self):
        if not self.process:
            return
        for line in self.process.stderr:
            print(f"[MOCK_TMUX_STDERR] {line.strip()}")
            with self.lock:
                self.output_buffer.append(line.strip())
                if len(self.output_buffer) > 1000:
                    self.output_buffer.pop(0)

    def cmd(self, *args):
        # Handle capture-pane
        if args[0] == "capture-pane":
            class Result:
                def __init__(self, stdout):
                    self.stdout = stdout
            
            with self.lock:
                return Result(list(self.output_buffer))
        return None

    def kill(self):
        if self.process:
            try:
                os.kill(self.process.pid, signal.SIGTERM)
            except:
                pass
            self.process = None

class MockWindow:
    def __init__(self, session_name, start_directory):
        self.attached_pane = MockPane(session_name, start_directory)

class MockSession:
    def __init__(self, session_name, start_directory):
        self.name = session_name
        self.attached_window = MockWindow(session_name, start_directory)
    
    def kill_session(self):
        self.attached_window.attached_pane.kill()

class MockTmuxServer:
    def __init__(self):
        self.sessions = {}

    def has_session(self, session_name):
        return session_name in self.sessions

    def new_session(self, session_name, start_directory=None, **kwargs):
        session = MockSession(session_name, start_directory)
        self.sessions[session_name] = session
        return session

    def get_by_id(self, session_name):
        return self.sessions.get(session_name)
