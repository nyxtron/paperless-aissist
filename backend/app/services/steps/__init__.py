"""Step plugins for the document processing pipeline.

Each step implements AbstractStep, handles a specific aspect of document processing
(OCR, title, correspondent, dtype, tags, fields), and is orchestrated by
DocumentProcessor in the modular pipeline.
"""

from .base import AbstractStep, StepContext, StepResult
from .ocr_step import OCRStep
from .ocr_fix_step import OCRFixStep
from .title_step import TitleStep
from .correspondent_step import CorrespondentStep
from .document_type_step import DocumentTypeStep
from .tags_step import TagsStep
from .fields_step import FieldsStep

__all__ = [
    "AbstractStep",
    "StepContext",
    "StepResult",
    "OCRStep",
    "OCRFixStep",
    "TitleStep",
    "CorrespondentStep",
    "DocumentTypeStep",
    "TagsStep",
    "FieldsStep",
]
