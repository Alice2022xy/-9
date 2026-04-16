from __future__ import annotations

from io import BytesIO
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import Submission, Team, Score, User, ScoreStatus, TeamGroup


def _build_scores_dataframe(db: Session, group: TeamGroup | None = None) -> pd.DataFrame:
    q = select(Submission, Team).join(Team, Submission.team_id == Team.id)
    if group is not None:
        q = q.where(Team.group == group)
    submissions = db.execute(q).all()

    teachers = list(db.scalars(select(User).where(User.role == "teacher").order_by(User.id)))

    data_rows = []
    for sub, team in submissions:
        row = {
            "组别": "本科组" if team.group == TeamGroup.undergrad else "研究生组",
            "submission_id": sub.id,
            "作品名称": team.work_name,
            "负责人": team.leader_name,
            "学校": team.school_name,
            "学院及专业": team.college_major,
            "手机": team.phone,

            "参赛成员1": team.member1_name,
            "参赛成员1学院": team.member1_college,
            "参赛成员1专业": team.member1_major,

            "参赛成员2": team.member2_name,
            "参赛成员2学院": team.member2_college,
            "参赛成员2专业": team.member2_major,

            "参赛成员3": team.member3_name,
            "参赛成员3学院": team.member3_college,
            "参赛成员3专业": team.member3_major,

            "指导老师姓名": team.advisor_name,
            "指导老师学院": team.advisor_college,
            "指导老师手机": team.advisor_phone,

            # 仅保留：匿名PDF
            "paper_pdf_anonymous_path": sub.paper_pdf_anonymous_path,

            "submitted_at": sub.submitted_at,
        }

        totals = []
        for t in teachers:
            score = db.scalar(
                select(Score).where(
                    Score.submission_id == sub.id,
                    Score.teacher_user_id == t.id,
                )
            )
            col_total = f"{t.username}_total"
            col_status = f"{t.username}_status"
            col_comment = f"{t.username}_comment"

            row[col_total] = score.total_score if score else None
            row[col_status] = score.status.value if score else None
            row[col_comment] = score.comment if score else None

            if score and score.status == ScoreStatus.submitted:
                totals.append(score.total_score)

        row["avg_score_submitted"] = (sum(totals) / len(totals)) if totals else None
        data_rows.append(row)

    return pd.DataFrame(data_rows)


def export_all_scores_excel(
    db: Session,
    group: str | None = None,      # undergrad/postgrad/None
    split_sheets: bool = False,    # True => 本科组/研究生组 两个sheet
) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        if split_sheets:
            df_u = _build_scores_dataframe(db, group=TeamGroup.undergrad)
            df_g = _build_scores_dataframe(db, group=TeamGroup.postgrad)
            df_u.to_excel(writer, index=False, sheet_name="本科组")
            df_g.to_excel(writer, index=False, sheet_name="研究生组")
        else:
            grp_enum = TeamGroup(group) if group else None
            df = _build_scores_dataframe(db, group=grp_enum)
            sheet = "scores"
            if grp_enum == TeamGroup.undergrad:
                sheet = "本科组"
            elif grp_enum == TeamGroup.postgrad:
                sheet = "研究生组"
            df.to_excel(writer, index=False, sheet_name=sheet)

    return bio.getvalue()