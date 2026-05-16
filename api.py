import asyncio

from bilibili_api import Credential, user
from bilibili_api.video import Video


def _build_video_data(item: dict) -> dict:
    """从API返回的item中提取视频字段"""
    return {
        "aid": item["aid"],
        "bvid": item["bvid"],
        "title": item["title"],
        "cover_url": item.get("pic", ""),
        "duration": item.get("duration", 0),
        "author_name": item.get("owner", {}).get("name", ""),
        "author_mid": item.get("owner", {}).get("mid", 0),
        "added_at": item.get("add_at", 0),
        "ctime": item.get("ctime", 0),
    }


def _needs_update(remote: dict, local: dict) -> bool:
    """比较远程数据与本地数据，判断是否需要更新"""
    return (
        remote.get("add_at", 0) != local["added_at"]
        or remote["title"] != local["title"]
        or remote.get("pic", "") != local.get("cover_url", "")
        or remote.get("duration", 0) != local["duration"]
        or remote.get("owner", {}).get("name", "") != local.get("author_name", "")
    )


def sync_watch_later(credential: Credential, conn) -> None:
    """从B站同步稍后再看列表到本地数据库

    同步策略：
    - 远程有、本地无 → 新增
    - 远程有、本地有且字段不同 → 更新
    - 远程有、本地有但已观看 → 更新并重置为未观看（用户重新添加）
    - 远程无、本地有且未观看 → 标记已观看（B站上被移除）
    - 远程无、本地有且已观看 → 跳过
    """
    from db import get_videos, mark_watched, upsert_video

    async def _sync():
        local_videos = get_videos(conn)
        local_map = {item["aid"]: item for item in local_videos}

        result = await user.get_toview_list(credential)
        remote_videos = result.get("list", [])
        remote_aids = {item["aid"] for item in remote_videos}

        inserted = 0
        updated = 0
        removed = 0

        for item in remote_videos:
            aid = item["aid"]
            video_data = _build_video_data(item)

            if aid not in local_map:
                upsert_video(conn, video_data)
                inserted += 1
            else:
                local = local_map[aid]
                if local["is_watched"]:
                    upsert_video(conn, video_data)
                    conn.execute(
                        "UPDATE videos SET is_watched = 0 WHERE aid = ?", (aid,)
                    )
                    conn.commit()
                    updated += 1
                elif _needs_update(item, local):
                    upsert_video(conn, video_data)
                    updated += 1

        for aid, local in local_map.items():
            if aid not in remote_aids and not local["is_watched"]:
                mark_watched(conn, aid)
                removed += 1

        return len(remote_videos), inserted, updated, removed

    count, inserted, updated, removed = asyncio.run(_sync())
    from db import stats

    s = stats(conn)
    print(
        f"同步完成，共 {count} 个视频（新增 {inserted}，更新 {updated}，移除 {removed}）"
        f" | 总计 {s['total']} 个，已观看 {s['watched']} 个"
    )


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
