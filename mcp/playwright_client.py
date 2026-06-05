from mcp.mcp_session import MCPSession


class PlaywrightClient:

    def __init__(self):

        self.session = MCPSession()

    def connect(self):

        self.session.start()

        response = (
            self.session.initialize()
        )

        print(response)

    def disconnect(self):

        self.session.stop()

    def list_tools(self):

        return self.session.request(
            "tools/list"
        )

    def call_tool(
            self,
            tool_name,
            arguments=None
    ):

        if arguments is None:

            arguments = {}

        return self.session.request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments
            }
        )

    def navigate(
            self,
            url
    ):

        return self.call_tool(
            "browser_navigate",
            {
                "url": url
            }
        )

    def snapshot(self):

        return self.call_tool(
            "browser_snapshot",
            {}
        )

    def click(
            self,
            target
    ):

        return self.call_tool(
            "browser_click",
            {
                "target": target
            }
        )

    def type(
            self,
            target,
            text
    ):

        return self.call_tool(
            "browser_type",
            {
                "target": target,
                "text": text
            }
        )

    def screenshot(
            self,
            filename,
            full_page: bool = True
    ):

        return self.call_tool(
            "browser_take_screenshot",
            {
                "type": "png",
                "filename": filename,
                "fullPage": full_page
            }
        )

    def wait(
            self,
            seconds
    ):

        return self.call_tool(
            "browser_wait_for",
            {
                "time": seconds
            }
        )

