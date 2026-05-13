import asyncio

from bilibili_api import Credential, user
from bilibili_api.video import Video


def sync_watch_later(credential: Credential, conn) -> None:
    """从B站同步稍后再看列表到本地数据库"""
    from db import upsert_video

    async def _sync():
        result = await user.get_toview_list(credential)
        videos = result.get("list", [])
        for item in videos:
            upsert_video(conn, {
                "aid": item["aid"],
                "bvid": item["bvid"],
                "title": item["title"],
                "cover_url": item.get("pic", ""),
                "duration": item.get("duration", 0),
                "author_name": item.get("owner", {}).get("name", ""),
                "author_mid": item.get("owner", {}).get("mid", 0),
                "added_at": item.get("add_at", 0),
                "ctime": item.get("ctime", 0),
            })
        return len(videos)

    count = asyncio.run(_sync())
    from db import stats
    s = stats(conn)
    print(f"同步完成，共 {count} 个视频 | 总计 {s['total']} 个，已观看 {s['watched']} 个")


def delete_video_from_wl(credential: Credential, aid: int) -> None:
    """从B站稍后再看列表中删除视频"""
    async def _delete():
        # Use bvid to construct Video object, then delete from toview
        v = Video(aid=aid, credential=credential)
        return await v.delete_from_toview()

    asyncio.run(_delete())


def get_video_detail(credential: Credential, bvid: str) -> dict:
    """获取单个视频的详细信息"""
    async def _get():
        v = Video(bvid=bvid, credential=credential)
        return await v.get_info()

    return asyncio.run(_get())
