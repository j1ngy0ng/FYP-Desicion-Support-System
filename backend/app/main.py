from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import hmac
import io
import json
import os
import random
import secrets
import statistics
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .engine import DEFAULT_RULES, HARD_RULE_CODES, RecommendationEngine, prepare_frame
from .models import BusinessRule, Campaign, Evaluation, HumanStudyResponse, Intent, Recommendation, RecommendationRule, User


ROOT = Path(__file__).resolve().parents[2]
ETHICS_APPROVAL_FILE = ROOT / "data" / "ethics_approval_reference.txt"
CHANNELS = ("Email", "Facebook", "Google", "Instagram", "WhatsApp", "YouTube")
CHANNEL_NAMES = {channel.casefold(): channel for channel in CHANNELS}
RAW_DATASET = ROOT / "data" / "layers" / "01_raw_dataset_55555x16.csv"
DATASET = ROOT / "data" / "layers" / "02_processed_model_data.csv"
AUDITED_BENCHMARK = ROOT / "data" / "benchmark_audited.csv"
CONFIRMATORY_RESULTS = ROOT / "results" / "R002.json"
SUPPLEMENTAL_RESULTS = ROOT / "results" / "R_SUP_50.json"
BENCHMARK_AUDIT = (
    ROOT / "data" / "human_annotations" / "completed" / "benchmark_audit.json"
)
CONFIRMATORY_PREDICTIONS = (
    ROOT / "outputs" / "confirmatory_evaluation" / "predictions.csv"
)
BENCHMARK_CANDIDATE = ROOT / "data" / "benchmark_candidate_125.csv"
DECISION_CASES = BENCHMARK_CANDIDATE
SYNTHETIC_DEVELOPMENT = ROOT / "data" / "Dataset_synthetic_development.csv"
HUMAN_PROVIDED_DEVELOPMENT = ROOT / "data" / "Dataset_human_provided_development.csv"
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "change-this-development-secret").encode()
ETHICS_APPROVAL_REFERENCE = os.getenv("ETHICS_APPROVAL_REFERENCE", "").strip() or (
    ETHICS_APPROVAL_FILE.read_text(encoding="utf-8").strip()
    if ETHICS_APPROVAL_FILE.exists()
    else ""
)
security = HTTPBearer(auto_error=False)
recommendation_engine: RecommendationEngine | None = None
STUDY_CONDITIONS = (
    "raw_uncalibrated",
    "calibrated_confidence",
    "structured_uncalibrated",
    "terse_calibrated",
    "structured_calibrated",
    "full_framework",
)
DEFAULT_RULE_CONDITIONS = {code: condition for code, _, _, condition, _, _ in DEFAULT_RULES}


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{base64.urlsafe_b64encode(salt).decode()}:{base64.urlsafe_b64encode(digest).decode()}"


def password_matches(password: str, stored: str) -> bool:
    salt, expected = (base64.urlsafe_b64decode(value) for value in stored.split(":"))
    return hmac.compare_digest(hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1), expected)


def make_token(user_id: int) -> str:
    payload = f"{user_id}:{int(time.time()) + 8 * 60 * 60}"
    signature = hmac.new(TOKEN_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()


def token_user_id(token: str) -> int:
    try:
        user_id, expires, signature = base64.urlsafe_b64decode(token.encode()).decode().split(":")
        payload = f"{user_id}:{expires}"
        if int(expires) < time.time() or not hmac.compare_digest(signature, hmac.new(TOKEN_SECRET, payload.encode(), hashlib.sha256).hexdigest()):
            raise ValueError
        return int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")


def make_study_token(
    participant_code: str,
    campaign_id: str,
    presentation_order: int,
    counterbalance_group: str,
) -> str:
    payload = (
        f"{participant_code}|{campaign_id}|{presentation_order}|"
        f"{counterbalance_group}"
    )
    signature = hmac.new(TOKEN_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{signature}".encode()).decode()


def study_token_data(token: str) -> tuple[str, str, int, str]:
    try:
        (
            participant_code,
            campaign_id,
            presentation_order,
            counterbalance_group,
            signature,
        ) = base64.urlsafe_b64decode(token.encode()).decode().split("|")
        payload = (
            f"{participant_code}|{campaign_id}|{presentation_order}|"
            f"{counterbalance_group}"
        )
        valid = (
            presentation_order.isdigit()
            and counterbalance_group
            in {f"CB-{index}" for index in range(1, len(STUDY_CONDITIONS) + 1)}
            and hmac.compare_digest(
                signature,
                hmac.new(TOKEN_SECRET, payload.encode(), hashlib.sha256).hexdigest(),
            )
        )
        if not valid:
            raise ValueError
        return (
            participant_code,
            campaign_id,
            int(presentation_order),
            counterbalance_group,
        )
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid study case token")


def db_session():
    with SessionLocal() as db:
        yield db


Db = Annotated[Session, Depends(db_session)]


def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)], db: Db) -> User:
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    user = db.get(User, token_user_id(credentials.credentials))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return user


def require_study_user(user: CurrentUser) -> User:
    if user.role not in {"admin", "participant"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Participant-study access required")
    return user


def seed(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)):
        return
    user = User(name="Jing Yong", email="jingyong@example.com", password_hash=password_hash("prototype"), role="admin")
    intents = {
        name: Intent(name=name, description=description)
        for name, description in {
            "Growth": "Prioritise acquisition and scalable returns.",
            "Retention": "Prioritise customer value and relationship continuity.",
            "Survival": "Prioritise cash preservation, cost control and low risk.",
        }.items()
    }
    db.add_all([user, *intents.values()]); db.flush()
    campaigns = [
        ("CMP-1048", "Mid-Year Growth Push", "Social Media", "Growth", "Instagram, Facebook", "Active", 4.51, 1250, 211, 18500),
        ("CMP-1042", "Premium Member Renewal", "Email", "Retention", "Email, WhatsApp", "Active", 2.64, 890, 209, 9200),
        ("CMP-1039", "Cashflow Recovery", "Paid Ads", "Survival", "Google, Facebook", "Review", -.20, 1800, 371, 6300),
        ("CMP-1031", "Youth Brand Awareness", "Influencer", "Growth", "YouTube, Instagram", "Completed", 5.73, 1600, 237, 22750),
        ("CMP-1026", "Loyalty Re-engagement", "Email", "Retention", "Email", "Completed", 1.58, 720, 47, 4800),
    ]
    for campaign_id, name, kind, intent, channels, campaign_status, roi, clicks, conversions, budget in campaigns:
        db.add(Campaign(
            id=campaign_id, user_id=user.id, intent_id=intents[intent].id, name=name, campaign_type=kind,
            channels=channels, status=campaign_status, roi=roi, budget=budget, duration=21,
            impressions=clicks * 12, clicks=clicks, leads=max(conversions, int(conversions * 1.7)), conversions=conversions,
            revenue=max(1000, budget * (roi + 1)), acquisition_cost=max(20, budget / max(conversions, 1)), engagement_score=18.4,
        ))
    for code, name, category, condition, weight, priority in DEFAULT_RULES:
        intent_name = "Growth" if code == "growth_safeguard" else "Survival" if code == "survival_safeguard" else "Retention" if code == "retention_safeguard" else None
        db.add(BusinessRule(code=code, name=name, category=category, condition=condition, weight=weight, priority=priority, intent_id=intents[intent_name].id if intent_name else None))
    db.commit()


