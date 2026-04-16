from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models import (
    User,
    Role,
    Team,
    TeamGroup,
    Submission,
    RubricItem,
    Score,
    ScoreItem,
    ScoreStatus,
)

from app.security import hash_password


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, username: str, password_hash: str, role: Role) -> User:
    user = User(username=username, password_hash=password_hash, role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ===== Superadmin: user management (paged + filters) =====

def _norm_kw(s: str | None) -> str:
    return (s or "").strip()


def list_users_by_role_paged(
    db: Session,
    role: Role,
    username_kw: str | None,
    page: int,
    page_size: int,
) -> tuple[list[User], int]:
    page = max(int(page), 1)
    page_size = min(max(int(page_size), 1), 200)

    kw = _norm_kw(username_kw)

    stmt = select(User).where(User.role == role)
    cnt_stmt = select(func.count()).select_from(User).where(User.role == role)

    if kw:
        stmt = stmt.where(User.username.like(f"%{kw}%"))
        cnt_stmt = cnt_stmt.where(User.username.like(f"%{kw}%"))

    stmt = stmt.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)

    items = list(db.scalars(stmt))
    total = int(db.scalar(cnt_stmt) or 0)
    return items, total


def list_students_with_team_paged(
    db: Session,
    username_kw: str | None,
    leader_name_kw: str | None,
    page: int,
    page_size: int,
) -> tuple[list[tuple[User, Team | None]], int]:
    """
    返回 (student_user, team_or_none) 的分页结果。
    Team 通过 Team.leader_user_id == User.id 关联（队长账号）。
    """
    page = max(int(page), 1)
    page_size = min(max(int(page_size), 1), 200)

    u_kw = _norm_kw(username_kw)
    l_kw = _norm_kw(leader_name_kw)

    base = (
        select(User, Team)
        .outerjoin(Team, Team.leader_user_id == User.id)
        .where(User.role == Role.student)
    )

    cnt = (
        select(func.count())
        .select_from(User)
        .outerjoin(Team, Team.leader_user_id == User.id)
        .where(User.role == Role.student)
    )

    if u_kw:
        base = base.where(User.username.like(f"%{u_kw}%"))
        cnt = cnt.where(User.username.like(f"%{u_kw}%"))

    if l_kw:
        base = base.where(Team.leader_name.like(f"%{l_kw}%"))
        cnt = cnt.where(Team.leader_name.like(f"%{l_kw}%"))

    base = base.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)

    rows = list(db.execute(base).all())
    total = int(db.scalar(cnt) or 0)
    return [(r[0], r[1]) for r in rows], total


