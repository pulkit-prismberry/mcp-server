"""Main entrypoint for the Multi-Tenant Support AI MCP Server."""
import os
import sys

# Ensure project root is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from config import settings
from tools import register_tools

# Initialize FastMCP Server
mcp = FastMCP(settings.SERVER_NAME)

# Register tools modularly
register_tools(mcp)


if __name__ == "__main__":
    mcp.run()
