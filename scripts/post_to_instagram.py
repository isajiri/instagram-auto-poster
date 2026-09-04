"""
Notionの「SNS投稿カレンダー」を投稿キューとして、Instagramへ自動投稿するスクリプト。

対象にする行の条件:
  - ステータス == "予約済み"
  - チェックボックス == オフ(未投稿)
  - プラットフォーム に "Instagram \U0001F4F8" を含む
  - 投稿日付 <= 今日

ページ本文の構成:
  ### 元画像       ... 撮影した画像(カルーセル投稿の元ネタ)
  ### 投稿画像     ... 実際に使う画像。空 or 「元画像と同じ」なら元画像を使う
  ### 投稿内容     ... キャプション本文(次の見出しの手前まで)
  ### 商品リンク   ... (使用しない)

投稿が終わったら、そのページの「チェックボックス」をオンにする。
GitHub Actionsから1日1回実行される想定。
"""

import datetime as dt
import os
import sys
import time

import requests

NOTION_VERSION = "2022-06-28"
NOTION_API_BASE = "https://api.notion.com/v1"

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

PLATFORM_TAG = "Instagram \U0001F4F8"
STATUS_READY = "予約済み"  # 予約済み

HEADING_TYPES = {"heading_1", "heading_2", "heading_3"}
IMAGE_HEADING = "元画像"      # 元画像
POST_IMAGE_HEADING = "投稿画像"  # 投稿画像
CAPTION_HEADING = "投稿内容"     # 投稿内容


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"環境変数 {name} が設定されていません", file=sys.stderr)
        sys.exit(1)
    return value


