"""TEMPLATE: example node. Copy it for new nodes, then delete it."""

from comfy_api.latest import io

from ..core.example_invert import invert


class SupernovaExampleInvert(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="SupernovaExampleInvert",
            display_name="Example Invert (Supernova)",
            category="Supernova/examples",
            description="Template node: inverts image colors, keeping alpha.",
            inputs=[
                io.Image.Input("image", tooltip="Image to invert."),
            ],
            outputs=[
                io.Image.Output(display_name="image", tooltip="Inverted image."),
            ],
        )

    @classmethod
    def execute(cls, image) -> io.NodeOutput:
        return io.NodeOutput(invert(image))
