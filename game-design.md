# SimulationCity — Game Design Document

## Overview

SimulationCity is a cooperative multiplayer city-building game modeled after SimCity 2000. Players collaboratively build and manage a city in real-time — zoning land, laying roads, managing utilities, balancing a city budget, and guiding a population toward growth and prosperity. The game targets the same depth as SC2000: enough systems to feel like a real city simulation without the bloat of later entries in the genre.

The core premise is that a city belongs to a group of players who work together (or sometimes at cross-purposes) to build something over time. Cities are persistent and publicly visible, but only invited collaborators can make changes.

---

## Core Gameplay Loop

A typical session for an active builder looks like:

1. Log in and navigate to their city (or a city they collaborate on)
2. Check the city's current stats — treasury, population, happiness, demand indicators
3. Respond to simulation needs — zone new areas to meet demand, extend roads, build or fund services
4. Monitor utility coverage (power, water) and fix gaps
5. Adjust the budget or tax rates as needed
6. Leave the city in a better state than they found it

There is no win condition. The game is an open-ended sandbox. Success is measured by the player's own goals — growing population, reaching financial stability, hitting certain city milestones, or simply building something that looks good.

---

## Player Roles & Permissions

Every player in a city has one of three roles. The city owner is always the admin.

### Admin
- Full builder capabilities (all city management actions)
- City settings: rename city, delete city, adjust simulation speed
- Player management: invite new builders by email, remove collaborators, change collaborator roles
- Disaster controls: enable or disable random disasters
- There is exactly one admin per city (the creator); ownership transfer is a future consideration

### Builder
- Place and demolish zones (residential, commercial, industrial)
- Build and demolish roads, highways, rails, and transit infrastructure
- Place and demolish utility infrastructure (power plants, water pumps, pipes, power lines)
- Place and demolish city services (police, fire, hospitals, schools, etc.)
- Adjust tax rates by zone type
- Issue municipal bonds
- Trigger the city budget screen and fund/defund departments
- Pause the simulation (see Time Controls)
- Trigger manual disasters (only when disasters are enabled by admin)

### Viewer
- Real-time read-only view of the city
- Can see all map layers (base, power, water, pollution, etc.)
- Cannot interact with the simulation in any way
- Does not affect the simulation clock
- Any authenticated or unauthenticated user browsing the city browser is effectively a viewer

---

## User Flows

### New Visitor (Unauthenticated)

1. Lands on the SimulationCity homepage
2. Can browse the public city browser without an account — cities are visible to anyone
3. Can click into any city and view it in read-only mode (viewer)
4. Prompted to sign up if they attempt any action that requires an account (building, creating a city)

### Account Creation

1. User clicks "Sign Up" — prompted for username, email, password
2. Email verification sent; user confirms
3. Returned to the city browser or the city they were viewing
4. Account is created with no cities — they must create one or be invited to one

### Creating a City

1. Authenticated user clicks "Create City"
2. One input: city name
3. City is created immediately with default settings (see City Settings below)
4. User is placed into the city as admin and dropped into the game view
5. City is immediately visible in the public city browser (as read-only to others)

### Joining a City as Builder

1. Admin sends an invite to a player's email address from within the city's player management panel
2. Recipient receives an email with an invite link
3. If they already have an account, clicking the link adds them as a builder and takes them to the city
4. If they don't have an account, the link takes them through account creation first, then into the city
5. Builder now appears in the city's collaborator list

### Entering a City (Returning Builder or Admin)

1. Player logs in and sees their dashboard — a list of cities they are admin or builder on
2. They click a city and are taken directly into the game view
3. On load, they see the current city state with live collaborator presence (other active players visible)

---

## Collaboration Model

### Concurrent Editing

Any builder can place or demolish anything anywhere on the map at any time. There are no territory locks or ownership zones. The collaboration model is intentionally simple: **last write wins**.

