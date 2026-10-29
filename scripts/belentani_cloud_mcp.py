"""MCP stdio entrypoint. Launch on the Oracle VM via SSH -T from the client."""
from mcp.server.fastmcp import FastMCP

from belentani_cloud_core import (
    catalog, estimate_cost, machine_status, cpu_llm_status,
    create_music, music_status, submit_video, video_status,
)

mcp = FastMCP("belentani-cloud")
mcp.tool()(catalog)
mcp.tool()(estimate_cost)
mcp.tool()(machine_status)
mcp.tool()(cpu_llm_status)
mcp.tool()(create_music)
mcp.tool()(music_status)
mcp.tool()(submit_video)
mcp.tool()(video_status)

if __name__ == "__main__":
    mcp.run(transport="stdio")
