# Travel & Subsistence System Overview

## Purpose

This system manages travel and subsistence claims from submission through document upload, OCR processing, fraud/risk scoring, multi-stage approval, and administrative configuration.

At a high level:

- Employees register or are created by admins.
- Employees create travel claims with allowance lines.
- The system calculates trip distance and stores a GPS validation baseline.
- Employees upload receipts and actual mileage after the trip.
- OCR runs on the uploaded receipt images in the background.
- Approvers or admins review submitted claims and make decisions.
- Fraud scoring can auto-approve some low-risk claims and flag others for manual review.

This document reflects the current codebase behavior as observed in:

- Backend: `tns_backend` / `tns_api`
- Frontend: `fe`

## System Architecture

## Backend

- Framework: Django 6 + Django REST Framework
- Auth: Token authentication via `rest_framework.authtoken`
- Storage:
  - relational database for domain data
  - file storage under `media/receipts/` for uploaded receipt images
- OCR integration:
  - OpenAI Responses API for receipt extraction
  - fallback error notes if `OPENAI_API_KEY` is missing or OCR fails
- Fraud scoring:
  - scikit-learn `IsolationForest`
  - persisted model snapshots and per-claim fraud scores

## Frontend

- Framework: React + TypeScript + Vite
- Routing: `react-router-dom`
- UI: React Bootstrap + custom CSS
- API client: Axios
- Auth persistence: token stored in `localStorage` under `tns_auth`

## Main Modules

## Public Experience

- Landing page
- Login page
- Multi-step signup page

## Employee Experience

- Dashboard
- My Claims
- Create/Edit Claim
- Claim preview
- Claim document upload
- OCR summary
- Profile

## Reviewer / Approver Experience

- Pending Claims review queue
- All Claims listing
- Claim preview with risk indicators

## Admin Experience

- Employee management
- Allowance management
- City/location registry
- Approval stage management
- User role management
- Password resets
- GPS threshold management
- Fraud model training

## Core Domain Model

The key backend entities are in `tns_api/models.py`.

## User and Identity

- `User`
  - Django auth user
- `UserProfile`
  - stores application role
  - roles:
    - `EMPLOYEE`
    - `APPROVER`
    - `ADMIN`
    - `SUPERUSER`
- `AuditLog`
  - records role updates, password resets, approvals, rejections, and some auto-approvals

## HR / Reference Data

- `Employee`
  - employee identity and business metadata
  - linked one-to-one to a Django user when available
- `Location`
  - city/location registry with latitude and longitude
- `Allowance`
  - configurable claimable item
  - can be tied to:
    - allowance nature
    - grade range
    - status
- `ApprovalStage`
  - ordered workflow stage
  - many-to-many assignment to employees who can act in that stage

## Claiming

- `Claim`
  - main travel claim record
  - stores:
    - employee id
    - purpose
    - origin / destination
    - departure / return dates
    - calculated trip metrics
    - stage
    - document submission flag
    - approval status
- `ClaimLine`
  - one allowance line within a claim
  - stores allowance id, quantity, amount
- `Receipt`
  - uploaded image attached to a claim line

## Validation / Intelligence

- `GPSValidation`
  - baseline and adjusted route distance
  - claimed mileage variance
  - threshold and validation status
- `OCRResult`
  - receipt extraction result
  - vendor, date, total, tax, receipt number, notes, raw text
- `ThresholdConfig`
  - configurable numeric thresholds
  - currently intended for GPS variance thresholds
- `FraudModelSnapshot`
  - serialized trained fraud model
- `FraudScore`
  - per-claim stored risk score and rule flags

## Roles and Access Model

The intended role model is:

- `EMPLOYEE`
  - submits and tracks own claims
- `APPROVER`
  - reviews submitted claims
- `ADMIN`
  - manages settings and review workflows
- `SUPERUSER`
  - highest privilege role

Frontend role checks are already used for navigation:

- employees see their dashboard, claims, submissions, profile
- approvers/admins see:
  - `All Claims`
  - `Pending Claims`
- admins additionally see:
  - `Settings`
  - `Fraud Training`

Important current note:

- Backend DRF default permissions are set to `AllowAny`
- several endpoints have commented-out permission decorators
- this means the intended role/security model is stronger in the frontend than it is in the backend right now

## Authentication Flow

## Login

1. User submits username and password.
2. Frontend calls `POST /api/auth/login/`.
3. Backend authenticates with Django auth.
4. Backend returns:
   - token
   - user details
   - role from `UserProfile`
5. Frontend stores the payload in `localStorage`.
6. Axios default `Authorization: Token <token>` is set.

## Signup

1. User completes the multi-step signup form.
2. Frontend calls `POST /api/auth/signup/`.
3. Backend validates password and employee data.
4. Backend creates:
   - `Employee`
   - `User`
   - `UserProfile`
   - token
5. Frontend stores auth and redirects into the app.

## Logout

1. Frontend calls `POST /api/auth/logout/`.
2. Frontend clears local auth regardless of server response.

## Profile

