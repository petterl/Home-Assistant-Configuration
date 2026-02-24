#!/usr/bin/env python3
"""
JupyterLab API helper for Claude Code.

Provides CLI access to JupyterLab running as a Home Assistant addon.
Supports kernel management, code execution, and notebook operations.

Usage:
    python3 jupyter.py execute "print('hello')"
    python3 jupyter.py execute --kernel-id <ID> "code here"
    python3 jupyter.py kernel-start
    python3 jupyter.py kernel-stop <ID>
    python3 jupyter.py kernel-list
    python3 jupyter.py list [path]
    python3 jupyter.py create <name.ipynb> "cell1 code" "cell2 code" ...
"""

import argparse
import json
import sys
import uuid
import urllib.request
import urllib.error

JUPYTER_BASE = "http://172.30.33.4:8099"
XSRF_HEADERS = {
    "X-XSRFToken": "dummy",
    "Cookie": "_xsrf=dummy",
}


def api_request(method, path, data=None):
    """Make a request to the Jupyter REST API."""
    url = f"{JUPYTER_BASE}{path}"
    headers = {"Content-Type": "application/json", **XSRF_HEADERS}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        if resp.status == 204:
            return None
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            msg = json.loads(body).get("message", body)
        except (json.JSONDecodeError, AttributeError):
            msg = body
        print(f"Error {e.code}: {msg}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        print("Is the JupyterLab addon running?", file=sys.stderr)
        sys.exit(1)


def kernel_start():
    """Start a new Python kernel and return its ID."""
    result = api_request("POST", "/api/kernels", {"name": "python3"})
    print(result["id"])
    return result["id"]


def kernel_stop(kernel_id):
    """Stop a running kernel."""
    api_request("DELETE", f"/api/kernels/{kernel_id}")
    print(f"Kernel {kernel_id} stopped.")


def kernel_list():
    """List all running kernels."""
    kernels = api_request("GET", "/api/kernels")
    if not kernels:
        print("No running kernels.")
        return
    for k in kernels:
        print(f"  {k['id']}  state={k['execution_state']}  name={k['name']}")


def execute_code(code, kernel_id=None, timeout=60):
    """Execute code on a Jupyter kernel and return output."""
    try:
        import websocket
    except ImportError:
        print("Error: websocket-client not installed.", file=sys.stderr)
        print("Run: pip install --break-system-packages websocket-client", file=sys.stderr)
        sys.exit(1)

    cleanup_kernel = False
    if kernel_id is None:
        kernel_id = kernel_start()
        cleanup_kernel = True

    ws_url = f"ws://172.30.33.4:8099/api/kernels/{kernel_id}/channels"

    try:
        ws = websocket.create_connection(ws_url, cookie="_xsrf=dummy", timeout=timeout)
    except Exception as e:
        print(f"WebSocket error: {e}", file=sys.stderr)
        if cleanup_kernel:
            kernel_stop(kernel_id)
        sys.exit(1)

    msg = {
        "header": {
            "msg_id": str(uuid.uuid4()),
            "msg_type": "execute_request",
            "username": "claude",
            "session": str(uuid.uuid4()),
            "version": "5.3",
        },
        "parent_header": {},
        "metadata": {},
        "content": {
            "code": code,
            "silent": False,
            "store_history": True,
            "user_expressions": {},
            "allow_stdin": False,
        },
        "buffers": [],
        "channel": "shell",
    }

    ws.send(json.dumps(msg))

    outputs = []
    error_occurred = False
    for _ in range(200):
        try:
            resp = json.loads(ws.recv())
            msg_type = resp.get("msg_type", "")
            if msg_type == "stream":
                text = resp["content"]["text"]
                outputs.append(text)
                print(text, end="")
            elif msg_type == "execute_result":
                data = resp["content"]["data"].get("text/plain", "")
                outputs.append(data + "\n")
                print(data)
            elif msg_type == "display_data":
                data = resp["content"]["data"]
                if "text/plain" in data:
                    outputs.append(data["text/plain"] + "\n")
                    print(data["text/plain"])
                if "image/png" in data:
                    print("[image/png output - view in JupyterLab]")
            elif msg_type == "error":
                ename = resp["content"]["ename"]
                evalue = resp["content"]["evalue"]
                traceback = resp["content"].get("traceback", [])
                print(f"{ename}: {evalue}", file=sys.stderr)
                for line in traceback:
                    # Strip ANSI codes for cleaner output
                    import re
                    clean = re.sub(r'\x1b\[[0-9;]*m', '', line)
                    print(clean, file=sys.stderr)
                error_occurred = True
            elif msg_type == "execute_reply":
                break
        except websocket.WebSocketTimeoutException:
            print("Execution timed out.", file=sys.stderr)
            break

    ws.close()

    if cleanup_kernel:
        api_request("DELETE", f"/api/kernels/{kernel_id}")

    if error_occurred:
        sys.exit(1)


def list_contents(path=""):
    """List notebooks and files."""
    api_path = f"/api/contents/{path}" if path else "/api/contents"
    result = api_request("GET", api_path)
    if result.get("type") == "directory":
        for item in result.get("content", []):
            icon = {"notebook": "nb", "directory": "dir", "file": "file"}.get(item["type"], "?")
            print(f"  [{icon}] {item['name']}")
    else:
        print(f"  {result['name']} ({result['type']})")


def create_notebook(name, cells):
    """Create a notebook with the given cells."""
    nb_cells = []
    for cell_content in cells:
        if cell_content.startswith("#") and not cell_content.startswith("#!"):
            cell_type = "markdown"
        else:
            cell_type = "code"
        cell = {
            "cell_type": cell_type,
            "source": cell_content,
            "metadata": {},
        }
        if cell_type == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
        nb_cells.append(cell)

    notebook = {
        "type": "notebook",
        "content": {
            "cells": nb_cells,
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3 (ipykernel)",
                    "language": "python",
                    "name": "python3",
                }
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        },
    }

    result = api_request("PUT", f"/api/contents/{name}", notebook)
    print(f"Created: {result['name']}")


