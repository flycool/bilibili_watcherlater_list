import asyncio
import time
import sys

from bilibili_api import Credential, user
from bilibili_api.login_v2 import QrCodeLogin, QrCodeLoginEvents

from db import save_credential, load_credentials, clear_credentials


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
    qr_login = QrCodeLogin()

    async def _login():
        try:
            await qr_login.generate_qrcode()
        except Exception as e:
            print(f"获取二维码失败: {e}")
            return None

        terminal_qr = qr_login.get_qrcode_terminal()
        # Strip ANSI codes for cleaner output on Windows
        print("请用B站APP扫描下方二维码登录:\n")
        print(terminal_qr)
        sys.stdout.flush()

        start = time.time()
        while time.time() - start < 180:
            try:
                event = await qr_login.check_state()
                if event == QrCodeLoginEvents.DONE:
                    credential = qr_login.get_credential()
                    persist_credential(conn, credential)
                    print("登录成功!")
                    return credential
                elif event == QrCodeLoginEvents.SCAN:
                    print("已扫码，请在手机上确认...")
                elif event == QrCodeLoginEvents.TIMEOUT:
                    print("二维码已过期，请重试。")
                    return None
                elif event == QrCodeLoginEvents.CONF:
                    print("已确认，正在登录...")
            except Exception as e:
                print(f"检查扫码状态出错: {e}")
            await asyncio.sleep(2)

        print("登录超时，请重试。")
        return None

    return asyncio.run(_login())


def get_user_name(credential: Credential) -> str:
    try:
        info = asyncio.run(user.get_self_info(credential))
        return info.get("name", "未知")
    except Exception:
        return "未知"


def do_logout(conn) -> None:
    clear_credentials(conn)
    print("已登出。")
