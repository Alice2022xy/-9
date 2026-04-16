from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db, engine, Base
from app.settings import UPLOAD_DIR, DB_USE_ALEMBIC
from app import crud
from app.models import Role, ScoreStatus, TeamGroup
from app.security import (
    hash_password,
    verify_password,
    set_session,
    clear_session,
    get_user_id_from_request,
)
from app.exporting import export_all_scores_excel
from app.upload_utils import validate_suffix, save_upload_with_limit

app = FastAPI(title="全国大学生统计建模大赛——广东工业大学校赛")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

if not DB_USE_ALEMBIC:
    Base.metadata.create_all(bind=engine)


def require_user(request: Request, db: Session):
    user_id = get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401)
    user = crud.get_user(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401)
    return user


def _empty_to_none(s: str | None) -> str | None:
    if s is None:
        return None
    s2 = s.strip()
    return s2 if s2 else None


def _group_label(group: TeamGroup) -> str:
    return "本科组" if group == TeamGroup.undergrad else "研究生组"


def _parse_login_role_from_query(request: Request) -> str:
    role = (request.query_params.get("role") or "").strip().lower()
    if role in ("student", "teacher", "superadmin"):
        return role
    return ""


def _normalize_role(role: str | None) -> str:
    r = (role or "").strip().lower()
    return r if r in ("", "student", "teacher", "superadmin") else ""


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user_id = get_user_id_from_request(request)
    user = crud.get_user(db, user_id) if user_id else None
    return templates.TemplateResponse("home.html", {"request": request, "user": user})


# ---------------- Student Auth (Login+Register in one page) ----------------

@app.get("/student/auth", response_class=HTMLResponse)
def student_auth_get(request: Request):
    mode = (request.query_params.get("mode") or "").strip().lower()
    if mode not in ("", "login", "register"):
        mode = ""
    # mode==register => 默认打开注册 tab；否则打开登录 tab
    return templates.TemplateResponse(
        "student_auth.html",
        {"request": request, "error": None, "mode": "register" if mode == "register" else "login"},
    )


# ---------------- Register ----------------

@app.get("/register", response_class=HTMLResponse)
def register_get(request: Request):
    # 仍保留这个入口（比如用户手动输入 /register），直接跳到二合一页面的注册 tab
    return RedirectResponse(url="/student/auth?mode=register", status_code=302)


@app.post("/register")
def register_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != password2:
        return templates.TemplateResponse(
            "student_auth.html",
            {"request": request, "error": "两次密码不一致", "mode": "register"},
        )

    if crud.get_user_by_username(db, username):
        # 注册失败：回到学生二合一页面，并停在注册 tab
        return templates.TemplateResponse(
            "student_auth.html",
            {"request": request, "error": "用户名已存在", "mode": "register"},
        )

    user = crud.create_user(db, username, hash_password(password), Role.student)
    resp = RedirectResponse(url="/student", status_code=302)
    set_session(resp, user.id)
    return resp


# ---------------- Login ----------------

@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    role = _parse_login_role_from_query(request)

    # 学生登录入口统一走 /student/auth
    if role == "student":
        return RedirectResponse(url="/student/auth", status_code=302)

    return templates.TemplateResponse("login.html", {"request": request, "error": None, "role": role})


@app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(""),  # student/teacher/superadmin or empty
    db: Session = Depends(get_db),
):
    role = _normalize_role(role)

    user = crud.get_user_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        if role == "student":
            return templates.TemplateResponse(
                "student_auth.html",
                {"request": request, "error": "用户名或密码错误", "mode": "login"},
            )
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "用户名或密码错误", "role": role},
        )

    # 按入口角色限制登录
    if role:
        if role == "student" and user.role != Role.student:
            return templates.TemplateResponse(
                "student_auth.html",
                {"request": request, "error": "该入口仅允许学生账号登录", "mode": "login"},
            )
        if role == "teacher" and user.role != Role.teacher:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "该入口仅允许评审专家账号登录", "role": role},
            )
        if role == "superadmin" and user.role != Role.superadmin:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "该入口仅允许管理员账号登录", "role": role},
            )

    resp = RedirectResponse(url="/", status_code=302)
    set_session(resp, user.id)
    return resp


