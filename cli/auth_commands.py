import typer
from rich.console import Console
from rich.table import Table

import db
import auth

auth_app = typer.Typer(help="登录管理")
console = Console()


@auth_app.command()
def login():
    """扫码登录B站"""
    conn = db.get_db()
    existing = auth.get_credential_from_db(conn)
    if existing:
        name = auth.get_user_name(existing)
        print(f"已登录为 {name}，如需重新登录请先运行: bili-wl logout")
        conn.close()
        return

    credential = auth.qr_login(conn)
    if credential:
        name = auth.get_user_name(credential)
        status = db.stats(conn)
        print(f"欢迎, {name}! 稍后再看 {status['total']} 个视频, {status['tags']} 个标签")
    conn.close()


@auth_app.command()
def logout():
    """登出"""
    conn = db.get_db()
    auth.do_logout(conn)
    conn.close()


@auth_app.command()
def status():
    """查看登录状态和统计"""
    conn = db.get_db()
    c = auth.get_credential_from_db(conn)
    if not c:
        console.print("[red]未登录，请运行: bili-wl login[/red]")
        conn.close()
        return

    name = auth.get_user_name(c)
    s = db.stats(conn)

    table = Table(title="状态")
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")
    table.add_row("登录用户", name)
    table.add_row("稍后再看", str(s["total"]))
    table.add_row("已观看", str(s["watched"]))
    table.add_row("标签数", str(s["tags"]))
    console.print(table)
    conn.close()