- Frontend calls `GET /api/auth/me/` to refresh the stored user profile.

## Claim Lifecycle

## 1. Claim Creation

The claim is created from the `CreateClaim` screen.

Employee enters:

- purpose
- departure and return date/time
- origin and destination
- allowance rows

The frontend also auto-generates allowance rows for some allowance natures when possible:

- breakfast
- lunch
- dinner
- out of station
- fuel

The backend `ClaimView.create()` then:

1. resolves the employee id
   - from payload, or
   - from the authenticated user’s linked employee record
2. blocks new claim creation if the employee already has a pending claim whose documents have not yet been submitted
3. derives:
   - days
   - nights
   - default stage id
4. calculates route distance
   - first from stored `Location` coordinates
   - otherwise via Nominatim geocoding
5. applies an errands factor of `1.2`
6. saves:
   - `Claim`
   - `GPSValidation`
   - related `ClaimLine` rows
7. optionally runs fraud scoring if a trained model exists
8. auto-approves low-risk claims when scoring rules allow it

## 2. GPS Validation

For each created claim, the system stores:

- base distance in km
- adjusted distance in km
- threshold percentage
- source

Later, when actual mileage is submitted, the backend compares the claimed distance against the adjusted baseline and updates:

- variance in km
- variance percentage
- validation status

## 3. Document Upload

From the `Claim Documents` page, the employee can:

- enter actual mileage
- upload image receipts per claim line

Frontend uploads receipt files to:

- `POST /api/claim-lines/{id}/receipts/`

Current receipt upload rules:

- only image files are accepted
- receipts are attached to a `ClaimLine`

After upload, the frontend:

1. patches the claim with `actual_mileage`
2. calls `POST /api/claims/{id}/submit-documents/`

Submitting documents:

- marks `documents_submitted = true` if receipts exist
- starts background OCR processing for receipts that do not yet have `OCRResult`

## 4. OCR Processing

OCR is handled in `tns_api/ocr.py` and background-threaded from `tns_api/views.py`.

Flow:

1. Receipt images are converted to data URLs.
2. OpenAI Responses API is called with a structured JSON schema.
3. The OCR result is stored in `OCRResult`.

Extracted fields:

- raw text
- vendor name
- receipt date
- total amount
- tax amount
- receipt number
- notes

If OCR fails, the system stores an error-flavored OCR record rather than crashing the claim flow.

## 5. OCR Summary

The `Claim Documents Summary` page uses:

- `GET /api/claims/{id}/documents-summary/`
- `POST /api/claims/{id}/reprocess-ocr/`

It shows:

- total receipts
- processed receipts
- pending receipts
- valid / mismatch / error / other counts
- individual receipt OCR details

Important current note:

- the current OCR build stores `match_status = "processed"` on success
- the summary logic explicitly counts `valid`, `mismatch`, `error`, and `pending`
- so successful OCR entries currently fall into `other`, not `valid`

## 6. Fraud Scoring

Fraud logic lives in `tns_api/fraud.py`.

The current trained model uses numeric features derived from claim history and claim structure, including:

- claim total
- claims in last 30 days
- claims in last 90 days
- days since last claim
- claim duration days

The system then adds rule-based flags, such as:

- too many claimed days in a month
- too many trips in a month
- repeated routes
- claims too close together
- mileage anomaly
- weekend concentration
- repeated receipt totals
- claim total above employee norm
- short trip with high amount
- multiple same-day claims
- delayed or missing receipts
- threshold gaming

The final result may indicate:

- low / medium / high risk
- auto-approve
- manual review required

Claim preview shows the risk score and triggered rule flags using:

- `GET /api/claims/{id}/risk-score/`

## 7. Approval Workflow

Approval is stage-based.

Each claim starts with a `stage_id`, normally `1`.

Approvers/admins use the `Pending Claims` page to review submitted claims.

They send:

- `POST /api/claims/{id}/decision/`

Payload:

- `decision`: `approve` or `deny`
- `justification`

Backend behavior:

- only claims still marked `pending` can be actioned
- approval:
  - moves the claim to the next approval stage if one exists
  - otherwise marks it `approved`
- denial:
  - marks the claim `rejected`
- every action creates an `AuditLog`

Important current note:

- the current backend decision endpoint does not enforce that the actor belongs to the assigned approval stage

## Frontend Route Map

## Public Routes

- `/`
  - landing page
- `/login`
  - login page
- `/signup`
  - multi-step registration page

## Authenticated Routes

- `/dashboard`
- `/my-claims`
- `/submissions`
- `/claims/:id`
- `/claims/:id/edit`
- `/claims/:id/documents`
- `/claims/:id/documents/summary`
- `/profile`
- `/settings`
- `/create-claim`
- `/all-claims`
- `/pending-claims`
- `/fraud-training`

Important current note:

- `PasswordReset.tsx` exists but is not currently wired into the router

## Settings / Admin Area

The `Settings` page is tab-based and currently includes:

- Employees
- Allowances
- Cities
- Approval Stages
- Users
- Thresholds

## Employees

