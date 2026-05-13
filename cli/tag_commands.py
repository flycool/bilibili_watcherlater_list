import typer
from rich.console import Console
from rich.table import Table

import db
import auth

tag_app = typer.Typer(help="标签管理")
console = Console()


def _require_login():
    conn = db.get_db()
    c = auth.get_credential_from_db(conn)
    if not c:
        console.print("[red]请先登录: bili-wl login[/red]")
        conn.close()
        return None, None
    return conn, c


@tag_app.command()
def add(name: str, color: str = "#ffffff"):
    """创建标签"""
    conn, _ = _require_login()
    if not conn:
        return
    try:
        tag_id = db.add_tag(conn, name, color)
        console.print(f"[green]标签已创建: {name} (id={tag_id})[/green]")
    except Exception as e:
        if "UNIQUE" in str(e):
            console.print(f"[red]标签已存在: {name}[/red]")
        else:
            console.print(f"[red]创建失败: {e}[/red]")
    conn.close()


@tag_app.command()
def remove(name: str):
    """删除标签"""
    conn, _ = _require_login()
    if not conn:
        return
    ok = db.remove_tag(conn, name)
    if ok:
        console.print(f"[green]标签已删除: {name}[/green]")
    else:
        console.print(f"[red]标签不存在: {name}[/red]")
    conn.close()


@tag_app.command(name="list-tags")
def list_tags():
    """列出所有标签及视频数"""
    conn, _ = _require_login()
    if not conn:
        return
    tags = db.list_tags(conn)
    if not tags:
        console.print("[yellow]暂无标签[/yellow]")
        conn.close()
        return

    table = Table(title="标签列表")
    table.add_column("名称", style="cyan")
    table.add_column("颜色", style="dim")
    table.add_column("视频数", style="green")
    for t in tags:
        table.add_row(t["name"], t["color"], str(t["video_count"]))
    console.print(table)
    conn.close()


@tag_app.command()
def assign(bvid: str, tag_names: list[str]):
    """给视频打标签"""
    conn, _ = _require_login()
    if not conn:
        return
    v = db.get_video(conn, bvid)
    if not v:
        console.print(f"[red]未找到视频: {bvid}[/red]")
        conn.close()
        return

    for name in tag_names:
        ok = db.assign_tag(conn, v["aid"], name)
        if ok:
            console.print(f"[green]已打标签 '{name}' → {v['title']}[/green]")
        else:
            console.print(f"[red]标签不存在: {name}，请先创建[/red]")
    conn.close()


@tag_app.command()
def unassign(bvid: str, tag_names: list[str]):
    """移除视频标签"""
    conn, _ = _require_login()
    if not conn:
        return
    v = db.get_video(conn, bvid)
    if not v:
        console.print(f"[red]未找到视频: {bvid}[/red]")
        conn.close()
        return

    for name in tag_names:
        ok = db.unassign_tag(conn, v["aid"], name)
        if ok:
            console.print(f"[green]已移除标签 '{name}' ← {v['title']}[/green]")
        else:
            console.print(f"[red]标签不存在: {name}[/red]")
    conn.close()


@tag_app.command()
def show(bvid: str):
    """查看视频的标签"""
    conn, _ = _require_login()
    if not conn:
        return
    v = db.get_video(conn, bvid)
    if not v:
        console.print(f"[red]未找到视频: {bvid}[/red]")
        conn.close()
        return

    tags = db.get_video_tags(conn, v["aid"])
    if not tags:
        console.print(f"[yellow]{v['title']} 没有标签[/yellow]")
    else:
        tag_str = ", ".join(f"{t['name']}" for t in tags)
        console.print(f"[cyan]{v['title']}[/cyan] 的标签: [magenta]{tag_str}[/magenta]")
    conn.close()
