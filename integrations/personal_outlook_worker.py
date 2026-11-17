import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PYTHON312 = Path(r"E:\outlook-mcp-venv\Scripts\python.exe")
SERVER_DIR = Path(
    r"E:\outlook-mcp-source\outlook-mcp-main\src\outlook_mcp"
)

ALLOWED_TOOLS = {
    "outlook_auth_status",
    "outlook_list_inbox",
    "outlook_read_message",
    "outlook_read_messages",
    "outlook_search_mail",
    "outlook_list_folders",
    "outlook_list_inbox_delta",
    "outlook_send_message",
    "outlook_reply",
    "outlook_forward",
    "outlook_move_message",
    "outlook_delete_message",
    "outlook_flag_message",
    "outlook_categorize_message",
    "outlook_mark_read",
    "outlook_reclassify_message",
    "outlook_list_inbox_overrides",
    "outlook_set_inbox_override",
    "outlook_delete_inbox_override",
    "outlook_list_events",
    "outlook_get_event",
    "outlook_find_event_by_key",
    "outlook_list_events_delta",
    "outlook_create_event",
    "outlook_update_event",
    "outlook_delete_event",
    "outlook_rsvp",
    "outlook_attach_to_event",
    "outlook_remove_event_attachment",
    "outlook_list_contacts",
    "outlook_search_contacts",
    "outlook_get_contact",
    "outlook_create_contact",
    "outlook_update_contact",
    "outlook_delete_contact",
    "outlook_list_task_lists",
    "outlook_list_tasks",
    "outlook_get_task",
    "outlook_create_task",
    "outlook_update_task",
    "outlook_complete_task",
    "outlook_delete_task",
    "outlook_add_checklist_item",
    "outlook_update_checklist_item",
    "outlook_delete_checklist_item",
    "outlook_list_task_attachments",
    "outlook_download_task_attachment",
    "outlook_upload_task_attachment",
    "outlook_delete_task_attachment",
    "outlook_list_drafts",
    "outlook_create_draft",
    "outlook_update_draft",
    "outlook_send_draft",
    "outlook_delete_draft",
    "outlook_list_attachments",
    "outlook_download_attachment",
    "outlook_send_with_attachments",
    "outlook_attach_to_draft",
    "outlook_remove_draft_attachment",
    "outlook_create_folder",
    "outlook_rename_folder",
    "outlook_delete_folder",
    "outlook_list_thread",
    "outlook_copy_message",
    "outlook_batch_triage",
    "outlook_whoami",
    "outlook_list_calendars",
    "outlook_list_categories",
    "outlook_get_mail_tips",
}


def emit(data):
    sys.stdout.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


async def main():
    if not PYTHON312.exists():
        raise FileNotFoundError(f"Python 3.12 not found: {PYTHON312}")

    if not SERVER_DIR.exists():
        raise FileNotFoundError(f"MCP server directory not found: {SERVER_DIR}")

    params = StdioServerParameters(
        command=str(PYTHON312),
        args=["-m", "outlook_mcp.server"],
        cwd=str(SERVER_DIR),
        env={
            **os.environ,
            "PYTHONPATH": str(SERVER_DIR.parent),
            "OUTLOOK_MCP_TRANSPORT": "stdio",
        },
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            discovered = await session.list_tools()
            tools = {tool.name: tool for tool in discovered.tools}

            unknown = ALLOWED_TOOLS - set(tools)
            if unknown:
                raise RuntimeError(
                    "Expected MCP tools missing: " + ", ".join(sorted(unknown))
                )

            print(
                f"[PERSONAL OUTLOOK WORKER] Connected; "
                f"{len(tools)} MCP tools discovered.",
                file=sys.stderr,
                flush=True,
            )

            while True:
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line:
                    break

                try:
                    request = json.loads(line)
                    request_id = request.get("id")
                    action = request.get("action")

                    if action == "list_tools":
                        result = []
                        for name in sorted(ALLOWED_TOOLS):
                            tool = tools[name]
                            result.append({
                                "name": tool.name,
                                "description": tool.description or "",
                                "inputSchema": (
                                    tool.model_dump(mode="json", by_alias=True).get("inputSchema")
                                    or tool.model_dump(mode="json").get("input_schema")
                                    or {}
                                ),
                            })

                        emit({
                            "id": request_id,
                            "ok": True,
                            "tools": result,
                        })

                    elif action == "call":
                        name = request.get("tool_name")
                        arguments = request.get("arguments", {})

                        if name not in ALLOWED_TOOLS or name not in tools:
                            raise PermissionError(
                                f"Personal Outlook tool is not allowlisted: {name}"
                            )

                        if not isinstance(arguments, dict):
                            raise ValueError("arguments must be a JSON object")

                        result = await session.call_tool(
                            name,
                            arguments=arguments,
                        )

                        result_data = result.model_dump(
                            mode="json",
                            by_alias=True,
                        )
                        is_error = bool(
                            result_data.get(
                                "isError",
                                result_data.get("is_error", False),
                            )
                        )

                        content = []
                        for item in result.content:
                            if hasattr(item, "text"):
                                content.append(item.text)
                            else:
                                content.append(str(item))

                        emit({
                            "id": request_id,
                            "ok": not is_error,
                            "content": "\n".join(content),
                            "isError": is_error,
                        })

                    elif action == "shutdown":
                        emit({"id": request_id, "ok": True})
                        break

                    else:
                        raise ValueError(f"Unknown worker action: {action}")

                except Exception as exc:
                    emit({
                        "id": request.get("id") if isinstance(request, dict) else None,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    })


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(
            f"[PERSONAL OUTLOOK WORKER ERROR] {type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
