"""ComfyUI entrypoint for the Supernova Pack."""

from comfy_api.latest import ComfyExtension, io
from typing_extensions import override

from .supernova.nodes import NODES


class SupernovaExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return NODES


async def comfy_entrypoint() -> SupernovaExtension:
    return SupernovaExtension()
