"""Concrete Admin AI actions backed by Concierge.AI's existing services."""
from __future__ import annotations

from copy import deepcopy
import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

from .configuration_actions import ActionContext, ConfigurationAction, ConfigurationActionRegistry
from .network_access import find_network_overlaps, normalize_cidrs, normalize_management_access, unsafe_management_networks


def _object(properties: dict[str, Any], required: list[str] | None = None, *, additional: bool = False) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": additional}


def _string(maximum: int = 1000, *, minimum: int = 0, enum: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "maxLength": maximum, "minLength": minimum}
    if enum is not None:
        schema["enum"] = enum
    return schema


def _strings(maximum: int = 80, *, count: int = 40) -> dict[str, Any]:
    return {"type": "array", "maxItems": count, "items": _string(maximum)}


def _restaurant(ctx: ActionContext, restaurant_id: str, permission: str) -> dict[str, Any]:
    return ctx.services["require_restaurant_access"](ctx.principal, ctx.property_id, restaurant_id, permission)


def _property_record(ctx: ActionContext) -> Any:
    record = ctx.services["properties"].get(ctx.property_id)
    if record is None:
        raise ValueError("Property not found.")
    return record


def _safe_property_fields(record: Any, names: tuple[str, ...]) -> dict[str, Any]:
    return {name: deepcopy(getattr(record, name)) for name in names}


def _hours_valid(value: Any) -> None:
    if not isinstance(value, dict) or len(value) > 14:
        raise ValueError("Operating hours must be an object with at most 14 periods.")
    for day, hours in value.items():
        if not isinstance(day, str) or len(day) > 24 or not isinstance(hours, str) or len(hours) > 80:
            raise ValueError("Each operating-hours period must have a short label and value.")
        if hours.casefold() == "closed":
            continue
        if not re.fullmatch(r"\s*(?:[01]?\d|2[0-3]):[0-5]\d\s*[-–]\s*(?:[01]?\d|2[0-3]):[0-5]\d\s*", hours):
            raise ValueError("Use 24-hour hours such as 06:30-23:00, or Closed.")


