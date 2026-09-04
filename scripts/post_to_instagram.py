"""
Notionカレンダーは使わず、posts/ フォルダに置かれた投稿を
古い順(フォルダ名の昇順)に1件だけInstagramへ自動投稿するスクリプト。

posts/01_example/
    caption.txt   ... 投稿本文(1行目でもOK、複数行可)
    1.jpg
    2.jpg
    3.jpg         ... 画像は最大10枚まで(カルーセル投稿に対応)

投稿に成功したフォルダは posts_done/ に移動する。
GitHub Actions から実行される想定(スケジュール実行)。
"""

import os
import sys
import time
import shutil
from pathlib import Path

import requests

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

POSTS_DIR = Path("posts")
POSTS_DONE_DIR = Path("posts_done")


def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"環境変数 {name} が設定されていません", file=sys.stderr)
        sys.exit(1)
    return value


def find_next_post_dir() -> Path | None:
    if not POSTS_DIR.exists():
        return None
    candidates = sorted(
        p for p in POSTS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    return candidates[0] if candidates else None


def load_caption(post_dir: Path) -> str:
    caption_file = post_dir / "caption.txt"
    if not caption_file.exists():
        return ""
    return caption_file.read_text(encoding="utf-8").strip()


def list_image_files(post_dir: Path) -> list[Path]:
    files = sorted(
        p for p in post_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    if len(files) > 10:
        print(f"警告: 画像が10枚を超えています。先頭10枚のみ使用します: {post_dir}")
        files = files[:10]
    return files


def build_raw_url(repo: str, branch: str, post_dir: Path, filename: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{post_dir.as_posix()}/{filename}"


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


def main() -> None:
    access_token = get_env("IG_ACCESS_TOKEN")
    ig_user_id = get_env("IG_BUSINESS_ACCOUNT_ID")
    repo = get_env("GITHUB_REPOSITORY")
    branch = os.environ.get("GITHUB_REF_NAME", "main")

    post_dir = find_next_post_dir()
    if post_dir is None:
        print("posts/ に投稿待ちのフォルダがありません。何もせず終了します。")
        return

    caption = load_caption(post_dir)
    images = list_image_files(post_dir)
    if not images:
        print(f"エラー: {post_dir} に画像が見つかりません", file=sys.stderr)
        sys.exit(1)

    print(f"投稿対象: {post_dir} (画像 {len(images)} 枚)")

    if len(images) == 1:
        image_url = build_raw_url(repo, branch, post_dir, images[0].name)
        container_id = create_image_container(ig_user_id, access_token, image_url, caption=caption)
        wait_until_finished(container_id, access_token)
        media_id = publish_container(ig_user_id, access_token, container_id)
    else:
        child_ids = []
        for image in images:
            image_url = build_raw_url(repo, branch, post_dir, image.name)
            child_id = create_image_container(
                ig_user_id, access_token, image_url, is_carousel_item=True
            )
            wait_until_finished(child_id, access_token)
            child_ids.append(child_id)

        carousel_id = create_carousel_container(ig_user_id, access_token, child_ids, caption)
        wait_until_finished(carousel_id, access_token)
        media_id = publish_container(ig_user_id, access_token, carousel_id)

    print(f"投稿に成功しました: media_id={media_id}")

    POSTS_DONE_DIR.mkdir(exist_ok=True)
    destination = POSTS_DONE_DIR / post_dir.name
    shutil.move(str(post_dir), str(destination))
    print(f"{post_dir} を {destination} へ移動しました")


if __name__ == "__main__":
    main()
