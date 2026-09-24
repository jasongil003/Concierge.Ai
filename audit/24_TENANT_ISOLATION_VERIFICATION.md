# 24 — Tenant isolation verification

Status: **FIXED AND VERIFIED** for the tested host, guest-session, admin URL, and global-admin surfaces.

Two properties (`hotel-a`, `hotel-b`) are created in regression fixtures with distinct hostnames. An unrecognized host is denied unless the explicit development override `ALLOW_BODY_PROPERTY_SELECTION=true` is set. A recognized hostname is authoritative and a conflicting body/query property identifier is rejected. Guest sessions remain bound to their stored property. Admin property paths are checked against the authenticated principal and server-side role permissions before route execution.

Verified cases:

- `test_unknown_host_cannot_select_property`
- `test_hotel_a_host_cannot_select_hotel_b`
- `test_hotel_a_guest_cannot_access_hotel_b_session`
- `test_hotel_a_admin_cannot_access_hotel_b_without_permission`
- `test_super_admin_can_access_authorized_global_resource`

Property-scoped services already bind resource IDs to `property_id` in SQL queries; existing catalog, zone, conversation, knowledge, reporting, provider, and analytics tests ran as part of the 126-test backend suite. The central admin middleware covers all `/api/admin/properties/{property_id}/...` routes, including guessed IDs and export URLs.

Residual risk: this pass does not claim an exhaustive external penetration test across every encoded/ambiguous HTTP variant. Production provisioning must assign every guest-facing property a unique trusted domain. Body selection remains enabled only in explicit test/development configuration.