def seed_study_user(db: Session) -> None:
    email = os.getenv("STUDY_ACCESS_EMAIL", "study@example.com").strip().lower()
    password = os.getenv("STUDY_ACCESS_PASSWORD", "participant")
    if not db.scalar(select(User.id).where(User.email == email)):
        db.add(User(
            name="Study Participant",
            email=email,
            password_hash=password_hash(password),
            role="participant",
            organisation="TAR UMT FYP Study",
        ))
        db.commit()


def seed_audited_campaigns(db: Session) -> None:
    """Add the frozen audited cases to the administrator's campaign workspace once."""
    if not AUDITED_BENCHMARK.exists():
        return
    user = db.scalar(select(User).where(User.email == "jingyong@example.com"))
    intents = {item.name: item for item in db.scalars(select(Intent)).all()}
    if not user or not {"Growth", "Retention", "Survival"}.issubset(intents):
        return

    existing_ids = set(db.scalars(select(Campaign.id)).all())
    frame = pd.read_csv(AUDITED_BENCHMARK)
    for row in frame.to_dict("records"):
        campaign_id = str(row["Campaign_ID"])
        if campaign_id in existing_ids:
            continue
        campaign_type = str(row["Campaign_Type"])
        target_audience = str(row["Target_Audience"])
        campaign_date = pd.to_datetime(row["Date"], dayfirst=True).date()
        intent = intents[str(row["Adjudicated_Intent"])]
        db.add(Campaign(
            id=campaign_id,
            user_id=user.id,
            intent_id=intent.id,
            name=f"{campaign_type} - {target_audience}"[:100],
            campaign_type=campaign_type,
            target_audience=target_audience,
            duration=int(row["Duration"]),
            channels=str(row["Channel_Used"]),
            impressions=int(row["Impressions"]),
            clicks=int(row["Clicks"]),
            leads=int(row["Leads"]),
            conversions=int(row["Conversions"]),
            revenue=float(row["Revenue"]),
            acquisition_cost=float(row["Acquisition_Cost"]),
            roi=float(row["ROI"]),
            language=str(row["Language"]),
            engagement_score=float(row["Engagement_Score"]),
            customer_segment=str(row["Customer_Segment"]),
            campaign_date=campaign_date,
            budget=None,
            status="Active",
        ))
        existing_ids.add(campaign_id)
    db.commit()


def upgrade_schema() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("human_study_responses")}
    additions = {
        "consent_confirmed": "BOOLEAN NOT NULL DEFAULT 0",
        "participant_group": "VARCHAR(30) NOT NULL DEFAULT 'Non-practitioner'",
        "presentation_order": "INTEGER NOT NULL DEFAULT 0",
        "counterbalance_group": "VARCHAR(20) NOT NULL DEFAULT ''",
        "specificity": "FLOAT NOT NULL DEFAULT 3",
        "feasibility": "FLOAT NOT NULL DEFAULT 3",
        "willingness_to_review": "FLOAT NOT NULL DEFAULT 3",
        "decision_time_ms": "FLOAT NOT NULL DEFAULT 0",
    }
    with engine.begin() as connection:
        for column, definition in additions.items():
            if column not in columns:
                connection.execute(
                    text(
                        f"ALTER TABLE human_study_responses "
                        f"ADD COLUMN {column} {definition}"
                    )
                )


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    upgrade_schema()
    with SessionLocal() as db:
        seed(db)
        seed_study_user(db)
        seed_audited_campaigns(db)
    yield