def main():
    parser = argparse.ArgumentParser(description="JupyterLab API helper")
    sub = parser.add_subparsers(dest="command", required=True)

    # execute
    p_exec = sub.add_parser("execute", help="Execute code on a kernel")
    p_exec.add_argument("code", help="Python code to execute")
    p_exec.add_argument("--kernel-id", help="Reuse existing kernel")
    p_exec.add_argument("--timeout", type=int, default=60, help="Execution timeout (seconds)")

    # kernel-start
    sub.add_parser("kernel-start", help="Start a new kernel")

    # kernel-stop
    p_stop = sub.add_parser("kernel-stop", help="Stop a kernel")
    p_stop.add_argument("kernel_id", help="Kernel ID to stop")

    # kernel-list
    sub.add_parser("kernel-list", help="List running kernels")

    # list
    p_list = sub.add_parser("list", help="List notebooks/files")
    p_list.add_argument("path", nargs="?", default="", help="Directory path")

    # create
    p_create = sub.add_parser("create", help="Create a notebook")
    p_create.add_argument("name", help="Notebook filename (e.g. analysis.ipynb)")
    p_create.add_argument("cells", nargs="+", help="Cell contents (code or # markdown)")

    args = parser.parse_args()

    if args.command == "execute":
        execute_code(args.code, kernel_id=args.kernel_id, timeout=args.timeout)
    elif args.command == "kernel-start":
        kernel_start()
    elif args.command == "kernel-stop":
        kernel_stop(args.kernel_id)
    elif args.command == "kernel-list":
        kernel_list()
    elif args.command == "list":
        list_contents(args.path)
    elif args.command == "create":
        create_notebook(args.name, args.cells)


if __name__ == "__main__":
    main()
