"""Validated presentation protocol for the parallel intelligent guest UI.

The protocol contains data only. It has no HTML, script, URL, API-route, or
model-selected action fields. The client renders each block with an allowlisted
DOM component and treats all text as untrusted.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from .guest_grounding import parse_source_id


MAX_TEXT_CONTENT_CHARS = 6000


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_source_ids(values: list[str]) -> list[str]:
    clean = list(dict.fromkeys(value.strip() for value in values))
    if len(clean) > 16 or any(parse_source_id(value) is None for value in clean):
        raise ValueError("Source references must use the bounded guest record reference format.")
    # This schema check proves shape only. The request handler must resolve
    # each reference against current, property-scoped, guest-visible records;
    # references never establish that a claim is true or entailed.
    return clean


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
    content: str = Field(max_length=MAX_TEXT_CONTENT_CHARS)
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)


class GroundedClaimBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["grounded_claim"]
    content: str = Field(min_length=1, max_length=1200)
    source_ids: list[str] = Field(min_length=1, max_length=16)

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        clean = _validate_source_ids(values)
        if not clean:
            raise ValueError("Factual claims require at least one source reference.")
        return clean


class SuggestionItem(StrictSchema):
    label: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=300)


class SuggestionChipsBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["suggestion_chips"]
    items: list[SuggestionItem] = Field(min_length=1, max_length=6)


class EntityCard(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["restaurant", "facility", "service", "place", "room", "menu_item"]
    title: str = Field(min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=500)
    detail: str = Field(default="", max_length=300)
    resource_id: str = Field(default="", max_length=80)
    image_url: str = Field(default="", max_length=500)
    image_label: str = Field(default="", max_length=80)
    location: str = Field(default="", max_length=240)
    opening_hours: str = Field(default="", max_length=160)
    policies: list[str] = Field(default_factory=list, max_length=8)
    menu_available: StrictBool = False
    reservation_url: str = Field(default="", max_length=1000)
    maps_url: str = Field(default="", max_length=1000)
    open_now: StrictBool | None = None
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("image_url", "reservation_url", "maps_url")
    @classmethod
    def validate_card_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if value.startswith("/") and not value.startswith("//") and not any(c in value for c in "\\\r\n\x00"):
            return value
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Card URLs must use HTTPS or a safe same-origin path.")
        return value

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)

    @field_validator("policies")
    @classmethod
    def validate_policies(cls, values: list[str]) -> list[str]:
        clean = [value.strip() for value in values]
        if any(not value or len(value) > 240 for value in clean):
            raise ValueError("Facility policies must contain 1 to 240 characters.")
        return clean


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
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)


class DetailsPanelBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["details_panel"]
    title: str = Field(min_length=1, max_length=100)
    fields: list[DetailField] = Field(min_length=1, max_length=12)
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)


class SelectionOption(StrictSchema):
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=120)


class SelectionFormField(StrictSchema):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=100)
    input_type: Literal["date", "time", "quantity", "party_size", "service_option"]
    required: StrictBool = True
    options: list[SelectionOption] = Field(default_factory=list, max_length=8)
    minimum: int | None = Field(default=None, ge=0, le=100000)
    maximum: int | None = Field(default=None, ge=0, le=100000)

    @model_validator(mode="after")
    def validate_input_configuration(self) -> "SelectionFormField":
        if self.input_type == "service_option":
            if not self.options:
                raise ValueError("Service option fields require configured choices.")
            if len({option.value for option in self.options}) != len(self.options):
                raise ValueError("Service option values must be unique.")
            if self.minimum is not None or self.maximum is not None:
                raise ValueError("Numeric limits apply only to quantity fields.")
        else:
            if self.options:
                raise ValueError("Choices are supported only for service option fields.")
            if self.input_type not in {"quantity", "party_size"} and (
                self.minimum is not None or self.maximum is not None
            ):
                raise ValueError("Numeric limits apply only to quantity fields.")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("A selection field minimum cannot exceed its maximum.")
        if self.input_type in {"quantity", "party_size"} and self.minimum is None:
            self.minimum = 1
        return self


class SelectionFormBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["selection_form"]
    title: str = Field(min_length=1, max_length=120)
    # `options` keeps schema 1.0 responses from older servers compatible.
    options: list[SelectionOption] = Field(default_factory=list, max_length=8)
    fields: list[SelectionFormField] = Field(default_factory=list, max_length=6)
    submit_label: str = Field(default="Review selections", min_length=1, max_length=40)
    continue_label: str = Field(default="Share with concierge", min_length=1, max_length=40)
    cancel_label: str = Field(default="Cancel selections", min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_form_shape(self) -> "SelectionFormBlock":
        if bool(self.fields) == bool(self.options):
            raise ValueError("A selection form needs either typed fields or legacy options.")
        if len({field.id for field in self.fields}) != len(self.fields):
            raise ValueError("Selection field identifiers must be unique.")
        if self.options and len({option.value for option in self.options}) != len(self.options):
            raise ValueError("Selection option values must be unique.")
        return self


class RequestReviewBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["request_review"]
    title: str = Field(min_length=1, max_length=120)
    department: str = Field(default="", max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    confirmation_token: str = Field(min_length=20, max_length=3000)
    confirm_label: str = Field(default="Confirm request", min_length=1, max_length=40)
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)


class VerifiedConfirmationBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["verified_confirmation"]
    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(default="", max_length=500)
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)


class RequestStatusItem(StrictSchema):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=240)
    department: str = Field(default="", max_length=100)
    status: Literal["new", "assigned", "accepted", "in_progress", "delivered", "completed", "cancelled"]
    updated_at: int = Field(default=0, ge=0)


class RequestStatusBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["request_status"]
    title: str = Field(min_length=1, max_length=120)
    items: list[RequestStatusItem] = Field(min_length=1, max_length=10)


class DirectionStep(StrictSchema):
    label: str = Field(min_length=1, max_length=120)
    instruction: str = Field(default="", max_length=240)
    floor_id: str = Field(default="", max_length=80)
    floor_label: str = Field(default="", max_length=120)
    source_ids: list[str] = Field(min_length=1, max_length=2)

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        clean = _validate_source_ids(values)
        if not clean:
            raise ValueError("Direction steps must reference published map nodes.")
        return clean


class DirectionsBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["directions"]
    title: str = Field(min_length=1, max_length=120)
    steps: list[DirectionStep] = Field(min_length=2, max_length=40)
    node_ids: list[str] = Field(default_factory=list, max_length=40)


class MapMarker(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    x_percent: float = Field(ge=0, le=100)
    y_percent: float = Field(ge=0, le=100)
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)


class MapFloorOption(StrictSchema):
    floor_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    map_image_url: str = Field(min_length=1, max_length=500)
    image_width: int = Field(ge=1, le=25000)
    image_height: int = Field(ge=1, le=25000)
    markers: list[MapMarker] = Field(default_factory=list, max_length=80)
    synthetic_demo: StrictBool = False
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("map_image_url")
    @classmethod
    def validate_map_image_url(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/") or value.startswith("//") or any(character in value for character in "\\\r\n\x00"):
            raise ValueError("Map image URLs must be safe same-origin paths.")
        return value

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)


class MapLocationDetails(StrictSchema):
    marker_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    floor_label: str = Field(default="", max_length=120)
    location: str = Field(default="", max_length=240)
    hours: str = Field(default="", max_length=160)
    policies: list[str] = Field(default_factory=list, max_length=8)
    image_url: str = Field(default="", max_length=500)
    image_label: str = Field(default="", max_length=80)
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, value: str) -> str:
        value = value.strip()
        if value and (not value.startswith("/") or value.startswith("//") or any(character in value for character in "\\\r\n\x00")):
            raise ValueError("Map detail images must be safe same-origin paths.")
        return value

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)

    @field_validator("policies")
    @classmethod
    def validate_policies(cls, values: list[str]) -> list[str]:
        clean = [value.strip() for value in values]
        if any(not value or len(value) > 240 for value in clean):
            raise ValueError("Facility policies must contain 1 to 240 characters.")
        return clean


class MapViewBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["map_view"]
    title: str = Field(min_length=1, max_length=120)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    label: str = Field(default="", max_length=120)
    map_image_url: str = Field(default="", max_length=500)
    map_alt: str = Field(default="", max_length=500)
    image_width: int | None = Field(default=None, ge=1, le=25000)
    image_height: int | None = Field(default=None, ge=1, le=25000)
    markers: list[MapMarker] = Field(default_factory=list, max_length=80)
    floor_id: str = Field(default="", max_length=80)
    floor_label: str = Field(default="", max_length=120)
    floors: list[MapFloorOption] = Field(default_factory=list, max_length=24)
    focused_marker_id: str = Field(default="", max_length=80)
    starting_node_id: str = Field(default="", max_length=80)
    synthetic_demo: StrictBool = False
    directions_enabled: StrictBool = False
    route_node_ids: list[str] = Field(default_factory=list, max_length=40)
    locations: list[MapLocationDetails] = Field(default_factory=list, max_length=80)
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)

    @field_validator("map_image_url")
    @classmethod
    def validate_map_image_url(cls, value: str) -> str:
        value = value.strip()
        if value and (
            not value.startswith("/") or value.startswith("//")
            or any(character in value for character in "\\\r\n\x00")
        ):
            raise ValueError("Map image URLs must be safe same-origin paths.")
        return value

    @model_validator(mode="after")
    def validate_location_source(self) -> "MapViewBlock":
        has_coordinates = self.latitude is not None and self.longitude is not None
        has_floor_map = bool(self.map_image_url and self.image_width and self.image_height)
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("A geographic map location requires both coordinates.")
        if not has_coordinates and not has_floor_map:
            raise ValueError("A map needs verified coordinates or a configured floor plan.")
        if self.map_image_url and not has_floor_map:
            raise ValueError("A floor plan requires its configured dimensions.")
        if self.starting_node_id and not any(
            marker.id == self.starting_node_id
            for floor in self.floors
            for marker in floor.markers
        ):
            raise ValueError("A wayfinding start node must be present on the published floor map.")
        return self


def _validate_official_reference_url(value: str) -> str:
    value = value.strip()
    parts = urlsplit(value)
    host = (parts.hostname or "").casefold().rstrip(".")
    official_hosts = {"rwgenting.com", "gentingskyworlds.com"}
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("Official reference links must use a valid HTTPS URL.") from exc
    if (
        parts.scheme != "https" or not host or parts.username or parts.password
        or (port is not None and port != 443)
        or not any(host == domain or host.endswith("." + domain) for domain in official_hosts)
        or any(character in value for character in "\\\r\n\x00")
    ):
        raise ValueError("Official reference links must use HTTPS on a Resorts World Genting domain.")
    return value


class FacilityDirectoryLocation(StrictSchema):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=160)
    category: str = Field(default="", max_length=100)
    building: str = Field(default="", max_length=160)
    floor: str = Field(default="", max_length=80)
    location: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=500)
    listed_hours: str = Field(default="", max_length=160)
    source_url: str = Field(default="", max_length=2000)
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return _validate_official_reference_url(value) if value else ""

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)


class OfficialMapLink(StrictSchema):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=160)
    scope: str = Field(default="", max_length=160)
    format: str = Field(default="", max_length=20)
    url: str = Field(min_length=1, max_length=2000)
    license_status: str = Field(default="", max_length=120)
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _validate_official_reference_url(value)

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)


class FacilityDirectoryBlock(StrictSchema):
    id: str = Field(min_length=1, max_length=80)
    type: Literal["facility_directory"]
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    locations: list[FacilityDirectoryLocation] = Field(default_factory=list, max_length=80)
    map_links: list[OfficialMapLink] = Field(default_factory=list, max_length=12)
    source_ids: list[str] = Field(default_factory=list, max_length=16)

    @field_validator("source_ids")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        return _validate_source_ids(values)

    @model_validator(mode="after")
    def require_directory_content(self) -> "FacilityDirectoryBlock":
        if not self.locations and not self.map_links:
            raise ValueError("A facility directory needs at least one location or official map link.")
        if len({item.id for item in self.locations}) != len(self.locations):
            raise ValueError("Facility directory location IDs must be unique.")
        if len({item.id for item in self.map_links}) != len(self.map_links):
            raise ValueError("Official map IDs must be unique.")
        return self


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
        GroundedClaimBlock,
        SuggestionChipsBlock,
        EntityCardBlock,
        CardCollectionBlock,
        DetailsPanelBlock,
        SelectionFormBlock,
        RequestReviewBlock,
        VerifiedConfirmationBlock,
        RequestStatusBlock,
        DirectionsBlock,
        MapViewBlock,
        FacilityDirectoryBlock,
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


def make_response(conversation_id: str, blocks: list[dict], turn_id: str | None = None) -> dict:
    """Validate and serialize a complete v1 presentation response."""
    response = IntelligentUIResponse(
        conversation_id=conversation_id,
        turn_id=turn_id or uuid4().hex,
        blocks=blocks,
    )
    return response.model_dump(mode="json")
