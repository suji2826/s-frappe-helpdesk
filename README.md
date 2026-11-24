# Frappe Helpdesk: Ticket List Filters & SLA Monitor

![Candidate](https://img.shields.io/badge/Candidate-Sujitha%20S-1F3A5F?style=for-the-badge)
![Program](https://img.shields.io/badge/Praskla%20Technology-Internship%202026-2E5A88?style=for-the-badge)
![Branch](https://img.shields.io/badge/Branch-feature%2Fticket--list--and--sla--monitor-4A6FA5?style=for-the-badge)

![Frappe](https://img.shields.io/badge/Backend-Frappe%20%2F%20Python-0089FF?style=flat-square&logo=python&logoColor=white)
![Vue](https://img.shields.io/badge/Frontend-Vue%203%20%2B%20TypeScript-42B883?style=flat-square&logo=vuedotjs&logoColor=white)
![MariaDB](https://img.shields.io/badge/Database-MariaDB%2011.8-003545?style=flat-square&logo=mariadb&logoColor=white)
![Docker](https://img.shields.io/badge/Runtime-Docker%20on%20WSL%202-2496ED?style=flat-square&logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-15%20passing-2EA44F?style=flat-square)

**Repository:** fork of [frappe/helpdesk](https://github.com/frappe/helpdesk) · **Base:** `main` (commit `0503116`)

| Task | What was built |
|---|---|
| **Modification** | A filter bar on the agent ticket list: **Search**, **Status**, **Priority**, **Assignee** and **Date** filters |
| **New feature** | An **SLA Monitor** page showing **remaining SLA time**, **overdue status**, **escalation warnings** and **colour indicators** |

---

## Contents
1. [Project setup](#1-project-setup)
2. [Architecture overview](#2-architecture-overview)
3. [Database structure](#3-database-structure)
4. [Modification: ticket list filters and search](#4-modification-ticket-list-filters-and-search)
5. [New feature: SLA Monitor](#5-new-feature-sla-monitor)
6. [Testing](#6-testing)
7. [Files changed and commits](#7-files-changed-and-commits)
8. [Challenges and solutions](#8-challenges-and-solutions)
9. [Screenshots](#9-screenshots)

---

## 1. Project setup

### Prerequisites
| Tool | Version / note |
|---|---|
| Windows + WSL 2 | Ubuntu distro |
| Docker Desktop | WSL integration turned on for Ubuntu |
| Git | Fork: `suji2826/s-frappe-helpdesk` |

### Steps
```bash
# 1. Clone the fork inside WSL Ubuntu
git clone https://github.com/suji2826/s-frappe-helpdesk.git
cd s-frappe-helpdesk/docker

# 2. In docker-compose.yml set the MariaDB image to mariadb:11.8 (see Challenges, item 2)

# 3. Start MariaDB + Redis + the Frappe bench
docker compose up -d
docker compose logs -f frappe        # wait until "bench start" is running
```
Open **http://helpdesk.localhost:8000/helpdesk** and log in as `Administrator` with the password `admin`.

### Load this branch into the bench
```bash
docker exec -it <frappe-container> bash
cd /home/frappe/frappe-bench/apps/helpdesk
git remote add fork https://github.com/suji2826/s-frappe-helpdesk.git
git fetch fork feature/ticket-list-and-sla-monitor
git checkout -b feature/ticket-list-and-sla-monitor FETCH_HEAD

cd /home/frappe/frappe-bench
bench --site helpdesk.localhost migrate         # adds the new HD Settings fields
bench build --app helpdesk                      # rebuilds the Vue agent UI
bench --site helpdesk.localhost clear-cache
```

---

## 2. Architecture overview

```mermaid
flowchart LR
    subgraph UI["Agent UI · Vue 3 + frappe-ui"]
        direction TB
        TL["Tickets.vue<br/>TicketListFilters.vue"]
        LVB["ListViewBuilder.vue"]
        SM["SlaMonitor.vue"]
    end
    subgraph API["Frappe backend · Python"]
        direction TB
        DOC["helpdesk.api.doc<br/>get_list_data · export_list"]
        SRCH["handle_search_filter<br/>(__search)"]
        SLA["helpdesk.api.sla_monitor<br/>get_sla_monitor"]
        SET["HD Settings<br/>threshold · refresh"]
    end
    DB[("MariaDB<br/>tabHD Ticket")]

    TL --> LVB -->|filters| DOC --> SRCH --> DB
    SM -->|REST| SLA --> DB
    SLA --> SET

    classDef ui fill:#E8F1FB,stroke:#2E5A88,color:#1F3A5F
    classDef api fill:#EAF6EE,stroke:#2EA44F,color:#1B5E31
    classDef db fill:#FFF4E5,stroke:#D9822B,color:#7A4A12
    class TL,LVB,SM ui
    class DOC,SRCH,SLA,SET api
    class DB db
```

| Layer | Location | Notes |
|---|---|---|
| Backend (Python, Frappe) | `helpdesk/` | DocTypes in `helpdesk/helpdesk/doctype/`, whitelisted APIs in `helpdesk/api/` |
| Agent UI (Vue 3, TypeScript, frappe-ui) | `desk/src/` | Pages in `pages/`, components in `components/`, Pinia stores in `stores/`, routes in `router/index.ts` |
| List view controls | `desk/src/components/view-controls/` | Filter, sort, columns, quick filters |
| Database | MariaDB | Each DocType is stored as a `tab<DocType>` table |

**How the ticket list loads:** `Tickets.vue` → `ListViewBuilder.vue` → `helpdesk.api.doc.get_list_data` → `frappe.get_list("HD Ticket", filters=…)`. Before the query runs, the backend resolves the custom filters `@me`, `__assigned_on` and the new `__search`.

---

## 3. Database structure

```mermaid
erDiagram
    HD_TICKET }o--|| HD_TICKET_STATUS : status
    HD_TICKET }o--|| HD_TICKET_PRIORITY : priority
    HD_TICKET }o--o| HD_TEAM : agent_group
    HD_TICKET }o--o| HD_SERVICE_LEVEL_AGREEMENT : sla
    HD_TICKET }o--o| HD_CUSTOMER : customer
    HD_TICKET ||--o{ TODO : assignment
    TODO }o--|| USER : allocated_to
    HD_AGENT ||--|| USER : user
    HD_SERVICE_LEVEL_AGREEMENT ||--o{ HD_SERVICE_LEVEL_PRIORITY : times_per_priority
    HD_SERVICE_LEVEL_AGREEMENT ||--o{ HD_SERVICE_DAY : working_hours

    HD_TICKET {
        int name PK
        string subject
        string raised_by
        string status FK
        string status_category
        string priority FK
        string agent_group FK
        text _assign
        date opening_date
        string sla FK
        datetime service_level_agreement_creation
        datetime response_by
        datetime resolution_by
        datetime first_responded_on
        datetime resolution_date
        datetime on_hold_since
    }
```

### `tabHD Ticket`: the fields this work uses
| Field | Type | Meaning |
|---|---|---|
| `name` | int (autoincrement) | Ticket ID |
| `subject`, `raised_by` | Data | Title and customer email (both searchable) |
| `status` | Link → HD Ticket Status | e.g. Open, Replied, Resolved, Closed |
| `status_category` | Data | `Open`, `Paused` or `Resolved` |
| `priority` | Link → HD Ticket Priority | Low, Medium, High, Urgent |
| `agent_group` | Link → HD Team | The team that owns the ticket |
| `_assign` | JSON text | Assigned users, mirrors the open **ToDo** rows |
| `opening_date` | Date | Date the ticket was opened |
| `sla` | Link → HD Service Level Agreement | The SLA applied to the ticket |
| `service_level_agreement_creation` | Datetime | When the SLA clock started |
| `response_by` / `resolution_by` | Datetime | SLA due times |
| `first_responded_on` / `resolution_date` | Datetime | When the targets were met |
| `on_hold_since` | Datetime | When the ticket was paused |

`HD Service Level Agreement.apply()` runs when a ticket is saved. It fills in `response_by` and `resolution_by` from the response and resolution times for the ticket's priority, counting working hours and holidays.

### Schema change made in this work
Two new fields on **HD Settings** (a Single DocType, so the values are stored in `tabSingles`):

| Field | Type | Default | Purpose |
|---|---|---|---|
| `sla_warning_threshold` | Percent | 75 | The share of the SLA window used before a ticket is flagged **At Risk** |
| `sla_monitor_refresh_interval` | Int (seconds) | 60 | Auto-refresh interval of the SLA Monitor (0 turns it off) |

You can change them under **/app/hd-settings → Ticket tab → SLA Monitor**, with no code change.

---

## 4. Modification: ticket list filters and search

**UI:** `desk/src/components/ticket-agent/TicketListFilters.vue`, mounted in `desk/src/pages/ticket/Tickets.vue`

| Control | Filter condition produced |
|---|---|
| Search (debounced 400 ms) | `["__search", "like", term]`, which matches ID, subject, status and email |
| Status | `["status", "=", value]` |
| Priority | `["priority", "=", value]` |
| Assignee: an agent / Assigned to me | `["_assign", "like", "%user%"]` / `"%@me%"` |
| Assignee: Unassigned | `["_assign", "not like", '%"%']` |
| Opened between | `["opening_date", "between", [from, to]]` |
| Clear (n) | Removes only the conditions this bar manages |

```mermaid
sequenceDiagram
    autonumber
    participant A as Agent
    participant F as TicketListFilters.vue
    participant L as ListViewBuilder.vue
    participant S as helpdesk.api.doc
    participant D as MariaDB
    A->>F: types "payment", picks Priority = Urgent
    F->>L: applyFilters([["__search","like","payment"], ["priority","=","Urgent"]])
    L->>S: get_list_data(filters)
    S->>D: or_filters on name / subject / raised_by
    D-->>S: matching ticket names
    S->>D: get_list(name in (...), priority = Urgent)
    D-->>L: rows
    L-->>A: filtered ticket list
```

**Design decisions**
- The bar reads and writes the **same filter list** as the existing Filter button (`ListViewBuilder.applyFilters` is now exposed). The two controls stay in sync, filters on other fields are kept, and the result can be saved as a view.
- **Searching several fields at once:** Frappe filters are AND-ed, so "subject OR email OR ID" can't be written as a normal filter. `__search` is a pseudo filter that `handle_search_filter()` resolves on the server into `name in (...)`. This follows the existing `__assigned_on` pattern and respects permissions through `frappe.get_list`.
- `__search` is also resolved in **export** (the new `export_list` wrapper) and in **ticket navigation**, so no path sends an unknown column to SQL.
- The existing quick filters, Filter button, sorting, columns and views still work as before.

---

## 5. New feature: SLA Monitor

**Route:** `/helpdesk/sla-monitor` (sidebar → SLA Monitor)
**Backend:** `helpdesk/api/sla_monitor.py` → `get_sla_monitor(team, priority, state, assigned_to_me, search)`, agents only
**UI:** `desk/src/pages/sla-monitor/SlaMonitor.vue`

### State indicators
![Overdue](https://img.shields.io/badge/Overdue-target%20passed-D73A49?style=for-the-badge)
![At Risk](https://img.shields.io/badge/At%20Risk-escalation%20warning-F66A0A?style=for-the-badge)
![On Track](https://img.shields.io/badge/On%20Track-within%20SLA-2EA44F?style=for-the-badge)
![Paused](https://img.shields.io/badge/Paused-clock%20stopped-0366D6?style=for-the-badge)

| State | Rule | Colour |
|---|---|---|
| **Overdue** | remaining < 0 (stays Overdue even if the ticket is paused later) | Red |
| **At Risk** | % of the SLA window used ≥ `sla_warning_threshold` → **escalation warning** | Orange |
| **On Track** | inside the window and below the threshold | Green |
| **Paused** | the ticket's status is in the Paused category | Blue |

### How the state is calculated
```mermaid
flowchart TD
    A["Open or paused ticket with an SLA"] --> B{"First response done?"}
    B -- No --> C["Target = response_by"]
    B -- Yes --> D{"Resolved?"}
    D -- No --> E["Target = resolution_by"]
    D -- Yes --> Z["Skipped"]
    C --> F["remaining = target - now<br/>used % = elapsed / window x 100"]
    E --> F
    F --> G{"remaining < 0?"}
    G -- Yes --> R["OVERDUE<br/>Escalate now"]
    G -- No --> H{"Paused?"}
    H -- Yes --> P["PAUSED<br/>clock frozen"]
    H -- No --> I{"used % >= threshold?"}
    I -- Yes --> O["AT RISK<br/>Escalation warning"]
    I -- No --> K["ON TRACK"]

    classDef red fill:#FDECEE,stroke:#D73A49,color:#86181D,stroke-width:2px
    classDef orange fill:#FFF1E5,stroke:#F66A0A,color:#8A3B00,stroke-width:2px
    classDef green fill:#E6F6EA,stroke:#2EA44F,color:#165C26,stroke-width:2px
    classDef blue fill:#E7F1FD,stroke:#0366D6,color:#03396C,stroke-width:2px
    classDef step fill:#F6F8FA,stroke:#8B949E,color:#24292F
    class R red
    class O orange
    class K green
    class P blue
    class A,B,C,D,E,F,G,H,I,Z step
```

### What the page shows
- **Escalation banner:** "N ticket(s) need escalation · X overdue, Y past the 75% warning threshold"
- **Summary tiles:** All open / Overdue / At Risk / On Track / Paused, with counts. Clicking a tile filters the table.
- **Filters:** search, team, priority, "Assigned to me"
- **Table:** ID, subject with the warning text, priority, team, SLA stage, due time, **live countdown** (updates every second), **SLA used** progress bar and a state badge. Clicking a row opens the ticket.
- **Auto refresh** at the interval set in HD Settings. A ticket whose deadline passes between refreshes turns Overdue on screen right away.
- Sorted by urgency: Overdue → At Risk → On Track → Paused, then by the least time left.

### Why this design
- **Time is computed on the server** in the system time zone, so the browser's clock and time zone can't skew it. The browser only counts down from the server's value.
- **Pause-aware:** a paused clock is frozen at `on_hold_since`, so paused tickets don't show a false breach.
- **Goes further than the existing Home "SLA Alerts" widget:** it covers every open SLA ticket and adds the remaining time, % used, a configurable escalation threshold, filters and auto refresh.

---

## 6. Testing
```bash
bench --site helpdesk.localhost set-config allow_tests true
bench --site helpdesk.localhost run-tests --app helpdesk --module helpdesk.tests.api.test_sla_monitor
```
Result: **`Ran 15 tests … OK`**

| Test group | Covers |
|---|---|
| `TestEvaluateTicket` (8) | On Track / At Risk / Overdue rules, switching from response to resolution, frozen paused clock, a breach before a pause stays Overdue, tickets with nothing pending are skipped, duration format |
| `TestMonitorSettings` (4) | Threshold read from HD Settings, invalid-threshold fallback, summary totals, unknown state rejected |
| `TestSearchFilter` (3) | `__search` matches subject and email, and a blank search is ignored |

---

## 7. Files changed and commits

| File | Change |
|---|---|
| `helpdesk/api/sla_monitor.py` | **new**: SLA Monitor API and logic |
| `helpdesk/tests/api/test_sla_monitor.py` | **new**: 15 tests |
| `desk/src/pages/sla-monitor/SlaMonitor.vue` | **new**: monitor page |
| `desk/src/components/ticket-agent/TicketListFilters.vue` | **new**: filter bar |
| `helpdesk/api/doc.py` | `__search` pseudo filter + `export_list` wrapper |
| `helpdesk/helpdesk/doctype/hd_ticket/api.py` | `__search` in ticket navigation |
| `helpdesk/helpdesk/doctype/hd_settings/hd_settings.json` | New SLA Monitor settings section |
| `desk/src/pages/ticket/Tickets.vue` | Mounts the filter bar; export through `export_list` |
| `desk/src/components/ListViewBuilder.vue` | Exposes `applyFilters` |
| `desk/src/router/index.ts`, `desk/src/components/layouts/layoutSettings.ts` | Route and sidebar link |

```mermaid
gitGraph
    commit id: "0503116 main"
    branch feature/ticket-list-and-sla-monitor
    commit id: "feat(list): __search filter"
    commit id: "feat(tickets): filter bar"
    commit id: "feat(settings): SLA settings"
    commit id: "feat(sla): monitor API + tests"
    commit id: "feat(desk): SLA Monitor page"
    commit id: "docs: notes + screenshots"
    commit id: "docs: README"
```

---

## 8. Challenges and solutions

| # | Challenge | Solution |
|---|---|---|
| 1 | Docker was unreachable from WSL (permission denied on the Docker socket) | Turned on WSL integration for Ubuntu in Docker Desktop and fixed the Docker permissions |
| 2 | MariaDB SSL error during `bench new-site` with `mariadb:10.8` | Switched the image to `mariadb:11.8` and did a clean restart with fresh volumes |
| 3 | Searching several fields with an AND-only filter list | Server-side `__search` pseudo filter, following the existing `__assigned_on` pattern |
| 4 | The first patches targeted `develop`, but the bench runs `main` (commit `0503116`), so `git am` failed | Rebased onto the exact base commit, adapted the imports, and added an `export_list` wrapper because `main` has no grouped export |
| 5 | New fields on a Single DocType have no stored value after migrate (read as `0`) | Read `tabSingles` directly and fall back to the DocType default |
| 6 | Time zones and paused SLAs | Remaining time computed on the server; paused clock frozen at `on_hold_since` |
| 7 | Pushing from a shallow ("grafted") clone; GitHub rejected workflow files | `git fetch --unshallow`, and a Personal Access Token with the `workflow` scope |
| 8 | Demo data for every SLA state | Created tickets and moved SLA timestamps through `bench console` |

---

## 9. Screenshots

### Ticket list with the new filter bar
![Ticket list filters](docs/screenshots/1-ticket-filters.png)

### SLA Monitor: escalation banner, state tiles and colour indicators
![SLA Monitor](docs/screenshots/2-sla-monitor.png)

### Overdue and At Risk tickets with escalation warnings
![Escalation warning](docs/screenshots/3-escalation-warning.png)

---

<sub>Original Frappe Helpdesk README: [docs/FRAPPE_HELPDESK_README.md](docs/FRAPPE_HELPDESK_README.md) · Built on [Frappe Helpdesk](https://github.com/frappe/helpdesk) (AGPL-3.0)</sub>
