import asyncio
import base64
import io
import sys
from urllib.request import url2pathname
from urllib.parse import urlparse

import eel
from bilibili_api import Credential
from bilibili_api.login_v2 import QrCodeLogin, QrCodeLoginEvents

import db
import auth
import api

# QR login session (one at a time)
_qr_login: QrCodeLogin | None = None


# ── Auth ──

@eel.expose
def check_login_status():
    conn = db.get_db()
    c = auth.get_credential_from_db(conn)
    if not c:
        conn.close()
        return {"logged_in": False, "user_name": "", "stats": {"total": 0, "watched": 0, "tags": 0}}
    name = auth.get_user_name(c)
    s = db.stats(conn)
    conn.close()
    return {"logged_in": True, "user_name": name, "stats": s}


@eel.expose
def generate_qr():
    global _qr_login
    try:
        _qr_login = QrCodeLogin()
        asyncio.run(_qr_login.generate_qrcode())
        pic = _qr_login.get_qrcode_picture()
        url = pic.url
        if url.startswith("file://"):
            path = url2pathname(urlparse(url).path)
        else:
            path = url
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return {"ok": True, "qr_image": f"data:image/png;base64,{b64}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@eel.expose
def check_qr_state():
    global _qr_login
    if not _qr_login:
        return {"state": "idle"}
    try:
        event = asyncio.run(_qr_login.check_state())
        if event == QrCodeLoginEvents.SCAN:
            return {"state": "scanned"}
        elif event == QrCodeLoginEvents.CONF:
            return {"state": "confirmed"}
        elif event == QrCodeLoginEvents.TIMEOUT:
            return {"state": "expired"}
        elif event == QrCodeLoginEvents.DONE:
            credential = _qr_login.get_credential()
            conn = db.get_db()
            auth.persist_credential(conn, credential)
            name = auth.get_user_name(credential)
            s = db.stats(conn)
            conn.close()
            _qr_login = None
            return {"state": "done", "user_name": name, "stats": s}
        else:
            return {"state": "waiting"}
    except Exception as e:
        return {"state": "waiting", "debug": str(e)}


@eel.expose
def cancel_qr():
    global _qr_login
    _qr_login = None


@eel.expose
def do_logout_gui():
    conn = db.get_db()
    auth.do_logout(conn)
    conn.close()
    return {"ok": True}


# ── Videos ──

@eel.expose
def do_sync():
    conn = db.get_db()
    c = auth.get_credential_from_db(conn)
    if not c:
        conn.close()
        return {"ok": False, "error": "未登录"}
    # Suppress print output from sync_watch_later
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        api.sync_watch_later(c, conn)
    finally:
        sys.stdout = old_stdout
    s = db.stats(conn)
    conn.close()
    return {"ok": True, "count": s["total"], "stats": s}


@eel.expose
def list_videos_gui(tag=None, page=1, limit=24, sort="added"):
    conn = db.get_db()
    videos = db.list_videos(conn, tag=tag, page=page, limit=limit, sort=sort)
    total = db.count_videos(conn, tag=tag)
    conn.close()
    for v in videos:
        if v.get("duration"):
            v["duration_str"] = f"{v['duration'] // 60}:{v['duration'] % 60:02d}"
        else:
            v["duration_str"] = "-"
    return {
        "videos": videos,
        "total": total,
        "total_pages": max(1, (total + limit - 1) // limit),
        "page": page,
    }


@eel.expose
def search_videos_gui(query):
    conn = db.get_db()
    videos = db.search_videos(conn, query)
    total = db.search_count(conn, query)
    conn.close()
    for v in videos:
        if v.get("duration"):
            v["duration_str"] = f"{v['duration'] // 60}:{v['duration'] % 60:02d}"
        else:
            v["duration_str"] = "-"
    return {"videos": videos, "total": total}


@eel.expose
def get_video_detail_gui(bvid):
    conn = db.get_db()
    v = db.get_video(conn, bvid)
    if not v:
        conn.close()
        return None
    tags = db.get_video_tags(conn, v["aid"])
    conn.close()
    v["tags"] = tags
    if v.get("duration"):
        v["duration_str"] = f"{v['duration'] // 60}:{v['duration'] % 60:02d}"
    return v


@eel.expose
def get_stats():
    conn = db.get_db()
    s = db.stats(conn)
    conn.close()
    return s


# ── Tags ──

@eel.expose
def list_tags_gui():
    conn = db.get_db()
    tags = db.list_tags(conn)
    conn.close()
    return tags


@eel.expose
def add_tag_gui(name, color="#6c5ce7"):
    conn = db.get_db()
    try:
        db.add_tag(conn, name, color)
        conn.close()
        return {"ok": True}
    except Exception as e:
        conn.close()
        return {"ok": False, "error": "标签已存在" if "UNIQUE" in str(e) else str(e)}


@eel.expose
def remove_tag_gui(name):
    conn = db.get_db()
    ok = db.remove_tag(conn, name)
    conn.close()
    return {"ok": ok}


@eel.expose
def assign_tag_gui(aid, tag_name):
    conn = db.get_db()
    ok = db.assign_tag(conn, aid, tag_name)
    conn.close()
    return {"ok": ok}


@eel.expose
def unassign_tag_gui(aid, tag_name):
    conn = db.get_db()
    ok = db.unassign_tag(conn, aid, tag_name)
    conn.close()
    return {"ok": ok}


# ── Watch / Delete ──

@eel.expose
def watch_video(bvid):
    import webbrowser
    webbrowser.open(f"https://www.bilibili.com/video/{bvid}")
    return {"ok": True}


@eel.expose
def delete_video(bvid):
    conn = db.get_db()
    c = auth.get_credential_from_db(conn)
    if not c:
        conn.close()
        return {"ok": False, "error": "未登录"}
    v = db.get_video(conn, bvid)
    if not v:
        conn.close()
        return {"ok": False, "error": "未找到视频"}
    try:
        api.delete_video_from_wl(c, v["aid"])
        db.mark_watched(conn, v["aid"])
        s = db.stats(conn)
        conn.close()
        return {"ok": True, "stats": s}
    except Exception as e:
        conn.close()
        return {"ok": False, "error": str(e)}


# ── Entry ──

if __name__ == "__main__":
    eel.init("web")
    eel.start("index.html", mode="chrome", size=(1280, 820))
