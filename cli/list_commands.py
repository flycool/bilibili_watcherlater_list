import typer
from rich.console import Console
from rich.table import Table

import db
import auth
import api

console = Console()


def _require_login():
    conn = db.get_db()
    c = auth.get_credential_from_db(conn)
    if not c:
        console.print("[red]请先登录: bili-wl login[/red]")
        conn.close()
        return None, None
    return conn, c


def do_sync():
    """从B站同步稍后再看列表"""
    conn, c = _require_login()
    if not conn:
        return
    api.sync_watch_later(c, conn)
    conn.close()


def do_list(
    tag: str | None = None,
    page: int = 1,
    limit: int = 20,
    sort: str = "added",
    refresh: bool = False,
):
    """浏览稍后再看视频列表"""
    conn, c = _require_login()
    if not conn:
        return

    if refresh:
        api.sync_watch_later(c, conn)

    videos = db.list_videos(conn, tag=tag, page=page, limit=limit, sort=sort)
    total = db.count_videos(conn, tag=tag)

    if not videos:
        tag_hint = f" (标签: {tag})" if tag else ""
        console.print(f"[yellow]没有视频{tag_hint}[/yellow]")
        conn.close()
        return

    title = f"稍后再看 ({total} 个)"
    if tag:
        title += f" - 标签: {tag}"

    table = Table(title=title)
    table.add_column("#", style="dim")
    table.add_column("标题", style="cyan", max_width=50)
    table.add_column("UP主", style="green", max_width=20)
    table.add_column("时长", style="yellow")
    table.add_column("标签", style="magenta", max_width=20)
    table.add_column("BV号", style="dim")

    for i, v in enumerate(videos, start=(page - 1) * limit + 1):
        dur = f"{v['duration'] // 60}:{v['duration'] % 60:02d}" if v["duration"] else "-"
        table.add_row(
            str(i), v["title"] or "-", v["author_name"] or "-",
            dur, v.get("tag_list") or "-", v["bvid"],
        )

    console.print(table)
    total_pages = (total + limit - 1) // limit
    if total_pages > 1:
        console.print(f"[dim]第 {page}/{total_pages} 页[/dim]")
    conn.close()


def do_info(bvid: str):
    """查看视频详细信息"""
    conn, c = _require_login()
    if not conn:
        return
    v = db.get_video(conn, bvid)
    if not v:
        console.print(f"[red]未找到视频: {bvid}[/red]")
        conn.close()
        return

    tags = db.get_video_tags(conn, v["aid"])
    tag_str = ", ".join(t["name"] for t in tags) if tags else "-"

    table = Table(title=f"视频信息: {v['title']}")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    table.add_row("BV号", v["bvid"])
    table.add_row("AV号", str(v["aid"]))
    table.add_row("标题", v["title"])
    table.add_row("UP主", v["author_name"] or "-")
    table.add_row("封面", v.get("cover_url") or "-")
    if v.get("duration"):
        table.add_row("时长", f"{v['duration'] // 60}:{v['duration'] % 60:02d}")
    table.add_row("标签", tag_str)
    console.print(table)
    conn.close()


def do_search(query: str):
    """搜索视频"""
    conn, c = _require_login()
    if not conn:
        return

    videos = db.search_videos(conn, query)
    total = db.search_count(conn, query)

    if not videos:
        console.print(f"[yellow]未找到匹配 '{query}' 的视频[/yellow]")
        conn.close()
        return

    table = Table(title=f"搜索: {query} ({total} 个)")
    table.add_column("#", style="dim")
    table.add_column("标题", style="cyan", max_width=50)
    table.add_column("UP主", style="green", max_width=20)
    table.add_column("时长", style="yellow")
    table.add_column("标签", style="magenta", max_width=20)
    table.add_column("BV号", style="dim")

    for i, v in enumerate(videos, 1):
        dur = f"{v['duration'] // 60}:{v['duration'] % 60:02d}" if v["duration"] else "-"
        table.add_row(
            str(i), v["title"] or "-", v["author_name"] or "-",
            dur, v.get("tag_list") or "-", v["bvid"],
        )

    console.print(table)
    conn.close()