If two players place conflicting structures on the same tile simultaneously, the server applies them in the order received. No merge conflict UI is shown to players — the result simply reflects whoever's action arrived last. Given that this is a cooperative game, direct conflicts are expected to be rare.

### Presence

Active builders in a city are shown in a live collaborator list in the HUD. Each player's cursor or active tile is highlighted on the map so players can see where others are working.

---

## City Settings (Defaults)

When a city is created, the following defaults apply. Admins can change these at any time.

| Setting | Default | Notes |
|---|---|---|
| Simulation speed | Normal | Admin-only |
| Starting funds | §10,000 | Set at creation only |
| Difficulty | Medium | Affects demand curves and event frequency |
| Random disasters | Off | Admin-only toggle |

---

## Simulation Systems

SimulationCity implements the full SimCity 2000 simulation model. The following systems are active during play.

### Zoning & Demand

- Three zone types: Residential (R), Commercial (C), Industrial (I)
- Three density levels per zone: Low, Medium, High
- Demand indicators (RCI bar) reflect the city's current need for each zone type
- Zones develop automatically when demand, land value, and coverage conditions are met
- Zones can decline or abandon if conditions deteriorate

### Transportation

- Dirt roads and paved roads (roads increase land value and enable zone development)
- Highways (high-capacity, connects city sectors)
- Rail (passenger and freight)
- Subway (underground rail for dense areas)
- Bus depots (reduces traffic, improves commute happiness)
- Airports (required for certain commercial and industrial growth thresholds)
- Seaports (enables freight and industrial scaling)
- Traffic simulation: congestion reduces land value and happiness in affected areas

### Power

- Power plants generate electricity; power lines and roads distribute it
- Building types by era (unlocked as city ages or population grows):
  - Coal plant
  - Oil plant
  - Gas plant
  - Nuclear plant
  - Wind turbines
  - Solar panels
  - Hydroelectric dam (terrain-dependent)
  - Microwave power satellite (late game)
  - Fusion reactor (late game)
- Unpowered zones do not develop; developed zones that lose power begin to decline

### Water

- Water pumps draw water; pipes distribute it to zones
- Water towers provide storage and pressure balancing
- Desalination plant (coastal cities, late game)
- Zones without water access have reduced development potential
- Water and power are independent systems; both are required for full zone development

### City Services

Each service has a coverage radius. Underfunded departments provide degraded coverage.

| Service | Effect |
|---|---|
| Police station | Reduces crime rate in coverage area |
| Fire station | Reduces fire risk; required for disaster recovery |
| Hospital | Improves health rate; required for population growth at scale |
| Elementary school | Increases Education Quotient (EQ) |
| High school | Increases EQ; required for commercial and industrial growth |
| College | Increases EQ significantly; enables high-tech industry |
| Library | Boosts EQ passively |
| Museum | Boosts city desirability and tourism |
| Marina | Coastal cities; boosts desirability |
| Stadium | Required for large population milestones; boosts happiness |
| Park / Plaza | Local land value boost |

### Simulation Metrics

The simulation continuously tracks and updates the following city-wide metrics:

- **Population** — derived from developed residential zones
- **Treasury** — running balance of income minus expenditures
- **Tax revenue** — collected each simulation year from R, C, I zones at configured rates
- **Land value** — per-tile, affected by proximity to services, pollution, traffic, crime
- **Crime rate** — affected by police coverage, poverty, population density
- **Pollution** — industrial zones, power plants, traffic; reduces land value and health
- **Traffic** — road network load; affects land value and happiness
- **Happiness** — composite of services coverage, traffic, crime, pollution, employment
- **Education Quotient (EQ)** — affects quality of commercial and industrial development
- **Health rate** — affects population growth and happiness
- **Fire risk** — reduced by fire station coverage
- **Unemployment** — imbalance between residential population and C/I job demand
- **City age** — unlocks certain buildings and milestones over time

### Special / Reward Buildings

