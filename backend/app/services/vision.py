"""Vision OCR pipeline for PDF text extraction using multimodal LLMs.

Supports Ollama (page-by-page JPEG) and OpenAI (native PDF) providers.
"""

import asyncio
import io
import logging
from typing import Optional, Any
import fitz
from PIL import Image
from .llm_handler import LLMHandlerManager, LLMHandler

logger = logging.getLogger(__name__)


class VisionPipeline:
    """Multimodal LLM pipeline for extracting text from PDFs.

    Attributes:
        llm_handler: The configured vision LLM handler.
    """

    def __init__(self, llm_handler: Optional[LLMHandler] = None):
        """Initialize with an optional LLM handler; use create() for default."""
        self.llm_handler = llm_handler

    @classmethod
    async def create(cls) -> "VisionPipeline":
        """Factory: create a pipeline with a vision LLM handler from config."""
        llm_handler = await LLMHandlerManager.get_handler(for_vision=True)
        return cls(llm_handler=llm_handler)

    async def pdf_to_images(self, pdf_bytes: bytes, dpi: int = 150) -> list[bytes]:
        """Convert PDF pages to JPEG images.

        Args:
            pdf_bytes: Raw PDF bytes.
            dpi: Rendering resolution.

        Returns:
            List of JPEG byte strings, one per page.
        """
        return await asyncio.to_thread(self._pdf_to_images_sync, pdf_bytes, dpi)

    def _pdf_to_images_sync(self, pdf_bytes: bytes, dpi: int = 150) -> list[bytes]:
        """Synchronous PDF-to-images renderer (runs in thread pool)."""
        images = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            page_count = len(doc)
            logger.debug(f"pdf_to_images: {page_count} page(s), dpi={dpi}")
            for page_num in range(page_count):
                logger.debug(
                    f"pdf_to_images: rendering page {page_num + 1}/{page_count}"
                )
                page = doc[page_num]
                pix = page.get_pixmap(dpi=dpi)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img_buffer = io.BytesIO()
                img.save(img_buffer, format="JPEG", quality=85)
                jpeg_bytes = img_buffer.getvalue()
                img_buffer.close()
                logger.debug(
                    f"pdf_to_images: page {page_num + 1} → {len(jpeg_bytes)} bytes JPEG"
                )
                images.append(jpeg_bytes)
                del pix
        finally:
            doc.close()
        return images

    async def extract_text_from_pdf(
        self,
        pdf_bytes: bytes,
        prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        if not self.llm_handler:
            raise ValueError("Vision LLM handler not initialized")

        logger.debug(
            f"extract_text_from_pdf: provider={self.llm_handler.provider}, pdf_size={len(pdf_bytes)} bytes"
        )

        if self.llm_handler.provider == "openai":
            # Send PDF natively — OpenAI processes all pages automatically
            result = await self.llm_handler.vision_complete(
                system_prompt=prompt or "",
                images=[],
                pdf_bytes=pdf_bytes,
                json_mode=False,
            )
        else:
            images = await self.pdf_to_images(pdf_bytes)
            result = await self.llm_handler.vision_complete(
                system_prompt=prompt or "",
                images=images,
                json_mode=False,
            )

        text = result.get("text", "") or result.get("raw", "")
        logger.debug(f"extract_text_from_pdf: extracted {len(text)} chars")
        return result

    async def extract_with_custom_prompt(
        self,
        pdf_bytes: bytes,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        if not self.llm_handler:
            raise ValueError("Vision LLM handler not initialized")

        if self.llm_handler.provider == "openai":
            result = await self.llm_handler.vision_complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                images=[],
                pdf_bytes=pdf_bytes,
                json_mode=False,
            )
        else:
            images = await self.pdf_to_images(pdf_bytes)
            result = await self.llm_handler.vision_complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                images=images,
                json_mode=False,
            )

        return result
