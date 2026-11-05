"""MCP stdio entrypoint. Launch on the Oracle VM via SSH -T from the client."""
from belentani_cloud_core import (
    catalog,
    cpu_llm_status,
    create_music,
    estimate_cost,
    machine_status,
    music_status,
    submit_video,
    video_status,
)
from mcp.server import MCPServer

mcp = MCPServer("belentani-cloud", version="0.1.0")
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
