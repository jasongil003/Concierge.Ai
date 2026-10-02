"""Validated, property-scoped page configuration for the guest experience.

The registry is deliberately small for Milestone 1. A stored design remains part
of its PropertyRecord, so ownership is enforced by the property store and the
existing authenticated admin routes rather than by a client supplied owner ID.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit


COMPONENT_REGISTRY: dict[str, dict[str, Any]] = {
    "heading": {"label": "Heading", "group": "Basic", "icon": "H", "defaults": {"text": "A heading", "level": 2, "alignment": "left"}, "fields": [{"name": "text", "label": "Text"}, {"name": "level", "label": "Level", "control": "select", "options": [1, 2, 3, 4, 5, 6]}, {"name": "alignment", "label": "Alignment", "control": "select", "options": ["left", "center", "right"]}]},
    "text": {"label": "Text", "group": "Basic", "icon": "¶", "defaults": {"content": "Add your text here.", "alignment": "left"}, "fields": [{"name": "content", "label": "Content", "control": "textarea"}, {"name": "alignment", "label": "Alignment", "control": "select", "options": ["left", "center", "right"]}]},
    "image": {"label": "Image", "group": "Basic", "icon": "▧", "defaults": {"url": "", "alt": "", "fit": "cover"}, "fields": [{"name": "url", "label": "Image URL"}, {"name": "alt", "label": "Alt text"}, {"name": "fit", "label": "Fit", "control": "select", "options": ["cover", "contain"]}]},
    "button": {"label": "Button", "group": "Basic", "icon": "↗", "defaults": {"label": "Explore", "icon": "", "style": "primary", "size": "medium", "action": {"type": "internal_page", "page_id": "explore"}}, "fields": [{"name": "label", "label": "Label"}]},
    "divider": {"label": "Divider", "group": "Basic", "icon": "—", "defaults": {}, "fields": []},
    "spacer": {"label": "Spacer", "group": "Basic", "icon": "↕", "defaults": {"size": "medium"}, "fields": []},
    "hero": {"label": "Hero", "group": "Layout", "icon": "▰", "defaults": {"eyebrow": "WELCOME", "headline": "How can we help with your stay?", "description": "Your personal concierge is here to help.", "alignment": "left", "height": "large", "buttons": []}, "fields": [{"name": "eyebrow", "label": "Eyebrow"}, {"name": "headline", "label": "Headline"}, {"name": "description", "label": "Description", "control": "textarea"}, {"name": "alignment", "label": "Alignment", "control": "select", "options": ["left", "center", "right"]}]},
    "banner": {"label": "Banner", "group": "Layout", "icon": "▣", "defaults": {"eyebrow": "", "headline": "", "description": "", "image_url": "", "alt": ""}, "fields": [{"name": "eyebrow", "label": "Eyebrow"}, {"name": "headline", "label": "Headline"}, {"name": "description", "label": "Description", "control": "textarea"}, {"name": "image_url", "label": "Image URL"}, {"name": "alt", "label": "Image alt text"}]},
    "card_grid": {"label": "Card Grid", "group": "Layout", "icon": "▦", "defaults": {"title": "", "source": "recommendations", "limit": 4, "columns": 2}, "fields": [{"name": "title", "label": "Title"}, {"name": "source", "label": "Property data", "control": "select", "options": ["recommendations", "restaurants", "facilities", "services", "promotions", "events"]}, {"name": "limit", "label": "Items to show", "control": "number", "min": 1, "max": 12}]},
    "carousel": {"label": "Carousel", "group": "Layout", "icon": "▤", "defaults": {"title": "", "source": "recommendations", "limit": 6, "columns": 2}, "fields": [{"name": "title", "label": "Title"}, {"name": "source", "label": "Property data", "control": "select", "options": ["recommendations", "restaurants", "facilities", "services", "promotions", "events"]}, {"name": "limit", "label": "Items to show", "control": "number", "min": 1, "max": 12}]},
    "container": {"label": "Container", "group": "Layout", "icon": "▱", "defaults": {"content": "Add a short introduction.", "width": "contained", "alignment": "left"}, "fields": [{"name": "content", "label": "Content", "control": "textarea"}, {"name": "width", "label": "Width", "control": "select", "options": ["contained", "wide", "full"]}, {"name": "alignment", "label": "Alignment", "control": "select", "options": ["left", "center", "right"]}]},
    "columns": {"label": "Columns", "group": "Layout", "icon": "▥", "defaults": {"primary": "First column content", "secondary": "Second column content", "columns": 2}, "fields": [{"name": "primary", "label": "First column", "control": "textarea"}, {"name": "secondary", "label": "Second column", "control": "textarea"}, {"name": "columns", "label": "Columns", "control": "select", "options": [1, 2, 3, 4]}]},
    "quick_actions": {"label": "Quick Actions", "group": "Hotel", "icon": "✦", "defaults": {"title": "Quick actions", "items": []}, "fields": [{"name": "title", "label": "Title"}]},
    "restaurant": {"label": "Restaurant", "group": "Hotel", "icon": "♨", "defaults": {"title": "Restaurants", "source": "restaurants", "limit": 4, "columns": 2}, "fields": [{"name": "title", "label": "Title"}]},
    "room_service": {"label": "Room Service", "group": "Hotel", "icon": "♧", "defaults": {"title": "Room service", "source": "services", "limit": 4, "columns": 2}, "fields": [{"name": "title", "label": "Title"}]},
    "housekeeping": {"label": "Housekeeping", "group": "Hotel", "icon": "✧", "defaults": {"title": "Housekeeping", "source": "services", "limit": 4, "columns": 2}, "fields": [{"name": "title", "label": "Title"}]},
    "transportation": {"label": "Transportation", "group": "Hotel", "icon": "⌖", "defaults": {"title": "Transportation", "source": "services", "limit": 4, "columns": 2}, "fields": [{"name": "title", "label": "Title"}]},
    "amenities": {"label": "Amenities", "group": "Hotel", "icon": "◈", "defaults": {"title": "Amenities", "source": "facilities", "limit": 4, "columns": 2}, "fields": [{"name": "title", "label": "Title"}]},
    "promotions": {"label": "Promotions", "group": "Hotel", "icon": "%", "defaults": {"title": "Special offers", "source": "promotions", "limit": 4, "columns": 2}, "fields": [{"name": "title", "label": "Title"}]},
    "events": {"label": "Events", "group": "Hotel", "icon": "◷", "defaults": {"title": "Events", "source": "events", "limit": 4, "columns": 2}, "fields": [{"name": "title", "label": "Title"}]},
    "concierge_composer": {"label": "Concierge Composer", "group": "AI & Concierge", "icon": "◉", "defaults": {"placeholder": "Ask your concierge...", "enabled": True}, "fields": [{"name": "placeholder", "label": "Placeholder"}, {"name": "enabled", "label": "Enabled", "control": "checkbox"}]},
    "ai_suggestion": {"label": "AI Suggestion", "group": "AI & Concierge", "icon": "✧", "defaults": {"title": "Suggested for you", "content": "Add a property-configured suggestion."}, "fields": [{"name": "title", "label": "Title"}, {"name": "content", "label": "Suggestion", "control": "textarea"}]},
    "header": {"label": "Header", "group": "Navigation", "icon": "▤", "defaults": {"show_menu": True, "show_logo": True, "show_hotel_name": True, "show_concierge_label": True}, "fields": []},
    "bottom_navigation": {"label": "Bottom Navigation", "group": "Navigation", "icon": "▥", "defaults": {"show_labels": True, "position": "fixed", "height": "medium", "icon_size": "medium", "safe_area_padding": True, "items": []}, "fields": []},
}
COMPONENT_TYPES = frozenset(COMPONENT_REGISTRY)
ACTION_TYPES = {
    "none", "prompt", "internal_page", "external_url", "phone", "email", "map",
    "service_request", "resource", "restaurant", "restaurant_menu", "room_service",
    "housekeeping", "transportation", "promotion", "event", "concierge",
}
STANDARD_PAGE_IDS = {"home", "explore", "requests", "stay", "concierge"}
RESERVED_SLUGS = {
    "admin", "api", "assets", "static", "login", "logout", "health", "docs",
    "openapi.json", "guest", "auth", "session", "sessions", "requests", "explore",
    "stay", "concierge", "home",
}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){0,5}$")
ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^\+?[0-9(). -]{5,32}$")
IMAGE_DATA_RE = re.compile(r"^data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]{1,700000}$", re.I)


def default_guest_pages() -> list[dict[str, Any]]:
    """A generic, removable default schema for the guest Home."""
    navigation_items = [
        {"id": f"nav-{item['page_id']}", "label": item["label"], "icon": item["icon"], "enabled": item["enabled"], "action": {"type": "internal_page", "page_id": item["page_id"]}}
        for item in default_navigation()
    ]
    sections = [
        _section("header", "header", "Header", 0),
        _section("hero", "hero", "Welcome", 1),
        _section("quick-actions", "quick_actions", "Quick actions", 2),
        _section("property-suggestions", "card_grid", "Suggested for you", 3, source="recommendations"),
        _section("concierge-composer", "concierge_composer", "Ask the concierge", 4),
        _section("bottom-navigation", "bottom_navigation", "Bottom Navigation", 5, show_labels=True, position="fixed", height="medium", icon_size="medium", safe_area_padding=True, items=navigation_items),
    ]
    pages = [{"id": "home", "type": "guest_home", "version": 2, "name": "Home", "slug": "/", "enabled": True, "navigation": True, "sections": sections}]
    # These IDs describe existing app routes; the Milestone 1 editor only edits Home.
    for page_id, page_name in (("explore", "Explore"), ("requests", "Requests"), ("stay", "My Stay"), ("concierge", "Concierge")):
        pages.append({"id": page_id, "type": "guest_page", "version": 1, "name": page_name, "slug": f"/{page_id}", "enabled": True, "navigation": True, "sections": []})
    return pages


def default_navigation() -> list[dict[str, Any]]:
    return [
        {"page_id": page_id, "label": label, "icon": icon, "enabled": True}
        for page_id, label, icon in (
            ("home", "Home", "home"), ("explore", "Explore", "explore"),
            ("requests", "Requests", "requests"), ("stay", "My Stay", "stay"),
            ("concierge", "Concierge", "concierge"),
        )
    ]


def _section(section_id: str, component_type: str, title: str, order: int, **properties: Any) -> dict[str, Any]:
    return {"id": section_id, "type": component_type, "title": title, "enabled": True, "order": order, "properties": properties}


def validate_guest_pages(raw_pages: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_pages, list) or not 1 <= len(raw_pages) <= 12:
        raise ValueError("Guest experience must contain between 1 and 12 pages.")
    pages: list[dict[str, Any]] = []
    page_ids: set[str] = set()
    slugs: set[str] = set()
    for raw in raw_pages:
        if not isinstance(raw, dict):
            raise ValueError("Each guest page must be an object.")
        if set(raw) - {"id", "type", "version", "name", "slug", "enabled", "navigation", "sections"}:
            raise ValueError("Unsupported guest page field.")
        page_id = _safe_id(raw.get("id"), "Page ID")
        name = _string(raw.get("name"), 60, "Page name")
        if page_id in page_ids:
            raise ValueError("Guest page IDs must be unique.")
        page_ids.add(page_id)
        slug = _string(raw.get("slug", "/" if page_id == "home" else page_id), 80, "Page slug")
        if page_id == "home":
            slug = "/"
        else:
            slug = slug.strip("/").lower()
            if not SLUG_RE.fullmatch(slug) or (slug in RESERVED_SLUGS and slug != page_id) or slug in slugs:
                raise ValueError("Page slug is invalid, reserved, or already in use.")
            slugs.add(slug)
            slug = f"/{slug}"
        enabled = _boolean(raw.get("enabled", True), "Page enabled")
        navigation = _boolean(raw.get("navigation", page_id in STANDARD_PAGE_IDS), "Page navigation")
        sections_raw = raw.get("sections", [])
        if not isinstance(sections_raw, list) or len(sections_raw) > 60:
            raise ValueError("A page can contain up to 60 sections.")
        sections = [validate_section(section, index) for index, section in enumerate(sections_raw)]
        section_ids = [section["id"] for section in sections]
        orders = [section["order"] for section in sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("Section IDs must be unique within a page.")
        if len(orders) != len(set(orders)):
            raise ValueError("Section order values must be unique.")
        sections.sort(key=lambda section: section["order"])
        for order, section in enumerate(sections):
            section["order"] = order
        pages.append({
            "id": page_id,
            "type": _string(raw.get("type", "guest_home" if page_id == "home" else "guest_page"), 40, "Page type"),
            "version": _integer(raw.get("version", 1), 1, 100, "Page schema version"),
            "name": name,
            "slug": slug,
            "enabled": enabled,
            "navigation": navigation,
            "sections": sections,
        })
    if "home" not in page_ids:
        raise ValueError("A guest experience must include the home page.")
    enabled_page_ids = {page["id"] for page in pages if page["enabled"]}
    for page in pages:
        for section in page["sections"]:
            for action in _actions_in(section.get("properties", {})):
                if action.get("type") in {"internal_page", "concierge"} and action.get("page_id") not in enabled_page_ids:
                    raise ValueError("Internal page actions must reference an enabled page.")
    return pages


def validate_navigation(raw: Any, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) > 12:
        raise ValueError("Navigation can contain up to 12 items.")
    allowed_pages = {page["id"] for page in pages if page["enabled"]}
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Navigation items must be objects.")
        page_id = _safe_id(item.get("page_id"), "Navigation page")
        label = _string(item.get("label"), 40, "Navigation label")
        if page_id not in allowed_pages or page_id in seen:
            raise ValueError("Navigation items must reference unique enabled pages.")
        seen.add(page_id)
        result.append({"page_id": page_id, "label": label, "icon": _string(item.get("icon", ""), 24, "Navigation icon"), "enabled": _boolean(item.get("enabled", True), "Navigation enabled")})
    return result


def validate_section(raw: Any, index: int = 0) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Guest sections must be objects.")
    if set(raw) - {"id", "type", "title", "enabled", "order", "properties", "responsive", "animation", "appearance", "layout"}:
        raise ValueError("Unsupported guest section field.")
    section_id = _safe_id(raw.get("id"), "Section ID")
    component_type = raw.get("type")
    if component_type not in COMPONENT_REGISTRY:
        raise ValueError("Section uses an unsupported component or identifier.")
    enabled = _boolean(raw.get("enabled", True), "Section enabled")
    order = _integer(raw.get("order", index), 0, 10000, "Section order")
    properties = raw.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("Section properties must be an object.")
    properties = validate_component_properties(component_type, properties)
    return {
        "id": section_id,
        "type": component_type,
        "title": _string(raw.get("title", COMPONENT_REGISTRY[component_type]["label"]), 80, "Section title"),
        "enabled": enabled,
        "order": order,
        "properties": properties,
        "responsive": validate_responsive(raw.get("responsive", {})),
        "animation": validate_animation(raw.get("animation", {})),
        "appearance": validate_appearance(raw.get("appearance", {})),
        "layout": validate_layout(raw.get("layout", {})),
    }


def validate_component_properties(component_type: str, raw: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "hero": {"eyebrow", "headline", "description", "alignment", "image_url", "alt", "height", "buttons"},
        "heading": {"text", "headline", "level", "alignment"},
        "text": {"content", "body", "description", "alignment"},
        "image": {"url", "alt", "fit"},
        "button": {"label", "icon", "style", "size", "action"},
        "divider": set(), "spacer": {"size"},
        "quick_actions": {"title", "items"},
        "card_grid": {"source", "limit", "title", "columns", "resource_id", "items"},
        "carousel": {"source", "limit", "title", "columns", "resource_id"},
        "container": {"content", "width", "alignment"},
        "columns": {"primary", "secondary", "columns"},
        "restaurant": {"title", "source", "limit", "columns", "resource_id"},
        "room_service": {"title", "source", "limit", "columns", "resource_id"},
        "housekeeping": {"title", "source", "limit", "columns", "resource_id"},
        "transportation": {"title", "source", "limit", "columns", "resource_id"},
        "amenities": {"title", "source", "limit", "columns", "resource_id"},
        "promotions": {"title", "source", "limit", "columns", "resource_id"},
        "events": {"title", "source", "limit", "columns", "resource_id"},
        "banner": {"eyebrow", "headline", "description", "image_url", "alt", "height", "title", "action"},
        "concierge_composer": {"enabled", "placeholder", "position", "show_microphone", "show_attachments"},
        "ai_suggestion": {"title", "content"},
        "header": {"show_menu", "show_brand", "show_logo", "show_hotel_name", "show_concierge_label", "menu_action"},
        "bottom_navigation": {"show_labels", "position", "height", "icon_size", "safe_area_padding", "items"},
    }[component_type]
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError("Unsupported settings for this component.")
    p: dict[str, Any] = {}
    registry_defaults = COMPONENT_REGISTRY[component_type]["defaults"]
    for key in ("eyebrow", "headline", "description", "text", "content", "label", "title", "placeholder", "alt", "url", "image_url", "alignment", "fit", "source", "resource_id", "icon", "style", "size", "position", "height", "width", "primary", "secondary"):
        if key not in raw:
            continue
        max_lengths = {"description": 600, "content": 3000, "url": 700000, "image_url": 700000, "alt": 180, "headline": 160, "placeholder": 120, "label": 48, "title": 80, "eyebrow": 80, "resource_id": 64}
        p[key] = _string(raw[key], max_lengths.get(key, 80), key)
    if component_type == "hero":
        p.setdefault("eyebrow", registry_defaults["eyebrow"])
        p.setdefault("headline", registry_defaults["headline"])
        p.setdefault("description", registry_defaults["description"])
    if component_type == "heading":
        p["text"] = _string(raw.get("text", raw.get("headline", registry_defaults["text"])), 160, "Heading text")
        p["level"] = _integer(raw.get("level", registry_defaults["level"]), 1, 6, "Heading level")
    if component_type == "text":
        p["content"] = _string(raw.get("content", raw.get("body", raw.get("description", registry_defaults["content"]))), 3000, "Text content")
    if component_type in {"hero", "heading", "text", "container"}:
        p["alignment"] = raw.get("alignment", registry_defaults.get("alignment", "left"))
        if p["alignment"] not in {"left", "center", "right"}:
            raise ValueError("Alignment must be left, center, or right.")
    if component_type in {"hero", "banner"}:
        if "height" in p and p["height"] not in {"small", "medium", "large"}:
            raise ValueError("Unsupported hero height.")
    if component_type == "container" and p.get("width", "contained") not in {"contained", "wide", "full"}:
        raise ValueError("Unsupported container width.")
    if component_type == "image":
        p.setdefault("url", "")
        p.setdefault("alt", "")
        p["fit"] = raw.get("fit", "cover")
        if p["fit"] not in {"cover", "contain"}:
            raise ValueError("Unsupported image fit.")
        if p["url"] and not is_safe_image_url(p["url"]):
            raise ValueError("Image must use HTTPS, a same-origin path, or a supported image upload.")
    if component_type == "button":
        p["label"] = _string(raw.get("label", registry_defaults["label"]), 48, "Button label")
        p["icon"] = _string(raw.get("icon", ""), 24, "Button icon")
        p["style"] = raw.get("style", "primary")
        p["size"] = raw.get("size", "medium")
        if p["style"] not in {"primary", "secondary", "outline", "text"} or p["size"] not in {"small", "medium", "large"}:
            raise ValueError("Unsupported button appearance.")
        p["action"] = validate_action(raw.get("action", registry_defaults["action"]))
    if component_type == "hero":
        p["height"] = raw.get("height", "large")
        p["buttons"] = _validate_buttons(raw.get("buttons", []))
        if raw.get("image_url") and not is_safe_image_url(p["image_url"]):
            raise ValueError("Image must use HTTPS, a same-origin path, or a supported image upload.")
    if component_type == "quick_actions":
        p["title"] = _string(raw.get("title", registry_defaults["title"]), 60, "Quick actions title")
        if "items" in raw:
            if not isinstance(raw["items"], list) or len(raw["items"]) > 12:
                raise ValueError("Quick actions can contain up to 12 items.")
            p["items"] = [validate_quick_action(item) for item in raw["items"]]
            ids = [item["id"] for item in p["items"]]
            if len(ids) != len(set(ids)):
                raise ValueError("Quick action IDs must be unique within a section.")
    collection_sources = {"card_grid", "carousel", "restaurant", "room_service", "housekeeping", "transportation", "amenities", "promotions", "events"}
    if component_type in collection_sources:
        default_source = registry_defaults.get("source", "recommendations")
        p["source"] = raw.get("source", default_source)
        if p["source"] not in {"restaurants", "facilities", "events", "promotions", "recommendations", "services"}:
            raise ValueError("Unsupported property data source.")
        p["limit"] = _integer(raw.get("limit", registry_defaults.get("limit", 4)), 1, 12, "Collection size")
        p["title"] = _string(raw.get("title", ""), 80, "Collection title")
        p["columns"] = _integer(raw.get("columns", registry_defaults.get("columns", 2)), 1, 4, "Collection columns")
        if "resource_id" in raw:
            p["resource_id"] = _safe_id(raw["resource_id"], "Resource ID")
        if component_type == "card_grid" and "items" in raw:
            if not isinstance(raw["items"], list) or len(raw["items"]) > 12:
                raise ValueError("A card grid can contain up to 12 cards.")
            p["items"] = [validate_card_item(item) for item in raw["items"]]
            ids = [item["id"] for item in p["items"]]
            if len(ids) != len(set(ids)):
                raise ValueError("Card IDs must be unique within a section.")
    if component_type == "banner":
        p["headline"] = _string(raw.get("headline", raw.get("title", "")), 160, "Banner headline")
        p["description"] = _string(raw.get("description", ""), 600, "Banner description")
        p["eyebrow"] = _string(raw.get("eyebrow", ""), 80, "Banner eyebrow")
        p["alt"] = _string(raw.get("alt", ""), 180, "Image alt text")
        p["image_url"] = _string(raw.get("image_url", ""), 700000, "Banner image")
        if p["image_url"] and not is_safe_image_url(p["image_url"]):
            raise ValueError("Image must use HTTPS, a same-origin path, or a supported image upload.")
        if "action" in raw:
            p["action"] = validate_action(raw["action"])
    if component_type == "spacer" and raw.get("size", "medium") not in {"small", "medium", "large"}:
        raise ValueError("Unsupported spacer size.")
    if component_type == "columns":
        p["primary"] = _string(raw.get("primary", registry_defaults["primary"]), 1200, "First column")
        p["secondary"] = _string(raw.get("secondary", registry_defaults["secondary"]), 1200, "Second column")
        p["columns"] = _integer(raw.get("columns", 2), 1, 4, "Column count")
    if component_type == "concierge_composer":
        p["enabled"] = _boolean(raw.get("enabled", True), "Composer enabled")
        p["placeholder"] = _string(raw.get("placeholder", registry_defaults["placeholder"]), 120, "Composer placeholder")
    if component_type == "ai_suggestion":
        p["title"] = _string(raw.get("title", registry_defaults["title"]), 80, "Suggestion title")
        p["content"] = _string(raw.get("content", registry_defaults["content"]), 500, "Suggestion content")
    if component_type == "header":
        p["show_menu"] = _boolean(raw.get("show_menu", True), "Header menu visibility")
        p["show_logo"] = _boolean(raw.get("show_logo", raw.get("show_brand", True)), "Header logo visibility")
        p["show_hotel_name"] = _boolean(raw.get("show_hotel_name", raw.get("show_brand", True)), "Header property name visibility")
        p["show_concierge_label"] = _boolean(raw.get("show_concierge_label", True), "Header concierge label visibility")
        if "menu_action" in raw:
            p["menu_action"] = validate_action(raw["menu_action"])
    if component_type == "bottom_navigation":
        p["show_labels"] = _boolean(raw.get("show_labels", True), "Navigation labels")
        p["position"] = raw.get("position", "fixed")
        if p["position"] not in {"fixed", "inline"}:
            raise ValueError("Bottom navigation position must be fixed or inline.")
        p["height"] = raw.get("height", "medium")
        if p["height"] not in {"compact", "medium", "tall"}:
            raise ValueError("Unsupported bottom navigation height.")
        p["icon_size"] = raw.get("icon_size", "medium")
        if p["icon_size"] not in {"small", "medium", "large"}:
            raise ValueError("Unsupported navigation icon size.")
        p["safe_area_padding"] = _boolean(raw.get("safe_area_padding", True), "Safe area padding")
        raw_items = raw.get("items", [])
        if not isinstance(raw_items, list) or len(raw_items) > 12:
            raise ValueError("Navigation can contain up to 12 items.")
        p["items"] = [validate_navigation_item(item) for item in raw_items]
        ids = [item["id"] for item in p["items"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Navigation item IDs must be unique within a section.")
    return p


def _validate_buttons(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) > 2:
        raise ValueError("A hero can contain up to two buttons.")
    result = []
    for item in raw:
        if not isinstance(item, dict) or set(item) - {"id", "label", "icon", "style", "size", "enabled", "action"}:
            raise ValueError("Unsupported button setting.")
        style = item.get("style", "primary")
        size = item.get("size", "medium")
        if style not in {"primary", "secondary", "outline", "text"} or size not in {"small", "medium", "large"}:
            raise ValueError("Unsupported button appearance.")
        result.append({
            "id": _safe_id(item.get("id", f"hero-cta-{len(result) + 1}"), "Button ID"),
            "label": _string(item.get("label", "Explore"), 48, "Button label"),
            "icon": _string(item.get("icon", ""), 24, "Button icon"),
            "style": style,
            "size": size,
            "enabled": _boolean(item.get("enabled", True), "Button enabled"),
            "action": validate_action(item.get("action", {"type": "internal_page", "page_id": "explore"})),
        })
    return result


def validate_responsive(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) - {"desktop", "tablet", "phone", "mobile", "columns", "mobile_behavior"}:
        raise ValueError("Unsupported responsive settings.")
    result: dict[str, Any] = {}
    for key in ("desktop", "tablet", "phone", "mobile"):
        if key in raw:
            result[key] = _boolean(raw[key], f"Responsive {key}")
    if "columns" in raw:
        result["columns"] = _integer(raw["columns"], 1, 4, "Responsive columns")
    if "mobile_behavior" in raw:
        behavior = raw["mobile_behavior"]
        if behavior not in {"stack", "scroll", "hide"}:
            raise ValueError("Unsupported mobile behavior.")
        result["mobile_behavior"] = behavior
    return result


def validate_animation(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) - {"entrance", "duration", "delay", "trigger", "repeat", "interaction"}:
        raise ValueError("Unsupported animation settings.")
    entrance = raw.get("entrance", "none")
    duration = raw.get("duration", "normal")
    trigger = raw.get("trigger", "page_load")
    repeat = raw.get("repeat", "once")
    interaction = raw.get("interaction", "none")
    if entrance not in {"none", "fade", "fade_up", "fade_down", "slide_left", "slide_right", "scale"}:
        raise ValueError("Unsupported entrance animation.")
    if duration not in {"fast", "normal", "slow"}:
        raise ValueError("Unsupported animation duration.")
    if trigger not in {"page_load", "enter_viewport"} or repeat not in {"once", "each"}:
        raise ValueError("Unsupported animation behavior.")
    if interaction not in {"none", "lift", "scale", "shadow"}:
        raise ValueError("Unsupported interaction effect.")
    return {"entrance": entrance, "duration": duration, "delay": _integer(raw.get("delay", 0), 0, 500, "Animation delay"), "trigger": trigger, "repeat": repeat, "interaction": interaction}


def validate_appearance(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) - {"text_color", "background_color", "active_color", "border_color", "overlay_color", "overlay_opacity", "radius", "shadow"}:
        raise ValueError("Unsupported component style settings.")
    result: dict[str, Any] = {}
    for key in ("text_color", "background_color", "active_color", "border_color", "overlay_color"):
        if key in raw:
            color = _string(raw[key], 7, f"{key.replace('_', ' ').title()} color")
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("Component colors must use six-digit hex values.")
            result[key] = color
    if "overlay_opacity" in raw:
        result["overlay_opacity"] = _integer(raw["overlay_opacity"], 0, 100, "Overlay opacity")
    if "radius" in raw:
        if raw["radius"] not in {"none", "small", "medium", "large", "pill"}:
            raise ValueError("Unsupported component corner radius.")
        result["radius"] = raw["radius"]
    if "shadow" in raw:
        if raw["shadow"] not in {"none", "subtle", "raised"}:
            raise ValueError("Unsupported component shadow.")
        result["shadow"] = raw["shadow"]
    return result


def validate_layout(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) - {"width", "height", "spacing", "alignment"}:
        raise ValueError("Unsupported component layout settings.")
    result: dict[str, Any] = {}
    if "width" in raw:
        if raw["width"] not in {"contained", "wide", "full"}:
            raise ValueError("Unsupported component width.")
        result["width"] = raw["width"]
    if "height" in raw:
        if raw["height"] not in {"small", "medium", "large", "full"}:
            raise ValueError("Unsupported component height.")
        result["height"] = raw["height"]
    if "spacing" in raw:
        if raw["spacing"] not in {"small", "medium", "large"}:
            raise ValueError("Unsupported component spacing.")
        result["spacing"] = raw["spacing"]
    if "alignment" in raw:
        if raw["alignment"] not in {"left", "center", "right"}:
            raise ValueError("Unsupported component alignment.")
        result["alignment"] = raw["alignment"]
    return result


def validate_quick_action(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) - {"id", "label", "description", "icon", "enabled", "action", "style_mode", "appearance"}:
        raise ValueError("Quick action entries must be objects.")
    result = {
        "id": _safe_id(raw.get("id", "action"), "Quick action ID"),
        "label": _string(raw.get("label", ""), 48, "Quick action label"),
        "description": _string(raw.get("description", ""), 140, "Quick action description"),
        "icon": _string(raw.get("icon", ""), 24, "Quick action icon"),
        "enabled": _boolean(raw.get("enabled", True), "Quick action enabled"),
        "action": validate_action(raw.get("action", {"type": "prompt", "prompt": raw.get("prompt", "")})),
    }
    result["style_mode"] = raw.get("style_mode", "section")
    if result["style_mode"] not in {"section", "custom"}:
        raise ValueError("Quick action style must inherit from its section or be custom.")
    if "appearance" in raw:
        result["appearance"] = validate_appearance(raw["appearance"])
    return result


def validate_navigation_item(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) - {"id", "label", "icon", "enabled", "action"}:
        raise ValueError("Unsupported navigation item setting.")
    return {
        "id": _safe_id(raw.get("id", "navigation-item"), "Navigation item ID"),
        "label": _string(raw.get("label", ""), 40, "Navigation label"),
        "icon": _string(raw.get("icon", ""), 24, "Navigation icon"),
        "enabled": _boolean(raw.get("enabled", True), "Navigation item enabled"),
        "action": validate_action(raw.get("action", {"type": "internal_page", "page_id": "home"})),
    }


def validate_card_item(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) - {"id", "image_url", "icon", "title", "description", "badge", "cta", "enabled", "action", "style_mode", "appearance"}:
        raise ValueError("Unsupported card setting.")
    image_url = _string(raw.get("image_url", ""), 700000, "Card image")
    if image_url and not is_safe_image_url(image_url):
        raise ValueError("Card image must use HTTPS, a same-origin path, or a supported image upload.")
    result = {
        "id": _safe_id(raw.get("id", "card"), "Card ID"),
        "image_url": image_url,
        "icon": _string(raw.get("icon", ""), 24, "Card icon"),
        "title": _string(raw.get("title", ""), 80, "Card title"),
        "description": _string(raw.get("description", ""), 300, "Card description"),
        "badge": _string(raw.get("badge", ""), 40, "Card badge"),
        "cta": _string(raw.get("cta", ""), 48, "Card CTA"),
        "enabled": _boolean(raw.get("enabled", True), "Card enabled"),
        "action": validate_action(raw.get("action", {"type": "none"})),
    }
    result["style_mode"] = raw.get("style_mode", "section")
    if result["style_mode"] not in {"section", "custom"}:
        raise ValueError("Card style must inherit from its section or be custom.")
    if "appearance" in raw:
        result["appearance"] = validate_appearance(raw["appearance"])
    return result


def validate_action(raw: Any) -> dict[str, Any]:
    """Validate existing prompt/navigation actions used by configured quick actions."""
    if not isinstance(raw, dict):
        raise ValueError("Quick action must be an object.")
    action_type = raw.get("type", "none")
    if action_type not in ACTION_TYPES:
        raise ValueError("Unsupported action type.")
    result: dict[str, Any] = {"type": action_type}
    if action_type == "prompt":
        result["prompt"] = _string(raw.get("prompt", ""), 500, "Concierge prompt")
    elif action_type == "internal_page":
        result["page_id"] = _safe_id(raw.get("page_id", "home"), "Page ID")
    elif action_type == "concierge":
        result["page_id"] = "concierge"
    elif action_type == "external_url":
        value = _string(raw.get("url", ""), 2048, "External URL")
        try:
            parts = urlsplit(value)
            port = parts.port
        except ValueError as exc:
            raise ValueError("External link must use a valid HTTP or HTTPS URL.") from exc
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or (port is not None and not 1 <= port <= 65535):
            raise ValueError("External link must use a valid HTTP or HTTPS URL.")
        result["url"] = value
        open_in = raw.get("open_in", "new_tab")
        if open_in not in {"same_tab", "new_tab"}:
            raise ValueError("External links must open in the same tab or a new tab.")
        result["open_in"] = open_in
    elif action_type == "phone":
        phone = _string(raw.get("phone", ""), 32, "Phone number")
        if not PHONE_RE.fullmatch(phone) or len(re.sub(r"\D", "", phone)) < 5:
            raise ValueError("Enter a valid phone number.")
        result["phone"] = phone
    elif action_type == "email":
        email = _string(raw.get("email", ""), 254, "Email address")
        if not EMAIL_RE.fullmatch(email):
            raise ValueError("Enter a valid email address.")
        result["email"] = email
    elif action_type in {"service_request", "room_service", "housekeeping", "transportation"}:
        result["service_id"] = _safe_id(raw.get("service_id", ""), "Service ID")
    elif action_type in {"resource", "restaurant", "restaurant_menu", "promotion", "event"}:
        kind = raw.get("resource_type") or ({"restaurant": "restaurant", "restaurant_menu": "restaurant", "promotion": "promotion", "event": "event"}.get(action_type))
        if kind not in {"restaurant", "promotion", "event", "facility"}:
            raise ValueError("Unsupported property resource action.")
        resource_id = raw.get("resource_id", raw.get("restaurant_id", ""))
        result.update(resource_type=kind, resource_id=_safe_id(resource_id, "Resource ID"))
    elif action_type == "map":
        result["destination"] = "property"
        if raw.get("url"):
            value = _string(raw["url"], 2048, "Map URL")
            try:
                parts = urlsplit(value)
                port = parts.port
            except ValueError as exc:
                raise ValueError("Map link must use a valid HTTP or HTTPS URL.") from exc
            if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or (port is not None and not 1 <= port <= 65535):
                raise ValueError("Map link must use a valid HTTP or HTTPS URL.")
            result["url"] = value
    return result


def is_safe_image_url(value: str) -> bool:
    if value.startswith("/") and not value.startswith("//"):
        return True
    if IMAGE_DATA_RE.fullmatch(value):
        return True
    parts = urlsplit(value)
    return parts.scheme == "https" and bool(parts.hostname) and not parts.username and not parts.password


def _actions_in(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"action", "menu_action"} and isinstance(child, dict):
                yield child
            else:
                yield from _actions_in(child)
    elif isinstance(value, list):
        for child in value:
            yield from _actions_in(child)


def _safe_id(value: Any, name: str = "Identifier") -> str:
    result = _string(value, 64, name)
    if not ID_RE.fullmatch(result):
        raise ValueError(f"{name} contains unsupported characters.")
    return result


def _string(value: Any, limit: int, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text.")
    value = value.strip()
    if len(value) > limit:
        raise ValueError(f"{name} must be {limit} characters or fewer.")
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false.")
    return value


def _integer(value: Any, minimum: int, maximum: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value
