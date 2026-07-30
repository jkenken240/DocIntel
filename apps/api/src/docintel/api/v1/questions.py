from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter, Request, status

from docintel.schemas.questions import QuestionCreate, QuestionResponse
from docintel.services.questions import QuestionService

router = APIRouter(prefix="/questions", tags=["questions"])


def get_question_service(request: Request) -> QuestionService:
    return cast(QuestionService, request.app.state.question_service)


@router.post(
    "",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ask_question(payload: QuestionCreate, request: Request) -> QuestionResponse:
    return await get_question_service(request).ask(
        question_text=payload.question,
        selected_document_ids=payload.document_ids,
    )


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(question_id: uuid.UUID, request: Request) -> QuestionResponse:
    return await get_question_service(request).get(question_id)
