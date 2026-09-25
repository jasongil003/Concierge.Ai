# Concierge.AI Manual UI Checklist

Test URL: `http://127.0.0.1:8080`

Admin URL: `http://127.0.0.1:8080/admin`

Default local credentials, unless overridden in `.env`:

- Username: `admin`
- Password: `ChangeMe123!`

Enter `Pass` or `Fail` in the Result column and add observations in Comments.

## Guest experience

| # | Check | Expected result | Result | Comments |
|---|---|---|---|---|
| G01 | Open guest page | Welcome screen loads without an error |  |  |
| G02 | Hotel menu button | Side menu opens |  |  |
| G03 | Header options button | Same side menu opens |  |  |
| G04 | Close menu button | Side menu closes |  |  |
| G05 | New conversation | Existing messages are cleared and a new session starts |  |  |
| G06 | Hotel information | Hotel information appears as an assistant message |  |  |
| G07 | Language | Language preference changes and confirmation appears |  |  |
| G08 | Accessibility | Accessibility display mode toggles |  |  |
| G09 | Privacy | Privacy guidance appears |  |  |
| G10 | Help | Concierge help guidance appears |  |  |
| G11 | Suggested prompt buttons | Every visible prompt sends its message |  |  |
| G12 | Empty composer | Send button remains disabled |  |  |
| G13 | Typed composer message | Send button becomes enabled |  |  |
| G14 | Send button | User message and assistant response appear |  |  |
| G15 | Enter key | Sends the message |  |  |
| G16 | Shift+Enter | Adds a new line without sending |  |  |
| G17 | Composer width | Text field uses most of the composer; placeholder is not vertically wrapped |  |  |
| G18 | Breakfast question | Verified breakfast hours are returned |  |  |
| G19 | Checkout question | Verified checkout time is returned |  |  |
| G20 | Pool question | Verified pool hours are returned |  |  |
| G21 | Wi-Fi request | Enabled authentication form or guidance appears |  |  |
| G22 | Wi-Fi Continue with empty fields | Validation message appears |  |  |
| G23 | Wi-Fi valid mock credentials | Authentication succeeds in mock mode |  |  |
| G24 | Dining request | Recommendation cards appear |  |  |
| G25 | Recommendation Details | Description expands and collapses |  |  |
| G26 | Recommendation Directions | Configured map URL opens |  |  |
| G27 | Service request | Confirmation card appears |  |  |
| G28 | Confirm service request | Request ID is returned |  |  |

## Administrator authentication

| # | Check | Expected result | Result | Comments |
|---|---|---|---|---|
| A01 | Open `/admin` while signed out | Redirects to admin login |  |  |
| A02 | Show/Hide password | Password visibility toggles |  |  |
| A03 | Invalid login | Error appears and page remains on login |  |  |
| A04 | Forgot password | Recovery dialog opens with username copied |  |  |
| A05 | Request reset | Generic reset confirmation appears |  |  |
| A06 | Recovery Cancel/Close | Dialog closes |  |  |
| A07 | Valid login | Admin dashboard opens |  |  |
| A08 | Logout | Session ends and `/admin` redirects to login |  |  |

## Admin navigation tabs

| # | Tab | Expected result | Result | Comments |
|---|---|---|---|---|
| N01 | Dashboard | Dashboard panel opens |  |  |
| N02 | Conversations | Conversation list opens |  |  |
| N03 | Guest Requests | Request workflow opens |  |  |
| N04 | Guest Sessions | Session/memory panel opens |  |  |
| N05 | Preview | Guest modules panel opens |  |  |
| N06 | Hotel Information | Correct placeholder/status panel opens |  |  |
| N07 | Rooms | Correct configuration-required panel opens |  |  |
| N08 | Facilities | Correct coming-soon panel opens |  |  |
| N09 | Restaurants | Correct coming-soon panel opens |  |  |
| N10 | Service Catalog | Department/service editor opens |  |  |
| N11 | Recommendations | Recommendation editor opens |  |  |
| N12 | Zones & Maps | Map editor opens |  |  |
| N13 | Knowledge Overview | Knowledge panel opens |  |  |
| N14 | Documents | Correct coming-soon panel opens |  |  |
| N15 | FAQs | Correct coming-soon panel opens |  |  |
| N16 | Models & Providers | AI provider panel opens |  |  |
| N17 | Personality | Correct coming-soon panel opens |  |  |
| N18 | Guardrails | Correct coming-soon panel opens |  |  |
| N19 | Improvement Loop | Loop controls open |  |  |
| N20 | AI Usage | Correct coming-soon panel opens |  |  |
| N21 | PMS | Correct configuration-required panel opens |  |  |
| N22 | ANTlabs / Wi-Fi | Correct configuration-required panel opens |  |  |
| N23 | Webhooks | Correct coming-soon panel opens |  |  |
| N24 | Design | Appearance editor and preview open |  |  |
| N25 | Branding / Intro | Intro editor opens |  |  |
| N26 | Location | Location analytics panel opens |  |  |
| N27 | Users | User table opens |  |  |
| N28 | Roles | Role list opens |  |  |
| N29 | Permissions | Permission catalog opens |  |  |
| N30 | Domain | Configuration-required panel opens |  |  |
| N31 | SSL | Configuration-required panel opens |  |  |
| N32 | Network | Configuration-required panel opens |  |  |
| N33 | Audit | Audit table opens |  |  |
| N34 | Security | Password and session panel opens |  |  |
| N35 | Settings | Correct coming-soon panel opens |  |  |
| N36 | License | License panel opens |  |  |

