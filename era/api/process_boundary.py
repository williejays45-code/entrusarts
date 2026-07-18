"""Owned process-tree execution for the ERA property API.

The parent starts a worker that has no API audit or persistence handles.  On
Windows the worker is assigned to a kill-on-close Job Object before the JSON
request is written to stdin, so every subsequently-created PowerShell/OLE DB
child is contained in the same owned process tree.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass


CREATE_NO_WINDOW = 0x08000000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1
MAX_FRAME_HEADER_BYTES = 20
MAX_FRAME_BODY_BYTES = 256 * 1024
MAX_STDERR_BYTES = 16_384


if os.name == "nt":
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION_STRUCT(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION_STRUCT(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]


class ProcessContainmentError(RuntimeError):
    """Closed process-containment failure with no OS diagnostics attached."""


class _WindowsJob:
    def __init__(self):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32 = kernel32
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._handle = kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise ProcessContainmentError("WORKER_CONTAINMENT_UNAVAILABLE")
        limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION_STRUCT()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
                self._handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ProcessContainmentError("WORKER_CONTAINMENT_UNAVAILABLE")

    def assign(self, process):
        if not self._kernel32.AssignProcessToJobObject(
                self._handle, wintypes.HANDLE(int(process._handle))):
            raise ProcessContainmentError("WORKER_CONTAINMENT_ASSIGNMENT_FAILED")

    def terminate(self):
        return bool(self._kernel32.TerminateJobObject(self._handle, 1))

    def active_processes(self):
        accounting = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION_STRUCT()
        returned = wintypes.DWORD()
        if not self._kernel32.QueryInformationJobObject(
                self._handle, JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                ctypes.byref(accounting), ctypes.sizeof(accounting),
                ctypes.byref(returned)):
            return None
        return int(accounting.ActiveProcesses)

    def close(self):
        if getattr(self, "_handle", None):
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


@dataclass(frozen=True)
class OwnedProcessResult:
    outcome: str
    stdout: bytes
    exit_code: int | None
    tree_closed: bool
    elapsed_seconds: float


class OwnedProcessBoundary:
    """One exact ``Popen`` plus its enforceable owned process-tree boundary."""

    def __init__(self, command=None):
        self.command = command or [sys.executable, "-B", "-m", "era.api.isolated_worker"]
        self._state_lock = threading.Lock()
        self._cancelled = threading.Event()
        self._process = None
        self._job = None
        self._closed = threading.Event()
        self.last_retained_stdout_bytes = 0
        self.last_retained_stderr_bytes = 0

    @staticmethod
    def _worker_environment():
        """Minimal execution environment; deliberately excludes every ERA secret."""
        allowed = {
            "COMSPEC", "PATH", "PATHEXT", "PYTHONHOME", "PYTHONPATH",
            "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "TMP", "VIRTUAL_ENV", "WINDIR",
        }
        environment = {
            key: value for key, value in os.environ.items()
            if key.upper() in allowed
        }
        environment["PYTHONIOENCODING"] = "utf-8"
        return environment

    def cancel(self, closure_seconds):
        """Cancel the exact currently-owned boundary; never resolve a PID."""
        self._cancelled.set()
        with self._state_lock:
            process, job = self._process, self._job
        if process is None:
            return True
        return self._terminate_tree(job, process, closure_seconds)

    def wait_closed(self, timeout):
        return self._closed.wait(timeout)

    @staticmethod
    def _read_framed_stdout(pipe, state, stop):
        try:
            header = bytearray()
            while not stop.is_set():
                byte = pipe.read(1)
                if not byte:
                    state["error"] = "IPC_TRUNCATED"
                    return
                if byte == b"\n":
                    break
                header.extend(byte)
                if len(header) > MAX_FRAME_HEADER_BYTES:
                    state["error"] = "IPC_HEADER_OVERLONG"
                    return
            if stop.is_set():
                return
            try:
                text = header.decode("ascii")
            except UnicodeDecodeError:
                state["error"] = "IPC_HEADER_INVALID"
                return
            if not text or not text.isascii() or not text.isdecimal():
                state["error"] = "IPC_HEADER_INVALID"
                return
            length = int(text)
            if length > MAX_FRAME_BODY_BYTES:
                state["error"] = "IPC_BODY_OVERSIZED"
                return
            body = bytearray()
            while len(body) < length and not stop.is_set():
                chunk = pipe.read(min(8192, length - len(body)))
                if not chunk:
                    state["error"] = "IPC_TRUNCATED"
                    return
                body.extend(chunk)
                state["stdout_retained"] = len(body)
                if len(body) > MAX_FRAME_BODY_BYTES:
                    state["error"] = "IPC_BODY_OVERSIZED"
                    return
            if stop.is_set():
                return
            trailing = pipe.read(1)
            if trailing:
                state["error"] = "IPC_TRAILING_BYTES"
                return
            state["body"] = bytes(body)
        except Exception:
            state["error"] = "IPC_READ_FAILED"
        finally:
            state["stdout_done"] = True

    @staticmethod
    def _read_bounded_stderr(pipe, state, stop):
        retained = bytearray()
        try:
            while not stop.is_set():
                chunk = pipe.read(4096)
                if not chunk:
                    break
                remaining = MAX_STDERR_BYTES + 1 - len(retained)
                if remaining > 0:
                    retained.extend(chunk[:remaining])
                if len(retained) > MAX_STDERR_BYTES:
                    state["error"] = "IPC_STDERR_OVERSIZED"
                    break
        except Exception:
            state["error"] = "IPC_STDERR_FAILED"
        finally:
            state["stderr_retained"] = len(retained)
            state["stderr_done"] = True

    @staticmethod
    def _wait_closed(job, process, ceiling):
        deadline = time.monotonic() + max(0.0, ceiling)
        while True:
            if os.name == "nt":
                active = job.active_processes()
                if active == 0:
                    return True
                if active is None:
                    return False
            else:
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    return True
                except OSError:
                    return False
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.005)

    @staticmethod
    def _terminate_tree(job, process, ceiling):
        if os.name == "nt":
            terminated = job.terminate()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                terminated = True
            except ProcessLookupError:
                terminated = True
            except OSError:
                terminated = False
        try:
            process.wait(timeout=max(0.01, ceiling))
        except Exception:
            try:
                process.kill()
                process.wait(timeout=max(0.01, ceiling))
            except Exception:
                terminated = False
        return terminated and OwnedProcessBoundary._wait_closed(job, process, ceiling)

    def run(self, request_bytes, timeout_seconds, closure_seconds):
        started = time.monotonic()
        job = None
        process = None
        try:
            if os.name == "nt":
                job = _WindowsJob()
            process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt",
                env=self._worker_environment(),
                text=False,
            )
            if os.name == "nt":
                try:
                    job.assign(process)
                except Exception:
                    self._terminate_tree(job, process, closure_seconds)
                    return OwnedProcessResult(
                        "CONTAINMENT_FAILED", b"", process.returncode, False,
                        time.monotonic() - started,
                    )
            else:
                job = None
            with self._state_lock:
                self._process, self._job = process, job
            if self._cancelled.is_set():
                closed = self._terminate_tree(job, process, closure_seconds)
                return OwnedProcessResult(
                    "CANCELLED" if closed else "CLOSURE_FAILED", b"",
                    process.returncode, closed, time.monotonic() - started,
                )
            state = {
                "body": b"", "error": None, "stdout_done": False,
                "stderr_done": False, "stderr_retained": 0,
                "stdout_retained": 0,
            }
            stop = threading.Event()
            stdout_reader = threading.Thread(
                target=self._read_framed_stdout,
                args=(process.stdout, state, stop), daemon=True,
            )
            stderr_reader = threading.Thread(
                target=self._read_bounded_stderr,
                args=(process.stderr, state, stop), daemon=True,
            )
            stdout_reader.start()
            stderr_reader.start()
            try:
                process.stdin.write(request_bytes)
                process.stdin.close()
            except Exception:
                state["error"] = "IPC_WRITE_FAILED"
            deadline = started + max(0.001, timeout_seconds)
            outcome = None
            while not (state["stdout_done"] and state["stderr_done"]):
                if self._cancelled.is_set():
                    outcome = "CANCELLED"
                    break
                if state["error"]:
                    outcome = "IPC_FAILED"
                    break
                if time.monotonic() >= deadline:
                    outcome = "TIMEOUT"
                    break
                time.sleep(0.002)
            if outcome is None and state["error"]:
                outcome = "IPC_FAILED"
            self.last_retained_stdout_bytes = state["stdout_retained"]
            self.last_retained_stderr_bytes = state["stderr_retained"]
            if outcome is not None:
                stop.set()
                closed = self._terminate_tree(job, process, closure_seconds)
                stdout_reader.join(timeout=closure_seconds)
                stderr_reader.join(timeout=closure_seconds)
                return OwnedProcessResult(
                    outcome if closed else "CLOSURE_FAILED", b"",
                    process.returncode, closed, time.monotonic() - started,
                )
            try:
                process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except Exception:
                closed = self._terminate_tree(job, process, closure_seconds)
                return OwnedProcessResult(
                    "TIMEOUT" if closed else "CLOSURE_FAILED", b"",
                    process.returncode, closed, time.monotonic() - started,
                )
            closed = self._wait_closed(job, process, closure_seconds)
            if not closed:
                closed = self._terminate_tree(job, process, closure_seconds)
                return OwnedProcessResult(
                    "PROCESS_TREE_REMAINED" if closed else "CLOSURE_FAILED", b"",
                    process.returncode, closed, time.monotonic() - started,
                )
            if process.returncode != 0:
                return OwnedProcessResult(
                    "WORKER_FAILED", b"", process.returncode, True,
                    time.monotonic() - started,
                )
            return OwnedProcessResult(
                "COMPLETED", state["body"], process.returncode, True,
                time.monotonic() - started,
            )
        except Exception:
            closed = False
            if process is not None:
                try:
                    closed = self._terminate_tree(job, process, closure_seconds)
                except Exception:
                    closed = False
            return OwnedProcessResult(
                "CLOSURE_FAILED" if process is not None and not closed else "START_FAILED",
                b"", getattr(process, "returncode", None), closed,
                time.monotonic() - started,
            )
        finally:
            with self._state_lock:
                self._process = None
                self._job = None
            if os.name == "nt" and job is not None:
                job.close()
            self._closed.set()