def register_admin_configuration_actions(registry: ConfigurationActionRegistry, services: dict[str, Any]) -> None:
    """Register actions after app services and route-level validators exist."""
    register = registry.register
    string = _string
    any_object = {"type": "object", "additionalProperties": True}

    def validate_empty_service(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return params

    # Property content uses a field allowlist, preserving security and network settings.
    property_fields = {
        "hotel_name": string(200, minimum=1),
        "description": string(4000),
        "address": string(500),
        "welcome": string(500),
        "contact_details": _object({"phone": string(80), "email": string(254), "website": string(500)}),
    }

    def validate_property_info(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        if not params:
            raise ValueError("Provide at least one property information field.")
        return params

    def property_info_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        record = _property_record(ctx)
        names = tuple(params)
        return {"current": _safe_property_fields(record, names), "proposed": params, "impact": "Updates guest-facing property information."}

    def property_info_execute(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        record = _property_record(ctx)
        for key, value in params.items():
            setattr(record, key, value)
        saved = services["properties"].upsert(record)
        return _safe_property_fields(saved, tuple(params))

    register(ConfigurationAction(
        "property.update_information", "Update guest-facing hotel information.", "properties.edit",
        _object(property_fields), validate_property_info, property_info_execute, property_info_preview,
    ))

    personality_fields = {
        "name": string(80),
        "tone": string(40, enum=["warm", "professional", "friendly", "luxury"]),
        "formality": string(40, enum=["balanced", "formal", "casual"]),
        "response_length": string(40, enum=["concise", "balanced", "detailed"]),
        "greeting_behavior": string(40, enum=["first_message", "when_helpful", "never"]),
        "property_instructions": string(4000),
    }

    def validate_personality(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        if not params:
            raise ValueError("Provide at least one personality field.")
        return params

    def personality_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        record = _property_record(ctx)
        current = deepcopy(record.personality or {})
        return {
            "current": {key: current.get(key, record.concierge_name if key == "name" else "") for key in params},
            "proposed": params, "impact": "Changes the hotel's guest-facing assistant personality.",
        }

    def personality_execute(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        record = _property_record(ctx)
        record.personality = {**(record.personality or {}), **params}
        if "name" in params:
            record.concierge_name = params["name"]
        services["properties"].upsert(record)
        return {key: record.personality[key] for key in params}

    register(ConfigurationAction(
        "property.update_personality", "Update the property's guest-facing AI personality.", "ai.configure",
        _object(personality_fields), validate_personality, personality_execute, personality_preview,
    ))

    # Design validation is the same validator used by the design editor and publish APIs.
    design_schema = _object({
        "theme": any_object, "branding": any_object, "typography": any_object,
        "layout": any_object, "card": any_object, "composer": any_object,
        "welcome": any_object, "header": any_object,
        "messages": any_object,
        "suggestions": {"type": "array", "maxItems": 24, "items": any_object},
        "pages": {"type": "array", "maxItems": 12, "items": any_object},
        "navigation": {"type": "array", "maxItems": 12, "items": any_object},
    })

    def validate_design(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        try:
            record = _property_record(ctx)
            expected_revision = params.get("expected_revision", record.design_revision)
            if expected_revision != record.design_revision:
                raise ValueError("The guest experience changed after this AI proposal was created. Create a new proposal from the current draft.")
            return {"config": services["validate_design_config"](params["config"]), "expected_revision": expected_revision}
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

    def design_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        record = _property_record(ctx)
        if record.design_revision != params["expected_revision"]:
            raise ValueError("The guest experience changed after this AI proposal was created. Create a new proposal from the current draft.")
        return {"current": record.design_draft, "proposed": params["config"], "impact": "Saves a design draft for preview; the published guest page is unchanged."}

    def design_execute(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        record = services["properties"].save_design_draft(ctx.property_id, params["config"], params["expected_revision"])
        return {"status": "draft_saved", "design": record.design_draft, "revision": record.design_revision}

    def design_rollback(ctx: ActionContext, params: dict[str, Any], current: Any) -> Any:
        return services["properties"].save_design_draft(ctx.property_id, current)

    register(ConfigurationAction(
        "design.create_draft", "Create and validate a guest landing-page design draft.", "concierge.edit",
        _object({"config": design_schema, "expected_revision": {"type": "integer", "minimum": 1}}, ["config"]), validate_design, design_execute, design_preview,
        rollback=design_rollback,
    ))

    def validate_design_publish(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        record = _property_record(ctx)
        expected_revision = params.get("expected_revision", record.design_revision)
        if expected_revision != record.design_revision:
            raise ValueError("The guest experience changed after this publish proposal was created. Create a new proposal from the current draft.")
        return {"expected_revision": expected_revision}

    def design_publish_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        record = _property_record(ctx)
        if record.design_revision != params["expected_revision"]:
            raise ValueError("The guest experience changed after this publish proposal was created. Create a new proposal from the current draft.")
        return {"current": record.design_published, "proposed": record.design_draft, "impact": "Publishes the validated design draft to the guest experience."}

    def design_publish_execute(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        record = services["properties"].publish_design(
            ctx.property_id, ctx.principal.user_id, params["expected_revision"],
        )
        return {"status": "published", "design": record.design_published, "revision": record.design_revision}

    register(ConfigurationAction(
        "design.publish", "Publish the property's current guest experience draft.", "concierge.edit",
        _object({"expected_revision": {"type": "integer", "minimum": 1}}),
        validate_design_publish, design_publish_execute, design_publish_preview,
        confirmation_requirement="normal",
    ))

    def validate_empty(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return params

    # Safe property AI settings only; credentials, arbitrary config blobs and API keys are excluded.
    provider_fields = {
        "enabled": {"type": "boolean"}, "selected_model": string(180),
        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
        "max_output_tokens": {"type": "integer", "minimum": 1, "maximum": 32000},
        "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
    }

    def validate_provider(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        provider_id = params["provider_id"]
        current = services["ai_provider_store"].get_connection(ctx.property_id, provider_id)
        model = params.get("selected_model", current["selected_model"])
        if model not in current.get("model_catalog", []):
            raise ValueError("Choose a model listed for this provider.")
        return params

    def provider_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = services["ai_provider_store"].get_connection(ctx.property_id, params["provider_id"])
        names = tuple(key for key in params if key != "provider_id")
        return {
            "current": {"provider_id": params["provider_id"], **{key: current.get(key) for key in names}},
            "proposed": {"provider_id": params["provider_id"], **{key: params.get(key, current.get(key)) for key in names}},
            "impact": "Changes property AI provider behavior. It does not add, reveal, or replace credentials.",
        }

    def provider_execute(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        provider_id = params["provider_id"]
        current = services["ai_provider_store"].get_connection(ctx.property_id, provider_id)
        payload = {
            "enabled": current["enabled"], "auth_method": current["auth_method"],
            "selected_model": current["selected_model"], "endpoint_url": current["endpoint_url"],
            "temperature": current["temperature"], "max_output_tokens": current["max_output_tokens"],
            "timeout_seconds": current["timeout_seconds"], "config": current.get("config") or {},
        }
        payload.update({key: value for key, value in params.items() if key != "provider_id"})
        result = services["ai_provider_store"].save_connection(ctx.property_id, provider_id, payload)
        return {"provider_id": provider_id, "enabled": result["enabled"], "selected_model": result["selected_model"]}

    register(ConfigurationAction(
        "ai.provider.update", "Change non-secret property AI provider settings.", "ai.configure",
        _object({"provider_id": string(80, minimum=1), **provider_fields}, ["provider_id"]),
        validate_provider, provider_execute, provider_preview, risk_level="MEDIUM", confirmation_requirement="strong",
    ))

    # Guest and management network updates go through the existing API handlers,
    # including their CIDR validation, overlap checks, lockout rollback, and audit.
    guest_network_fields = {
        "guest_access_enabled": {"type": "boolean"}, "guest_domain": string(253), "guest_url": string(1000),
        "guest_https_required": {"type": "boolean"}, "reverse_proxy": {"type": "boolean"},
        "guest_network_only": {"type": "boolean"}, "allowed_cidrs": _strings(80, count=64),
        "trusted_proxy_ranges": _strings(80, count=64),
        "session_network_revalidation": string(20, enum=["suspend", "expire"]),
        "guest_session_timeout": {"type": "integer", "minimum": 5, "maximum": 1440},
        "antlabs_gateway_enabled": {"type": "boolean"}, "antlabs_gateway_ranges": _strings(80, count=64),
    }

    def guest_network_state(record: Any) -> dict[str, Any]:
        guardrails = services["normalize_guardrails"](record.guardrails)
        deployment = dict((record.app_settings or {}).get("deployment") or {})
        return {
            "guest_access_enabled": deployment.get("guest_access_enabled", True) is not False,
            "guest_domain": record.domain or "", "guest_url": deployment.get("public_base_url", ""),
            "guest_https_required": deployment.get("https_required", True) is not False,
            "reverse_proxy": bool(deployment.get("reverse_proxy", False)),
            "guest_network_only": bool(guardrails["guest_network_only"]),
            "allowed_cidrs": guardrails["allowed_cidrs"], "trusted_proxy_ranges": guardrails["trusted_proxy_ranges"],
            "session_network_revalidation": guardrails["session_network_revalidation"],
            "guest_session_timeout": guardrails["guest_session_timeout"],
            "antlabs_gateway_enabled": bool(guardrails["antlabs_gateway_enabled"]),
            "antlabs_gateway_ranges": guardrails["antlabs_gateway_ranges"],
        }

    def validate_guest_network(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        if not params:
            raise ValueError("Provide at least one Guest Access field.")
        current = guest_network_state(_property_record(ctx))
        merged = {**current, **params}
        merged["allowed_cidrs"] = normalize_cidrs(merged["allowed_cidrs"], "allowed_cidrs")
        merged["trusted_proxy_ranges"] = normalize_cidrs(merged["trusted_proxy_ranges"], "trusted_proxy_ranges")
        merged["antlabs_gateway_ranges"] = normalize_cidrs(merged["antlabs_gateway_ranges"], "antlabs_gateway_ranges")
        merged["guest_domain"] = services["validated_guest_domain"](merged["guest_domain"])
        merged["guest_url"] = services["validated_guest_url"](merged["guest_url"], merged["guest_domain"], merged["guest_https_required"])
        return merged

    def guest_network_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = guest_network_state(_property_record(ctx))
        overlaps = find_network_overlaps(params["allowed_cidrs"], services["effective_management_access"]().get("management_allowed_cidrs", []))
        warnings = [f"Guest and management networks overlap: {guest} overlaps {admin}." for guest, admin in overlaps]
        return {
            "current": current, "proposed": params,
            "impact": "Guest network and domain changes affect guest access. " + " ".join(warnings),
            "warnings": warnings,
        }

    async def guest_network_execute(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        result = await services["save_guest_network_access"](
            ctx.property_id,
            services["GuestNetworkAccessPayload"](**params, confirm_overlap=True),
            ctx.request,
        )
        return {"status": "updated", "guest": result.get("guest", {})}

    register(ConfigurationAction(
        "network.update_guest_access", "Update Guest Access networks, proxies, and guest domain settings.", "network.manage",
        _object(guest_network_fields), validate_guest_network, guest_network_execute, guest_network_preview,
        risk_level="MEDIUM", confirmation_requirement="strong",
    ))

    management_fields = {
        "management_access_enabled": {"type": "boolean"},
        "management_allowed_cidrs": _strings(80, count=64),
        "management_trusted_proxy_ranges": _strings(80, count=64),
    }

    def management_current() -> dict[str, Any]:
        return normalize_management_access(services["effective_management_access"](), default_allowed_cidrs=(), default_trusted_proxy_ranges=())

    def validate_management(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        if not params:
            raise ValueError("Provide at least one Management Access field.")
        return normalize_management_access({**management_current(), **params}, default_allowed_cidrs=(), default_trusted_proxy_ranges=())

    def management_warnings(ctx: ActionContext, params: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        if unsafe_management_networks(params["management_allowed_cidrs"]):
            warnings.append("A /0 management network allows every IPv4 or IPv6 address.")
        if not params["management_access_enabled"]:
            warnings.append("Disabling Management Access removes the network restriction from Admin and metrics endpoints.")
        guest_ranges = services["normalize_guardrails"](_property_record(ctx).guardrails).get("allowed_cidrs", [])
        overlaps = find_network_overlaps(guest_ranges, params["management_allowed_cidrs"])
        warnings.extend(f"Management and guest networks overlap: {management} overlaps {guest}." for guest, management in overlaps)
        request = ctx.request
        decision = services["management_access_guard"].evaluate(
            request.client.host if request.client else "", request.headers, params,
        )
        if params["management_access_enabled"] and not decision.allowed:
            warnings.append("The current administrator source IP is outside this allow list. The existing API starts a 10-minute rollback window.")
        return warnings

    def management_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = management_current()
        proposed = {key: params[key] for key in management_fields}
        warnings = management_warnings(ctx, params)
        return {"current": current, "proposed": proposed, "impact": "Management Access changes may block administrator access. " + " ".join(warnings), "warnings": warnings}

    async def management_execute(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        warnings = management_warnings(ctx, params)
        result = await services["save_management_network_access"](
            ctx.property_id,
            services["ManagementAccessPayload"](
                **params, confirm_unsafe=True, confirm_overlap=True,
                confirm_lockout=True, confirm_public_exposure=True,
            ),
            ctx.request,
        )
        return {"status": "updated", "rollback_pending": result.get("rollback_pending", False), "warnings": warnings}

    register(ConfigurationAction(
        "network.update_management_access", "Update installation-wide Management Access networks and trusted proxies.",
        "network.manage", _object(management_fields), validate_management, management_execute, management_preview,
        risk_level="MEDIUM", confirmation_requirement="strong", allowed_roles=frozenset({"super-admin"}),
        property_scope="installation",
    ))

    # Property-scoped facilities and service catalog actions.
    facility_fields = {
        "name": string(160, minimum=1), "facility_type": string(80), "description": string(1000),
        "opening_hours": any_object, "images": _strings(500, count=12), "capacity": {"type": "integer", "minimum": 0, "maximum": 100000},
        "booking_supported": {"type": "boolean"}, "live_status": string(32, enum=["open", "closed", "temporarily_closed", "full", "maintenance", "private_event"]),
        "status_note": string(240),
    }

    def facility_list(ctx: ActionContext) -> list[dict[str, Any]]:
        return services["hospitality"].overview(ctx.property_id).get("facilities", [])

    def validate_facility_create(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        if "opening_hours" in params:
            _hours_valid(params["opening_hours"])
        return params

    def facility_create_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return {"current": None, "proposed": params, "impact": "Creates a property facility visible to hotel operations."}

    def facility_create(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["hospitality"].upsert_facility_profile(ctx.property_id, params)

    register(ConfigurationAction(
        "facility.create", "Create a property facility profile.", "properties.edit",
        _object(facility_fields, ["name"]), validate_facility_create, facility_create, facility_create_preview,
    ))

    facility_update_schema = _object({"facility_id": string(100, minimum=1), "changes": _object(facility_fields)}, ["facility_id", "changes"])

    def validate_facility_update(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = next((item for item in facility_list(ctx) if item.get("facility_id") == params["facility_id"]), None)
        if not current:
            raise ValueError("Facility not found in this property.")
        changes = params["changes"]
        if not changes:
            raise ValueError("Provide at least one facility field to update.")
        if "opening_hours" in changes:
            _hours_valid(changes["opening_hours"])
        return {**params, "_current": current}

    def facility_update_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = params["_current"]
        return {"current": {key: current.get(key) for key in params["changes"]}, "proposed": params["changes"], "impact": "Updates this facility profile."}

    def facility_update(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = params["_current"]
        return services["hospitality"].upsert_facility_profile(ctx.property_id, {**current, **params["changes"], "facility_id": params["facility_id"]})

    register(ConfigurationAction(
        "facility.update", "Update a facility profile in the selected property.", "properties.edit",
        facility_update_schema, validate_facility_update, facility_update, facility_update_preview,
    ))

    service_fields = {
        "name": string(160, minimum=1), "description": string(1000), "department_id": string(100),
        "keywords": _strings(80, count=30), "sla_minutes": {"type": "integer", "minimum": 1, "maximum": 1440},
        "confirmation_required": {"type": "boolean"}, "enabled": {"type": "boolean"},
        "sort_order": {"type": "integer", "minimum": -10000, "maximum": 10000},
    }

    def service_create(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["hospitality"].upsert_service(ctx.property_id, params)

    def service_create_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return {"current": None, "proposed": params, "impact": "Adds a guest service to the property catalog."}

    register(ConfigurationAction(
        "service_catalog.create", "Add a guest service to the property service catalog.", "properties.edit",
        _object(service_fields, ["name"]), validate_empty_service, service_create, service_create_preview,
    ))

    service_update_schema = _object({"service_id": string(100, minimum=1), "changes": _object(service_fields)}, ["service_id", "changes"])

    def validate_service_update(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = services["hospitality"].get_service(ctx.property_id, params["service_id"])
        if not current:
            raise ValueError("Service not found in this property.")
        if not params["changes"]:
            raise ValueError("Provide at least one service field to update.")
        return {**params, "_current": current}

    def service_update_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = params["_current"]
        return {"current": {key: current.get(key) for key in params["changes"]}, "proposed": params["changes"], "impact": "Updates the guest service catalog."}

    def service_update(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["hospitality"].upsert_service(ctx.property_id, {**params["_current"], **params["changes"], "service_id": params["service_id"]})

    register(ConfigurationAction(
        "service_catalog.update", "Update a guest service in the property catalog.", "properties.edit",
        service_update_schema, validate_service_update, service_update, service_update_preview,
    ))

    event_schema = _object({
        "title": string(180, minimum=1), "starts_at": {"type": "integer", "minimum": 0},
        "ends_at": {"type": "integer", "minimum": 0}, "facility_id": string(100),
        "zone_id": string(100), "audience": string(120),
        "capacity": {"type": "integer", "minimum": 0, "maximum": 100000},
        "description": string(1000), "notification_timing": any_object,
        "cta": string(200), "status": string(32, enum=["scheduled"]),
    }, ["title"])

    def validate_event(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        starts_at = params.get("starts_at")
        ends_at = params.get("ends_at")
        if starts_at is not None and ends_at is not None and ends_at < starts_at:
            raise ValueError("Event end time must be after its start time.")
        facility_id = params.get("facility_id")
        if facility_id and not any(item.get("facility_id") == facility_id for item in facility_list(ctx)):
            raise ValueError("Facility not found in this property.")
        return params

    register(ConfigurationAction(
        "event.create", "Schedule a guest-facing property event.", "properties.edit",
        event_schema, validate_event,
        lambda ctx, params: services["hospitality"].create_event(ctx.property_id, params),
        lambda ctx, params: {"current": None, "proposed": params, "impact": "Schedules a property event for guests after confirmation."},
    ))

    # Restaurant information and hours always resolve the restaurant assignment again.
    restaurant_fields = {
        "name": string(160, minimum=1), "location": string(240), "description": string(1000),
        "cuisine": string(120), "dress_code": string(120), "capacity": {"type": "integer", "minimum": 1, "maximum": 100000},
        "phone_extension": string(80), "guest_notes": string(1000), "reservation_available": {"type": "boolean"},
    }
    restaurant_update_schema = _object({"restaurant_id": string(100, minimum=1), "changes": _object(restaurant_fields)}, ["restaurant_id", "changes"])

    def validate_restaurant_update(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = _restaurant(ctx, params["restaurant_id"], "restaurant.manage")
        if not params["changes"]:
            raise ValueError("Provide at least one restaurant field to update.")
        return {**params, "_current": current}

    def restaurant_update_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = params["_current"]
        return {"restaurant_id": params["restaurant_id"], "restaurant_name": current["name"], "current": {key: current.get(key) for key in params["changes"]}, "proposed": params["changes"], "impact": "Updates this assigned restaurant's guest-facing information."}

    def restaurant_update(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["hospitality"].update_restaurant(ctx.property_id, params["restaurant_id"], params["changes"], ctx.principal.user_id)

    register(ConfigurationAction(
        "restaurant.update", "Update guest-facing details for an assigned restaurant.", "restaurant.manage",
        restaurant_update_schema, validate_restaurant_update, restaurant_update, restaurant_update_preview, restaurant_scope=True,
    ))

    hours_schema = _object({
        "restaurant_id": string(100, minimum=1), "opening_hours": any_object,
        "meal_periods": {"type": "array", "maxItems": 12, "items": any_object},
    }, ["restaurant_id"])

    def validate_hours(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = _restaurant(ctx, params["restaurant_id"], "restaurant.hours.edit")
        if not ("opening_hours" in params or "meal_periods" in params):
            raise ValueError("Provide opening_hours or meal_periods.")
        if "opening_hours" in params:
            _hours_valid(params["opening_hours"])
        return {**params, "_current": current}

    def hours_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = params["_current"]
        return {"restaurant_id": params["restaurant_id"], "restaurant_name": current["name"], "current": {key: current.get(key) for key in ("opening_hours", "meal_periods")}, "proposed": {key: params[key] for key in ("opening_hours", "meal_periods") if key in params}, "impact": "Changes guest-visible operating hours for this assigned restaurant."}

    def hours_execute(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["hospitality"].update_restaurant(ctx.property_id, params["restaurant_id"], {key: params[key] for key in ("opening_hours", "meal_periods") if key in params}, ctx.principal.user_id)

    register(ConfigurationAction(
        "restaurant.update_hours", "Update operating hours for an assigned restaurant.", "restaurant.hours.edit",
        hours_schema, validate_hours, hours_execute, hours_preview, restaurant_scope=True,
    ))

    restaurant_create_schema = _object({"name": string(160, minimum=1), "location": string(240), "description": string(1000), "cuisine": string(120)}, ["name"])
    register(ConfigurationAction(
        "restaurant.create", "Create a restaurant in the selected property.", "properties.edit",
        restaurant_create_schema, validate_empty_service,
        lambda ctx, params: services["hospitality"].create_restaurant(ctx.property_id, params, actor_user_id=ctx.principal.user_id),
        lambda ctx, params: {"current": None, "proposed": params, "impact": "Creates a restaurant in the selected property."},
    ))

    # Menu workflows call HospitalityStore, preserving its approval state transitions and audit trail.
    menu_create_schema = _object({"restaurant_id": string(100, minimum=1), "name": string(160, minimum=1), "meal_period": string(80)}, ["restaurant_id", "name"])

    def validate_menu_create(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        target = _restaurant(ctx, params["restaurant_id"], "restaurant.menu.edit")
        return {**params, "_restaurant_name": target["name"]}

    def menu_create_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return {"restaurant_id": params["restaurant_id"], "restaurant_name": params["_restaurant_name"], "current": None, "proposed": {key: params[key] for key in ("name", "meal_period") if key in params}, "impact": "Creates a menu pending approval. No menu is published."}

    def menu_create(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["hospitality"].create_menu(ctx.property_id, params["restaurant_id"], {key: params[key] for key in ("name", "meal_period") if key in params}, actor_user_id=ctx.principal.user_id)

    register(ConfigurationAction(
        "menu.create_draft", "Create a menu draft for an assigned restaurant.", "restaurant.menu.edit",
        menu_create_schema, validate_menu_create, menu_create, menu_create_preview, restaurant_scope=True,
    ))

    menu_update_schema = _object({"restaurant_id": string(100, minimum=1), "menu_id": string(100, minimum=1), "name": string(160), "meal_period": string(80)}, ["restaurant_id", "menu_id"])

    def validate_menu_update(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        _restaurant(ctx, params["restaurant_id"], "restaurant.menu.edit")
        if services["hospitality"].restaurant_id_for_menu(ctx.property_id, params["menu_id"]) != params["restaurant_id"]:
            raise ValueError("Menu is not in the assigned restaurant.")
        current = next((menu for menu in services["hospitality"].restaurant_menus(ctx.property_id, params["restaurant_id"]) if menu["menu_id"] == params["menu_id"]), None)
        if current is None or not any(key in params for key in ("name", "meal_period")):
            raise ValueError("Menu not found or no menu fields were supplied.")
        return {**params, "_current": current}

    def menu_update_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = params["_current"]
        return {"restaurant_id": params["restaurant_id"], "restaurant_name": current.get("restaurant_name", ""), "current": {key: current.get(key) for key in ("name", "meal_period")}, "proposed": {key: params[key] for key in ("name", "meal_period") if key in params}, "impact": "Updates this menu and returns it to pending approval."}

    def menu_update(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["hospitality"].update_menu(ctx.property_id, params["menu_id"], {key: params[key] for key in ("name", "meal_period") if key in params}, actor_user_id=ctx.principal.user_id)

    register(ConfigurationAction(
        "menu.update", "Update a menu in an assigned restaurant.", "restaurant.menu.edit",
        menu_update_schema, validate_menu_update, menu_update, menu_update_preview, restaurant_scope=True,
    ))

    item_fields = {
        "name": string(160, minimum=1), "description": string(1000), "price": string(40),
        "ingredients": _strings(160, count=40), "allergens": _strings(80, count=40),
        "dietary_tags": _strings(80, count=40), "available": {"type": "boolean"},
    }
    item_schema = _object(item_fields, ["name"])
    add_item_schema = _object({"restaurant_id": string(100, minimum=1), "menu_id": string(100, minimum=1), "item": item_schema}, ["restaurant_id", "menu_id", "item"])

    def validate_add_item(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        _restaurant(ctx, params["restaurant_id"], "restaurant.menu.edit")
        if services["hospitality"].restaurant_id_for_menu(ctx.property_id, params["menu_id"]) != params["restaurant_id"]:
            raise ValueError("Menu is not in the assigned restaurant.")
        return params

    def add_item_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        target = _restaurant(ctx, params["restaurant_id"], "restaurant.menu.edit")
        return {"restaurant_id": params["restaurant_id"], "restaurant_name": target["name"], "current": None, "proposed": params["item"], "impact": "Adds a menu item and moves the menu to pending approval."}

    def add_item(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["hospitality"].create_menu_item(ctx.property_id, params["menu_id"], params["item"], actor_user_id=ctx.principal.user_id)

    register(ConfigurationAction(
        "menu.add_item", "Add an item to a menu in an assigned restaurant.", "restaurant.menu.edit",
        add_item_schema, validate_add_item, add_item, add_item_preview, restaurant_scope=True,
    ))

    imported_menu_schema = _object({
        "restaurant_id": string(100, minimum=1), "name": string(160, minimum=1),
        "meal_period": string(80),
        "items": {"type": "array", "minItems": 1, "maxItems": 100, "items": item_schema},
    }, ["restaurant_id", "name", "items"])

    def validate_imported_menu(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        target = _restaurant(ctx, params["restaurant_id"], "restaurant.menu.edit")
        return {**params, "_restaurant_name": target["name"]}

    def imported_menu_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        items = params["items"]
        missing_prices = sum(not str(item.get("price") or "").strip() for item in items)
        missing_allergens = sum("allergens" not in item for item in items)
        warnings = []
        if missing_prices:
            warnings.append(f"{missing_prices} item(s) have no price in the supplied menu; review before approval.")
        if missing_allergens:
            warnings.append(f"{missing_allergens} item(s) have no allergen information in the supplied menu; verify before approval.")
        return {
            "restaurant_id": params["restaurant_id"], "restaurant_name": params["_restaurant_name"],
            "current": None,
            "proposed": {"name": params["name"], "meal_period": params.get("meal_period", ""), "items": items},
            "impact": f"Creates a {len(items)}-item menu draft pending approval. It will not be published to guests." + (" " + " ".join(warnings) if warnings else ""),
            "warnings": warnings,
        }

    def imported_menu_execute(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        # Scope is rechecked on confirmation, immediately before calling the same
        # service operations used by the restaurant menu APIs.
        _restaurant(ctx, params["restaurant_id"], "restaurant.menu.edit")
        menu = services["hospitality"].create_menu(
            ctx.property_id, params["restaurant_id"],
            {"name": params["name"], "meal_period": params.get("meal_period", "")},
            actor_user_id=ctx.principal.user_id,
        )
        items = [
            services["hospitality"].create_menu_item(
                ctx.property_id, menu["menu_id"], item, actor_user_id=ctx.principal.user_id,
            )
            for item in params["items"]
        ]
        return {**menu, "workflow_status": "pending_approval", "items": items, "item_count": len(items)}

    register(ConfigurationAction(
        "menu.import_draft", "Extract and create a reviewable menu draft from provided text or a document.",
        "restaurant.menu.edit", imported_menu_schema, validate_imported_menu,
        imported_menu_execute, imported_menu_preview, restaurant_scope=True,
    ))

    update_item_schema = _object({"restaurant_id": string(100, minimum=1), "item_id": string(100, minimum=1), "changes": _object(item_fields)}, ["restaurant_id", "item_id", "changes"])

    def validate_update_item(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        _restaurant(ctx, params["restaurant_id"], "restaurant.menu.edit")
        if services["hospitality"].restaurant_id_for_menu_item(ctx.property_id, params["item_id"]) != params["restaurant_id"]:
            raise ValueError("Menu item is not in the assigned restaurant.")
        if not params["changes"]:
            raise ValueError("Provide at least one menu-item field to update.")
        current_menu = next((menu for menu in services["hospitality"].restaurant_menus(ctx.property_id, params["restaurant_id"]) if any(item["item_id"] == params["item_id"] for item in menu["items"])), None)
        current = next((item for item in current_menu["items"] if item["item_id"] == params["item_id"]), None) if current_menu else None
        if current is None:
            raise ValueError("Menu item not found.")
        return {**params, "_current": current}

    def update_item_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = params["_current"]
        return {"restaurant_id": params["restaurant_id"], "current": {key: current.get(key) for key in params["changes"]}, "proposed": params["changes"], "impact": "Updates this menu item and moves its menu to pending approval."}

    def update_item(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["hospitality"].update_menu_item(ctx.property_id, params["item_id"], params["changes"], actor_user_id=ctx.principal.user_id)

    register(ConfigurationAction(
        "menu.update_item", "Update a menu item in an assigned restaurant.", "restaurant.menu.edit",
        update_item_schema, validate_update_item, update_item, update_item_preview, restaurant_scope=True,
    ))

    menu_approval_schema = _object({"restaurant_id": string(100, minimum=1), "menu_id": string(100, minimum=1)}, ["restaurant_id", "menu_id"])

    def validate_menu_approval(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        _restaurant(ctx, params["restaurant_id"], "restaurant.menu.approve")
        if services["hospitality"].restaurant_id_for_menu(ctx.property_id, params["menu_id"]) != params["restaurant_id"]:
            raise ValueError("Menu is not in the assigned restaurant.")
        menu = next((item for item in services["hospitality"].restaurant_menus(ctx.property_id, params["restaurant_id"]) if item["menu_id"] == params["menu_id"]), None)
        if not menu:
            raise ValueError("Menu not found.")
        return {**params, "_current": menu}

    def menu_approval_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return {"restaurant_id": params["restaurant_id"], "current": {"workflow_status": params["_current"].get("workflow_status")}, "proposed": {"workflow_status": "approved"}, "impact": "Approves this menu. Publishing is a separate confirmed action."}

    register(ConfigurationAction(
        "menu.approve", "Approve a menu for its separate publish workflow.", "restaurant.menu.approve",
        menu_approval_schema, validate_menu_approval,
        lambda ctx, params: services["hospitality"].approve_menu(ctx.property_id, params["menu_id"], ctx.principal.user_id),
        menu_approval_preview, restaurant_scope=True,
    ))

    def menu_publish_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = params["_current"]
        return {"restaurant_id": params["restaurant_id"], "current": {"workflow_status": current.get("workflow_status"), "active": current.get("active")}, "proposed": {"workflow_status": "published", "active": True}, "impact": "Publishes this approved menu to restaurant guests."}

    register(ConfigurationAction(
        "menu.publish", "Publish an approved menu to restaurant guests.", "restaurant.menu.approve",
        menu_approval_schema, validate_menu_approval,
        lambda ctx, params: services["hospitality"].publish_menu(ctx.property_id, params["menu_id"], ctx.principal.user_id),
        menu_publish_preview, restaurant_scope=True,
    ))

    def menu_combined_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = params["_current"]
        target = _restaurant(ctx, params["restaurant_id"], "restaurant.menu.approve")
        return {"restaurant_id": params["restaurant_id"], "restaurant_name": target["name"], "current": {"workflow_status": current.get("workflow_status"), "active": current.get("active")}, "proposed": {"workflow_status": "published", "active": True}, "impact": "Approves and publishes this menu to restaurant guests."}

    def menu_approve_and_publish(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        services["hospitality"].approve_menu(ctx.property_id, params["menu_id"], ctx.principal.user_id)
        return services["hospitality"].publish_menu(ctx.property_id, params["menu_id"], ctx.principal.user_id)

    register(ConfigurationAction(
        "menu.approve_and_publish", "Approve and publish a menu after an explicit confirmation.", "restaurant.menu.approve",
        menu_approval_schema, validate_menu_approval, menu_approve_and_publish, menu_combined_preview,
        restaurant_scope=True,
    ))

    # Promotions stay in the existing pending-approval workflow.
    promotion_fields = {"title": string(180, minimum=1), "description": string(1000), "starts_at": {"type": "integer", "minimum": 0}, "ends_at": {"type": "integer", "minimum": 0}}
    promotion_create_schema = _object({"restaurant_id": string(100, minimum=1), **promotion_fields}, ["restaurant_id", "title"])

    def validate_promotion_create(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        target = _restaurant(ctx, params["restaurant_id"], "restaurant.promotions.edit")
        if params.get("starts_at") is not None and params.get("ends_at") is not None and params["ends_at"] < params["starts_at"]:
            raise ValueError("Promotion end time must be after its start time.")
        return {**params, "_restaurant_name": target["name"]}

    def promotion_create_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return {"restaurant_id": params["restaurant_id"], "restaurant_name": params["_restaurant_name"], "current": None, "proposed": {key: value for key, value in params.items() if key in promotion_fields}, "impact": "Creates a promotion pending approval; it is not published."}

    def promotion_create(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["hospitality"].create_promotion(ctx.property_id, params["restaurant_id"], {key: value for key, value in params.items() if key in promotion_fields}, actor_user_id=ctx.principal.user_id)

    register(ConfigurationAction(
        "promotion.create_draft", "Create a restaurant promotion draft pending approval.", "restaurant.promotions.edit",
        promotion_create_schema, validate_promotion_create, promotion_create, promotion_create_preview, restaurant_scope=True,
    ))

    promotion_update_schema = _object({"restaurant_id": string(100, minimum=1), "promotion_id": string(100, minimum=1), "changes": _object(promotion_fields)}, ["restaurant_id", "promotion_id", "changes"])

    def validate_promotion_update(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        _restaurant(ctx, params["restaurant_id"], "restaurant.promotions.edit")
        if services["hospitality"].restaurant_id_for_promotion(ctx.property_id, params["promotion_id"]) != params["restaurant_id"]:
            raise ValueError("Promotion is not in the assigned restaurant.")
        current = next((item for item in services["hospitality"].restaurant_promotions(ctx.property_id, params["restaurant_id"]) if item["promotion_id"] == params["promotion_id"]), None)
        if not current or not params["changes"]:
            raise ValueError("Promotion not found or no fields were supplied.")
        starts = params["changes"].get("starts_at", current.get("starts_at"))
        ends = params["changes"].get("ends_at", current.get("ends_at"))
        if starts is not None and ends is not None and ends < starts:
            raise ValueError("Promotion end time must be after its start time.")
        return {**params, "_current": current}

    def promotion_update_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = params["_current"]
        return {"restaurant_id": params["restaurant_id"], "current": {key: current.get(key) for key in params["changes"]}, "proposed": params["changes"], "impact": "Updates this promotion and returns it to pending approval."}

    def promotion_update(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["hospitality"].update_promotion(ctx.property_id, params["promotion_id"], params["changes"], actor_user_id=ctx.principal.user_id)

    register(ConfigurationAction(
        "promotion.update", "Update a promotion in an assigned restaurant.", "restaurant.promotions.edit",
        promotion_update_schema, validate_promotion_update, promotion_update, promotion_update_preview, restaurant_scope=True,
    ))

    promotion_approval_schema = _object({"restaurant_id": string(100, minimum=1), "promotion_id": string(100, minimum=1)}, ["restaurant_id", "promotion_id"])

    def validate_promotion_approval(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        _restaurant(ctx, params["restaurant_id"], "restaurant.promotions.approve")
        if services["hospitality"].restaurant_id_for_promotion(ctx.property_id, params["promotion_id"]) != params["restaurant_id"]:
            raise ValueError("Promotion is not in the assigned restaurant.")
        current = next((item for item in services["hospitality"].restaurant_promotions(ctx.property_id, params["restaurant_id"]) if item["promotion_id"] == params["promotion_id"]), None)
        if not current:
            raise ValueError("Promotion not found.")
        return {**params, "_current": current}

    def promotion_approval_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return {"restaurant_id": params["restaurant_id"], "current": {"status": params["_current"].get("status")}, "proposed": {"status": "approved"}, "impact": "Approves this promotion. Publishing is a separate confirmed action."}

    register(ConfigurationAction(
        "promotion.approve", "Approve a promotion for its separate publish workflow.", "restaurant.promotions.approve",
        promotion_approval_schema, validate_promotion_approval,
        lambda ctx, params: services["hospitality"].approve_promotion(ctx.property_id, params["promotion_id"], ctx.principal.user_id),
        promotion_approval_preview, restaurant_scope=True,
    ))

    def promotion_publish_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        current = params["_current"]
        return {"restaurant_id": params["restaurant_id"], "current": {"status": current.get("status")}, "proposed": {"status": "published"}, "impact": "Publishes this approved promotion to restaurant guests."}

    register(ConfigurationAction(
        "promotion.publish", "Publish an approved promotion to restaurant guests.", "restaurant.promotions.approve",
        promotion_approval_schema, validate_promotion_approval,
        lambda ctx, params: services["hospitality"].publish_promotion(ctx.property_id, params["promotion_id"], ctx.principal.user_id),
        promotion_publish_preview, restaurant_scope=True,
    ))

    def promotion_combined_preview(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        target = _restaurant(ctx, params["restaurant_id"], "restaurant.promotions.approve")
        return {"restaurant_id": params["restaurant_id"], "restaurant_name": target["name"], "current": {"status": params["_current"].get("status")}, "proposed": {"status": "published"}, "impact": "Approves and publishes this promotion to restaurant guests."}

    def promotion_approve_and_publish(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        services["hospitality"].approve_promotion(ctx.property_id, params["promotion_id"], ctx.principal.user_id)
        return services["hospitality"].publish_promotion(ctx.property_id, params["promotion_id"], ctx.principal.user_id)

    register(ConfigurationAction(
        "promotion.approve_and_publish", "Approve and publish a promotion after explicit confirmation.", "restaurant.promotions.approve",
        promotion_approval_schema, validate_promotion_approval, promotion_approve_and_publish, promotion_combined_preview,
        restaurant_scope=True,
    ))

    # Admin-only knowledge content stays as an unpublished draft until the existing review workflow.
    knowledge_schema = _object({"title": string(200, minimum=1), "content": string(4000, minimum=1), "category": string(80)}, ["title", "content"])

    def validate_knowledge(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        category = params.get("category", "Other")
        if category not in services["knowledge_categories"]:
            raise ValueError("Choose a supported knowledge category.")
        return {**params, "category": category}

    register(ConfigurationAction(
        "knowledge.create_draft", "Create an unpublished property knowledge draft.", "knowledge.edit",
        knowledge_schema, validate_knowledge,
        lambda ctx, params: services["knowledge_management"].create_draft(ctx.property_id, params["title"], params["content"], params["category"], ctx.principal.user_id),
        lambda ctx, params: {"current": None, "proposed": params, "impact": "Creates an Admin Only knowledge draft for review; it is not published."},
    ))

    faq_schema = _object({"question": string(500, minimum=1), "answer": string(2000, minimum=1) }, ["question", "answer"])

    def create_faq(ctx: ActionContext, params: dict[str, Any]) -> dict[str, Any]:
        return services["operations"].save_knowledge(ctx.property_id, {"kind": "faq", "question": params["question"], "answer": params["answer"], "enabled": False})

    register(ConfigurationAction(
        "faq.create", "Create a disabled FAQ draft for property review.", "knowledge.edit",
        faq_schema, validate_empty_service, create_faq,
        lambda ctx, params: {"current": None, "proposed": params, "impact": "Creates an unpublished FAQ draft for review."},
    ))
