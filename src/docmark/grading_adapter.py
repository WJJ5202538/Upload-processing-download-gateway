from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from docmark.services.annotator import annotate_docx
from docmark.services.extractor import ExtractedDocument, extract_docx, extract_pdf

ENGINE_NAME = "内置规则引擎"


class GradingError(Exception):
    """A user-facing grading failure that can be shown in the web UI."""


@dataclass
class GradeResult:
    engine: str
    issue_count: int | None = None
    extractions: list[ExtractedDocument] = field(default_factory=list)


def grade(pdf_source: Path, docx_source: Path, output: Path) -> GradeResult:
    """Connect the web layer to the document-processing modules.

    Every submission contains exactly one PDF and one DOCX. The DOCX is the
    annotation target; the PDF is available to the extraction/grading logic.

    Integrate your own modules by importing and calling them in this process.
    Do not start a CLI, subprocess, or external service here. A typical
    integration looks like this:

        from my_extractor import extract
        from my_annotator import annotate

        pdf_data = extract(str(pdf_source))
        docx_data = extract(str(docx_source))
        issue_count = annotate(str(docx_source), pdf_data, docx_data, str(output))

        return GradeResult(
            engine="My grading module",
            issue_count=issue_count,
            extractions=[],  # optional, only used for local debug sidecars
        )

    Raise GradingError with a user-facing Chinese message when processing
    cannot be completed. The output argument must point to the final DOCX.
    """
    pdf_extracted = extract_pdf(pdf_source)
    docx_extracted = extract_docx(docx_source)
    issue_count = annotate_docx(docx_source, output)

    return GradeResult(
        engine=ENGINE_NAME,
        issue_count=issue_count,
        extractions=[pdf_extracted, docx_extracted],
    )