app = FastAPI(title="MarketSense DSS API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173", "http://localhost:5173",
        "http://127.0.0.1:5180", "http://localhost:5180",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginInput(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)


class RegisterInput(LoginInput):
    name: str = Field(min_length=2, max_length=100)
    organisation: str = Field(default="SME Marketing Lab", max_length=100)


class ChangePasswordInput(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ProfileInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str
    organisation: str = Field(max_length=100)


class CampaignInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    campaign_type: str
    intent: Literal["Growth", "Retention", "Survival"]
    channels: str = Field(min_length=2)
    target_audience: str = "General"
    duration: int = Field(default=21, ge=1)
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    leads: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    revenue: float = Field(default=0, ge=0)
    acquisition_cost: float = Field(default=0, ge=0)
    roi: float = 0
    engagement_score: float = Field(default=0, ge=0)
    budget: float | None = Field(default=None, ge=0)
    status: Literal["Active", "Review", "Completed"] = "Review"

    @field_validator("channels", mode="before")
    @classmethod
    def validate_channels(cls, value: Any) -> str:
        return normalize_channels(value)


def normalize_channels(value: Any) -> str:
    names = [name.strip() for name in str(value).split(",") if name.strip()]
    unsupported = sorted({name for name in names if name.casefold() not in CHANNEL_NAMES})
    if unsupported:
        raise ValueError(
            f"Unsupported channel(s): {', '.join(unsupported)}. "
            f"Choose from: {', '.join(CHANNELS)}."
        )
    normalized = {CHANNEL_NAMES[name.casefold()] for name in names}
    if not normalized:
        raise ValueError("Select at least one channel.")
    return ", ".join(channel for channel in CHANNELS if channel in normalized)


class GenerateInput(BaseModel):
    campaign_id: str
    intent: Literal["Growth", "Retention", "Survival"] | None = None
    risk_tolerance: Literal["Balanced", "Conservative", "Aggressive"] = "Balanced"


class DecisionInput(BaseModel):
    decision: Literal["Accepted", "Rejected", "Deferred", "Modified"]


class EvaluationInput(BaseModel):
    actionability: float = Field(ge=1, le=5)
    trust_alignment: float = Field(ge=1, le=5)
    explanation_usefulness: float = Field(ge=1, le=5)
    user_acceptance: float = Field(ge=1, le=5)
    comments: str = Field(default="", max_length=1000)


class HumanStudyInput(BaseModel):
    participant_code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    participant_group: Literal["Marketing practitioner", "Non-practitioner"]
    study_token: str
    actionability: float = Field(ge=1, le=5)
    specificity: float = Field(ge=1, le=5)
    feasibility: float = Field(ge=1, le=5)
    explanation_usefulness: float = Field(ge=1, le=5)
    reliance: float = Field(ge=1, le=5)
    willingness_to_review: float = Field(ge=1, le=5)
    user_acceptance: float = Field(ge=1, le=5)
    decision: Literal[
        "Accept without checking",
        "Verify before accepting",
        "Modify before accepting",
        "Reject",
    ]
    decision_time_ms: float = Field(ge=0, le=3_600_000)
    consent: bool
    comments: str = Field(default="", max_length=1000)


class RuleInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    weight: float = Field(ge=0, le=1)
    priority: int = Field(ge=1, le=3)
    active: bool


class RuleCreateInput(RuleInput):
    metric: Literal[
        "ROI", "conversion_rate", "ctr", "Engagement_Score", "Clicks",
        "Conversions", "Impressions", "Revenue", "Acquisition_Cost",
        "cost_per_conversion", "budget",
    ]
    operator: Literal["lt", "lte", "gt", "gte", "eq"]
    threshold: float = Field(allow_inf_nan=False)
    action: Literal["Increase", "Maintain", "Reduce", "Investigate"]
    intent: Literal["Growth", "Retention", "Survival"] | None = None


def campaign_json(campaign: Campaign) -> dict[str, Any]:
    return {
        "id": campaign.id, "name": campaign.name, "type": campaign.campaign_type,
        "intent": campaign.intent.name, "channel": campaign.channels, "status": campaign.status,
        "roi": campaign.roi, "conversion": round(100 * campaign.conversions / campaign.clicks, 2) if campaign.clicks else 0,
        "budget": campaign.budget, "target_audience": campaign.target_audience, "duration": campaign.duration,
        "impressions": campaign.impressions, "clicks": campaign.clicks, "leads": campaign.leads,
        "conversions": campaign.conversions, "revenue": campaign.revenue,
        "acquisition_cost": campaign.acquisition_cost, "engagement_score": campaign.engagement_score,
    }


def engine_case(campaign: Campaign) -> dict[str, Any]:
    return {
        "Duration": campaign.duration, "Impressions": campaign.impressions, "Clicks": campaign.clicks,
        "Leads": campaign.leads, "Conversions": campaign.conversions, "Revenue": campaign.revenue,
        "Acquisition_Cost": campaign.acquisition_cost, "ROI": campaign.roi,
        "Engagement_Score": campaign.engagement_score, "channels": campaign.channels, "budget": campaign.budget,
    }


RULE_OPERATOR_LABELS = {"lt": "is below", "lte": "is at most", "gt": "exceeds", "gte": "is at least", "eq": "equals"}
RULE_METRIC_LABELS = {
    "ROI": "ROI", "conversion_rate": "conversion rate", "ctr": "CTR",
    "Engagement_Score": "engagement score", "Clicks": "clicks", "Conversions": "conversions",
    "Impressions": "impressions", "Revenue": "revenue", "Acquisition_Cost": "acquisition cost",
    "cost_per_conversion": "cost per conversion", "budget": "budget",
}


def rule_definition(rule: BusinessRule) -> dict[str, Any] | None:
    try:
        definition = json.loads(rule.condition)
        return definition if definition.get("kind") == "threshold" else None
    except (json.JSONDecodeError, AttributeError):
        return None


def rule_condition(definition: dict[str, Any]) -> str:
    condition = f"Penalise {definition['action']} when {RULE_METRIC_LABELS[definition['metric']]} {RULE_OPERATOR_LABELS[definition['operator']]} {definition['threshold']:g}"
    return condition + (f" under {definition['intent']} intent" if definition.get("intent") else "")


def rule_json(rule: BusinessRule) -> dict[str, Any]:
    definition = rule_definition(rule)
    return {
        "id": rule.id, "code": rule.code, "name": rule.name, "category": rule.category,
        "condition": (
            rule_condition(definition)
            if definition
            else DEFAULT_RULE_CONDITIONS.get(rule.code, rule.condition)
        ),
        "definition": definition, "weight": rule.weight, "priority": rule.priority, "active": rule.active,
        "constraint_type": "Hard" if rule.code in HARD_RULE_CODES else "Soft",
    }


def get_engine() -> RecommendationEngine:
    global recommendation_engine
    if recommendation_engine is None:
        recommendation_engine = RecommendationEngine(
            DATASET,
            audited_benchmark=AUDITED_BENCHMARK,
        )
    return recommendation_engine


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(payload: LoginInput, db: Db) -> dict[str, Any]:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not password_matches(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return {"token": make_token(user.id), "user": {"name": user.name, "email": user.email, "role": user.role, "organisation": user.organisation}}


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterInput, db: Db) -> dict[str, Any]:
    user = User(
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        password_hash=password_hash(payload.password),
        role="manager",
        organisation=payload.organisation.strip(),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    return {
        "token": make_token(user.id),
        "user": {
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "organisation": user.organisation,
        },
    }


@app.get("/api/profile")
def profile(user: CurrentUser) -> dict[str, Any]:
    return {"name": user.name, "email": user.email, "role": user.role, "organisation": user.organisation, "created_at": user.created_at}


@app.patch("/api/profile")
def update_profile(payload: ProfileInput, user: CurrentUser, db: Db) -> dict[str, Any]:
    user.name = payload.name.strip()
    user.email = payload.email.strip().lower()
    user.organisation = payload.organisation.strip()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    return profile(user)


@app.patch("/api/profile/password", status_code=204)
def update_password(
    payload: ChangePasswordInput,
    user: CurrentUser,
    db: Db,
) -> None:
    if not password_matches(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a different new password")
    user.password_hash = password_hash(payload.new_password)
    db.commit()


@app.get("/api/campaigns")
def campaigns(user: CurrentUser, db: Db) -> list[dict[str, Any]]:
    return [campaign_json(item) for item in db.scalars(select(Campaign).where(Campaign.user_id == user.id).order_by(Campaign.id.desc())).all()]


@app.get("/api/campaigns/{campaign_id}")
def campaign(campaign_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    item = db.get(Campaign, campaign_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    return campaign_json(item)


def apply_campaign(item: Campaign, payload: CampaignInput, intent: Intent) -> None:
    for target, source in {
        "name": "name", "campaign_type": "campaign_type", "channels": "channels", "target_audience": "target_audience",
        "duration": "duration", "impressions": "impressions", "clicks": "clicks", "leads": "leads", "conversions": "conversions",
        "revenue": "revenue", "acquisition_cost": "acquisition_cost", "roi": "roi", "engagement_score": "engagement_score",
        "budget": "budget", "status": "status",
    }.items():
        setattr(item, target, getattr(payload, source))
    item.intent_id = intent.id


@app.post("/api/campaigns", status_code=201)
def create_campaign(payload: CampaignInput, user: CurrentUser, db: Db) -> dict[str, Any]:
    intent = db.scalar(select(Intent).where(Intent.name == payload.intent))
    number = max([int("".join(filter(str.isdigit, value.id)) or 0) for value in db.scalars(select(Campaign)).all()] + [1048]) + 1
    item = Campaign(id=f"CMP-{number}", user_id=user.id, intent_id=intent.id, name=payload.name, campaign_type=payload.campaign_type, channels=payload.channels)
    apply_campaign(item, payload, intent)
    db.add(item); db.commit()
    return campaign_json(item)


@app.put("/api/campaigns/{campaign_id}")
def update_campaign(campaign_id: str, payload: CampaignInput, user: CurrentUser, db: Db) -> dict[str, Any]:
    item = db.get(Campaign, campaign_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    intent = db.scalar(select(Intent).where(Intent.name == payload.intent))
    apply_campaign(item, payload, intent); db.commit()
    return campaign_json(item)


@app.delete("/api/campaigns/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: str, user: CurrentUser, db: Db) -> None:
    item = db.get(Campaign, campaign_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    db.delete(item); db.commit()


@app.post("/api/campaigns/import")
def import_campaigns(file: Annotated[UploadFile, File()], user: CurrentUser, db: Db) -> dict[str, int]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a CSV file")
    frame = pd.read_csv(io.BytesIO(file.file.read()))
    required = {"Campaign_ID", "Campaign_Type", "Channel_Used", "Intent"}
    if not required.issubset(frame.columns):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Missing columns: {', '.join(sorted(required - set(frame.columns)))}")
    added = skipped = 0
    seen: set[str] = set()
    for row in frame.to_dict("records"):
        campaign_id = str(row["Campaign_ID"]).strip()
        if not campaign_id or campaign_id in seen or db.get(Campaign, campaign_id):
            skipped += 1
            continue
        seen.add(campaign_id)
        intent = db.scalar(select(Intent).where(Intent.name == str(row["Intent"]).strip().title()))
        if not intent:
            skipped += 1
            continue

        def value(name: str, default: Any = 0) -> Any:
            item = row.get(name, default)
            return default if pd.isna(item) else item

        parsed_date = pd.to_datetime(value("Date", None), errors="coerce")
        try:
            channels = normalize_channels(value("Channel_Used", ""))
        except ValueError as error:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Campaign {campaign_id}: {error}",
            ) from error
        db.add(Campaign(
            id=campaign_id, user_id=user.id, intent_id=intent.id, name=campaign_id,
            campaign_type=str(value("Campaign_Type", "Unknown")), channels=channels,
            target_audience=str(value("Target_Audience", "General")), duration=int(float(value("Duration"))),
            impressions=int(float(value("Impressions"))), clicks=int(float(value("Clicks"))),
            leads=int(float(value("Leads"))), conversions=int(float(value("Conversions"))),
            revenue=float(value("Revenue")), acquisition_cost=float(value("Acquisition_Cost")),
            roi=float(value("ROI")), engagement_score=float(value("Engagement_Score")),
            budget=(None if value("Budget", None) is None else float(value("Budget", None))),
            language=str(value("Language", "English")), customer_segment=str(value("Customer_Segment", "General")),
            campaign_date=parsed_date.date() if not pd.isna(parsed_date) else date.today(),
        )); added += 1
    db.commit()
    return {"imported": added, "skipped": skipped}


@app.get("/api/campaigns/{campaign_id}/analysis")
def analysis(campaign_id: str, user: CurrentUser, db: Db) -> dict[str, Any]:
    item = db.get(Campaign, campaign_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    rules = [rule_json(rule) for rule in db.scalars(select(BusinessRule)).all()]
    result = get_engine().recommend(engine_case(item), rules, item.intent.name)
    return {
        "campaign": campaign_json(item),
        "performance_score": result.performance_score,
        "attribution": result.attribution,
        "channel_attribution": result.channel_attribution,
        "calibration_status": result.calibration_status,
        "action_evidence_status": result.action_evidence_status,
        "decision_status": result.decision_status,
        "decision_reasons": result.decision_reasons,
        "feasible_actions": result.feasible_actions,
        "hard_rejected_actions": result.hard_rejected_actions,
        "coverage_status": result.coverage_status,
        "coverage_reasons": result.coverage_reasons,
    }


def recommendation_json(item: Recommendation) -> dict[str, Any]:
    explanation = json.loads(item.explanation)
    evidence = json.loads(item.evidence)
    return {
        "id": f"REC-{item.id:04d}", "numeric_id": item.id, "campaign_id": item.campaign_id,
        "campaign": item.campaign.name, "intent": item.intent.name, "action": item.action,
        "confidence": round(item.confidence * 100, 1), "raw_confidence": round(item.raw_confidence * 100, 1),
        "performance_score": round(item.performance_score * 100, 1), "explanation": explanation,
        "evidence": evidence, "ranked_actions": json.loads(item.ranked_actions),
        "calibration_status": evidence.get("calibration_status", "legacy_unknown"),
        "action_evidence_status": evidence.get("action_evidence_status", "legacy_unknown"),
        "decision_status": evidence.get("decision_status", "legacy_unknown"),
        "decision_reasons": evidence.get("decision_reasons", []),
        "coverage_status": evidence.get("coverage_status", "legacy_unknown"),
        "coverage_reasons": evidence.get("coverage_reasons", []),
        "latency_ms": item.latency_ms, "status": item.decision, "date": item.generated_at.strftime("%d %b %Y"),
    }


@app.post("/api/recommendations", status_code=201)
def generate(payload: GenerateInput, user: CurrentUser, db: Db) -> dict[str, Any]:
    item = db.get(Campaign, payload.campaign_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")
    intent = db.scalar(select(Intent).where(Intent.name == (payload.intent or item.intent.name)))
    rules = [rule_json(rule) for rule in db.scalars(select(BusinessRule).order_by(BusinessRule.priority.desc())).all()]
    result = get_engine().recommend(engine_case(item), rules, intent.name, payload.risk_tolerance)
    record = Recommendation(
        campaign_id=item.id, intent_id=intent.id, action=result.action, confidence=result.confidence,
        raw_confidence=result.raw_confidence, performance_score=result.performance_score,
        explanation=json.dumps(result.explanation),
        evidence=json.dumps({
            "attribution": result.attribution,
            "channels": result.channel_attribution,
            "confidence_level": result.confidence_level,
            "calibration_status": result.calibration_status,
            "action_evidence_status": result.action_evidence_status,
            "decision_status": result.decision_status,
            "decision_reasons": result.decision_reasons,
            "feasible_actions": result.feasible_actions,
            "hard_rejected_actions": result.hard_rejected_actions,
            "coverage_status": result.coverage_status,
            "coverage_reasons": result.coverage_reasons,
        }),
        ranked_actions=json.dumps(result.ranked_actions), latency_ms=result.latency_ms,
    )
    db.add(record); db.flush()
    for rule_result in result.rule_results:
        selected_check = rule_result["action"] == result.action
        hard_exclusion = rule_result["triggered"] and rule_result.get("constraint_type") == "Hard"
        if rule_result.get("id") and (selected_check or hard_exclusion):
            detail = rule_result["detail"]
            if hard_exclusion:
                detail = f"Hard exclusion — {rule_result['action']}: {detail}"
            db.add(RecommendationRule(recommendation_id=record.id, rule_id=rule_result["id"], score=rule_result["score"], triggered=rule_result["triggered"], detail=detail))
    db.commit()
    return recommendation_json(record)


@app.get("/api/recommendations")
def recommendations(user: CurrentUser, db: Db) -> list[dict[str, Any]]:
    query = select(Recommendation).join(Campaign).where(Campaign.user_id == user.id).order_by(Recommendation.id.desc())
    return [recommendation_json(item) for item in db.scalars(query).unique().all()]


@app.get("/api/recommendations/{recommendation_id}")
def recommendation(recommendation_id: int, user: CurrentUser, db: Db) -> dict[str, Any]:
    item = db.get(Recommendation, recommendation_id)
    if not item or item.campaign.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation not found")
    result = recommendation_json(item)
    result["rules"] = [{"name": link.detail, "triggered": link.triggered, "score": link.score} for link in db.scalars(select(RecommendationRule).where(RecommendationRule.recommendation_id == item.id)).all()]
    return result


@app.patch("/api/recommendations/{recommendation_id}/decision")
def decide(recommendation_id: int, payload: DecisionInput, user: CurrentUser, db: Db) -> dict[str, Any]:
    item = db.get(Recommendation, recommendation_id)
    if not item or item.campaign.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation not found")
    item.decision = payload.decision; db.commit()
    return recommendation_json(item)


@app.post("/api/recommendations/{recommendation_id}/evaluations", status_code=201)
def evaluate(recommendation_id: int, payload: EvaluationInput, user: CurrentUser, db: Db) -> dict[str, int]:
    item = db.get(Recommendation, recommendation_id)
    if not item or item.campaign.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation not found")
    record = Evaluation(recommendation_id=item.id, **payload.model_dump())
    db.add(record); db.commit()
    return {"id": record.id}


def frozen_study_rows() -> list[dict[str, Any]]:
    if not ETHICS_APPROVAL_REFERENCE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Human study is locked until an ethics approval or exemption reference is configured.",
        )
    if not AUDITED_BENCHMARK.exists():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Human study is locked until data/benchmark_audited.csv exists.",
        )
    frame = pd.read_csv(AUDITED_BENCHMARK)
    required = {
        "Reviewer_1_Intent", "Reviewer_1_Action",
        "Reviewer_2_Intent", "Reviewer_2_Action",
        "Adjudicated_Intent", "Adjudicated_Action", "Annotation_Status",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Audited benchmark is missing columns: " + ", ".join(missing),
        )
    if len(frame) < 120 or not frame.Annotation_Status.eq("Audited").all():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Human study is locked until at least 120 cases are fully audited.",
        )
    intents = {"Growth", "Retention", "Survival"}
    actions = {"Increase", "Maintain", "Reduce", "Investigate"}
    if not set(frame.Adjudicated_Intent).issubset(intents) or not set(frame.Adjudicated_Action).issubset(actions):
        raise HTTPException(status.HTTP_409_CONFLICT, "Audited benchmark contains invalid intent or action values.")
    frame["Intent"] = frame.Adjudicated_Intent
    frame["model_label"] = frame.Adjudicated_Action
    prepared = prepare_frame(DATASET)
    frame = frame.drop(columns=[column for column in prepared.columns if column in frame.columns and column not in {"Campaign_ID"}]).merge(
        prepared,
        on="Campaign_ID",
        how="inner",
    )
    selected: list[dict[str, Any]] = []
    for intent in ("Growth", "Retention", "Survival"):
        group = frame[frame.Intent == intent].sort_values("Campaign_ID")
        selected.extend(group.head(3).to_dict("records"))
    if len(selected) != 9:
        raise HTTPException(status.HTTP_409_CONFLICT, "Audited benchmark needs at least three cases per intent.")
    return selected


def rating_summary(values: list[float], low: float = 1, high: float = 5) -> dict[str, Any]:
    if not values:
        return {"mean": None, "sd": None, "ci95": None}
    mean = statistics.fmean(values); sd = statistics.stdev(values) if len(values) > 1 else 0.0
    margin = 1.96 * sd / len(values) ** .5
    return {"mean": mean, "sd": sd, "ci95": [max(low, mean - margin), min(high, mean + margin)]}


def human_study_statistics(rows: list[HumanStudyResponse]) -> dict[str, Any]:
    trust = [1 - abs((row.reliance - 1) / 4 - float(row.correct)) for row in rows]
    at_risk = [row for row in rows if not row.correct or row.low_confidence]
    return {
        "responses": len(rows), "participants": len({row.participant_code for row in rows}),
        "participant_groups": {
            str(group): int(count)
            for group, count in pd.Series(
                [getattr(row, "participant_group", "Unspecified") for row in rows]
            ).value_counts().items()
        } if rows else {},
        "actionability": rating_summary([row.actionability for row in rows]),
        "specificity": rating_summary(
            [getattr(row, "specificity", 3) for row in rows]
        ),
        "feasibility": rating_summary(
            [getattr(row, "feasibility", 3) for row in rows]
        ),
        "explanation_usefulness": rating_summary([row.explanation_usefulness for row in rows]),
        "trust_alignment": rating_summary(trust, 0, 1),
        "overtrust_rate": statistics.fmean(row.decision == "Accept without checking" for row in at_risk) if at_risk else None,
        "overtrust_cases": len(at_risk),
        "willingness_to_review": rating_summary(
            [getattr(row, "willingness_to_review", 3) for row in rows]
        ),
        "user_acceptance": rating_summary([row.user_acceptance for row in rows]),
        "decision_time_seconds": rating_summary(
            [getattr(row, "decision_time_ms", 0) / 1000 for row in rows],
            0,
            3600,
        ),
    }


def study_assignment(participant_code: str) -> tuple[int, str]:
    offset = int(
        hashlib.sha256((participant_code + ":condition").encode()).hexdigest(),
        16,
    ) % len(STUDY_CONDITIONS)
    return offset, f"CB-{offset + 1}"


def study_result(row: dict[str, Any], condition: str):
    ablation = (
        "full"
        if condition in {
            "calibrated_confidence",
            "terse_calibrated",
            "structured_calibrated",
            "full_framework",
        }
        else "without_calibration"
    )
    result = get_engine().recommend(
        row,
        get_engine().default_rules,
        str(row["Intent"]),
        ablation=ablation,
    )
    presentation = {
        "raw_uncalibrated": "raw",
        "calibrated_confidence": "confidence_only",
        "structured_uncalibrated": "structured",
        "terse_calibrated": "terse",
        "structured_calibrated": "structured_no_caveat",
        "full_framework": "structured",
    }[condition]
    return result, presentation


@app.get("/api/human-study/cases")
def human_study_cases(
    participant_code: Annotated[str, Query(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")],
    _: Annotated[User, Depends(require_study_user)], db: Db,
) -> dict[str, Any]:
    participant_code = participant_code.upper()
    rows = frozen_study_rows(); rng = random.Random(int(hashlib.sha256(participant_code.encode()).hexdigest()[:16], 16)); rng.shuffle(rows)
    existing_response = db.scalar(
        select(HumanStudyResponse)
        .where(HumanStudyResponse.participant_code == participant_code)
        .limit(1)
    )
    completed = set(db.scalars(select(HumanStudyResponse.campaign_id).where(HumanStudyResponse.participant_code == participant_code)).all())
    start, counterbalance_group = study_assignment(participant_code)
    cases = []
    for index, row in enumerate(rows):
        if row["Campaign_ID"] in completed:
            continue
        presentation_order = index + 1
        condition = STUDY_CONDITIONS[(index + start) % len(STUDY_CONDITIONS)]
        result, presentation = study_result(row, condition)
        cases.append({
            "study_token": make_study_token(
                participant_code,
                str(row["Campaign_ID"]),
                presentation_order,
                counterbalance_group,
            ),
            "case_id": row["Campaign_ID"], "campaign_type": row["Campaign_Type"],
            "channels": row["Channel_Used"], "intent": row["Intent"], "roi": row["ROI"],
            "conversion_rate": row["conversion_rate"], "engagement_score": row["Engagement_Score"],
            "action": result.action, "confidence": result.confidence, "confidence_level": result.confidence_level,
            "presentation": presentation,
            "terse_features": (
                [
                    f"{str(item['feature']).replace('_', ' ')} "
                    f"({float(item['contribution']):.2f})"
                    for item in result.attribution[:3]
                ]
                if presentation == "terse"
                else None
            ),
            "raw_explanation": (
                f"{result.action}: {result.explanation['driver']} "
                f"{result.explanation['implication']}"
                if presentation == "raw"
                else None
            ),
            "explanation": (
                result.explanation
                if presentation in {"structured", "structured_no_caveat"}
                else None
            ),
        })
    return {
        "participant_code": participant_code,
        "participant_group": (
            existing_response.participant_group if existing_response else None
        ),
        "completed": len(completed),
        "total": len(rows),
        "cases": cases,
    }


@app.post("/api/human-study/responses", status_code=201)
def submit_human_study(
    payload: HumanStudyInput,
    _: Annotated[User, Depends(require_study_user)],
    db: Db,
) -> dict[str, Any]:
    if not payload.consent:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Participant consent is required")
    (
        participant_code,
        campaign_id,
        presentation_order,
        counterbalance_group,
    ) = study_token_data(payload.study_token)
    if participant_code != payload.participant_code.upper():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Participant code does not match this study case")
    existing_response = db.scalar(
        select(HumanStudyResponse)
        .where(HumanStudyResponse.participant_code == participant_code)
        .limit(1)
    )
    if (
        existing_response
        and existing_response.participant_group != payload.participant_group
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Participant group must remain unchanged when resuming the study",
        )
    rows = frozen_study_rows()
    rng = random.Random(
        int(hashlib.sha256(participant_code.encode()).hexdigest()[:16], 16)
    )
    rng.shuffle(rows)
    if not 1 <= presentation_order <= len(rows):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Study case not found")
    row = rows[presentation_order - 1]
    expected_start, expected_group = study_assignment(participant_code)
    if (
        str(row["Campaign_ID"]) != campaign_id
        or counterbalance_group != expected_group
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Study assignment does not match this participant")
    condition = STUDY_CONDITIONS[
        (presentation_order - 1 + expected_start) % len(STUDY_CONDITIONS)
    ]
    result, _ = study_result(row, condition)
    record = HumanStudyResponse(
        participant_code=participant_code,
        participant_group=payload.participant_group,
        campaign_id=campaign_id,
        condition=condition,
        presentation_order=presentation_order,
        counterbalance_group=counterbalance_group,
        recommended_action=result.action, confidence=result.confidence,
        correct=result.action == row["model_label"], low_confidence=result.confidence < .5,
        actionability=payload.actionability,
        specificity=payload.specificity,
        feasibility=payload.feasibility,
        explanation_usefulness=payload.explanation_usefulness,
        reliance=payload.reliance,
        willingness_to_review=payload.willingness_to_review,
        user_acceptance=payload.user_acceptance,
        decision=payload.decision,
        decision_time_ms=payload.decision_time_ms,
        consent_confirmed=True,
        comments=payload.comments,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This participant already evaluated the study case")
    return {"id": record.id, "recorded": True}


@app.get("/api/human-study/summary")
def human_study_summary(_: Annotated[User, Depends(require_admin)], db: Db) -> dict[str, Any]:
    rows = list(db.scalars(select(HumanStudyResponse).order_by(HumanStudyResponse.id)).all())
    return {
        "overall": human_study_statistics(rows),
        "conditions": {
            condition: human_study_statistics(
                [row for row in rows if row.condition == condition]
            )
            for condition in STUDY_CONDITIONS
        },
    }


@app.get("/api/human-study/export.csv")
def export_human_study(
    _: Annotated[User, Depends(require_admin)],
    db: Db,
) -> Response:
    rows = list(
        db.scalars(
            select(HumanStudyResponse).order_by(
                HumanStudyResponse.participant_code,
                HumanStudyResponse.presentation_order,
            )
        ).all()
    )
    fields = [
        "Participant_Code",
        "Participant_Group",
        "Campaign_ID",
        "Condition",
        "Presentation_Order",
        "Counterbalance_Group",
        "Recommended_Action",
        "Calibrated_or_Raw_Confidence",
        "Reference_Agreement",
        "Low_Confidence",
        "Actionability",
        "Specificity",
        "Feasibility",
        "Explanation_Usefulness",
        "Willingness_to_Act",
        "Willingness_to_Review",
        "User_Acceptance",
        "Managerial_Decision",
        "Decision_Time_Seconds",
        "Consent_Confirmed",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "Participant_Code": row.participant_code,
            "Participant_Group": row.participant_group,
            "Campaign_ID": row.campaign_id,
            "Condition": row.condition,
            "Presentation_Order": row.presentation_order,
            "Counterbalance_Group": row.counterbalance_group,
            "Recommended_Action": row.recommended_action,
            "Calibrated_or_Raw_Confidence": f"{row.confidence:.6f}",
            "Reference_Agreement": int(row.correct),
            "Low_Confidence": int(row.low_confidence),
            "Actionability": row.actionability,
            "Specificity": row.specificity,
            "Feasibility": row.feasibility,
            "Explanation_Usefulness": row.explanation_usefulness,
            "Willingness_to_Act": row.reliance,
            "Willingness_to_Review": row.willingness_to_review,
            "User_Acceptance": row.user_acceptance,
            "Managerial_Decision": row.decision,
            "Decision_Time_Seconds": f"{row.decision_time_ms / 1000:.3f}",
            "Consent_Confirmed": int(row.consent_confirmed),
        })
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                "attachment; filename=human_study_anonymised_responses.csv"
            )
        },
    )


@app.get("/api/rules")
def rules(_: CurrentUser, db: Db) -> list[dict[str, Any]]:
    return [rule_json(rule) for rule in db.scalars(select(BusinessRule).order_by(BusinessRule.priority.desc(), BusinessRule.id)).all()]


@app.post("/api/rules", status_code=201)
def create_rule(payload: RuleCreateInput, _: Annotated[User, Depends(require_admin)], db: Db) -> dict[str, Any]:
    definition = {
        "kind": "threshold", "metric": payload.metric, "operator": payload.operator,
        "threshold": payload.threshold, "action": payload.action, "intent": payload.intent,
    }
    encoded = json.dumps(definition, sort_keys=True, separators=(",", ":"))
    code = "custom_" + hashlib.sha256(encoded.encode()).hexdigest()[:16]
    if db.scalar(select(BusinessRule.id).where(BusinessRule.code == code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An equivalent rule already exists")
    intent = db.scalar(select(Intent).where(Intent.name == payload.intent)) if payload.intent else None
    category = "Intent" if payload.intent else "Cost" if payload.metric in {"Revenue", "Acquisition_Cost", "cost_per_conversion", "budget"} else "Performance"
    rule = BusinessRule(
        code=code, name=payload.name, category=category, condition=encoded,
        weight=payload.weight, priority=payload.priority, active=payload.active,
        intent_id=intent.id if intent else None,
    )
    db.add(rule); db.commit()
    return rule_json(rule)


@app.patch("/api/rules/{rule_id}")
def update_rule(rule_id: int, payload: RuleInput, _: Annotated[User, Depends(require_admin)], db: Db) -> dict[str, Any]:
    rule = db.get(BusinessRule, rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    rule.name, rule.weight, rule.priority, rule.active = payload.name, payload.weight, payload.priority, payload.active
    db.commit()
    return rule_json(rule)


def run_metric_row(
    label: str,
    metrics: dict[str, dict[str, float]],
    system_name: str,
) -> dict[str, Any]:
    return {"System": label, **metrics[system_name]}


def constraint_reversal_rate() -> float | None:
    if not CONFIRMATORY_PREDICTIONS.exists():
        return None
    frame = pd.read_csv(CONFIRMATORY_PREDICTIONS)
    required = {"Campaign_ID", "Seed", "System", "Prediction"}
    if not required.issubset(frame.columns):
        return None
    full = frame[
        frame.System.eq("Proposed System - Full Framework")
    ][["Campaign_ID", "Seed", "Prediction"]].rename(
        columns={"Prediction": "constrained"}
    )
    no_rules = frame[
        frame.System.eq("Proposed Ablation - Without Rules")
    ][["Campaign_ID", "Seed", "Prediction"]].rename(
        columns={"Prediction": "unconstrained"}
    )
    paired = full.merge(no_rules, on=["Campaign_ID", "Seed"], how="inner")
    if paired.empty:
        return None
    return float((paired.constrained != paired.unconstrained).mean())


def experiment_blocks(
    metrics: dict[str, dict[str, float]],
    study_rows: list[HumanStudyResponse],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    participant_count = len({row.participant_code for row in study_rows})
    response_count = len(study_rows)
    completed_participants = sum(
        count >= 9
        for count in pd.Series(
            [row.participant_code for row in study_rows]
        ).value_counts().tolist()
    ) if study_rows else 0
    human_complete = completed_participants >= 18
    human_status = "complete" if human_complete else "pending_participants"
    human_detail = (
        f"{completed_participants} complete participants; "
        f"{response_count} responses recorded"
    )
    audit = (
        json.loads(BENCHMARK_AUDIT.read_text(encoding="utf-8"))
        if BENCHMARK_AUDIT.exists()
        else {}
    )
    full_name = "Proposed System - Full Framework"
    without_calibration = "Proposed Ablation - Without Calibration"
    without_rules = "Proposed Ablation - Without Rules"
    without_intent = "Proposed Ablation - Without Intent"
    posthoc = (
        "Post-hoc Hard-Rule Filter"
        if "Post-hoc Hard-Rule Filter" in metrics
        else "Baseline D - Post-Hoc Rule Overlay"
    )
    runs = [
        {
            "id": "R001",
            "name": "Source audit and benchmark freeze",
            "status": "complete",
            "detail": (
                f"{audit.get('cases', 125)} audited cases; action kappa "
                f"{audit.get('action_kappa', 0):.3f}"
            ),
        },
        {
            "id": "R002",
            "name": "Baseline decision-performance comparison",
            "status": "complete",
            "detail": "Chronological three-seed technical evaluation complete",
        },
        {
            "id": "R003",
            "name": "Calibration and appropriate-reliance study",
            "status": human_status,
            "detail": (
                "Technical ECE comparison complete; " + human_detail
            ),
        },
        {
            "id": "R004",
            "name": "Logic-constrained consistency experiment",
            "status": "complete",
            "detail": "No-logic, post-hoc and weighted-rule comparisons available",
        },
        {
            "id": "R005",
            "name": "Intent-conditioning experiment",
            "status": (
                "complete" if human_complete else "technical_complete_human_pending"
            ),
            "detail": "Technical scenario-fit comparison complete; " + human_detail,
        },
        {
            "id": "R006",
            "name": "Explanation-template experiment",
            "status": human_status,
            "detail": human_detail,
        },
    ]
    condition_stats = {
        condition: human_study_statistics(
            [row for row in study_rows if row.condition == condition]
        )
        for condition in STUDY_CONDITIONS
    }
    blocks = {
        "R001": {
            "source_records": 55555,
            "benchmark_cases": audit.get("cases", 125),
            "intent_kappa": audit.get("intent_kappa"),
            "action_kappa": audit.get("action_kappa"),
            "provenance_complete": audit.get("provenance_complete", False),
        },
        "R003": {
            "systems": [
                run_metric_row(
                    "H1: Raw-Uncalibrated",
                    metrics,
                    without_calibration,
                ),
                run_metric_row(
                    "H6: Complete Calibrated DIAC",
                    metrics,
                    full_name,
                ),
            ],
            "participant_status": human_status,
            "completed_participants": completed_participants,
            "target_participants": 18,
            "conditions": {
                condition: condition_stats[condition]
                for condition in (
                    "raw_uncalibrated",
                    "calibrated_confidence",
                    "structured_uncalibrated",
                    "full_framework",
                )
            },
        },
        "R004": {
            "systems": [
                run_metric_row("A1: Full Method without Rules", metrics, without_rules),
                run_metric_row("Post-hoc Hard-Rule Filter", metrics, posthoc),
                run_metric_row("P: Full Proposed Method", metrics, full_name),
            ],
            "reversal_rate": constraint_reversal_rate(),
            "active_rule_count": len(DEFAULT_RULES),
        },
        "R005": {
            "systems": [
                run_metric_row("A2: Full Method without Intent", metrics, without_intent),
                run_metric_row(
                    "A3: Full Method without Calibration",
                    metrics,
                    without_calibration,
                ),
                run_metric_row("P: Full Proposed Method", metrics, full_name),
            ],
            "participant_status": human_status,
        },
        "R006": {
            "participant_status": human_status,
            "completed_participants": completed_participants,
            "target_participants": 18,
            "conditions": {
                condition: condition_stats[condition]
                for condition in (
                    "terse_calibrated",
                    "structured_calibrated",
                    "full_framework",
                )
            },
        },
        "participant_count": participant_count,
    }
    return runs, blocks


@app.get("/api/evaluation/summary")
def evaluation_summary(_: CurrentUser, db: Db) -> dict[str, Any]:
    audited_exists = AUDITED_BENCHMARK.exists()
    study_rows = list(db.scalars(select(HumanStudyResponse)).all())
    if audited_exists and CONFIRMATORY_RESULTS.exists():
        result = json.loads(CONFIRMATORY_RESULTS.read_text(encoding="utf-8"))
        metrics = result["metrics"]
        intervals = result["confidence_intervals_95"]
        proposed_name = "Proposed System - Full Framework"
        baseline_names = [
            name for name in metrics
            if name.startswith(
                (
                    "B0:",
                    "B1:",
                    "B2:",
                    "B3:",
                    "B4:",
                    "Post-hoc",
                    "Intent-Only Deterministic",
                    "Weighted Deterministic",
                    "Unconstrained AI",
                )
            )
        ]
        ablation_names = [name for name in metrics if name.startswith("Proposed Ablation")]
        runs, blocks = experiment_blocks(metrics, study_rows)
        supplemental = (
            json.loads(SUPPLEMENTAL_RESULTS.read_text(encoding="utf-8"))
            if SUPPLEMENTAL_RESULTS.exists()
            else None
        )
        return {
            "status": "confirmatory_technical_complete",
            "message": (
                "The frozen 125-case human-audited benchmark has been evaluated on "
                "a chronological held-out test partition. Technical metrics and "
                "bootstrap intervals are available; participant-based reliance "
                "metrics remain pending the blinded human study."
            ),
            "dataset": "audited_benchmark",
            "source_records": 55555,
            "processed_records": len(pd.read_csv(DATASET)) if DATASET.exists() else 0,
            "candidate_benchmark_records": len(pd.read_csv(AUDITED_BENCHMARK)),
            "candidate_benchmark_status": "frozen_human_audited",
            "dataset_records": len(pd.read_csv(AUDITED_BENCHMARK)),
            "target_records": 125,
            "configuration": result["metadata"]["split"],
            "synthetic_development_records": (
                len(pd.read_csv(SYNTHETIC_DEVELOPMENT))
                if SYNTHETIC_DEVELOPMENT.exists()
                else 0
            ),
            "human_provided_development_records": (
                len(pd.read_csv(HUMAN_PROVIDED_DEVELOPMENT))
                if HUMAN_PROVIDED_DEVELOPMENT.exists()
                else 0
            ),
            "development_annotation_status": get_engine().annotation_status,
            "decision_cases": len(pd.read_csv(AUDITED_BENCHMARK)),
            "audited_benchmark_present": True,
            "calibration_status": get_engine().calibration_status,
            "baselines": [
                {
                    "Baseline": name,
                    **metrics[name],
                    "Confidence Intervals": intervals[name],
                }
                for name in baseline_names
            ],
            "proposed": metrics[proposed_name],
            "proposed_ci": intervals[proposed_name],
            "ablations": {name: metrics[name] for name in ablation_names},
            "ablation_ci": {name: intervals[name] for name in ablation_names},
            "protocol": {
                "seed": ", ".join(map(str, result["metadata"]["seeds"])),
                "test_cases": result["metadata"]["test_records"],
                "label_source": "frozen human-adjudicated benchmark",
                "identical_holdout": True,
                "ruleset": "predeclared shared conflict catalogue",
            },
            "benchmark": {
                "ground_truth_conflict_rate": result["metadata"].get(
                    "ground_truth_conflict_rate", 0.0
                )
            },
            "evaluation_metadata": result["metadata"],
            "human_evaluation": human_study_statistics(study_rows),
            "runs": runs,
            "experiment_blocks": blocks,
            "supplemental_evaluation": supplemental,
        }
    return {
        "status": "pending_human_annotations",
        "message": (
            "The raw and processed data layers are active. The supplied 125 cases "
            "remain benchmark candidates because their intent/action schema and review "
            "provenance do not satisfy the locked protocol. Confirmatory evaluation and "
            "calibration remain locked until independent plan-aligned review, "
            "adjudication and data/benchmark_audited.csv are complete."
        ),
        "dataset": "audited_benchmark",
        "source_records": 55555,
        "processed_records": (
            len(pd.read_csv(DATASET))
            if DATASET.exists()
            else 0
        ),
        "candidate_benchmark_records": (
            len(pd.read_csv(BENCHMARK_CANDIDATE))
            if BENCHMARK_CANDIDATE.exists()
            else 0
        ),
        "candidate_benchmark_status": "requires_independent_reannotation",
        "synthetic_development_records": (
            len(pd.read_csv(SYNTHETIC_DEVELOPMENT))
            if SYNTHETIC_DEVELOPMENT.exists()
            else 0
        ),
        "human_provided_development_records": (
            len(pd.read_csv(HUMAN_PROVIDED_DEVELOPMENT))
            if HUMAN_PROVIDED_DEVELOPMENT.exists()
            else 0
        ),
        "development_annotation_status": get_engine().annotation_status,
        "decision_cases": len(pd.read_csv(DECISION_CASES)),
        "audited_benchmark_present": audited_exists,
        "calibration_status": get_engine().calibration_status,
        "baselines": [],
        "proposed": {},
        "proposed_ci": {},
        "ablations": {},
        "ablation_ci": {},
        "human_evaluation": human_study_statistics(study_rows),
        "runs": [],
        "experiment_blocks": {},
        "supplemental_evaluation": None,
    }
