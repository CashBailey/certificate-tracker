"""
Documents API endpoints.
"""

import io
import json
import logging
import warnings
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
import redis

from ..deps import (
    get_db_session,
    get_repository,
    get_storage,
    get_uuid_generator,
    require_coordinator,
    get_redis,
    get_doc_view_token_user,
)
from ..shared.models import CertificateDocument, Employee, ExtractionRun, ReviewState
from ..shared.protocols import Repository, Storage, UuidGenerator, UploadValidationError
from ..shared.utils import (
    MAX_UPLOAD_SIZE_BYTES,
    sanitize_filename,
    validate_upload_bytes_and_type,
    build_content_disposition,
)
from ..shared.audit import audit_employee_action
from ..auth.security import create_doc_view_token
from ..authorizer import authorizer
from .schemas import DocumentUploadResponse

router = APIRouter(prefix="/documents", tags=["documents"])

_MAX_PREVIEW_FRAMES = 20
_MAX_PREVIEW_PIXELS = 40_000_000
_MAX_PREVIEW_BYTES = MAX_UPLOAD_SIZE_BYTES * 3


def _convert_image_to_pdf_preview(image_bytes: bytes) -> bytes:
    """Build a bounded PDF preview without changing the stored original."""
    frames: list[Image.Image] = []
    total_pixels = 0

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(image_bytes)) as source:
                frame_count = getattr(source, "n_frames", 1)
                if frame_count > _MAX_PREVIEW_FRAMES:
                    raise ValueError("Image has too many pages to preview")

                for index in range(frame_count):
                    source.seek(index)
                    total_pixels += source.width * source.height
                    if total_pixels > _MAX_PREVIEW_PIXELS:
                        raise ValueError("Image is too large to preview safely")

                    frame = source.copy()
                    frame.load()
                    if "A" in frame.getbands() or "transparency" in frame.info:
                        rgba = frame.convert("RGBA")
                        rgb = Image.new("RGB", rgba.size, "white")
                        rgb.paste(rgba, mask=rgba.getchannel("A"))
                        frame.close()
                        rgba.close()
                        frame = rgb
                    elif frame.mode != "RGB":
                        converted = frame.convert("RGB")
                        frame.close()
                        frame = converted
                    frames.append(frame)

        if not frames:
            raise ValueError("Image contains no previewable pages")

        output = io.BytesIO()
        frames[0].save(
            output,
            "PDF",
            resolution=300.0,
            save_all=len(frames) > 1,
            append_images=frames[1:],
        )
        preview = output.getvalue()
        if len(preview) > _MAX_PREVIEW_BYTES:
            raise ValueError("Generated preview is too large")
        return preview
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Image is too large to preview safely") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Stored image cannot be previewed") from exc
    finally:
        for frame in frames:
            frame.close()