## Admin controls and workflows

| # | Check | Expected result | Result | Comments |
|---|---|---|---|---|
| C01 | Collapse/expand sidebar | Sidebar changes state and remains usable |  |  |
| C02 | Profile and Account Settings | Profile panel opens |  |  |
| C03 | Security and Change Password menu | Security panel opens |  |  |
| C04 | Switch Property | Property selector receives focus |  |  |
| C05 | Save Draft | Draft design is saved |  |  |
| C06 | Publish | Guest app receives published design |  |  |
| C07 | Discard | Unsaved design changes are restored |  |  |
| C08 | Restore design version | Selected version becomes the draft |  |  |
| C09 | Add/remove prompt | Prompt row is added/removed and preview updates |  |  |
| C10 | Mobile/Tablet/Desktop preview | Preview width changes |  |  |
| C11 | Save AI Settings | Settings persist and success message appears |  |  |
| C12 | Configure provider | Provider drawer opens |  |  |
| C13 | Save provider | Provider configuration persists |  |  |
| C14 | Add/replace provider credential | Credential status updates; secret is not displayed |  |  |
| C15 | Remove provider credential | Credential is removed |  |  |
| C16 | Close provider drawer | Drawer closes |  |  |
| C17 | Save improvement loop | Objective and settings persist |  |  |
| C18 | Loop lifecycle controls | Enabled controls change loop state appropriately |  |  |
| C19 | Map Select/Rectangle/Polygon/Ellipse | Selected tool becomes active |  |  |
| C20 | Map Duplicate/Delete/Undo/Redo | Draft objects change correctly |  |  |
| C21 | Save Object | Zone/facility/AP is saved |  |  |
| C22 | Floor-map upload | Valid PNG/JPEG/SVG/PDF uploads |  |  |
| C23 | Create/Restore Stay | Stay ID appears |  |  |
| C24 | Save Compact Memory | Memory persists |  |  |
| C25 | Record Observation | Observation is accepted |  |  |
| C26 | Load Report | Location report appears |  |  |
| C27 | Save Intro | Intro settings persist |  |  |
| C28 | Intro asset upload | Valid supported asset uploads |  |  |
| C29 | Refresh conversations | Conversation list refreshes |  |  |
| C30 | Take Over/Return to AI | Conversation ownership toggles |  |  |
| C31 | Send Response | Staff response appears in conversation |  |  |
| C32 | Close conversation | Conversation status becomes closed |  |  |
| C33 | Save Department | Department appears and can be edited |  |  |
| C34 | Save Service | Service appears and can be edited |  |  |
| C35 | Duplicate/Archive/Delete service | Each action updates the service list |  |  |
| C36 | Create Request | Operational request appears |  |  |
| C37 | Advance request status | Status moves to the next workflow state |  |  |
| C38 | Save/Edit/Delete recommendation | Recommendation list updates correctly |  |  |
| C39 | Create/Edit user | User table updates correctly |  |  |
| C40 | Reset user password | Temporary password is accepted |  |  |
| C41 | Disable/Enable user | User status changes |  |  |
| C42 | Revoke Sessions | Confirmation appears |  |  |
| C43 | View Activity | Audit panel opens filtered to the user |  |  |
| C44 | Delete User | Confirmation appears and user is removed |  |  |
| C45 | Create/Edit Role | Role list updates correctly |  |  |
| C46 | Refresh/Apply audit filters | Audit results refresh |  |  |
| C47 | Change own password | Password changes without a JavaScript error |  |  |

## Responsive and visual review

| # | Check | Expected result | Result | Comments |
|---|---|---|---|---|
| R01 | Guest desktop | No clipping, overlap, or horizontal scrollbar |  |  |
| R02 | Guest mobile | Header, prompts, composer, and send button remain usable |  |  |
| R03 | Admin desktop | Sidebar, top bar, forms, dialogs, and drawers fit correctly |  |  |
| R04 | Admin tablet | No horizontal page overflow |  |  |
| R05 | Admin mobile | Every navigation item is reachable |  |  |
| R06 | Keyboard navigation | Focus indicator is visible and order is logical |  |  |
| R07 | Dialog keyboard behavior | Tab remains usable; Escape/Close works |  |  |
| R08 | Dark mode | Guest page remains readable |  |  |

## Environment-dependent checks

These require valid staging credentials or connected services.

| # | Check | Expected result | Result | Comments |
|---|---|---|---|---|
| E01 | Test AI provider connection | Successful connection and latency appear |  |  |
| E02 | Refresh provider models | Live provider models populate |  |  |
| E03 | Run improvement-loop iteration | Provider returns an iteration for review |  |  |
| E04 | ANTlabs live authentication | Gateway accepts valid guest credentials |  |  |
| E05 | Production upload storage | Uploaded files remain available after restart |  |  |
