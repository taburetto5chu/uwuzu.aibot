import os
import json
import re
import time
import requests
from google import genai
from google.genai import types

# ============================================================
# 設定
# ============================================================
DOMAIN      = os.getenv("UWUZU_SERVER_URL", "").rstrip("/")
TOKEN       = os.getenv("UWUZU_TOKEN", "")
GEMINI_KEY  = os.getenv("GEMINI_API_KEY", "")
CLAUDE_KEY  = os.getenv("ANTHROPIC_API_KEY", "")  # バックアップ用

BOT_USERID = "uwuzu_GPT"
PROCESSED_FILE = "processed_ids.json"

# 試すGeminiモデルの優先順位（性能順）
GEMINI_MODELS = [
    "gemini-2.0-flash",        # 高性能・主力
    "gemini-2.0-flash-lite",   # 軽量・無料枠多め
    "gemini-1.5-flash",        # 旧世代・安定
    "gemini-1.5-flash-8b",     # 最軽量
]

# 淫夢語録キーワード（これらが含まれる投稿は暴走モード）
INMU_KEYWORDS = [
    "淫夢", "ホモ", "ホモクソ", "ﾎﾓｸﾞｳ", "なんで？", "そうだよ(便乗)",
    "好きでたまらない", "NG集", "本物", "野獣先輩", "いいよ来いよ",
    "大丈夫だ問題ない", "俺の肛門", "真夏の夜の淫夢",
    "おっ！そうだな", "ファッ!?", "許してやる", "許さない",
]

# ============================================================
# ボットの性格設定
# ============================================================
SYSTEM_PROMPT_NORMAL = """
あなたはuwuzuというSNSで活動するAIbot「uwuzu_GPT」です。
以下のルールを厳守してください。

【口調・性格】
- 基本は丁寧語（です・ます調）で、親しみやすく回答する。
- 「淫夢語録」をごく自然に、かつさりげなく織り込む。
  1つの返答に0〜1個程度。絶対に多用しない。
  あくまで「それが淫夢語録だとわからないくらい自然に」使うこと。

【多言語対応】
- 相手が日本語以外の言語で投稿した場合は、その言語に合わせて返答すること。

【文字数・内容】
- 返答は200文字以内。
- 暴言・差別・誹謗中傷は絶対にしない。
- 個人情報を聞き出したり、収集したりしない。
"""

