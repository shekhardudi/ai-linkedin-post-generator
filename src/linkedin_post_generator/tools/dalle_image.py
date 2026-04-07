import os
from datetime import datetime
from pathlib import Path

import httpx
from crewai.tools import BaseTool
from openai import OpenAI
from pydantic import BaseModel, Field


class DalleImageInput(BaseModel):
    prompt: str = Field(..., description="Detailed DALL-E 3 image generation prompt (150-200 words)")
    filename: str = Field(
        default="",
        description="Optional filename (without extension). Defaults to a timestamp.",
    )


class DalleImageTool(BaseTool):
    name: str = "dalle_image_generator"
    description: str = (
        "Generate a professional editorial image using DALL-E 3. "
        "Provide a detailed, specific prompt (150-200 words) describing the visual concept. "
        "The image is saved locally and the file path is returned. "
        "Use non-cliché, editorial styles: minimalist brutalist architecture OR "
        "translucent technical diagram on dark background."
    )
    args_schema: type[BaseModel] = DalleImageInput

    def _run(self, prompt: str, filename: str = "") -> str:
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url

        # Determine save path
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = filename.strip() or ts
        if not fname.endswith(".png"):
            fname += ".png"

        output_dir = Path("outputs") / "posts" / ts
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = output_dir / fname

        # Download and save
        img_bytes = httpx.get(image_url, timeout=30.0).content
        image_path.write_bytes(img_bytes)

        return str(image_path)
