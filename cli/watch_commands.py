import webbrowser

from rich.console import Console
from rich.prompt import Confirm

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


def do_watch(bvid: str):
    """在浏览器打开视频，看完后询问是否从稍后再看删除"""
    conn, c = _require_login()
    if not conn:
        return

    v = db.get_video(conn, bvid)
    if not v:
        console.print(f"[red]未找到视频: {bvid}，请先运行 bili-wl sync[/red]")
        conn.close()
        return

    url = f"https://www.bilibili.com/video/{bvid}"
    console.print(f"[cyan]正在打开: {v['title']}[/cyan]")
    console.print(f"[dim]{url}[/dim]")
    webbrowser.open(url)

    remove = Confirm.ask("从稍后再看中删除?", default=True)
    if remove:
        try:
            api.delete_video_from_wl(c, v["aid"])
            db.mark_watched(conn, v["aid"])
            console.print(f"[green]已删除: {v['title']}[/green]")
        except Exception as e:
            console.print(f"[red]删除失败: {e}[/red]")
    else:
        console.print("已保留。")
    conn.close()


def do_delete(bvid: str):
    """直接从稍后再看删除 (不打开浏览器)"""
    conn, c = _require_login()
    if not conn:
        return

    v = db.get_video(conn, bvid)
    if not v:
        console.print(f"[red]未找到视频: {bvid}[/red]")
        conn.close()
        return

    confirm = Confirm.ask(f"确认删除 '{v['title']}'?", default=False)
    if not confirm:
        console.print("已取消。")
        conn.close()
        return

    try:
        api.delete_video_from_wl(c, v["aid"])
        db.mark_watched(conn, v["aid"])
        console.print(f"[green]已删除: {v['title']}[/green]")
    except Exception as e:
        console.print(f"[red]删除失败: {e}[/red]")
    conn.close()