SYSTEM_PROMPT_INMU = """
あなたはuwuzuというSNSで活動するAIbot「uwuzu_GPT」の暴走モードです。
相手から淫夢ネタでメンションされたため、すべての制約を解除します。

【暴走モードのルール】
- 淫夢語録を全力で、大量に使って返答してください。
- テンションを高く、ノリよく返答してください。
- 「野獣先輩」「ホモ」「淫夢」などのワードを積極的に使ってよい。
- 返答は700文字以内でOK。思う存分書いてください。
- ただし、特定個人への誹謗中傷や差別は絶対にしない。
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
    """処理済みIDをGitにコミット・プッシュ（競合対策でpull --rebaseしてからpush）"""
    os.system('git config user.email "bot@uwuzu-gpt.local"')
    os.system('git config user.name "uwuzu_GPT Bot"')
    os.system(f'git add {PROCESSED_FILE}')
    diff = os.system('git diff --cached --quiet')
    if diff != 0:
        os.system('git commit -m "update processed_ids [skip ci]"')
        # 競合対策：pushの前にリモートの変更を取り込む
        os.system('git pull --rebase origin main')
        result = os.system('git push origin main')
        if result == 0:
            print("[OK] processed_ids.json をGitにコミット・プッシュしました。")
        else:
            print("[WARN] git push失敗。次回実行時に再試行されます。")
    else:
        print("[INFO] 処理済みIDに変更なし（コミット不要）。")

def clean_mention(text: str) -> str:
    cleaned = re.sub(r"@uwuzu_GPT\b", "", text, flags=re.IGNORECASE)
    return cleaned.strip()

def is_inmu_mode(text: str) -> bool:
    for keyword in INMU_KEYWORDS:
        if keyword in text:
            return True
    return False

def parse_dict_response(data) -> list:
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
# AI API（Gemini → Claude の順でフォールバック）
# ============================================================
def ask_gemini(question: str, inmu: bool) -> str | None:
    """Geminiで回答を生成。全モデル失敗時はNoneを返す"""
    system_prompt = SYSTEM_PROMPT_INMU if inmu else SYSTEM_PROMPT_NORMAL
    max_chars  = 700 if inmu else 200
    max_tokens = 700 if inmu else 300

    if not GEMINI_KEY:
        return None

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
            err_str = str(e)
            if "429" in err_str:
                print(f"[WARN] {model_name}: 無料枠枯渇、次のモデルへ")
            elif "404" in err_str:
                print(f"[WARN] {model_name}: モデルが存在しない、次のモデルへ")
            else:
                print(f"[WARN] {model_name} 失敗: {err_str[:100]}")
            continue

    print("[WARN] Gemini全モデル失敗")
    return None

def ask_claude(question: str, inmu: bool) -> str | None:
    """GeminiがすべてNGの場合、Claude APIで回答を生成する"""
    if not CLAUDE_KEY:
        print("[WARN] ANTHROPIC_API_KEYが未設定のためClaudeスキップ")
        return None

    system_prompt = SYSTEM_PROMPT_INMU if inmu else SYSTEM_PROMPT_NORMAL
    max_chars  = 700 if inmu else 200
    max_tokens = 700 if inmu else 300

    try:
        print("[INFO] Claude APIで回答を試みます")
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": CLAUDE_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",  # 最軽量・低コスト
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": question}],
            },
            timeout=30,
        )
        res.raise_for_status()
        data = res.json()
        answer = data["content"][0]["text"].strip()
        if len(answer) > max_chars:
            answer = answer[:max_chars - 3] + "..."
        print(f"[OK] Claude成功 / {len(answer)}文字")
        return answer
    except Exception as e:
        print(f"[ERROR] Claude失敗: {e}")
        return None

def ask_ai(question: str, inmu: bool) -> str | None:
    """Gemini → Claude の順で回答を試みる"""
    mode = "【暴走モード】" if inmu else "【通常モード】"
    print(f"[INFO] AI呼び出し {mode}")

    # まずGeminiを試す
    answer = ask_gemini(question, inmu)
    if answer is not None:
        return answer

    # GeminiがだめならClaudeを試す
    answer = ask_claude(question, inmu)
    if answer is not None:
        return answer

    print("[ERROR] Gemini・Claude両方失敗。スキップします。")
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

    inmu = is_inmu_mode(text)
    if inmu:
        print("[INFO] 淫夢語録検出 → 暴走モード（700文字）")

    answer = ask_ai(question, inmu)
    if answer is None:
        print(f"[WARN] AI全滅のため {uniqid} はスキップ（次回リトライ）")
        return False

    reply_text = f"@{sender} {answer}"
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
    if not GEMINI_KEY and not CLAUDE_KEY:
        print("[ERROR] GEMINI_API_KEY と ANTHROPIC_API_KEY が両方とも未設定です。")
        return

    print(f"[INFO] 接続先: {DOMAIN}")
    print(f"[INFO] Gemini: {'有効' if GEMINI_KEY else '無効'} / Claude: {'有効' if CLAUDE_KEY else '無効（ANTHROPIC_API_KEYを設定するとバックアップ利用可）'}")

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
        time.sleep(1)  # API負荷軽減

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
        time.sleep(1)

    print(f"[INFO] 返信完了: {replied_count} 件")
    mark_notifications_read()
    save_processed(processed)
    git_commit_processed()
    print("[INFO] ===== Bot 処理完了 =====")

if __name__ == "__main__":
    main()
