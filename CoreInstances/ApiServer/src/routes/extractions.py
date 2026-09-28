"""
Extractions API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

# Must match _UNBOUNDED_QUERY_CAP in repository.py. Keep in sync or move to a shared constants module.
_EXTRACTIONS_CAP = 10_000

from ..deps import get_repository, require_coordinator
from ..review import ReviewService
from ..shared.models import Employee, ReviewState
from ..shared.protocols import Repository
from ..authorizer import authorizer
from .schemas import (
    ExtractionApprove,
    ExtractionReject,
    ExtractionResponse,
    VerifiedRecordResponse,
)

router = APIRouter(prefix="/extractions", tags=["extractions"])


@router.get("", response_model=list[ExtractionResponse])
async def list_extractions(
    state: str | None = None,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    List extractions.

    Only Coordinator can list extractions.
    Optionally filter by review state.
    """
    if state:
        try:
            review_state = ReviewState(state)
            extractions = await repository.list_extractions_by_state(review_state)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid state: {state}. Must be one of: Processing, PendingReview, Approved, Rejected",
            )
    else:
        # No state filter — return all extractions. Pass limit=None so
        # dashboard pending-review counters and any aggregate views computed
        # from this response don't silently truncate at 10k rows.
        extractions = await repository.list_all_extractions(limit=None)

    items = [
        ExtractionResponse(
            id=e.id,
            document_id=e.document_id,
            review_state=e.review_state.value,
            extracted_fields=e.extracted_fields,
            needs_review=e.needs_review,
            needs_review_reasons=e.needs_review_reasons,
            template_id=e.template_id,
            template_version=e.template_version,
            template_match_evidence=e.template_match_evidence,
            review_assist=e.review_assist,
            reviewed_by_id=e.reviewed_by_id,
            reviewed_at=e.reviewed_at,
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
        for e in extractions
    ]
    if len(items) == _EXTRACTIONS_CAP:
        return JSONResponse(
            content=[item.model_dump(mode="json") for item in items],
            headers={"X-Total-Capped": "true"},
        )
    return items


@router.get("/{extraction_id}", response_model=ExtractionResponse)
async def get_extraction(
    extraction_id: int,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """Get a specific extraction by ID."""
    extraction = await repository.get_extraction_by_id(extraction_id)

    if not extraction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction {extraction_id} not found",
        )

    # Get document to check employee ownership
    document = await repository.get_document_by_id(extraction.document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document for extraction {extraction_id} not found",
        )
    authorizer.require_can_view_extraction(current_user, document.employee_id)

    return ExtractionResponse(
        id=extraction.id,
        document_id=extraction.document_id,
        review_state=extraction.review_state.value,
        extracted_fields=extraction.extracted_fields,
        needs_review=extraction.needs_review,
        needs_review_reasons=extraction.needs_review_reasons,
        template_id=extraction.template_id,
        template_version=extraction.template_version,
        template_match_evidence=extraction.template_match_evidence,
        review_assist=extraction.review_assist,
        reviewed_by_id=extraction.reviewed_by_id,
        reviewed_at=extraction.reviewed_at,
        created_at=extraction.created_at,
        updated_at=extraction.updated_at,
    )


@router.post("/{extraction_id}/approve", response_model=VerifiedRecordResponse)
async def approve_extraction(
    extraction_id: int,
    request: ExtractionApprove,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    Approve an extraction and create verified record.

    Only Coordinator can approve extractions.
    Cannot approve your own certificate (separation of duties).
    """
    # Get extraction to check certificate holder
    extraction = await repository.get_extraction_by_id(extraction_id)
    if not extraction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction {extraction_id} not found",
        )

    # Get document to check certificate holder
    document = await repository.get_document_by_id(extraction.document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document for extraction {extraction_id} not found",
        )
    authorizer.require_can_review_extraction(current_user, document.employee_id)

    # Perform approval
    review_service = ReviewService(repository)
    record = await review_service.reviewer_approve(
        extraction_id=extraction_id,
        reviewer=current_user,
        corrections=request.corrections,
        requirement_id=request.requirement_id,
    )

    return VerifiedRecordResponse(
        id=record.id,
        extraction_id=record.extraction_id,
        document_id=record.document_id,
        employee_id=record.employee_id,
        certificate_holder_name=record.certificate_holder_name,
        certificate_type=record.certificate_type,
        certificate_number=record.certificate_number,
        issuing_authority=record.issuing_authority,
        issue_date=record.issue_date,
        expiration_date=record.expiration_date,
        training_hours=record.training_hours,
        license_class=record.license_class,
        endorsements=record.endorsements,
        created_at=record.created_at,
    )


@router.post("/{extraction_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_extraction(
    extraction_id: int,
    request: ExtractionReject,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    Reject an extraction.

    Only Coordinator can reject extractions.
    """
    # Get extraction to check certificate holder
    extraction = await repository.get_extraction_by_id(extraction_id)
    if not extraction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction {extraction_id} not found",
        )

    # Get document to check certificate holder
    document = await repository.get_document_by_id(extraction.document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document for extraction {extraction_id} not found",
        )
    authorizer.require_can_review_extraction(current_user, document.employee_id)

    # Perform rejection
    review_service = ReviewService(repository)
    await review_service.reviewer_reject(
        extraction_id=extraction_id,
        reviewer=current_user,
        reason=request.reason,
    )
