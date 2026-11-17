import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PYTHON312 = Path(r"E:\outlook-mcp-venv\Scripts\python.exe")
SERVER_SCRIPT = Path(
    r"E:\outlook-mcp-source\outlook-mcp-main\src\outlook_mcp\server.py"
)

# Initial safety boundary: only allow mailbox-reading tools.
# Do not add write tools until Ghost confirmation handling is integrated.
READ_ONLY_PREFIXES = (
    "outlook_get_",
    "outlook_list_",
    "outlook_read_",
    "outlook_search_",
    "outlook_find_",
    "outlook_changes_since",
)

READ_ONLY_EXACT = {
    "outlook_whoami",
    "outlook_auth_status",
    "outlook_get_recent_messages",
    "outlook_get_message",
    "outlook_search_messages",
    "outlook_list_inbox_delta",
    "outlook_list_calendar_delta",
    "outlook_list_contacts_delta",
}

class PersonalOutlookMCP:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._stdio_context = None
        self._session_context = None
        self.session = None
        self.tools = {}

    async def connect(self):
        if self.session is not None:
            return

        if not PYTHON312.exists():
            raise FileNotFoundError(
                f"Python 3.12 not found: {PYTHON312}"
            )

        if not SERVER_SCRIPT.exists():
            raise FileNotFoundError(
                f"Outlook MCP server not found: {SERVER_SCRIPT}"
            )

        params = StdioServerParameters(
            command=str(PYTHON312),
            args=["-m", "outlook_mcp.server"],
            cwd=str(SERVER_SCRIPT.parent),
            env={
                **os.environ,
                "PYTHONPATH": str(SERVER_SCRIPT.parent.parent),
                "OUTLOOK_MCP_TRANSPORT": "stdio",
            },
        )

        self._stdio_context = stdio_client(params)
        read_stream, write_stream = await self._stdio_context.__aenter__()

        self._session_context = ClientSession(
            read_stream,
            write_stream
        )

        self.session = await self._session_context.__aenter__()
        await self.session.initialize()

        result = await self.session.list_tools()

        self.tools = {
            tool.name: tool
            for tool in result.tools
        }

        print(
            f"[PERSONAL OUTLOOK] Connected. "
            f"{len(self.tools)} MCP tools discovered."
        )

    async def disconnect(self):
        async with self._lock:
            if self._session_context is not None:
                await self._session_context.__aexit__(
                    None, None, None
                )
                self._session_context = None

            if self._stdio_context is not None:
                await self._stdio_context.__aexit__(
                    None, None, None
                )
                self._stdio_context = None

            self.session = None
            self.tools = {}

    def list_read_only_tools(self):
        available = []

        for name, tool in self.tools.items():
            if (
                name in READ_ONLY_EXACT
                or name.startswith(READ_ONLY_PREFIXES)
            ):
                available.append({
                    "name": name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema,
                })

        return available

    async def call_tool(self, name, arguments=None):
        arguments = arguments or {}

        async with self._lock:
            await self.connect()

            allowed = {
                item["name"]
                for item in self.list_read_only_tools()
            }

            if name not in allowed:
                raise PermissionError(
                    f"Personal Outlook action blocked: {name}. "
                    "Only approved read-only tools are allowed."
                )

            result = await self.session.call_tool(
                name,
                arguments=arguments
            )

            output = []

            for item in result.content:
                if hasattr(item, "text"):
                    output.append(item.text)
                else:
                    output.append(str(item))

            if result.isError:
                raise RuntimeError("\n".join(output))

            return "\n".join(output)

    async def get_tool_list(self):
        async with self._lock:
            await self.connect()
            return self.list_read_only_tools()


personal_outlook = PersonalOutlookMCP()


async def personal_outlook_action(action, arguments=None):
    """
    Ghost entry point for personal Outlook.

    Actions:
      list_tools
      call
    """
    try:
        if action == "list_tools":
            tools = await personal_outlook.get_tool_list()
            return json.dumps(
                tools,
                ensure_ascii=False,
                indent=2
            )

        if action == "call":
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be a dictionary")

            tool_name = arguments.pop("tool_name", None)

            if not tool_name:
                raise ValueError("tool_name is required")

            return await personal_outlook.call_tool(
                tool_name,
                arguments
            )

        return (
            "Unknown personal Outlook action. "
            "Use list_tools or call."
        )

    except Exception as exc:
        return f"Personal Outlook error: {type(exc).__name__}: {exc}"


if __name__ == "__main__":
    async def test():
        await personal_outlook.connect()

        tools = await personal_outlook.get_tool_list()

        print("\nPERSONAL OUTLOOK READ-ONLY TOOLS:")
        for item in tools:
            print(f"- {item['name']}")

        await personal_outlook.disconnect()

    asyncio.run(test())
