import sys

import typer

# Fix Windows console encoding for Chinese characters
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

app = typer.Typer(help="B站稍后再看管理器 - 分类浏览 & 一键删除")

from cli.auth_commands import auth_app
from cli.tag_commands import tag_app

app.add_typer(auth_app, name="auth")
app.add_typer(tag_app, name="tag")


# ── Top-level convenience commands ──


@app.command()
def login():
    """扫码登录B站 (等同于 auth login)"""
    from cli.auth_commands import login as _login

    _login()


@app.command()
def logout():
    """登出 (等同于 auth logout)"""
    from cli.auth_commands import logout as _logout

    _logout()


@app.command()
def status():
    """查看登录状态 (等同于 auth status)"""
    from cli.auth_commands import status as _status

    _status()


@app.command()
def sync():
    """同步稍后再看列表"""
    from cli.list_commands import do_sync

    do_sync()


@app.command()
def list(
    tag: str = typer.Option(None, "--tag", "-t", help="按标签筛选"),
    page: int = typer.Option(1, "--page", "-p", min=1, help="页码"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100, help="每页数量"),
    sort: str = typer.Option("added", "--sort", "-s", help="排序: added/title/author"),
    refresh: bool = typer.Option(False, "--refresh", "-r", help="先同步再显示"),
):
    """浏览稍后再看视频列表"""
    from cli.list_commands import do_list

    do_list(tag=tag, page=page, limit=limit, sort=sort, refresh=refresh)


@app.command()
def info(bvid: str):
    """查看视频详细信息"""
    from cli.list_commands import do_info

    do_info(bvid)


@app.command()
def search(query: str):
    """搜索视频 (标题/UP主)"""
    from cli.list_commands import do_search

    do_search(query)


@app.command()
def watch(bvid: str):
    """浏览器打开视频，看完询问删除"""
    from cli.watch_commands import do_watch

    do_watch(bvid)


@app.command()
def tag(tagName: str):
    """创建标签"""
    from cli.tag_commands import add

    add(tagName)


@app.command()
def delete(bvid: str):
    """从稍后再看删除视频"""
    from cli.watch_commands import do_delete

    do_delete(bvid)


if __name__ == "__main__":
    app()
