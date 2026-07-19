from __future__ import annotations

import base64
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
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from baseline_evaluation import (
    baseline_a_predict,
    baseline_b_predict,
    baseline_c_predict,
    baseline_d_predict,
    build_channel_attribution,
    conflict_reasons,
    expected_calibration_error,
    fit_centroid_model,
    load_dataset,
    stratified_split,
)

from .database import Base, SessionLocal, engine
from .engine import DEFAULT_RULES, RecommendationEngine, prepare_frame
from .models import BusinessRule, Campaign, Evaluation, Intent, Recommendation, RecommendationRule, User


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data" / "Dataset.csv"
TOKEN_SECRET = os.getenv("TOKEN_SECRET", "change-this-development-secret").encode()
security = HTTPBearer(auto_error=False)
recommendation_engine: RecommendationEngine | None = None


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="MarketSense DSS API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginInput(BaseModel):
    email: str
    password: str


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
    budget: float = Field(default=0, ge=0)
    status: Literal["Active", "Review", "Completed"] = "Review"


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
    action: Literal["Increase", "Maintain", "Decrease", "Investigate"]
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
        "condition": rule_condition(definition) if definition else rule.condition,
        "definition": definition, "weight": rule.weight, "priority": rule.priority, "active": rule.active,
    }


def get_engine() -> RecommendationEngine:
    global recommendation_engine
    if recommendation_engine is None:
        recommendation_engine = RecommendationEngine(DATASET)
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


@app.get("/api/profile")
def profile(user: CurrentUser) -> dict[str, Any]:
    return {"name": user.name, "email": user.email, "role": user.role, "organisation": user.organisation, "created_at": user.created_at}


