from __future__ import annotations

from typing import List, Optional

from .agents_list_tool import create_agents_list_tool
from .core import BackendTool
from .cron_tool import create_cron_tool
from .gateway_tool import create_gateway_tool
from .heartbeat_response_tool import create_heartbeat_response_tool
from .image_generate_tool import create_image_generate_tool
from .image_tool import create_image_tool
from .message_tool import create_message_tool
from .music_generate_tool import create_music_generate_tool
from .nodes_tool import create_nodes_tool
from .pdf_tool import create_pdf_tool
from .providers import default_provider_map
from .runtime_shared import GatewayCaller, ProviderCaller
from .session_status_tool import create_session_status_tool
from .sessions_history_tool import create_sessions_history_tool
from .sessions_list_tool import create_sessions_list_tool
from .sessions_send_tool import create_sessions_send_tool
from .sessions_spawn_tool import create_sessions_spawn_tool
from .sessions_yield_tool import create_sessions_yield_tool
from .subagents_tool import create_subagents_tool
from .tts_tool import create_tts_tool
from .update_plan_tool import create_update_plan_tool
from .video_generate_tool import create_video_generate_tool
from .web_fetch import create_web_fetch_tool
from .web_search import create_web_search_tool


def create_default_runtime_tools(
    *,
    gateway: Optional[GatewayCaller] = None,
    web_search_provider: Optional[ProviderCaller] = None,
    image_provider: Optional[ProviderCaller] = None,
    pdf_provider: Optional[ProviderCaller] = None,
    image_generate_provider: Optional[ProviderCaller] = None,
    music_generate_provider: Optional[ProviderCaller] = None,
    video_generate_provider: Optional[ProviderCaller] = None,
    tts_provider: Optional[ProviderCaller] = None,
) -> List[BackendTool]:
    """Create the migrated backend tool catalog from individual Python scripts."""

    defaults = default_provider_map()
    tools = [
        create_web_search_tool(web_search_provider or defaults["web_search"]),
        create_web_fetch_tool(),
        create_message_tool(gateway),
        create_sessions_list_tool(gateway),
        create_sessions_history_tool(gateway),
        create_sessions_send_tool(gateway),
        create_sessions_spawn_tool(gateway),
        create_sessions_yield_tool(),
        create_subagents_tool(),
        create_agents_list_tool(),
        create_session_status_tool(gateway),
        create_update_plan_tool(),
        create_heartbeat_response_tool(),
        create_gateway_tool(gateway),
        create_cron_tool(gateway),
        create_nodes_tool(gateway),
        create_image_tool(image_provider or defaults["image"]),
        create_pdf_tool(pdf_provider or defaults["pdf"]),
        create_image_generate_tool(image_generate_provider or defaults["image_generate"]),
        create_music_generate_tool(music_generate_provider or defaults["music_generate"]),
        create_video_generate_tool(video_generate_provider or defaults["video_generate"]),
        create_tts_tool(tts_provider or defaults["tts"]),
    ]

    return tools


def available_default_tool_names() -> List[str]:
    """Return backend tool names that can be activated by build/runtime config."""

    return sorted(tool.name for tool in create_default_runtime_tools())

