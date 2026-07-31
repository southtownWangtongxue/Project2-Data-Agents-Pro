"""
用户模型 —— da_sys_user 表 ORM 映射
（登录账号表，与业务库 jb_bi 中既有的 sys_user 区分，避免列结构冲突）
"""
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


class SysUser(Base):
    __tablename__ = "da_sys_user"

    user_name: Mapped[str] = mapped_column(String(30), primary_key=True, comment="登录账号")
    password: Mapped[str] = mapped_column(String(200), nullable=False, comment="密码（sha256:salt:hash）")
    user_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="01", comment="用户类型: 00=Admin, 01=普通用户"
    )
    nick_name: Mapped[str] = mapped_column(
        String(50), nullable=False, default="", comment="用户昵称/显示名"
    )
    status: Mapped[str] = mapped_column(
        String(1), nullable=False, default="0", comment="状态: 0=正常, 1=禁用"
    )
    del_flag: Mapped[str] = mapped_column(
        String(1), nullable=False, default="0", comment="删除标记: 0=正常, 1=已删除"
    )
    login_ip: Mapped[str] = mapped_column(String(50), nullable=False, default="", comment="最后登录IP")
    login_date: Mapped[str] = mapped_column(String(20), nullable=False, default="", comment="最后登录时间")