@app.patch("/api/profile")
def update_profile(payload: ProfileInput, user: CurrentUser, db: Db) -> dict[str, Any]:
    user.name, user.email, user.organisation = payload.name, payload.email, payload.organisation
    db.commit()
    return profile(user)


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
        db.add(Campaign(
            id=campaign_id, user_id=user.id, intent_id=intent.id, name=campaign_id,
            campaign_type=str(value("Campaign_Type", "Unknown")), channels=str(value("Channel_Used", "Unknown")),
            target_audience=str(value("Target_Audience", "General")), duration=int(float(value("Duration"))),
            impressions=int(float(value("Impressions"))), clicks=int(float(value("Clicks"))),
            leads=int(float(value("Leads"))), conversions=int(float(value("Conversions"))),
            revenue=float(value("Revenue")), acquisition_cost=float(value("Acquisition_Cost")),
            roi=float(value("ROI")), engagement_score=float(value("Engagement_Score")),
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
    return {"campaign": campaign_json(item), "performance_score": result.performance_score, "attribution": result.attribution, "channel_attribution": result.channel_attribution}


def recommendation_json(item: Recommendation) -> dict[str, Any]:
    explanation = json.loads(item.explanation)
    return {
        "id": f"REC-{item.id:04d}", "numeric_id": item.id, "campaign_id": item.campaign_id,
        "campaign": item.campaign.name, "intent": item.intent.name, "action": item.action,
        "confidence": round(item.confidence * 100, 1), "raw_confidence": round(item.raw_confidence * 100, 1),
        "performance_score": round(item.performance_score * 100, 1), "explanation": explanation,
        "evidence": json.loads(item.evidence), "ranked_actions": json.loads(item.ranked_actions),
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
        explanation=json.dumps(result.explanation), evidence=json.dumps({"attribution": result.attribution, "channels": result.channel_attribution, "confidence_level": result.confidence_level}),
        ranked_actions=json.dumps(result.ranked_actions), latency_ms=result.latency_ms,
    )
    db.add(record); db.flush()
    for rule_result in result.rule_results:
        if rule_result["action"] == result.action and rule_result.get("id"):
            db.add(RecommendationRule(recommendation_id=record.id, rule_id=rule_result["id"], score=rule_result["score"], triggered=rule_result["triggered"], detail=rule_result["detail"]))
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


ALLOWED_ACTIONS = {
    "Growth": {"Increase", "Maintain"},
    "Retention": {"Increase", "Maintain", "Investigate"},
    "Survival": {"Reduce", "Maintain", "Investigate"},
}


def decision_metrics(rows: list[dict[str, Any]], predictions: list[str], confidences: list[float], labels: list[str], latency_ms: float = 0, explanations: bool = False) -> dict[str, float]:
    correct = [int(prediction == label) for prediction, label in zip(predictions, labels)]
    scenario = [prediction in ALLOWED_ACTIONS[row["Intent"]] for row, prediction in zip(rows, predictions)]
    conflicts = [bool(conflict_reasons(row, prediction)) for row, prediction in zip(rows, predictions)]
    scenario_fit = statistics.fmean(scenario); conflict_rate = statistics.fmean(conflicts)
    return {
        "Recommendation Accuracy": statistics.fmean(correct),
        "Scenario-Fit Rate": scenario_fit,
        "Logical Conflict Rate": conflict_rate,
        "Expected Calibration Error (ECE)": expected_calibration_error(confidences, correct),
        "Recommendation Latency (ms)": latency_ms,
        "Actionability Proxy": .45 * scenario_fit + .35 * (1 - conflict_rate) + .20 * statistics.fmean(confidences),
        "Explanation Usefulness Proxy": 1.0 if explanations else 0.0,
    }


def bootstrap_intervals(rows: list[dict[str, Any]], predictions: list[str], confidences: list[float], labels: list[str], samples: int = 1000) -> dict[str, list[float]]:
    rng = random.Random(42); count = len(rows)
    values: dict[str, list[float]] = {key: [] for key in ("Recommendation Accuracy", "Scenario-Fit Rate", "Logical Conflict Rate", "Expected Calibration Error (ECE)", "Actionability Proxy")}
    for _ in range(samples):
        indices = [rng.randrange(count) for _ in range(count)]
        metrics = decision_metrics([rows[i] for i in indices], [predictions[i] for i in indices], [confidences[i] for i in indices], [labels[i] for i in indices])
        for key in values:
            values[key].append(metrics[key])
    return {key: [float(np.quantile(result, .025)), float(np.quantile(result, .975))] for key, result in values.items()}


def framework_evaluation(variant: str, ruleset: list[dict[str, Any]], test_frame: pd.DataFrame | None = None) -> tuple[dict[str, float], dict[str, list[float]]]:
    service = get_engine(); frame = test_frame if test_frame is not None else service.test
    rows = frame.to_dict("records"); results = [service.recommend(row, ruleset, str(row["Intent"]), ablation=variant) for row in rows]
    predictions = ["Reduce" if result.action == "Decrease" else result.action for result in results]
    labels = ["Reduce" if label == "Decrease" else label for label in frame.model_label]
    confidences = [result.confidence for result in results]
    metrics = decision_metrics(rows, predictions, confidences, labels, statistics.fmean(result.latency_ms for result in results), variant != "backbone")
    return metrics, bootstrap_intervals(rows, predictions, confidences, labels)


def framework_metrics(variant: str, ruleset: list[dict[str, Any]], test_frame: pd.DataFrame | None = None) -> dict[str, float]:
    return framework_evaluation(variant, ruleset, test_frame)[0]


@app.get("/api/evaluation/summary")
def evaluation_summary(_: CurrentUser, db: Db, dataset: Literal["normal", "conflict_stress"] = Query("normal")) -> dict[str, Any]:
    normal_rows = load_dataset(DATASET)
    baseline_train, normal_test = stratified_split(normal_rows, .2, 42)
    evaluation_rows = normal_test if dataset == "normal" else stratified_split(load_dataset(ROOT / "data" / "Dataset_conflict_stress.csv"), .2, 42)[1]
    model = fit_centroid_model(baseline_train); channel_attribution = build_channel_attribution(baseline_train)
    baseline_results = [
        baseline_a_predict(evaluation_rows), baseline_b_predict(evaluation_rows, model),
        baseline_c_predict(evaluation_rows, model, channel_attribution), baseline_d_predict(evaluation_rows, model),
    ]
    baseline_rows = []
    labels = [row["label"] for row in evaluation_rows]
    for baseline in baseline_results:
        metrics = decision_metrics(evaluation_rows, baseline.predictions, baseline.confidences, labels, baseline.latency_ms, bool(baseline.explanations and any(baseline.explanations)))
        baseline_rows.append({"Baseline": baseline.name, **metrics, "Confidence Intervals": bootstrap_intervals(evaluation_rows, baseline.predictions, baseline.confidences, labels)})
    ruleset = [rule_json(rule) for rule in db.scalars(select(BusinessRule)).all()]
    if dataset == "normal":
        evaluation_frame = get_engine().test
    else:
        stress_frame = prepare_frame(ROOT / "data" / "Dataset_conflict_stress.csv")
        _, stress_test = stratified_split(stress_frame.to_dict("records"), .2, 42)
        evaluation_frame = pd.DataFrame(stress_test)
    baseline_ids = {row["Campaign_ID"] for row in evaluation_rows}; proposed_ids = set(evaluation_frame.Campaign_ID)
    if baseline_ids != proposed_ids:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Evaluation protocol produced inconsistent holdout cases")
    proposed, proposed_ci = framework_evaluation("full", ruleset, evaluation_frame)
    ablations = {
        "Without Trust Calibration": framework_metrics("without_calibration", ruleset, evaluation_frame),
        "Without Intent Awareness": framework_metrics("without_intent", ruleset, evaluation_frame),
        "Without Soft-Rule Reasoning": framework_metrics("without_rules", ruleset, evaluation_frame),
        "Backbone Only": framework_metrics("backbone", ruleset, evaluation_frame),
    }
    ground_truth_conflicts = statistics.fmean(bool(conflict_reasons(row, label)) for row, label in zip(evaluation_rows, labels))
    human_count, human_actionability = db.execute(select(func.count(Evaluation.id), func.avg(Evaluation.actionability))).one()
    return {
        "dataset": dataset, "dataset_records": len(get_engine().data), "target_records": 500,
        "configuration": "simplified" if len(get_engine().data) < 500 else "target",
        "protocol": {"seed": 42, "test_cases": len(evaluation_rows), "label_source": "reviewer consensus, otherwise reference action", "identical_holdout": True},
        "benchmark": {"ground_truth_conflict_rate": ground_truth_conflicts},
        "baselines": baseline_rows, "proposed": proposed, "proposed_ci": proposed_ci, "ablations": ablations,
        "human_evaluation": {"responses": human_count, "actionability": float(human_actionability / 5) if human_actionability is not None else None},
    }
