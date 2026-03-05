import io
from typing import Optional
import fitz
from PIL import Image
from .llm_handler import LLMHandler


class VisionPipeline:
    def __init__(self, llm_handler: Optional[LLMHandler] = None):
        self.llm_handler = llm_handler
    
    @classmethod
    async def create(cls) -> "VisionPipeline":
        llm_handler = await LLMHandler.from_config(for_vision=True)
        return cls(llm_handler=llm_handler)
    
    async def pdf_to_images(self, pdf_bytes: bytes, dpi: int = 150) -> list[bytes]:
        images = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            img_buffer = io.BytesIO()
            img.save(img_buffer, format="JPEG", quality=85)
            images.append(img_buffer.getvalue())
        
        doc.close()
        return images
    
    async def extract_text_from_pdf(
        self,
        pdf_bytes: bytes,
        prompt: Optional[str] = None,
    ) -> dict[str, any]:
        if not self.llm_handler:
            raise ValueError("Vision LLM handler not initialized")

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

        return result

    async def extract_with_custom_prompt(
        self,
        pdf_bytes: bytes,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, any]:
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