Admins can create and edit employee records.

When an employee is created through the backend:

- a linked Django user is also created if needed
- the employee email becomes the username
- a temporary password may be generated and returned
- an email can be sent using the configured Django email backend

## Allowances

Admins manage:

- title
- cost
- nature
- grade range
- status

These are later used during claim creation and auto-generated allowance suggestions.

## Cities / Locations

Admins manage the location registry used for:

- trip origin/destination choices
- route distance calculation without external geocoding when known

## Approval Stages

Admins can:

- create stages
- edit titles
- delete stages
- reorder stages
- assign employees to stages

Stage assignment also influences user roles:

- assigned employees may be promoted to `APPROVER`
- removing all stage assignments can downgrade them back to `EMPLOYEE`

## Users

Admins can:

- change user roles
- reset passwords

Password reset returns a temporary password in the API response and logs the action.

## Thresholds

Thresholds are configurable records.

Current backend serializer explicitly allows:

- `GPS_VARIANCE_THRESHOLD`

This threshold affects mileage variance validation.

## Fraud Training

Admins can inspect fraud model status and upload a CSV to train a model.

Endpoints:

- `POST /api/fraud/train/`
- `POST /api/fraud/train-csv/`
- `GET /api/fraud/model/`

The frontend currently uses the CSV training flow.

## API Surface Summary

## Router-based CRUD endpoints

- `/api/allowances/`
- `/api/approval-stages/`
- `/api/employee/`
- `/api/claims/`
- `/api/claim-lines/`
- `/api/receipts/`
- `/api/gps-validations/`
- `/api/threshold-configs/`
- `/api/locations/`
- `/api/cities/`

## Auth and user endpoints

- `GET /api/enums/`
- `POST /api/auth/login/`
- `POST /api/auth/signup/`
- `POST /api/auth/logout/`
- `GET /api/auth/me/`
- `POST /api/auth/password-reset/`
- `GET /api/users/`
- `POST /api/users/{user_id}/role/`

## Claim-specific actions

- `POST /api/claims/{id}/decision/`
- `POST /api/claims/{id}/submit-documents/`
- `POST /api/claims/{id}/reprocess-ocr/`
- `GET /api/claims/{id}/documents-summary/`
- `GET /api/claims/{id}/risk-score/`
- `GET|POST /api/claim-lines/{id}/receipts/`

## AI / model / environment endpoints

- `GET /api/openai-health/`
- `POST /api/fraud/train/`
- `POST /api/fraud/train-csv/`
- `GET /api/fraud/model/`

## Important Technical Notes

## Data modeling style

Some core relationships are still stored as raw ids instead of foreign keys:

- `Claim.employee_id`
- `Claim.stage_id`
- `ClaimLine.claim_id`
- `ClaimLine.allowance_id`

This works, but it means:

- integrity is enforced more by code than by the database
- queries are more manual than fully relational Django models

## Security state

The system is designed around authenticated and role-based use, but the backend currently allows broad access because:

- DRF default permission class is `AllowAny`
- some stricter decorators are commented out

This should be treated as a major hardening task before production use.

## OCR result semantics

The OCR pipeline extracts fields, but it does not yet perform a true receipt-to-claim reconciliation step that marks records as:

- valid
- mismatch

Instead, successful OCR is currently stored as `processed`.

## Frontend/backend mismatches worth noting

- Frontend sometimes tries `/api/claims/{id}/lines/`, but the backend does not currently expose that route.
  - The frontend falls back to `/api/claim-lines/?claim_id=...`.
- `PasswordReset.tsx` exists but is not routed.
- The frontend fraud training sample exposes more CSV columns than the backend fraud engine currently uses for training.

## Environment and Configuration

## Backend settings

Notable settings and env-driven behavior:

- `DJANGO_SECRET_KEY`
- `DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- database settings via env vars
- `OPENAI_API_KEY`
- `OPENAI_OCR_MODEL` defaulting to `gpt-4o-mini`
- `NOMINATIM_EMAIL`
- `GPS_VARIANCE_THRESHOLD`

Current backend also enables:

- token auth
- CORS headers
- media file serving in debug

## Frontend settings

- Vite frontend proxies API requests to `http://localhost:8000`
- auth token is restored on startup and applied to Axios defaults

## Recommended Next Documentation Additions

This file documents the current behavior. The next useful docs to add would be:

1. API contract reference with request/response examples
2. database/entity relationship diagram
3. approval workflow matrix by role
4. deployment guide
5. security hardening checklist
6. known bugs and roadmap

## Short End-to-End Flow Summary

1. User signs up or is created by an admin.
2. User logs in and lands on the dashboard.
3. User creates a claim with trip details and allowance lines.
4. Backend calculates route distance and creates GPS validation.
5. If a trained model exists, the claim is risk-scored.
6. Low-risk claims may auto-approve.
7. Otherwise the employee uploads receipts and actual mileage.
8. OCR runs in the background on receipt images.
9. Approvers/admins review pending submitted claims.
10. Claims progress through approval stages until approved or rejected.