def create_teacher_user(db: Session, username: str, password: str) -> tuple[bool, str | None]:
    username = (username or "").strip()
    if not username:
        return False, "用户名不能为空"

    existing = db.scalar(select(User).where(User.username == username))
    if existing:
        return False, "用户名已存在"

    u = User(
        username=username,
        password_hash=hash_password(password),
        role=Role.teacher,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return True, None


def reset_user_password(db: Session, user_id: int, new_password: str) -> tuple[bool, str | None]:
    u = db.get(User, user_id)
    if not u:
        return False, "用户不存在"

    u.password_hash = hash_password(new_password)
    db.commit()
    return True, None


def toggle_user_active(
    db: Session,
    acting_user_id: int,
    target_user_id: int,
) -> tuple[bool, str | None]:
    u = db.get(User, target_user_id)
    if not u:
        return False, "用户不存在"

    # 防止管理员把自己停用导致无法登录
    if u.id == acting_user_id and u.is_active:
        return False, "不能停用当前登录的管理员账号"

    u.is_active = not u.is_active
    db.commit()
    return True, None


def get_team_by_leader(db: Session, leader_user_id: int) -> Team | None:
    return db.scalar(select(Team).where(Team.leader_user_id == leader_user_id))


def create_or_update_team(
    db: Session,
    leader_user_id: int,
    group: str,
    work_name: str,
    leader_name: str,
    school_name: str,
    college_major: str,
    phone: str,
    member1_name: str,
    member1_college: str,
    member1_major: str,
    member2_name: str,
    member2_college: str,
    member2_major: str,
    member3_name: str,
    member3_college: str,
    member3_major: str,
    advisor_name: str | None,
    advisor_college: str | None,
    advisor_phone: str | None,
) -> Team:
    team = get_team_by_leader(db, leader_user_id)
    if team is None:
        team = Team(leader_user_id=leader_user_id)
        db.add(team)

    team.group = TeamGroup(group)

    team.work_name = work_name
    team.leader_name = leader_name
    team.school_name = school_name
    team.college_major = college_major
    team.phone = phone

    team.member1_name = member1_name
    team.member1_college = member1_college
    team.member1_major = member1_major

    team.member2_name = member2_name
    team.member2_college = member2_college
    team.member2_major = member2_major

    team.member3_name = member3_name
    team.member3_college = member3_college
    team.member3_major = member3_major

    team.advisor_name = advisor_name
    team.advisor_college = advisor_college
    team.advisor_phone = advisor_phone

    db.commit()
    db.refresh(team)
    return team


def get_submission_by_team(db: Session, team_id: int) -> Submission | None:
    return db.scalar(select(Submission).where(Submission.team_id == team_id))


def create_or_update_submission_pdf(
    db: Session,
    team_id: int,
    paper_pdf_anonymous_path: str | None,
    plagiarism_report_path: str | None = None,
) -> Submission:
    sub = get_submission_by_team(db, team_id)
    if sub is None:
        sub = Submission(team_id=team_id, submitted_at=datetime.utcnow())
        db.add(sub)

    if paper_pdf_anonymous_path is not None:
        sub.paper_pdf_anonymous_path = paper_pdf_anonymous_path

    if plagiarism_report_path is not None:
        sub.plagiarism_report_path = plagiarism_report_path

    sub.submitted_at = datetime.utcnow()
    db.commit()
    db.refresh(sub)
    return sub


# ---------------- Rubric ----------------

def list_active_rubric_items(db: Session) -> list[RubricItem]:
    return list(
        db.scalars(
            select(RubricItem)
            .where(RubricItem.is_active == True)
            .order_by(RubricItem.order, RubricItem.id)
        )
    )


def list_all_rubric_items(db: Session) -> list[RubricItem]:
    return list(
        db.scalars(
            select(RubricItem)
            .order_by(RubricItem.is_active.desc(), RubricItem.order, RubricItem.id)
        )
    )


def create_rubric_item(db: Session, name: str, max_score: float, order: int) -> RubricItem:
    item = RubricItem(name=name, max_score=max_score, order=order, is_active=True)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_rubric_item(db: Session, item_id: int, name: str, max_score: float, order: int, is_active: bool) -> RubricItem:
    item = db.get(RubricItem, item_id)
    if item is None:
        raise ValueError("Rubric item not found")

    item.name = name
    item.max_score = max_score
    item.order = order
    item.is_active = is_active

    db.commit()
    db.refresh(item)
    return item


def set_rubric_item_active(db: Session, item_id: int, is_active: bool) -> RubricItem:
    item = db.get(RubricItem, item_id)
    if item is None:
        raise ValueError("Rubric item not found")
    item.is_active = is_active
    db.commit()
    db.refresh(item)
    return item


# ---------------- Scoring ----------------

def list_submissions_with_team(db: Session) -> list[tuple[Submission, Team]]:
    stmt = select(Submission, Team).join(Team, Submission.team_id == Team.id).order_by(Submission.id.desc())
    rows = list(db.execute(stmt).all())
    return [(r[0], r[1]) for r in rows]


def get_or_create_score(db: Session, submission_id: int, teacher_user_id: int) -> Score:
    s = db.scalar(
        select(Score).where(
            Score.submission_id == submission_id,
            Score.teacher_user_id == teacher_user_id,
        )
    )
    if s:
        return s

    s = Score(submission_id=submission_id, teacher_user_id=teacher_user_id, total_score=0.0, status=ScoreStatus.draft)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def set_score_items(
    db: Session,
    score: Score,
    points_map: dict[int, float],
    comment: str | None,
    status: ScoreStatus,
):
    # 更新 comment/status
    score.comment = comment
    score.status = status

    # 重新写 score_items
    score.items.clear()
    total = 0.0
    for rubric_item_id, points in points_map.items():
        total += float(points or 0.0)
        score.items.append(ScoreItem(score_id=score.id, rubric_item_id=rubric_item_id, points=float(points or 0.0)))
    score.total_score = total

    db.commit()
    db.refresh(score)
    return score


def get_teacher_scores_map_for_submission(db: Session, submission_id: int) -> dict[int, Score]:
    stmt = select(Score).where(Score.submission_id == submission_id)
    scores = list(db.scalars(stmt))
    return {s.teacher_user_id: s for s in scores}


def get_average_score_for_submission(db: Session, submission_id: int) -> float | None:
    stmt = select(Score).where(
        Score.submission_id == submission_id,
        Score.status == ScoreStatus.submitted,
    )
    scores = list(db.scalars(stmt))
    if not scores:
        return None
    return float(sum(s.total_score for s in scores) / len(scores))