"""Reading images during ingestion (Phase 6): OCR for scanned PDFs, descriptions for images.

The rest of the pipeline only understands text, so a vision model turns pixels into text
*once*, at import time, and everything after (chunking, embedding, search, citations) works
unchanged. This is the "convert to text" approach to multimodal RAG; the alternative embeds
page images directly (ColPali-style), which keeps layout but needs a second index and model.

    scanned PDF  -> page with a text layer? use it : render to PNG -> vision model transcribes
    image upload -> vision model writes a Markdown description with every value in a table
"""

import base64
import logging

import anyio

from core.images import sniff
from core.interfaces.data_source import Document
from core.llm import ChatMessage, ImagePart, LLMGateway, TextDelta
from core.multimodal_config import IngestionVisionConfig
from core.prompts import PromptRegistry
from core.tracing import Span, Tracer
from ingestion.parsers.pdf import page_texts, render_page_png

logger = logging.getLogger(__name__)

NO_TEXT = "[no text]"


class VisionReader:
    def __init__(
        self,
        gateway: LLMGateway,
        prompts: PromptRegistry,
        tracer: Tracer,
        model_id: str,
        config: IngestionVisionConfig,
    ):
        self._gateway = gateway
        self._prompts = prompts
        self._tracer = tracer
        self._model_id = model_id
        self._config = config

    async def read(self, document: Document) -> tuple[str | None, str]:
        """Return (title if the file has one, text) for a PDF or an image document.

        One Langfuse trace per document, so you can see every page the model read and what
        each one cost."""
        if isinstance(document.content, str):
            raise ValueError(f"{document.content_type} content must be bytes")
        trace = self._tracer.start_trace(
            "ingest_vision", input={"document": document.id, "type": document.content_type}
        )
        try:
            if document.content_type == "image":
                title, text = None, await self._describe_image(document, document.content, trace)
            else:
                title, text = await self._read_pdf(document, document.content, trace)
        except Exception as exc:
            trace.finish(error=str(exc))
            raise
        trace.finish(output=text[:2000])
        return title, text

    async def _read_pdf(
        self, document: Document, data: bytes, trace: Span
    ) -> tuple[str | None, str]:
        """Use each page's text layer; transcribe only the pages that have none (scans).
        A mixed PDF (typed pages plus a scanned signature page) costs only the scanned pages."""
        title, pages = await anyio.to_thread.run_sync(page_texts, data)
        scanned = [i for i, text in enumerate(pages) if not text]
        if len(scanned) > self._config.max_ocr_pages:
            logger.warning(
                "%s: %d scanned pages, reading the first %d",
                document.id, len(scanned), self._config.max_ocr_pages,
            )  # fmt: skip
        for index in scanned[: self._config.max_ocr_pages]:
            # Rendering is CPU work in C: run it in a thread so the server keeps responding.
            png = await anyio.to_thread.run_sync(
                render_page_png, data, index, self._config.render_dpi
            )
            prompt = self._prompts.render(
                "ocr_page", title=document.title, page=str(index + 1), pages=str(len(pages))
            )
            text = await self._ask(prompt.text, prompt.ref, png, "image/png", "ocr_page", trace)
            pages[index] = "" if text == NO_TEXT else text
        return title, "\n\n".join(p for p in pages if p)

    async def _describe_image(self, document: Document, data: bytes, trace: Span) -> str:
        media_type = sniff(data)
        if media_type is None:
            raise ValueError("not a PNG, JPEG, WebP or GIF image")
        prompt = self._prompts.render("image_index", title=document.title)
        return await self._ask(prompt.text, prompt.ref, data, media_type, "image_index", trace)

    async def _ask(
        self, prompt: str, prompt_ref: str, image: bytes, media_type: str, name: str, trace: Span
    ) -> str:
        part = ImagePart(media_type=media_type, data=base64.b64encode(image).decode())  # type: ignore[arg-type]
        message = ChatMessage(role="user", content=prompt, images=[part])
        pieces: list[str] = []
        stream = self._gateway.stream_chat(
            self._model_id, [message], trace=trace, name=name, prompt_ref=prompt_ref
        )
        async for chunk in stream:
            if isinstance(chunk, TextDelta):
                pieces.append(chunk.text)
        return "".join(pieces).strip()
