"""Validated presentation protocol for the parallel intelligent guest UI.

The protocol contains data only. It has no HTML, script, URL, API-route, or
model-selected action fields. The client renders each block with an allowlisted
DOM component and treats all text as untrusted.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntelligentUIFlag(StrictSchema):
    enabled: StrictBool = False


class GuestExperienceSettings(StrictSchema):
    intelligent_ui: IntelligentUIFlag = Field(default_factory=IntelligentUIFlag)
    welcome_message: str = Field(default="", max_length=300)
    suggested_prompts: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("welcome_message")
    @classmethod
    def normalize_welcome_message(cls, value: str) -> str:
        return value.strip()

    @field_validator("suggested_prompts")
    @classmethod
    def validate_suggested_prompts(cls, items: list[str]) -> list[str]:
        clean: list[str] = []
        for item in items:
            if not isinstance(item, str):
                raise ValueError("Suggested prompts must be text.")
            item = item.strip()
            if not item or len(item) > 160:
                raise ValueError("Suggested prompts must contain 1 to 160 characters.")
            clean.append(item)
        return clean


class TextBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["text"]
    content: str = Field(max_length=6000)


class SuggestionItem(StrictSchema):
    label: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=300)


class SuggestionChipsBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["suggestion_chips"]
    items: list[SuggestionItem] = Field(min_length=1, max_length=6)


class EntityCard(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["restaurant", "facility"]
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=500)
    detail: str = Field(default="", max_length=300)


class EntityCardBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["entity_card"]
    card: EntityCard


class CardCollectionBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["card_collection"]
    title: str = Field(min_length=1, max_length=100)
    cards: list[EntityCard] = Field(min_length=1, max_length=8)


class DetailField(StrictSchema):
    label: str = Field(min_length=1, max_length=60)
    value: str = Field(max_length=300)


class DetailsPanelBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["details_panel"]
    title: str = Field(min_length=1, max_length=100)
    fields: list[DetailField] = Field(min_length=1, max_length=12)


class SelectionOption(StrictSchema):
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=120)


class SelectionFormBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["selection_form"]
    title: str = Field(min_length=1, max_length=120)
    options: list[SelectionOption] = Field(min_length=1, max_length=8)
    submit_label: str = Field(default="Continue", min_length=1, max_length=40)


class RequestReviewBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["request_review"]
    title: str = Field(min_length=1, max_length=120)
    department: str = Field(default="", max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    confirmation_token: str = Field(min_length=20, max_length=3000)
    confirm_label: str = Field(default="Confirm request", min_length=1, max_length=40)


class VerifiedConfirmationBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["verified_confirmation"]
    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(default="", max_length=500)


class MapViewBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["map_view"]
    title: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    label: str = Field(default="", max_length=120)


class LoadingStateBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["loading_state"]
    message: str = Field(default="Checking that for you…", max_length=160)


class ErrorStateBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["error_state"]
    message: str = Field(min_length=1, max_length=500)
    retryable: StrictBool = False


PresentationBlock = Annotated[
    Union[
        TextBlock,
        SuggestionChipsBlock,
        EntityCardBlock,
        CardCollectionBlock,
        DetailsPanelBlock,
        SelectionFormBlock,
        RequestReviewBlock,
        VerifiedConfirmationBlock,
        MapViewBlock,
        LoadingStateBlock,
        ErrorStateBlock,
    ],
    Field(discriminator="type"),
]


class IntelligentUIResponse(StrictSchema):
    schema_version: Literal["1.0"] = "1.0"
    conversation_id: str = Field(min_length=1, max_length=200)
    turn_id: str = Field(min_length=1, max_length=80)
    blocks: list[PresentationBlock] = Field(min_length=1, max_length=20)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def validate_guest_experience_settings(raw: object) -> dict:
    """Return normalized property configuration or reject unsafe shapes."""
    return GuestExperienceSettings.model_validate(raw).model_dump(mode="json")


def make_response(conversation_id: str, blocks: list[dict]) -> dict:
    """Validate and serialize a complete v1 presentation response."""
    response = IntelligentUIResponse(
        conversation_id=conversation_id,
        turn_id=uuid4().hex,
        blocks=blocks,
    )
    return response.model_dump(mode="json")
