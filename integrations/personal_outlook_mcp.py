import atexit
import json
import os
import queue
import subprocess
import threading
from pathlib import Path


PROJECT_DIR = Path(r"E:\kaizumi\kaizumi")
WORKER = PROJECT_DIR / "integrations" / "personal_outlook_worker.py"
PYTHON312 = Path(r"E:\outlook-mcp-venv\Scripts\python.exe")

REQUEST_TIMEOUT = 180


class PersonalOutlookBridge:
    def __init__(self):
        self.process = None
        self.lock = threading.Lock()
        self.responses = queue.Queue()
        self.request_id = 0
        self.reader_thread = None

    def _read_stdout(self, process):
        try:
            for line in process.stdout:
                try:
                    self.responses.put(json.loads(line))
                except json.JSONDecodeError as exc:
                    self.responses.put({
                        "ok": False,
                        "error": f"Invalid worker JSON: {exc}"
                    })
        except Exception as exc:
            self.responses.put({
                "ok": False,
                "error": f"Worker output error: {exc}"
            })

        self.responses.put({
            "ok": False,
            "error": "Personal Outlook worker stopped."
        })

    def _start(self):
        if self.process and self.process.poll() is None:
            return

        if not PYTHON312.is_file():
            raise FileNotFoundError(
                f"Python 3.12 not found: {PYTHON312}"
            )

        if not WORKER.is_file():
            raise FileNotFoundError(
                f"Worker script not found: {WORKER}"
            )

        self.responses = queue.Queue()

        self.process = subprocess.Popen(
            [str(PYTHON312), "-u", str(WORKER)],
            cwd=str(PROJECT_DIR),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env={**os.environ.copy(), "PYTHONIOENCODING": "utf-8"},
        )

        self.reader_thread = threading.Thread(
            target=self._read_stdout,
            args=(self.process,),
            daemon=True,
            name="PersonalOutlookWorkerReader",
        )
        self.reader_thread.start()

    def _request(self, payload):
        with self.lock:
            self._start()

            self.request_id += 1
            request_id = self.request_id

            payload["id"] = request_id

            try:
                self.process.stdin.write(
                    json.dumps(payload, ensure_ascii=False) + "\n"
                )
                self.process.stdin.flush()
            except Exception as exc:
                self._stop()
                raise RuntimeError(
                    f"Could not communicate with Outlook worker: {exc}"
                ) from exc

            try:
                response = self.responses.get(
                    timeout=REQUEST_TIMEOUT
                )
            except queue.Empty:
                self._stop()
                raise TimeoutError(
                    "Personal Outlook worker timed out."
                )

            if response.get("id") != request_id:
                self._stop()
                raise RuntimeError(
                    "Personal Outlook worker returned an unexpected response."
                )

            if not response.get("ok"):
                raise RuntimeError(
                    response.get("error")
                    or response.get("content")
                    or "Personal Outlook operation failed."
                )

            return response

    def list_tools(self):
        response = self._request({
            "action": "list_tools"
        })
        return json.dumps(
            response.get("tools", []),
            ensure_ascii=False,
            indent=2,
        )

    def call_tool(self, tool_name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a dictionary")

        response = self._request({
            "action": "call",
            "tool_name": tool_name,
            "arguments": arguments,
        })
        return response.get("content", "")

    def _stop(self):
        process = self.process
        self.process = None

        if process is None:
            return

        try:
            if process.poll() is None:
                process.stdin.close()
                process.terminate()
                process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def shutdown(self):
        with self.lock:
            self._stop()


personal_outlook = PersonalOutlookBridge()



def _preview_decode(result, label):
    """Decode one JSON response returned by the Outlook MCP bridge."""
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        raise ValueError(f"{label}: unexpected response type")

    try:
        data = json.loads(result)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}: Outlook returned invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{label}: expected a JSON object")
    return data


def _preview_pages(tool_name, base_arguments, label, page_size):
    """Read every page using the MCP cursor; never invokes a mutation."""
    collected = []
    cursor = None
    seen_cursors = set()

    for _ in range(100):
        arguments = dict(base_arguments)
        arguments["count"] = page_size
        arguments["concise"] = True
        if cursor:
            arguments["cursor"] = cursor

        data = _preview_decode(
            personal_outlook.call_tool(tool_name, arguments),
            label,
        )

        items = data.get("messages", [])
        if not isinstance(items, list):
            raise ValueError(f"{label}: response has no valid messages list")

        collected.extend(item for item in items if isinstance(item, dict))

        if not data.get("has_more"):
            return collected

        next_cursor = data.get("cursor")
        if not next_cursor or next_cursor in seen_cursors:
            raise ValueError(f"{label}: pagination cursor missing or repeated")

        seen_cursors.add(next_cursor)
        cursor = next_cursor

    raise ValueError(f"{label}: stopped after 100 pages for safety")


