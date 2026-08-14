from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="manager")
    organisation: Mapped[str] = mapped_column(String(100), default="SME Marketing Lab")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Intent(Base):
    __tablename__ = "intents"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)
    description: Mapped[str] = mapped_column(Text)


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    intent_id: Mapped[int] = mapped_column(ForeignKey("intents.id"))
    name: Mapped[str] = mapped_column(String(100))
    campaign_type: Mapped[str] = mapped_column(String(50))
    target_audience: Mapped[str] = mapped_column(String(100), default="General")
    duration: Mapped[int] = mapped_column(Integer, default=21)
    channels: Mapped[str] = mapped_column(String(255))
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    leads: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0)
    acquisition_cost: Mapped[float] = mapped_column(Float, default=0)
    roi: Mapped[float] = mapped_column(Float, default=0)
    engagement_score: Mapped[float] = mapped_column(Float, default=0)
    customer_segment: Mapped[str] = mapped_column(String(100), default="General")
    language: Mapped[str] = mapped_column(String(50), default="English")
    campaign_date: Mapped[date] = mapped_column(Date, default=date.today)
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Review")
    intent: Mapped[Intent] = relationship()


class BusinessRule(Base):
    __tablename__ = "business_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    intent_id: Mapped[int | None] = mapped_column(ForeignKey("intents.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(30))
    condition: Mapped[str] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Float)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"))
    intent_id: Mapped[int] = mapped_column(ForeignKey("intents.id"))
    action: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    raw_confidence: Mapped[float] = mapped_column(Float)
    performance_score: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
    ranked_actions: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(50), default="full_framework")
    latency_ms: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(20), default="Pending")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    campaign: Mapped[Campaign] = relationship()
    intent: Mapped[Intent] = relationship()


class RecommendationRule(Base):
    __tablename__ = "recommendation_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"))
    rule_id: Mapped[int] = mapped_column(ForeignKey("business_rules.id"))
    score: Mapped[float] = mapped_column(Float)
    triggered: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[str] = mapped_column(Text)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"))
    actionability: Mapped[float] = mapped_column(Float)
    trust_alignment: Mapped[float] = mapped_column(Float)
    explanation_usefulness: Mapped[float] = mapped_column(Float)
    user_acceptance: Mapped[float] = mapped_column(Float)
    comments: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HumanStudyResponse(Base):
    __tablename__ = "human_study_responses"
    __table_args__ = (UniqueConstraint("participant_code", "campaign_id", name="uq_study_participant_case"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    participant_code: Mapped[str] = mapped_column(String(40), index=True)
    participant_group: Mapped[str] = mapped_column(String(30), default="Non-practitioner")
    campaign_id: Mapped[str] = mapped_column(String(20))
    condition: Mapped[str] = mapped_column(String(30))
    presentation_order: Mapped[int] = mapped_column(Integer)
    counterbalance_group: Mapped[str] = mapped_column(String(20))
    recommended_action: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    correct: Mapped[bool] = mapped_column(Boolean)
    low_confidence: Mapped[bool] = mapped_column(Boolean)
    actionability: Mapped[float] = mapped_column(Float)
    specificity: Mapped[float] = mapped_column(Float)
    feasibility: Mapped[float] = mapped_column(Float)
    explanation_usefulness: Mapped[float] = mapped_column(Float)
    reliance: Mapped[float] = mapped_column(Float)
    willingness_to_review: Mapped[float] = mapped_column(Float)
    user_acceptance: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(30))
    decision_time_ms: Mapped[float] = mapped_column(Float)
    consent_confirmed: Mapped[bool] = mapped_column(Boolean)
    comments: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