@app.post("/logout")
def logout_post():
    resp = RedirectResponse(url="/", status_code=302)
    clear_session(resp)
    return resp


# ---------------- Student ----------------

@app.get("/student", response_class=HTMLResponse)
def student_dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if user.role != Role.student:
        raise HTTPException(status_code=403)

    team = crud.get_team_by_leader(db, user.id)
    submission = crud.get_submission_by_team(db, team.id) if team else None
    return templates.TemplateResponse(
        "student_dashboard.html",
        {
            "request": request,
            "user": user,
            "team": team,
            "submission": submission,
            "upload_error": None,
            "upload_success": None,
        },
    )


@app.post("/student/team")
def student_team_post(
    request: Request,
    group: str = Form("undergrad"),
    work_name: str = Form(...),
    leader_name: str = Form(...),
    school_name: str = Form(...),
    college_major: str = Form(...),
    phone: str = Form(...),
    member1_name: str = Form(...),
    member1_college: str = Form(...),
    member1_major: str = Form(...),
    member2_name: str = Form(...),
    member2_college: str = Form(...),
    member2_major: str = Form(...),
    member3_name: str = Form(...),
    member3_college: str = Form(...),
    member3_major: str = Form(...),
    advisor_name: str | None = Form(None),
    advisor_college: str | None = Form(None),
    advisor_phone: str | None = Form(None),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if user.role != Role.student:
        raise HTTPException(status_code=403)

    if group not in (TeamGroup.undergrad.value, TeamGroup.postgrad.value):
        raise HTTPException(status_code=400, detail="组别参数不合法")

    team = crud.create_or_update_team(
        db=db,
        leader_user_id=user.id,
        group=group,
        work_name=work_name,
        leader_name=leader_name,
        school_name=school_name,
        college_major=college_major,
        phone=phone,
        member1_name=member1_name,
        member1_college=member1_college,
        member1_major=member1_major,
        member2_name=member2_name,
        member2_college=member2_college,
        member2_major=member2_major,
        member3_name=member3_name,
        member3_college=member3_college,
        member3_major=member3_major,
        advisor_name=_empty_to_none(advisor_name),
        advisor_college=_empty_to_none(advisor_college),
        advisor_phone=_empty_to_none(advisor_phone),
    )

    submission = crud.get_submission_by_team(db, team.id)
    return templates.TemplateResponse(
        "student_dashboard.html",
        {
            "request": request,
            "user": user,
            "team": team,
            "submission": submission,
            "upload_error": None,
            "upload_success": "参赛信息已保存。",
        },
    )


@app.post("/student/upload")
def student_upload_post(
    request: Request,
    paper_pdf_anonymous: UploadFile = File(...),
    plagiarism_report: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if user.role != Role.student:
        raise HTTPException(status_code=403)

    team = crud.get_team_by_leader(db, user.id)
    if not team:
        raise HTTPException(status_code=400, detail="请先保存参赛信息")

    MAX_100MB = 100 * 1024 * 1024
    MAX_10MB = 10 * 1024 * 1024

    pdf_anonymous_path: str | None = None
    plagiarism_report_path: str | None = None

    try:
        # 仅允许 PDF
        validate_suffix(
            paper_pdf_anonymous.filename,
            allowed={".pdf"},
            error_message="匿名论文仅支持 PDF（.pdf）",
        )
        dest = UPLOAD_DIR / f"team{team.id}_paper_pdf_anonymous.pdf"
        pdf_anonymous_path = save_upload_with_limit(
            paper_pdf_anonymous,
            dest,
            max_bytes=MAX_100MB,
            too_large_message="匿名论文PDF需小于100MB",
        )

        # 查重报告（可选）
        if plagiarism_report and plagiarism_report.filename:
            validate_suffix(
                plagiarism_report.filename,
                allowed={".pdf"},
                error_message="查重报告仅支持 PDF（.pdf）",
            )
            dest_pr = UPLOAD_DIR / f"team{team.id}_plagiarism_report.pdf"
            plagiarism_report_path = save_upload_with_limit(
                plagiarism_report,
                dest_pr,
                max_bytes=MAX_10MB,
                too_large_message="查重报告需小于10MB",
            )

    except HTTPException as e:
        latest_submission = crud.get_submission_by_team(db, team.id)
        return templates.TemplateResponse(
            "student_dashboard.html",
            {
                "request": request,
                "user": user,
                "team": team,
                "submission": latest_submission,
                "upload_error": str(e.detail),
                "upload_success": None,
            },
        )

    crud.create_or_update_submission_pdf(
        db,
        team_id=team.id,
        paper_pdf_anonymous_path=pdf_anonymous_path,
        plagiarism_report_path=plagiarism_report_path,
    )
    latest_submission = crud.get_submission_by_team(db, team.id)

    pr_msg = "查重报告已更新" if plagiarism_report_path else "查重报告未上传"
    upload_success_msg = f"上传成功：匿名论文PDF已更新；{pr_msg}。"

    return templates.TemplateResponse(
        "student_dashboard.html",
        {
            "request": request,
            "user": user,
            "team": team,
            "submission": latest_submission,
            "upload_error": None,
            "upload_success": upload_success_msg,
        },
    )


@app.get("/files/{submission_id}/{kind}")
def serve_submission_file(submission_id: int, kind: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)

    rows = crud.list_submissions_with_team(db)
    match = None
    for sub, team in rows:
        if sub.id == submission_id:
            match = (sub, team)
            break
    if match is None:
        raise HTTPException(status_code=404)

    sub, team = match

    # 学生仅能访问自己��� submission 文件
    if user.role == Role.student:
        t = crud.get_team_by_leader(db, user.id)
        if not t or t.id != team.id:
            raise HTTPException(status_code=403)

    # 支持匿名PDF和查重报告
    if kind == "paper_pdf_anonymous":
        path = sub.paper_pdf_anonymous_path
    elif kind == "plagiarism_report":
        path = sub.plagiarism_report_path
    else:
        raise HTTPException(status_code=404)

    if not path:
        raise HTTPException(status_code=404)
    return FileResponse(path)


# ---------------- Teacher ----------------

@app.get("/teacher", response_class=HTMLResponse)
def teacher_list(
    request: Request,
    group: str | None = None,
    filter: str | None = None,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if user.role != Role.teacher:
        raise HTTPException(status_code=403)

    if group is None:
        group = TeamGroup.undergrad.value

    if group not in (TeamGroup.undergrad.value, TeamGroup.postgrad.value):
        raise HTTPException(status_code=400, detail="组别参数不合法")

    rows = crud.list_submissions_with_team(db)

    items = []
    for sub, team in rows:
        if team.group != TeamGroup(group):
            continue

        my_score = crud.get_or_create_score(db, submission_id=sub.id, teacher_user_id=user.id)
        if filter == "unscored" and my_score.status == ScoreStatus.submitted:
            continue

        items.append(
            {
                "submission": sub,
                "team": team,
                "group_label": _group_label(team.group),
                "my_score": my_score,
            }
        )

    return templates.TemplateResponse(
        "teacher_list.html",
        {
            "request": request,
            "user": user,
            "items": items,
            "group": group,
            "group_label": _group_label(TeamGroup(group)),
            "filter": filter,
        },
    )


@app.get("/teacher/score/{submission_id}", response_class=HTMLResponse)
def teacher_score_get(submission_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if user.role != Role.teacher:
        raise HTTPException(status_code=403)

    rows = crud.list_submissions_with_team(db)
    match = None
    for sub, team in rows:
        if sub.id == submission_id:
            match = (sub, team)
            break
    if match is None:
        raise HTTPException(status_code=404)

    submission, team = match

    rubric_items = crud.list_active_rubric_items(db)
    score = crud.get_or_create_score(db, submission_id=submission.id, teacher_user_id=user.id)

    existing_points = {it.rubric_item_id: it.points for it in score.items}

    return templates.TemplateResponse(
        "teacher_score.html",
        {
            "request": request,
            "user": user,
            "submission": submission,
            "team": team,
            "rubric_items": rubric_items,
            "score": score,
            "existing_points": existing_points,
            "group_label": _group_label(team.group),
        },
    )


@app.post("/teacher/score/{submission_id}")
async def teacher_score_post(
    submission_id: int,
    request: Request,
    action: str = Form(...),  # save/submit
    comment: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if user.role != Role.teacher:
        raise HTTPException(status_code=403)

    rows = crud.list_submissions_with_team(db)
    match = None
    for sub, team in rows:
        if sub.id == submission_id:
            match = (sub, team)
            break
    if match is None:
        raise HTTPException(status_code=404)

    submission, team = match

    rubric_items = crud.list_active_rubric_items(db)
    score = crud.get_or_create_score(db, submission_id=submission.id, teacher_user_id=user.id)

    # 收集分数
    form = await request.form()
    points_map: dict[int, float] = {}
    for item in rubric_items:
        key = f"item_{item.id}"
        val = form.get(key)
        try:
            points_map[item.id] = float(val) if val is not None and str(val).strip() != "" else 0.0
        except Exception:
            points_map[item.id] = 0.0

    status = ScoreStatus.draft if action == "save" else ScoreStatus.submitted

    # 未上传匿名PDF时禁止提交评分（模板也禁用了按钮，这里再兜底）
    if status == ScoreStatus.submitted and not submission.paper_pdf_anonymous_path:
        raise HTTPException(status_code=400, detail="学生未上传匿名PDF，禁止提交评分")

    crud.set_score_items(
        db,
        score=score,
        points_map=points_map,
        comment=comment,
        status=status,
    )

    return RedirectResponse(url=f"/teacher/score/{submission_id}", status_code=302)


# ---------------- Admin ----------------

@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(
    request: Request,
    tab: str = "student",
    page: int = 1,
    username: str | None = None,
    leader_name: str | None = None,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if user.role != Role.superadmin:
        raise HTTPException(status_code=403)

    tab = (tab or "student").strip().lower()
    if tab not in ("student", "teacher", "superadmin"):
        tab = "student"

    PAGE_SIZE = 20

    teachers = []
    admins = []
    students_rows: list[tuple] = []
    total = 0

    if tab == "student":
        students_rows, total = crud.list_students_with_team_paged(
            db,
            username_kw=username,
            leader_name_kw=leader_name,
            page=page,
            page_size=PAGE_SIZE,
        )
    elif tab == "teacher":
        teachers, total = crud.list_users_by_role_paged(
            db,
            role=Role.teacher,
            username_kw=username,
            page=page,
            page_size=PAGE_SIZE,
        )
    else:
        admins, total = crud.list_users_by_role_paged(
            db,
            role=Role.superadmin,
            username_kw=username,
            page=page,
            page_size=PAGE_SIZE,
        )

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1
    total_pages = max(total_pages, 1)

    return templates.TemplateResponse(
        "admin_users.html",
        {
            "request": request,
            "user": user,
            "tab": tab,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "q_username": username or "",
            "q_leader_name": leader_name or "",
            "students_rows": students_rows,
            "teachers": teachers,
            "admins": admins,
            "error": None,
            "message": None,
        },
    )


@app.post("/admin/users/create-teacher")
def admin_create_teacher(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if user.role != Role.superadmin:
        raise HTTPException(status_code=403)

    if password != password2:
        return RedirectResponse(url="/admin/users?tab=teacher", status_code=302)

    ok, err = crud.create_teacher_user(db, username=username, password=password)
    if not ok:
        return templates.TemplateResponse(
            "admin_users.html",
            {
                "request": request,
                "user": user,
                "tab": "teacher",
                "page": 1,
                "total_pages": 1,
                "total": 0,
                "q_username": "",
                "q_leader_name": "",
                "students_rows": [],
                "teachers": [],
                "admins": [],
                "error": err,
                "message": None,
            },
        )

    return RedirectResponse(url="/admin/users?tab=teacher", status_code=302)


@app.post("/admin/users/{user_id}/reset-password")
def admin_reset_password(
    request: Request,
    user_id: int,
    new_password: str = Form(...),
    new_password2: str = Form(...),
    db: Session = Depends(get_db),
):
    acting = require_user(request, db)
    if acting.role != Role.superadmin:
        raise HTTPException(status_code=403)

    if new_password != new_password2:
        return RedirectResponse(url="/admin/users", status_code=302)

    crud.reset_user_password(db, user_id=user_id, new_password=new_password)
    return RedirectResponse(url="/admin/users", status_code=302)


@app.post("/admin/users/{user_id}/toggle-active")
def admin_toggle_user_active(request: Request, user_id: int, db: Session = Depends(get_db)):
    acting = require_user(request, db)
    if acting.role != Role.superadmin:
        raise HTTPException(status_code=403)

    crud.toggle_user_active(db, acting_user_id=acting.id, target_user_id=user_id)
    return RedirectResponse(url="/admin/users", status_code=302)


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if user.role != Role.superadmin:
        raise HTTPException(status_code=403)

    rubric_items = crud.list_all_rubric_items(db)

    rows = crud.list_submissions_with_team(db)
    overview = []
    for sub, team in rows:
        avg = crud.get_average_score_for_submission(db, sub.id)
        overview.append(
            {
                "submission": sub,
                "team": team,
                "group_label": _group_label(team.group),
                "avg": avg if avg is not None else "-",
            }
        )

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "user": user,
            "rubric_items": rubric_items,
            "overview": overview,
        },
    )


@app.post("/admin/rubric/add")
def admin_rubric_add(
    request: Request,
    name: str = Form(...),
    max_score: float = Form(...),
    order: int = Form(0),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if user.role != Role.superadmin:
        raise HTTPException(status_code=403)

    crud.create_rubric_item(db, name=name, max_score=float(max_score), order=int(order))
    return RedirectResponse(url="/admin", status_code=302)


@app.post("/admin/rubric/{item_id}/update")
def admin_rubric_update(
    request: Request,
    item_id: int,
    name: str = Form(...),
    max_score: float = Form(...),
    order: int = Form(0),
    is_active: int = Form(1),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if user.role != Role.superadmin:
        raise HTTPException(status_code=403)

    crud.update_rubric_item(
        db,
        item_id=item_id,
        name=name,
        max_score=float(max_score),
        order=int(order),
        is_active=bool(int(is_active)),
    )
    return RedirectResponse(url="/admin", status_code=302)


@app.post("/admin/rubric/{item_id}/toggle")
def admin_rubric_toggle(
    request: Request,
    item_id: int,
    is_active: int = Form(...),
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if user.role != Role.superadmin:
        raise HTTPException(status_code=403)

    crud.set_rubric_item_active(db, item_id=item_id, is_active=bool(int(is_active)))
    return RedirectResponse(url="/admin", status_code=302)


@app.get("/admin/export.xlsx")
def admin_export_xlsx(
    request: Request,
    group: str | None = None,
    mode: str | None = None,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    if user.role != Role.superadmin:
        raise HTTPException(status_code=403)

    split_sheets = (mode or "").strip().lower() == "split"
    content = export_all_scores_excel(db, group=group, split_sheets=split_sheets)

    resp = Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp.headers["Content-Disposition"] = "attachment; filename=scores.xlsx"
    return resp