Certain milestones unlock special buildings that can be placed by any builder. These include the Mayor's House, City Hall, the Llama Dome, the Arcologies (end-game large residential structures), and others from the SC2000 catalog.

---

## Time & Simulation Controls

### Simulation Speed

Admin controls the global simulation speed. Speed settings:

- Paused
- Slow
- Normal (default)
- Fast

### Player Pause

Any builder can pause the simulation at any time. A player-triggered pause lasts for a fixed duration of **3 minutes**, after which the simulation automatically resumes at the previously set speed. A visible countdown timer is shown to all players in the HUD during a player pause.

Admins can lift a player pause early. Admins can also set a permanent pause (no countdown) through the speed controls.

### Simulation Year

The simulation advances one in-game year per real-time interval (determined by simulation speed). Year advancement triggers:

- Tax collection
- Budget allocation to departments
- Bond interest payments
- Population growth/decline calculations
- Building aging and upgrade eligibility

---

## Economy & Budget System

### Tax Rates

Builders and admins can set tax rates independently for each zone type (Residential, Commercial, Industrial). Rates are a percentage applied annually at year end. Higher rates generate more revenue but suppress zone demand and development if too aggressive.

### City Budget

Each year, the city receives tax revenue and allocates funds to departments (police, fire, health, education, transit, etc.). Builders and admins can:

- View the annual budget breakdown
- Adjust funding levels per department (affects service quality and coverage)
- Review projected income vs. expenditure

Underfunding a department degrades its service level proportionally rather than turning it off entirely, to avoid abrupt simulation cliff edges.

### Municipal Bonds

When the treasury is low or depleted, any builder can issue a municipal bond:

- Bonds provide an immediate cash infusion
- Bonds accrue annual interest and must be paid back over time
- Multiple bonds can be outstanding simultaneously

### Bankruptcy & Consequences

There is no hard game-over state. A city can never be deleted by bankruptcy. However, running out of money has cascading consequences:

1. Treasury reaches zero — bond issuance becomes available as an emergency measure
2. If debt exceeds a threshold without recovery, department budgets are automatically reduced in priority order:
   - First: parks, museums, stadiums (luxuries)
   - Then: schools, libraries (education)
   - Then: hospitals (health)
   - Finally: police and fire (critical services)
3. Defunded services degrade coverage, which causes simulation-level deterioration:
   - Crime rises → land value drops → residents leave → tax revenue shrinks
   - This death spiral is fully recoverable if builders intervene with bonds, tax adjustments, or spending cuts

---

## Disasters

Disasters are **disabled by default** and are **not an MVP feature**. They are documented here for future implementation.

### Random Disasters

When enabled by admin, random disasters can occur at intervals determined by difficulty setting. Types based on SC2000:

- Fire (most common, limited area impact)
- Flood
- Tornado
- Earthquake
- Plane crash
- Monster attack (Godzilla-style)
- Meteor strike

### Manual Disasters

When disasters are enabled, any builder can manually trigger a disaster of their choosing from a disasters menu. This is a deliberate action, not accidental — it requires confirmation.

### Disaster Recovery

Fire stations respond to fires automatically. Other disasters leave damage that builders must repair manually by rebuilding destroyed tiles. The simulation continues during disaster damage.

---

## Premium Features

Premium features (AI-generated building assets, custom visual styles) are documented separately in `premium-features.md`. They do not affect core gameplay balance — they are cosmetic and quality-of-life enhancements only.

---

## MVP Scope Notes

The following are explicitly **out of scope for MVP**:

- Disasters system (random or manual)
- Arcologies (can be added post-launch as a milestone feature)
- Rail and subway (road-based transport is sufficient for MVP; rail adds significant simulation complexity)
- Airports and seaports (same rationale as rail)
- Premium AI asset generation
- City ownership transfer between admins
- In-game chat between collaborators (presence indicators are sufficient for MVP)

MVP delivers: zoning, roads, power, water, core city services, budget/tax system, the RCI simulation loop, and the full collaboration and role model described above.
