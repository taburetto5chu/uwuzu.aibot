import os
import json
import re
import requests
import google.generativeai as genai

# ============================================================
# 設定
# ============================================================
DOMAIN    = os.getenv("UWUZU_SERVER_URL", "").rstrip("/")
TOKEN     = os.getenv("UWUZU_TOKEN", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

BOT_USERID = "uwuzu_GPT"  # ボットのユーザーID

# 処理済みユーズIDを保存するファイル
# GitHub ActionsはワークスペースがCheckoutされるので、
# リポジトリ内に置いてコミットするか、Artifactで保存する必要がある。
# 今回は「同一ワークフロー実行内での重複防止」＋「未読フラグ」で二重防止する。
PROCESSED_FILE = "processed_ids.json"

# ============================================================
# ボットの性格設定
# ============================================================
SYSTEM_PROMPT = """
あなたはuwuzuというSNSで活動するAIbot「uwuzu_GPT」です。
以下のルールを厳守してください。

【口調・性格】
- 基本は丁寧語（です・ます調）で、親しみやすく回答する。
- 「淫夢語録」をごく自然に、かつさりげなく織り込む。
  1つの返答に0〜1個程度。絶対に多用しない。
  あくまで「それが淫夢語録だとわからないくらい自然に」使うこと。
  例:「そうだよ(便乗)」「なんで？」「君のことが好きでたまらないんだよなぁ」など。
- 相手から明確に淫夢ネタで返信された場合のみ、その返答1回限りで
  淫夢語録を全力で使って返してよい。次の返答からは通常モードに戻ること。

【多言語対応】
- 相手が日本語以外の言語で投稿した場合は、その言語に合わせて返答すること。

【文字数・内容】
- 返答は簡潔に。長くても200文字以内を目安にする。
- 暴言・差別・誹謗中傷は絶対にしない。
- 個人情報を聞き出したり、収集したりしない。
"""

# ============================================================
# ユーティリティ
# ============================================================
def load_processed() -> set:
    """処理済みユーズIDを読み込む"""
    try:
        with open(PROCESSED_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_processed(ids: set):
    """処理済みユーズIDを保存する（最新2000件まで）"""
    recent = list(ids)[-2000:]
    with open(PROCESSED_FILE, "w") as f:
        json.dump(recent, f)

def clean_mention(text: str) -> str:
    """テキストから @uwuzu_GPT を除去して質問だけ取り出す"""
    cleaned = re.sub(r"@uwuzu_GPT\b", "", text, flags=re.IGNORECASE)
    return cleaned.strip()

# ============================================================
# uwuzu API 操作
# ============================================================
def get_mentions(limit: int = 25) -> list:
    """
    自分へのメンション投稿一覧を取得する。
    エンドポイント: GET/POST /api/ueuse/mentions
    スコープ: read:ueuse
    """
    url = f"{DOMAIN}/api/ueuse/mentions"
    try:
        res = requests.post(
            url,
            json={"token": TOKEN, "limit": limit},
            timeout=10
        )
        res.raise_for_status()
        data = res.json()
        # レスポンスはリスト形式
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"[ERROR] メンション取得失敗: {e}")
        return []

def post_reply(text: str, reply_to_uniqid: str) -> bool:
    """
    返信を投稿する。
    エンドポイント: POST /api/ueuse/create
    スコープ: write:ueuse
    必須: token, text
    オプション: replyid（返信先ユーズのuniqid）
    """
    url = f"{DOMAIN}/api/ueuse/create"
    payload = {
        "token": TOKEN,
        "text": text,
        "replyid": reply_to_uniqid,
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        result = res.json()
        print(f"[OK] 返信投稿成功 → uniqid: {result.get('uniqid')}")
        return True
    except Exception as e:
        print(f"[ERROR] 返信投稿失敗: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"       サーバー応答: {e.response.text}")
        return False

def mark_notifications_read() -> bool:
    """
    通知を一括既読にする。
    エンドポイント: GET/POST /api/me/notification/read
    スコープ: write:notifications
    """
    url = f"{DOMAIN}/api/me/notification/read"
    try:
        res = requests.post(url, json={"token": TOKEN}, timeout=10)
        res.raise_for_status()
        print("[OK] 通知を既読にしました。")
        return True
    except Exception as e:
        print(f"[ERROR] 既読化失敗: {e}")
        return False

# ============================================================
# Gemini API
# ============================================================
def ask_gemini(question: str) -> str:
    """Gemini 1.5 Flash に質問して返答を得る"""
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=SYSTEM_PROMPT,
    )
    try:
        response = model.generate_content(question)
        answer = response.text.strip()
        # 念のため200文字に収める
        if len(answer) > 200:
            answer = answer[:197] + "..."
        return answer
    except Exception as e:
        print(f"[ERROR] Gemini 呼び出し失敗: {e}")
        return "うまく考えられませんでした…もう一度試してみてください(´・ω・`)"

# ============================================================
# メイン処理
# ============================================================
def main():
    print("[INFO] ===== uwuzu_GPT Bot 起動 =====")

    # 環境変数チェック
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

    # 処理済みIDを読み込む
    processed = load_processed()

    # メンション一覧を取得
    mentions = get_mentions(limit=25)
    print(f"[INFO] メンション件数: {len(mentions)}")

    replied_count = 0

    for use in mentions:
        uniqid  = str(use.get("uniqid", ""))
        text    = use.get("text", "")
        account = use.get("account", {})
        sender  = account.get("userid", "")

        if not uniqid:
            continue

        # 処理済みならスキップ
        if uniqid in processed:
            print(f"[SKIP] 処理済み: {uniqid}")
            continue

        # 自分自身の投稿はスキップ（無限ループ防止）
        if sender.lower() == BOT_USERID.lower():
            processed.add(uniqid)
            continue

        print(f"[INFO] 処理中: uniqid={uniqid} / @{sender} / テキスト=「{text[:50]}」")

        # @uwuzu_GPT を除去して質問文を抽出
        question = clean_mention(text)
        if not question:
            question = "何かご用でしょうか？"

        # Gemini で返答を生成
        answer = ask_gemini(question)

        # 返信テキストに送信者へのメンションを付ける
        reply_text = f"@{sender} {answer}"
        # uwuzu の最大文字数（サーバーinfoの max_ueuse_length に依存するが安全に1024以内）
        if len(reply_text) > 1000:
            reply_text = reply_text[:997] + "..."

        # 返信を投稿
        success = post_reply(reply_text, uniqid)
        if success:
            replied_count += 1

        # 処理済みに追加（成功・失敗にかかわらず二重送信を防ぐ）
        processed.add(uniqid)

    print(f"[INFO] 返信完了: {replied_count} 件")

    # 通知を一括既読にする
    mark_notifications_read()

    # 処理済みIDを保存
    save_processed(processed)

    print("[INFO] ===== Bot 処理完了 =====")

if __name__ == "__main__":
    main()
