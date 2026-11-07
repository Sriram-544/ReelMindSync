"""
generator.py — Local GPU image & video generation for ReelMind.

Uses diffusers with MPS (Apple Silicon) or CUDA backend.
- Image: Stable Diffusion 1.5
- Video: AnimateDiff (short animated GIFs, 16 frames)
"""

import torch
import uuid
from pathlib import Path


class ReelGenerator:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self._img_pipe = None
        self._video_pipe = None

    # ── Image generation ──────────────────────────────────────────────────

    def _get_image_pipe(self):
        if self._img_pipe is not None:
            return self._img_pipe

        from diffusers import StableDiffusionPipeline

        pipe = StableDiffusionPipeline.from_pretrained(
            "runwayml/stable-diffusion-v1-5",
            torch_dtype=torch.float32,
            safety_checker=None,
            requires_safety_checker=False,
        )
        pipe = pipe.to(self.device)
        pipe.enable_attention_slicing()
        if self.device == "mps":
            pipe.vae.enable_slicing()

        self._img_pipe = pipe
        return pipe

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        num_steps: int = 25,
        height: int = 512,
        width: int = 512,
        guidance_scale: float = 7.5,
    ) -> str:
        pipe = self._get_image_pipe()

        with torch.no_grad():
            result = pipe(
                prompt=prompt,
                negative_prompt=negative_prompt or "blurry, low quality, distorted, ugly",
                num_inference_steps=num_steps,
                height=height,
                width=width,
                guidance_scale=guidance_scale,
            )

        img = result.images[0]
        filename = f"img_{uuid.uuid4().hex[:8]}.png"
        path = self.output_dir / filename
        img.save(path, "PNG")
        return filename

    # ── Video generation ──────────────────────────────────────────────────

    def _get_video_pipe(self):
        if self._video_pipe is not None:
            return self._video_pipe

        from diffusers import AnimateDiffPipeline, MotionAdapter, DDIMScheduler

        adapter = MotionAdapter.from_pretrained(
            "guoyww/animatediff-motion-adapter-v1-5-2",
            torch_dtype=torch.float32,
        )

        pipe = AnimateDiffPipeline.from_pretrained(
            "emilianJR/epiCRealism",
            motion_adapter=adapter,
            torch_dtype=torch.float32,
        )
        pipe.scheduler = DDIMScheduler.from_config(
            pipe.scheduler.config,
            beta_schedule="linear",
            clip_sample=False,
            timestep_spacing="trailing",
            steps_offset=1,
        )
        pipe = pipe.to(self.device)
        pipe.enable_attention_slicing()
        if self.device == "mps":
            pipe.vae.enable_slicing()

        self._video_pipe = pipe
        return pipe

    def generate_video(
        self,
        prompt: str,
        negative_prompt: str = "",
        num_steps: int = 25,
        num_frames: int = 16,
        guidance_scale: float = 7.5,
    ) -> str:
        pipe = self._get_video_pipe()

        with torch.no_grad():
            result = pipe(
                prompt=prompt,
                negative_prompt=negative_prompt or "blurry, low quality, distorted, ugly, bad anatomy",
                num_inference_steps=num_steps,
                num_frames=num_frames,
                guidance_scale=guidance_scale,
                width=512,
                height=512,
            )

        frames = result.frames[0]

        filename = f"vid_{uuid.uuid4().hex[:8]}.gif"
        path = self.output_dir / filename

        from diffusers.utils import export_to_gif
        export_to_gif(frames, str(path))

        return filename

    # ── Helpers ───────────────────────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        return self._img_pipe is not None or self._video_pipe is not None

    def image_loaded(self) -> bool:
        return self._img_pipe is not None

    def video_loaded(self) -> bool:
        return self._video_pipe is not None