def notion_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def find_next_page(token: str, database_id: str) -> dict | None:
    today = dt.date.today().isoformat()
    payload = {
        "filter": {
            "and": [
                {"property": "ステータス", "status": {"equals": STATUS_READY}},
                {"property": "チェックボックス", "checkbox": {"equals": False}},
                {"property": "プラットフォーム", "multi_select": {"contains": PLATFORM_TAG}},
                {"property": "投稿日付", "date": {"on_or_before": today}},
            ]
        },
        "sorts": [{"property": "投稿日付", "direction": "ascending"}],
        "page_size": 1,
    }
    resp = requests.post(
        f"{NOTION_API_BASE}/databases/{database_id}/query",
        headers=notion_headers(token),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None


def get_all_children(token: str, block_id: str) -> list[dict]:
    blocks = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        resp = requests.get(
            f"{NOTION_API_BASE}/blocks/{block_id}/children",
            headers=notion_headers(token),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return blocks


def collect_image_urls(token: str, blocks: list[dict]) -> list[str]:
    urls = []
    for block in blocks:
        btype = block.get("type")
        if btype == "image":
            image = block["image"]
            url = image.get("file", {}).get("url") or image.get("external", {}).get("url")
            if url:
                urls.append(url)
        elif block.get("has_children") and btype in ("column_list", "column"):
            children = get_all_children(token, block["id"])
            urls.extend(collect_image_urls(token, children))
    return urls


def block_plain_text(block: dict) -> str:
    btype = block.get("type")
    data = block.get(btype, {})
    rich_text = data.get("rich_text", [])
    return "".join(rt.get("plain_text", "") for rt in rich_text)


def heading_text(block: dict) -> str | None:
    btype = block.get("type")
    if btype not in HEADING_TYPES:
        return None
    return block_plain_text(block).strip()


def split_into_sections(blocks: list[dict]) -> dict[str, list[dict]]:
    sections: dict[str, list[dict]] = {}
    current = None
    for block in blocks:
        title = heading_text(block)
        if title is not None:
            current = title
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(block)
    return sections


def extract_images(token: str, sections: dict[str, list[dict]]) -> list[str]:
    post_images = collect_image_urls(token, sections.get(POST_IMAGE_HEADING, []))
    if post_images:
        return post_images
    return collect_image_urls(token, sections.get(IMAGE_HEADING, []))


def extract_caption(sections: dict[str, list[dict]]) -> str:
    lines = [block_plain_text(b) for b in sections.get(CAPTION_HEADING, [])]
    return "\n".join(line for line in lines if line).strip()


def wait_until_finished(container_id: str, access_token: str, timeout_sec: int = 120) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        resp = requests.get(
            f"{GRAPH_API_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        resp.raise_for_status()
        status = resp.json().get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"メディア処理が失敗しました: container_id={container_id}")
        time.sleep(3)
    raise TimeoutError(f"メディア処理がタイムアウトしました: container_id={container_id}")


def create_image_container(ig_user_id: str, access_token: str, image_url: str,
                            caption: str | None = None, is_carousel_item: bool = False) -> str:
    payload = {"image_url": image_url, "access_token": access_token}
    if caption is not None:
        payload["caption"] = caption
    if is_carousel_item:
        payload["is_carousel_item"] = "true"

    resp = requests.post(f"{GRAPH_API_BASE}/{ig_user_id}/media", data=payload, timeout=60)
    if not resp.ok:
        print(f"メディアコンテナ作成に失敗: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()["id"]


def create_carousel_container(ig_user_id: str, access_token: str,
                               children_ids: list[str], caption: str) -> str:
    payload = {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": access_token,
    }
    resp = requests.post(f"{GRAPH_API_BASE}/{ig_user_id}/media", data=payload, timeout=60)
    if not resp.ok:
        print(f"カルーセルコンテナ作成に失敗: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()["id"]


def publish_container(ig_user_id: str, access_token: str, container_id: str) -> str:
    payload = {"creation_id": container_id, "access_token": access_token}
    resp = requests.post(f"{GRAPH_API_BASE}/{ig_user_id}/media_publish", data=payload, timeout=60)
    if not resp.ok:
        print(f"投稿の公開に失敗: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
    return resp.json()["id"]


def mark_as_posted(token: str, page_id: str) -> None:
    payload = {"properties": {"チェックボックス": {"checkbox": True}}}
    resp = requests.patch(
        f"{NOTION_API_BASE}/pages/{page_id}",
        headers=notion_headers(token),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()


def post_images(ig_user_id: str, access_token: str, images: list[str], caption: str) -> str:
    if len(images) == 1:
        container_id = create_image_container(ig_user_id, access_token, images[0], caption=caption)
        wait_until_finished(container_id, access_token)
        return publish_container(ig_user_id, access_token, container_id)

    child_ids = []
    for image_url in images[:10]:
        child_id = create_image_container(ig_user_id, access_token, image_url, is_carousel_item=True)
        wait_until_finished(child_id, access_token)
        child_ids.append(child_id)

    carousel_id = create_carousel_container(ig_user_id, access_token, child_ids, caption)
    wait_until_finished(carousel_id, access_token)
    return publish_container(ig_user_id, access_token, carousel_id)


def main() -> None:
    notion_token = get_env("NOTION_TOKEN")
    database_id = get_env("NOTION_DATABASE_ID")
    ig_access_token = get_env("IG_ACCESS_TOKEN")
    ig_user_id = get_env("IG_BUSINESS_ACCOUNT_ID")

    page = find_next_page(notion_token, database_id)
    if page is None:
        print("投稿予定のページが見つかりませんでした。何もせず終了します。")
        return

    page_id = page["id"]
    title_prop = page["properties"].get("件名", {}).get("title", [])
    title = "".join(rt.get("plain_text", "") for rt in title_prop) or page_id
    print(f"投稿対象: {title} ({page_id})")

    blocks = get_all_children(notion_token, page_id)
    sections = split_into_sections(blocks)

    images = extract_images(notion_token, sections)
    if not images:
        print(f"エラー: {title} に画像が見つかりません", file=sys.stderr)
        sys.exit(1)

    caption = extract_caption(sections)
    print(f"画像 {len(images)} 枚 / キャプション {len(caption)} 文字")

    media_id = post_images(ig_user_id, ig_access_token, images, caption)
    print(f"投稿に成功しました: media_id={media_id}")

    mark_as_posted(notion_token, page_id)
    print(f"Notion側の「チェックボックス」をオンにしました: {title}")


if __name__ == "__main__":
    main()