def _preview_move(query="subject:URGENT",
                  destination_folder="Ghost_Test_Folder_Renamed",
                  count=100):
    """Build a read-only move preview using fixed read-only MCP tools."""
    query = str(query or "subject:URGENT").strip()
    destination_folder = str(
        destination_folder or "Ghost_Test_Folder_Renamed"
    ).strip()

    if not query:
        raise ValueError("Search query cannot be empty")
    if not destination_folder:
        raise ValueError("Destination folder cannot be empty")

    count = max(1, min(int(count), 100))

    # 1. Enumerate folders, including nested folders.
    folder_data = _preview_decode(
        personal_outlook.call_tool(
            "outlook_list_folders",
            {"recursive": True},
        ),
        "Folder listing",
    )
    folders = folder_data.get("folders", [])
    if not isinstance(folders, list):
        raise ValueError("Folder listing did not contain a valid folders list")

    folder_by_id = {
        f.get("id"): f.get("path") or f.get("name") or "Unknown folder"
        for f in folders
        if isinstance(f, dict) and f.get("id")
    }

    destination = next(
        (
            f for f in folders
            if isinstance(f, dict)
            and str(f.get("name", "")).casefold()
                == destination_folder.casefold()
        ),
        None,
    )
    if destination is None:
        raise ValueError(
            f"Destination folder not found: {destination_folder}"
        )

    destination_name = destination.get("path") or destination.get("name")

    # 2. Search each non-empty folder separately.
    matches_by_id = {}
    searched_folders = []

    for folder in folders:
        if not isinstance(folder, dict):
            continue
        folder_name = folder.get("path") or folder.get("name")
        if not folder_name:
            continue

        try:
            total = int(folder.get("total", 0) or 0)
        except (TypeError, ValueError):
            total = 0

        if total <= 0:
            continue

        searched_folders.append(folder_name)

        messages = _preview_pages(
            "outlook_search_mail",
            {
                "query": query,
                "folder": folder_name,
            },
            f"Search in {folder_name}",
            count,
        )

        for message in messages:
            message_id = message.get("id")
            if not message_id:
                continue

            # Prefer the actual parent folder ID returned by Outlook.
            parent_id = message.get("parent_folder_id")
            current_folder = folder_by_id.get(parent_id, folder_name)

            normalized = dict(message)
            normalized["current_folder"] = current_folder
            matches_by_id[message_id] = normalized

    # 3. Read the destination folder separately.
    destination_messages = _preview_pages(
        "outlook_list_inbox",
        {"folder": destination_name},
        "Destination folder",
        count,
    )

    destination_ids = {
        message.get("id")
        for message in destination_messages
        if message.get("id")
    }

    already_there = []
    proposed_moves = []

    for message in matches_by_id.values():
        item = {
            "id": message.get("id"),
            "subject": message.get("subject") or "(No subject)",
            "sender": (
                message.get("from_name")
                or message.get("from_email")
                or "Unknown sender"
            ),
            "sender_email": message.get("from_email"),
            "current_folder": message.get("current_folder"),
            "proposed_destination": destination_name,
            "received": message.get("received"),
        }

        if message["id"] in destination_ids:
            already_there.append(item)
        else:
            proposed_moves.append(item)

    return {
        "preview_only": True,
        "changes_made": False,
        "query": query,
        "destination": destination_name,
        "folders_searched": searched_folders,
        "matching_count": len(matches_by_id),
        "proposed_move_count": len(proposed_moves),
        "proposed_moves": proposed_moves,
        "already_in_destination_count": len(already_there),
        "already_in_destination": already_there,
        "destination_existing_count": len(destination_messages),
        "destination_existing_messages": [
            {
                "subject": m.get("subject") or "(No subject)",
                "sender": (
                    m.get("from_name")
                    or m.get("from_email")
                    or "Unknown sender"
                ),
                "sender_email": m.get("from_email"),
            }
            for m in destination_messages
        ],
        "safety": (
            "Read-only preview. No messages were moved, modified, "
            "deleted, or approved."
        ),
    }


def personal_outlook_action(parameters=None, **kwargs):
    args = parameters if isinstance(parameters, dict) else {}
    action = str(args.get("action", "")).strip().lower()

    try:
        if action == "list_tools":
            return personal_outlook.list_tools()

        if action == "preview_move":
            result = _preview_move(
                query=args.get("query", "subject:URGENT"),
                destination_folder=args.get(
                    "destination_folder",
                    "Ghost_Test_Folder_Renamed",
                ),
                count=args.get("count", 100),
            )
            return json.dumps(result, ensure_ascii=False, indent=2)

        if action == "call":
            tool_name = str(args.get("tool_name", "")).strip()

            if not tool_name:
                return "Please provide tool_name."

            arguments = args.get("arguments", {})
            return personal_outlook.call_tool(
                tool_name,
                arguments,
            )

        return "Unknown action. Use list_tools, call, or preview_move."

    except Exception as exc:
        return (
            f"Personal Outlook error: "
            f"{type(exc).__name__}: {exc}"
        )


atexit.register(personal_outlook.shutdown)
