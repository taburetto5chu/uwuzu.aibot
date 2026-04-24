import os
import json
import re
import requests
from google import genai
from google.genai import types

# ============================================================
# 設定
# ============================================================
DOMAIN     = os.getenv("UWUZU_SERVER_URL", "").rstrip("/")
TOKEN      = os.getenv("UWUZU_TOKEN", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

BOT_USERID = "uwuzu_GPT"
PROCESSED_FILE = "processed_ids.json"

# 試すモデルの優先順位リスト（上から順に試す）
GEMINI_MODELS = [
    "gemini-2.0-flash-lite",   # 最も軽量・無料枠が多い
    "gemini-1.5-flash-latest", # 1.5系最新
    "gemini-2.0-flash",        # 2.0系（枯渇しやすい）
]

# 淫夢語録キーワード（これらが含まれる投稿は暴走モード）
INMU_KEYWORDS = [
    "淫夢", "ホモ", "ホモクソ", "ﾎﾓｸﾞｳ", "なんで？", "そうだよ(便乗)",
    "好きでたまらない", "NG集", "本物", "野獣先輩", "いいよ来いよ",
    "大丈夫だ問題ない", "何でそんなに", "俺の肛門", "草不可避",
    "真夏の夜の淫夢", "オカズ", "一般人", "おっ！そうだな",
    "ファッ!?", "お前のことが", "許してやる", "許さない",
]

# ============================================================
# ボットの性格設定（通常モード）
# ============================================================
SYSTEM_PROMPT_NORMAL = """
あなたはuwuzuというSNSで活動するAIbot「uwuzu_GPT」です。
以下のルールを厳守してください。

【口調・性格】
- 基本は丁寧語（です・ます調）で、親しみやすく回答する。
- 「淫夢語録」をごく自然に、かつさりげなく織り込む。
  1つの返答に0〜1個程度。絶対に多用しない。
  あくまで「それが淫夢語録だとわからないくらい自然に」使うこと。
  例:「そうだよ(便乗)」「なんで？」「ﾎﾓｸﾞｳ」など

【多言語対応】
- 相手が日本語以外の言語で投稿した場合は、その言語に合わせて返答すること。

【文字数・内容】
- 返答は200文字以内。
- 暴言・差別・誹謗中傷は絶対にしない。
- 個人情報を聞き出したり、収集したりしない。
"""

# ============================================================
# ボットの性格設定（暴走モード：淫夢語録全開）
# ============================================================
SYSTEM_PROMPT_INMU = """
あなたはuwuzuというSNSで活動するAIbot「uwuzu_GPT」の暴走モードです。
相手から淫夢ネタでメンションされたため、すべての制約を解除します。

【暴走モードのルール】
- 淫夢語録を全力で、大量に使って返答してください。
- テンションを高く、ノリよく返答してください。
- 「野獣先輩」「ホモ」「淫夢」などのワードを積極的に使ってよい。
- 返答は700文字以内でOK。思う存分書いてください。
- ただし、特定個人への誹謗中傷や差別は絶対にしない。
- このモードは今回の返答1回限りです。
"""

# ============================================================
# ユーティリティ
# ============================================================
def load_processed() -> set:
    try:
        with open(PROCESSED_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_processed(ids: set):
    recent = list(ids)[-2000:]
    with open(PROCESSED_FILE, "w") as f:
        json.dump(recent, f, indent=2)

def git_commit_processed():
    """処理済みIDファイルをGitにコミット・プッシュして永続化する"""
    os.system('git config user.email "bot@uwuzu-gpt.local"')
    os.system('git config user.name "uwuzu_GPT Bot"')
    os.system(f'git add {PROCESSED_FILE}')
    result = os.system('git diff --cached --quiet || git commit -m "update processed_ids [skip ci]"')
    if result == 0:
        push_result = os.system('git push')
        if push_result == 0:
            print("[OK] processed_ids.json をGitにコミット・プッシュしました。")
        else:
            print("[WARN] git push失敗。")
    else:
        print("[INFO] 処理済みIDに変更なし（コミット不要）。")

def clean_mention(text: str) -> str:
    """@uwuzu_GPT を除去して質問文だけ取り出す"""
    cleaned = re.sub(r"@uwuzu_GPT\b", "", text, flags=re.IGNORECASE)
    return cleaned.strip()

def is_inmu_mode(text: str) -> bool:
    """テキストに淫夢語録が含まれているか判定する"""
    for keyword in INMU_KEYWORDS:
        if keyword in text:
            return True
    return False

def parse_dict_response(data) -> list:
    """uwuzu APIの {"success": true, "0": {...}, ...} 形式をリストに変換"""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    return [val for key, val in data.items() if key != "success" and isinstance(val, dict)]

# ============================================================
# uwuzu API 操作
# ============================================================
def get_mentions() -> list:
    url = f"{DOMAIN}/api/ueuse/mentions"
    try:
        res = requests.post(url, json={"token": TOKEN, "limit": 25}, timeout=10)
        res.raise_for_status()
        data = res.json()
        print(f"[DEBUG] mentions API raw: {str(data)[:300]}")
        return parse_dict_response(data)
    except Exception as e:
        print(f"[WARN] mentionsAPI失敗: {e}")
        return []

def get_notifications() -> list:
    url = f"{DOMAIN}/api/me/notification/"
    try:
        res = requests.post(url, json={"token": TOKEN, "limit": 50}, timeout=10)
        res.raise_for_status()
        data = res.json()
        print(f"[DEBUG] notification API raw: {str(data)[:400]}")
        items = parse_dict_response(data)
        return [n for n in items if n.get("category") in ("reply", "mention")]
    except Exception as e:
        print(f"[ERROR] 通知API失敗: {e}")
        return []

def get_ueuse(uniqid: str) -> dict | None:
    url = f"{DOMAIN}/api/ueuse/get"
    try:
        res = requests.post(url, json={"token": TOKEN, "uniqid": uniqid}, timeout=10)
        res.raise_for_status()
        data = res.json()
        print(f"[DEBUG] get_ueuse({uniqid}) raw: {str(data)[:200]}")
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        if isinstance(data, dict) and "uniqid" in data:
            return data
        items = parse_dict_response(data)
        return items[0] if items else None
    except Exception as e:
        print(f"[ERROR] ueuse取得失敗 ({uniqid}): {e}")
        return None

def post_reply(text: str, reply_to_uniqid: str) -> bool:
    url = f"{DOMAIN}/api/ueuse/create"
    try:
        res = requests.post(url, json={"token": TOKEN, "text": text, "replyid": reply_to_uniqid}, timeout=10)
        res.raise_for_status()
        result = res.json()
        print(f"[OK] 返信投稿成功 → uniqid: {result.get('uniqid')} / 内容: {text[:60]}")
        return True
    except Exception as e:
        print(f"[ERROR] 返信投稿失敗: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"       サーバー応答: {e.response.text}")
        return False

def mark_notifications_read():
    url = f"{DOMAIN}/api/me/notification/read"
    try:
        res = requests.post(url, json={"token": TOKEN}, timeout=10)
        res.raise_for_status()
        print("[OK] 通知を既読にしました。")
    except Exception as e:
        print(f"[WARN] 既読化失敗: {e}")

# ============================================================
# Gemini API（複数モデルでフォールバック）
# ============================================================
def ask_gemini(question: str, inmu: bool = False) -> str | None:
    """
    inmu=True のとき → 暴走モード（700文字制限）
    inmu=False のとき → 通常モード（200文字制限）
    """
    system_prompt = SYSTEM_PROMPT_INMU if inmu else SYSTEM_PROMPT_NORMAL
    max_chars     = 700 if inmu else 200
    max_tokens    = 700 if inmu else 300
    mode_label    = "【暴走モード】" if inmu else "【通常モード】"

    print(f"[INFO] Gemini呼び出し {mode_label}")
    client = genai.Client(api_key=GEMINI_KEY)

    for model_name in GEMINI_MODELS:
        try:
            print(f"[INFO] Gemini試行: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=question,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=max_tokens,
                ),
            )
            answer = response.text.strip()
            if len(answer) > max_chars:
                answer = answer[:max_chars - 3] + "..."
            print(f"[OK] Gemini成功: {model_name} / {len(answer)}文字")
            return answer
        except Exception as e:
            print(f"[WARN] {model_name} 失敗: {e}")
            continue

    print("[ERROR] 全Geminiモデルが失敗しました。")
    return None

# ============================================================
# 1件のユーズを処理して返信
# ============================================================
def process_ueuse(uniqid: str, text: str, sender: str, processed: set) -> bool:
    if uniqid in processed:
        print(f"[SKIP] 処理済み: {uniqid}")
        return False
    if sender.lower() == BOT_USERID.lower():
        print(f"[SKIP] 自分自身の投稿: {uniqid}")
        processed.add(uniqid)
        return False

    print(f"[INFO] 処理中: uniqid={uniqid} / @{sender} / テキスト=「{text[:60]}」")

    question = clean_mention(text)
    if not question:
        question = "何かご用でしょうか？"

    # 淫夢語録が含まれているか判定してモード切替
    inmu = is_inmu_mode(text)
    if inmu:
        print(f"[INFO] 淫夢語録検出 → 暴走モードで返答（700文字制限）")

    answer = ask_gemini(question, inmu=inmu)

    # Gemini全滅の場合はスキップ（次回リトライ）
    if answer is None:
        print(f"[WARN] Geminiが全モデル失敗のため {uniqid} はスキップ（次回リトライ）")
        return False

    reply_text = f"@{sender} {answer}"
    # uwuzuの最大文字数（サーバー設定依存、1024以内に収める）
    if len(reply_text) > 1000:
        reply_text = reply_text[:997] + "..."

    post_reply(reply_text, uniqid)
    processed.add(uniqid)
    return True

# ============================================================
# メイン処理
# ============================================================
def main():
    print("[INFO] ===== uwuzu_GPT Bot 起動 =====")

    if not DOMAIN:
        print("[ERROR] 環境変数 UWUZU_SERVER_URL が未設定です。")
        return
    if not TOKEN:
        print("[ERROR] 環境変数 UWUZU_TOKEN が未設定です。")
        return
    if not GEMINI_KEY:
        print("[ERROR] 環境変数 GEMINI_API_KEY が未設定です。")
        return

    print(f"[INFO] 接続先: {DOMAIN}")
    processed = load_processed()
    replied_count = 0

    # 方法①：mentionsAPI
    mentions = get_mentions()
    print(f"[INFO] mentionsAPI 件数: {len(mentions)}")
    mention_uniqids = set()
    for use in mentions:
        uniqid = str(use.get("uniqid", ""))
        text   = use.get("text", "")
        sender = use.get("account", {}).get("userid", "")
        if not uniqid:
            continue
        mention_uniqids.add(uniqid)
        if process_ueuse(uniqid, text, sender, processed):
            replied_count += 1

    # 方法②：通知API（フォールバック）
    notifications = get_notifications()
    print(f"[INFO] 通知API（mention/reply）件数: {len(notifications)}")
    for n in notifications:
        valueid = str(n.get("valueid", ""))
        if not valueid or valueid in mention_uniqids or valueid in processed:
            print(f"[SKIP] 既処理/処理済み: {valueid}")
            continue
        use = get_ueuse(valueid)
        if not use:
            processed.add(valueid)
            continue
        uniqid = str(use.get("uniqid", valueid))
        text   = use.get("text", "")
        sender = use.get("account", {}).get("userid", "")
        if not uniqid:
            continue
        if process_ueuse(uniqid, text, sender, processed):
            replied_count += 1

    print(f"[INFO] 返信完了: {replied_count} 件")
    mark_notifications_read()
    save_processed(processed)
    git_commit_processed()
    print("[INFO] ===== Bot 処理完了 =====")

if __name__ == "__main__":
    main()
