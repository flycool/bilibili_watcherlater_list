"""B站扫码登录。

没有直接使用 bilibili-api 的 QrCodeLogin：它只从登录结果 URL 的查询参数里取
Cookie，而该接口的成功响应并不保证在 URL 中带上这些 Cookie，解析不到时会静默
生成空凭据（登录"成功"但数据库里全是空值）。这里直接调用 passport 接口，并从
响应头 (Set-Cookie) 与响应体 (url) 两处提取，取到为止。
"""

import asyncio
import base64
import enum
import io
import json
import re
import time
from urllib.parse import parse_qsl, unquote, urlparse

import aiohttp
import qrcode
import qrcode_terminal
from bilibili_api import Credential, user

from db import save_credential, load_credentials, clear_credentials

_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}

# 需要保存的 Cookie（小写，同时也是 Credential 的字段名）
_COOKIE_KEYS = ("sessdata", "bili_jct", "buvid3", "dedeuserid")


class QrState(enum.Enum):
    WAITING = "waiting"  # 未扫码
    SCANNED = "scanned"  # 已扫码，等待手机端确认
    EXPIRED = "expired"  # 二维码已过期
    DONE = "done"  # 登录成功


# 轮询接口返回的业务码 -> 登录状态
_STATE_BY_CODE = {86101: QrState.WAITING, 86090: QrState.SCANNED, 86038: QrState.EXPIRED}


_STATE_TEXT = {
    QrState.WAITING: "等待扫码...",
    QrState.SCANNED: "已扫码，请在手机上确认...",
    QrState.EXPIRED: "二维码已过期，请重试。",
    QrState.DONE: "登录成功!",
}


class LoginFailed(RuntimeError):
    """不可恢复的登录失败，例如响应中拿不到任何凭据。"""


def _mask(text: str) -> str:
    """日志中隐藏凭据值（支持 k=v 与 JSON 两种写法）。"""
    return re.sub(
        r"(?i)([\"']?"
        r"(?:sessdata|bili_jct|buvid3|buvid4|dedeuserid|refresh_token)"
        r"[\"']?\s*[:=]\s*[\"']?)[^&;,\"'}\s]*",
        r"\1***",
        text,
    )


def qrcode_png_base64(link: str) -> str:
    """把二维码链接渲染成 base64 PNG，供网页端显示。"""
    buf = io.BytesIO()
    qrcode.make(link).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _cookies_from_headers(headers) -> dict:
    cookies = {}
    for raw in headers.getall("Set-Cookie", []):
        name, _, value = raw.split(";", 1)[0].partition("=")
        key = name.strip().lower()
        if key in _COOKIE_KEYS and value:
            cookies[key] = value
    return cookies


def _collect_query_cookies(query: str, cookies: dict) -> None:
    for name, value in parse_qsl(query):
        key = name.lower()
        if key in _COOKIE_KEYS and value:
            cookies.setdefault(key, value)
        elif value.startswith("http"):
            # 参数值可能又是一个带 Cookie 的 URL
            _collect_query_cookies(urlparse(value).query, cookies)


def _cookies_from_url(url: str) -> dict:
    """从登录结果 URL 中提取 Cookie（兼容整个 URL 被编码的情况）。"""
    cookies: dict = {}
    for candidate in (url, unquote(url)):
        _collect_query_cookies(urlparse(candidate).query, cookies)
    return cookies


class QrLoginSession:
    """一次扫码登录会话：生成二维码 -> 轮询状态 -> 成功后得到凭据。"""

    def __init__(self) -> None:
        self.link = ""  # 二维码内容（链接）
        self.credential: Credential | None = None
        self._qrcode_key = ""

    def generate(self) -> None:
        payload, _ = asyncio.run(self._get(_GENERATE_URL))
        data = payload.get("data") or {}
        self._qrcode_key = data.get("qrcode_key", "")
        self.link = data.get("url", "")
        if not self._qrcode_key or not self.link:
            raise LoginFailed(
                f"获取二维码失败: {payload.get('code')} {payload.get('message')}"
            )

    def check(self) -> QrState:
        """轮询一次状态；返回 DONE 时 self.credential 已就绪。"""
        payload, header_cookies = asyncio.run(
            self._get(_POLL_URL, {"qrcode_key": self._qrcode_key})
        )
        data = payload.get("data") or {}
        code = data.get("code")
        if code is None:
            raise LoginFailed(
                f"查询扫码状态失败: {payload.get('code')} {payload.get('message')}"
            )
        state = _STATE_BY_CODE.get(code, QrState.DONE)
        if state is QrState.DONE:
            cookies = _cookies_from_url(data.get("url", ""))
            cookies.update(header_cookies)
            self.credential = self._build_credential(cookies, data)
        return state

    @staticmethod
    async def _get(url: str, params: dict | None = None):
        async with aiohttp.ClientSession(headers=_HEADERS) as session:
            async with session.get(url, params=params) as resp:
                payload = await resp.json(content_type=None)
                cookies = _cookies_from_headers(resp.headers)
        return payload, cookies

    @staticmethod
    def _build_credential(cookies: dict, data: dict) -> Credential:
        if not cookies.get("sessdata"):
            raise LoginFailed(
                "登录响应中未找到 Cookie，无法保存凭据。响应: "
                + _mask(json.dumps(data, ensure_ascii=False))
            )
        return Credential(**{key: cookies.get(key, "") for key in _COOKIE_KEYS})


def get_credential_from_db(conn) -> Credential | None:
    creds = load_credentials(conn)
    if not creds:
        return None
    c = Credential(
        sessdata=creds.get("sessdata", ""),
        bili_jct=creds.get("bili_jct", ""),
        buvid3=creds.get("buvid3", ""),
        dedeuserid=creds.get("dedeuserid", ""),
    )
    try:
        if asyncio.run(c.check_valid()):
            return c
    except Exception:
        pass
    return None


def persist_credential(conn, credential: Credential) -> None:
    for key in ("sessdata", "bili_jct", "buvid3", "dedeuserid"):
        value = getattr(credential, key, "") or ""
        save_credential(conn, key, value)


def qr_login(conn) -> Credential | None:
    """CLI 扫码登录：终端打印二维码并轮询，成功后写入数据库。"""
    session = QrLoginSession()
    try:
        session.generate()
    except Exception as e:
        print(f"获取二维码失败: {e}")
        return None

    print("请用B站APP扫描下方二维码登录:\n")
    print(qrcode_terminal.qr_terminal_str(session.link))

    deadline = time.time() + 180
    state = None
    while time.time() < deadline:
        try:
            new_state = session.check()
        except LoginFailed as e:
            print(f"登录失败: {e}")
            return None
        except Exception as e:
            print(f"检查扫码状态出错: {e}")
            time.sleep(2)
            continue
        if new_state is not state:
            print(_STATE_TEXT[new_state])
            state = new_state
        if state is QrState.DONE:
            persist_credential(conn, session.credential)
            return session.credential
        if state is QrState.EXPIRED:
            return None
        time.sleep(2)

    print("登录超时，请重试。")
    return None


def get_user_name(credential: Credential) -> str:
    try:
        info = asyncio.run(user.get_self_info(credential))
        return info.get("name", "未知")
    except Exception:
        return "未知"


def do_logout(conn) -> None:
    clear_credentials(conn)
    print("已登出。")
