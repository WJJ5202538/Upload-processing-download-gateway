from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from docmark.config import OUTPUT_DIR
from docmark.grading_adapter import GradingError, grade
from docmark.jobs import JobStore
from docmark.services.annotator import AnnotationError
from docmark.services.extractor import ExtractedDocument, ExtractionError

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """A failure whose message is safe to show to the user."""


def process_job(job_id: str, store: JobStore) -> None:
    job = store.get(job_id)
    if job is None:
        return

    store.mark_processing(job_id)
    output_path = OUTPUT_DIR / f"{job_id}.docx"

    try:
        result = grade(job.pdf_path, job.docx_path, output_path)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise ProcessingError("批注稿没有成功生成，请重试。")

        _save_extraction_sidecars(job_id, result.extractions)
        store.complete(
            job_id,
            output_name=_output_filename(job.docx_name),
            output_path=output_path,
            issue_count=result.issue_count,
            engine=result.engine,
        )
    except (ExtractionError, AnnotationError, GradingError, ProcessingError) as exc:
        _remove_failed_output(output_path)
        store.fail(job_id, str(exc))
    except Exception:
        logger.exception("Unexpected failure while processing job %s", job_id)
        _remove_failed_output(output_path)
        store.fail(job_id, "处理文档时出现意外错误，请重试或更换文件。")


def _output_filename(original_name: str) -> str:
    stem = Path(original_name).stem
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .")
    if not stem:
        stem = "文档"
    if len(stem) > 80:
        stem = stem[:80].rstrip()
    return f"{stem}_批注.docx"


def _save_extraction_sidecars(job_id: str, extractions: list[ExtractedDocument]) -> None:
    """Keep JSON/Markdown outputs for debugging and module hand-off."""
    try:
        for extraction in extractions:
            prefix = f"{job_id}.{extraction.source_type}"
            json_path = OUTPUT_DIR / f"{prefix}.extraction.json"
            md_path = OUTPUT_DIR / f"{prefix}.extraction.md"
            json_path.write_text(
                json.dumps(extraction.as_json, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            md_path.write_text(extraction.markdown, encoding="utf-8")
    except OSError:
        logger.warning("Could not write extraction sidecars for %s", job_id, exc_info=True)


def _remove_failed_output(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove incomplete output %s", path, exc_info=True)
