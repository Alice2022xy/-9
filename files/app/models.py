import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Enum,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    Float,
    Text,
)
from sqlalchemy.orm import relationship

from app.db import Base


class Role(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    superadmin = "superadmin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(Role), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TeamGroup(str, enum.Enum):
    undergrad = "undergrad"   # 本科组
    postgrad = "postgrad"     # 研究生组


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    leader_user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # 参赛组别
    group = Column(Enum(TeamGroup), nullable=False, default=TeamGroup.undergrad, index=True)

    # 学生端填写字段
    work_name = Column(String(500), nullable=False)        # 作品名称
    leader_name = Column(String(200), nullable=False)      # 负责人
    school_name = Column(String(200), nullable=False)      # 学校
    college_major = Column(String(500), nullable=False)    # 学院及专业
    phone = Column(String(50), nullable=False)             # 手机

    member1_name = Column(String(200), nullable=False)
    member1_college = Column(String(200), nullable=False)
    member1_major = Column(String(200), nullable=False)

    member2_name = Column(String(200), nullable=False)
    member2_college = Column(String(200), nullable=False)
    member2_major = Column(String(200), nullable=False)

    member3_name = Column(String(200), nullable=False)
    member3_college = Column(String(200), nullable=False)
    member3_major = Column(String(200), nullable=False)

    # 指导老师信息（三个字段可选填）
    advisor_name = Column(String(200), nullable=True)
    advisor_college = Column(String(200), nullable=True)
    advisor_phone = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    leader = relationship("User")
    submission = relationship("Submission", back_populates="team", uselist=False)


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), unique=True, nullable=False)

    # 仅保留：论文PDF匿名版
    paper_pdf_anonymous_path = Column(String(500), nullable=True)   # 论文PDF匿名版
    plagiarism_report_path = Column(String(500), nullable=True)     # 查重报告PDF（可选）

    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    team = relationship("Team", back_populates="submission")
    scores = relationship("Score", back_populates="submission")


class RubricItem(Base):
    __tablename__ = "rubric_items"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    max_score = Column(Float, nullable=False, default=10.0)
    order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)


class ScoreStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("submission_id", "teacher_user_id", name="uq_submission_teacher"),
    )

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"), nullable=False, index=True)
    teacher_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    total_score = Column(Float, nullable=False, default=0.0)
    status = Column(Enum(ScoreStatus), nullable=False, default=ScoreStatus.draft)

    # 评语
    comment = Column(Text, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    submission = relationship("Submission", back_populates="scores")
    teacher = relationship("User")
    items = relationship("ScoreItem", back_populates="score", cascade="all, delete-orphan")


class ScoreItem(Base):
    __tablename__ = "score_items"
    __table_args__ = (
        UniqueConstraint("score_id", "rubric_item_id", name="uq_score_rubric_item"),
    )

    id = Column(Integer, primary_key=True)
    score_id = Column(Integer, ForeignKey("scores.id"), nullable=False, index=True)
    rubric_item_id = Column(Integer, ForeignKey("rubric_items.id"), nullable=False, index=True)

    points = Column(Float, nullable=False, default=0.0)

    score = relationship("Score", back_populates="items")
    rubric_item = relationship("RubricItem")