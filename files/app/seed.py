from sqlalchemy.orm import Session

from app.db import SessionLocal, engine, Base
from app.models import Role
from app.security import hash_password
from app import crud
from app.settings import DB_USE_ALEMBIC

DEFAULT_RUBRIC = [
    ("题目与摘要", 10, 1),
    ("模型假设与合理性", 20, 2),
    ("数据处理", 15, 3),
    ("结果分析", 20, 4),
    ("创新性", 15, 5),
    ("论文结构与表达", 10, 6),
    ("格式规范", 10, 7),
]

def main():
    # 方式B：不用 Alembic 就直接建表
    if not DB_USE_ALEMBIC:
        Base.metadata.create_all(bind=engine)

    db: Session = SessionLocal()

    # superadmin(超级管理员的账号 admin 和密码 admin123，实际使用时请修改密码并妥善保管)
    if crud.get_user_by_username(db, "admin") is None:
        crud.create_user(db, "admin", hash_password("admin123"), Role.superadmin)

    # teachers（默认 3 个评委，对应的账号teacher1和密码都是teacher123）
    for i in range(1, 4):
        uname = f"teacher{i}"
        if crud.get_user_by_username(db, uname) is None:
            crud.create_user(db, uname, hash_password("teacher123"), Role.teacher)

    # rubric（若数据库里没有 rubric 才初始化）
    existing = crud.list_active_rubric_items(db)
    if not existing:
        for name, max_score, order in DEFAULT_RUBRIC:
            crud.create_rubric_item(db, name=name, max_score=float(int(max_score)), order=int(order))

    db.close()
    print("Seed done.")

if __name__ == "__main__":
    main()