@router.post(
    "", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    employee_id: Optional[int] = Form(None),
    current_user: Employee = Depends(require_coordinator),
    session: AsyncSession = Depends(get_db_session),
    repository: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
    uuid_generator: UuidGenerator = Depends(get_uuid_generator),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Upload a certificate document.

    - Validates file type and size
    - Stores in MinIO
    - Creates document record
    - Triggers extraction pipeline

    `employee_id` is REQUIRED — uploads are always on behalf of a named
    employee. Defaulting to the uploader silently misattributes the
    resulting verified record (especially harmful when a Coordinator
    uploads someone else's cert without realising the form lacked the
    employee context). The frontend deep-link path
    `/upload?employee_id=X` must always be used; the bare `/upload` form
    must require the user to pick an employee first.
    """
    # employee_id is required — refuse silent fallback to uploader id
    if employee_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "employee_id is required. Uploads must be attributed to a "
                "specific employee. Use the per-row Upload action on the "
                "Requirements page (or pass ?employee_id=<id>)."
            ),
        )
    target_employee_id = employee_id

    # Check upload permission
    authorizer.require_can_upload(current_user, target_employee_id)

    # Validate the target employee exists before reading the file — avoids a
    # FK-violation 500 deep in the insert path and returns a clear 4xx to the
    # caller. Regression guard: T-UPL-015 (employee_id=99999999 used to 500).
    target_employee = await repository.get_employee_by_id(target_employee_id)
    if target_employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown employee: no employee found with id {target_employee_id}",
        )

    # Reject oversized uploads before reading the body (layer 1 of 2).
    # Content-Length can be absent or spoofed; the post-read check in
    # validate_upload_bytes_and_type() is the authoritative second layer.
    # MAX_UPLOAD_SIZE_BYTES is imported at module level from ..shared.utils.
    content_length_header = request.headers.get("content-length")
    if content_length_header is not None:
        try:
            declared_length = int(content_length_header)
            if declared_length > MAX_UPLOAD_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large: declared {declared_length} bytes (max {MAX_UPLOAD_SIZE_BYTES})",
                )
        except ValueError:
            pass  # Malformed Content-Length; let the post-read check handle it

    # Reject path-traversal filenames outright before reading the body.
    # sanitize_filename() also rewrites `/`, `\`, and leading dots, but an
    # explicit reject gives clients a clear 4xx rather than a silently
    # renamed file. Regression guard: T-SEC-016.
    raw_filename = file.filename or ""
    if (
        ".." in raw_filename
        or raw_filename.startswith(("/", "\\"))
        or "\x00" in raw_filename
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename contains path-traversal characters",
        )

    # Read file content
    file_bytes = await file.read()

    # Validate file
    is_valid, mime_type, error = validate_upload_bytes_and_type(
        file_bytes,
        file.filename or "unknown",
    )

    if not is_valid:
        raise UploadValidationError(error or "Invalid file")

    # Sanitize filename (belt-and-suspenders: the reject above caught the
    # obvious cases; sanitize_filename normalizes remaining quirks)
    safe_filename = sanitize_filename(file.filename or "document")

    # Generate storage key
    storage_key = f"{target_employee_id}/{uuid_generator.generate()}/{safe_filename}"

    # Store file
    await storage.put(storage_key, file_bytes, mime_type)

    # Determine acting_as (only Coordinators can upload, enforced by guards)
    if current_user.id == target_employee_id:
        acting_as = "Self"
    else:
        acting_as = "Coordinator"

    # Create document record
    document = CertificateDocument(
        id=0,
        employee_id=target_employee_id,
        storage_key=storage_key,
        file_name=safe_filename,
        file_type=mime_type,
        file_size_bytes=len(file_bytes),
        uploaded_by_id=current_user.id,
        acting_as=acting_as,
    )

    saved_document = await repository.create_document(document)

    # Audit log for document creation
    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="document_created",
        target_type="document",
        target_id=str(saved_document.id),
        details={
            "employee_id": target_employee_id,
            "file_name": safe_filename,
            "intake_channel": "MANUAL_UPLOAD",
        },
    )

    # Create initial extraction record in Processing state (SM-01).
    # It transitions to PendingReview only after the extraction pipeline completes.
    extraction = ExtractionRun(
        id=0,
        document_id=saved_document.id,
        review_state=ReviewState.PROCESSING,
        extracted_fields={},
        needs_review=True,
        needs_review_reasons=["Extraction in progress"],
    )

    saved_extraction = await repository.create_extraction(extraction)

    # Commit database changes BEFORE pushing to Redis
    # This ensures the worker can find the document
    await session.commit()

    # Trigger extraction pipeline via Redis
    try:
        task = {"document_id": saved_document.id}
        redis_client.rpush("extraction_tasks", json.dumps(task))
    except redis.RedisError as e:
        # Log but don't fail - extraction can be triggered manually
        logger.warning(
            "Failed to queue extraction task for document %d: %s",
            saved_document.id,
            str(e),
        )

    return DocumentUploadResponse(
        document_id=saved_document.id,
        extraction_id=saved_extraction.id,
        file_name=safe_filename,
        file_type=mime_type,
        file_size_bytes=len(file_bytes),
    )


@router.post("/{document_id}/view-token")
async def create_document_view_token(
    document_id: int,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    Issue a short-lived (60-second) document view token for the PDF viewer.

    Requires normal Bearer authentication. Returns a signed JWT with
    type='doc_view' that is accepted ONLY by GET /{document_id}/content
    and only for the specific document_id encoded in the token.
    """
    document = await repository.get_document_by_id(document_id)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    authorizer.require_can_view_extraction(current_user, document.employee_id)

    view_token = create_doc_view_token(current_user.id, document_id)
    return {"view_token": view_token}


async def _fetch_document_file(
    document_id: int,
    current_user: Employee,
    repository: Repository,
    storage: Storage,
) -> tuple[CertificateDocument, bytes]:
    """
    Fetch and validate a document file.

    Args:
        document_id: ID of the document to fetch
        current_user: Authenticated user making the request
        repository: Repository instance
        storage: Storage instance

    Returns:
        Tuple of (document record, file bytes)

    Raises:
        HTTPException: If document not found or user lacks permission
    """
    document = await repository.get_document_by_id(document_id)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    authorizer.require_can_view_extraction(current_user, document.employee_id)

    try:
        file_bytes = await storage.get(document.storage_key)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found in storage",
        )
    except RuntimeError:
        # RuntimeError: Storage layer errors (S3Error wrapped by MinioStorageClient).
        # Log full exception server-side; return a generic message to the caller
        # to avoid leaking infrastructure details (bucket names, endpoints, etc.).
        logger.exception(
            "Storage error retrieving document %d (key: %s)",
            document_id,
            document.storage_key,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document due to a storage error. Please try again or contact support.",
        )

    return document, file_bytes


@router.get("/{document_id}/download")
async def download_document(
    document_id: int,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
):
    """
    Download the original document file.

    Returns the document as a streaming response with appropriate headers
    for browser download.
    """
    document, file_bytes = await _fetch_document_file(
        document_id, current_user, repository, storage
    )

    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type=document.file_type,
        headers={
            "Content-Disposition": build_content_disposition(
                "attachment",
                document.file_name,
            ),
            "Content-Length": str(len(file_bytes)),
        },
    )


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: int,
    current_user: Employee = Depends(get_doc_view_token_user),
    repository: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
):
    """
    Get document content for viewing in the browser.

    Returns the document as a streaming response with inline content disposition,
    suitable for embedding in a document viewer (e.g., PDF viewer).
    """
    document, file_bytes = await _fetch_document_file(
        document_id, current_user, repository, storage
    )

    preview_bytes = file_bytes
    preview_type = document.file_type
    preview_name = document.file_name
    if document.file_type.startswith("image/"):
        try:
            preview_bytes = await run_in_threadpool(
                _convert_image_to_pdf_preview,
                file_bytes,
            )
        except ValueError as exc:
            logger.warning(
                "Unable to generate image preview for document %d: %s",
                document_id,
                str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This image cannot be previewed safely; download the original file instead.",
            ) from exc
        preview_type = "application/pdf"
        preview_name = f"{Path(document.file_name).stem or 'document'}.pdf"

    return StreamingResponse(
        io.BytesIO(preview_bytes),
        media_type=preview_type,
        headers={
            "Content-Disposition": build_content_disposition(
                "inline",
                preview_name,
            ),
            "Content-Length": str(len(preview_bytes)),
            "Cache-Control": "no-store",
        },
    )
