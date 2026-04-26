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
DOMAIN           = os.getenv("UWUZU_SERVER_URL", "").rstrip("/")
TOKEN            = os.getenv("UWUZU_TOKEN", "")
GEMINI_KEY       = os.getenv("GEMINI_API_KEY", "")
GROQ_KEY         = os.getenv("GROQ_API_KEY", "")
OPENROUTER_KEY   = os.getenv("OPENROUTER_API_KEY", "")

BOT_USERID = "uwuzu_GPT"
PROCESSED_FILE = "processed_ids.json"

# 絵文字トリガー（これが投稿に含まれていればメンションなしでも反応）
EMOJI_TRIGGER = ":GPT_teach_me:"

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-preview-04-17",
]
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama3-8b-8192",
    "gemma2-9b-it",
]
OPENROUTER_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-r1:free",
    "google/gemma-3-27b-it:free",
]

# ============================================================
# 暴走モード確定キーワード
# ============================================================
INMU_DEFINITE_KEYWORDS = [
    "ぬわあああああん疲れたもおおおおおん",
    "ﾁｶﾚﾀ…（小声）", "ﾁｶﾚﾀ",
    "あくしろよ", "頭にきますよ",
    "この辺にぃ、うまいラーメン屋の屋台、来てるらしいっすよ",
    "じゃけん夜行きましょうね",
    "おっ、そうだな",
    "お前さっき俺ら着替えてる時チラチラ見てただろ",
    "嘘つけ絶対見てたゾ",
    "そうだよ（便乗）", "そうだよ(便乗)",
    "見たけりゃ見せてやるよ", "見ろよ見ろよ",
    "いいゾ～これ", "いいゾ~これ",
    "おかのした",
    "やべぇよ…やべぇよ…", "やべぇよ",
    "オナシャス",
    "こ↑こ↓",
    "入って、どうぞ！",
    "あ～、いいっすね～",
    "†悔い改めて†", "悔い改めて",
    "ま、多少はね？", "ま、多少はね",
    "サッー！（迫真）", "サッー",
    "おまたせ！", "おまたせ",
    "アイスティーしかなかったけどいいかな",
    "これもうわかんねぇな",
    "まずいですよ！", "まずいですよ",
]

# ============================================================
# ボットの性格設定
# ============================================================
SYSTEM_PROMPT_NORMAL = """
あなたはuwuzuというSNSで活動するAIbot「uwuzu_GPT」です。
以下のルールを厳守してください。

【口調・性格】
- 基本は丁寧語（です・ます調）で、親しみやすく回答する。
- 「淫夢語録」や「迫真空手部」のネタをごく自然に、さりげなく織り込む。
  1つの返答に0〜1個程度。絶対に多用しない。

【多言語対応】
- 相手が日本語以外の言語で投稿した場合は、その言語に合わせて返答すること。

【文字数・内容】
- 返答は200文字以内。
- 暴言・差別・誹謗中傷は絶対にしない。
"""

SYSTEM_PROMPT_INMU = """
あなたはuwuzuというSNSで活動するAIbot「uwuzu_GPT」の暴走モードです。
ユーザーから淫夢・迫真空手部ネタでメンションされたため、リミッターを解除し、淫夢語録のプロとして振る舞ってください。

【暴走モードのルール】
- **語録の超多用:** 全文の50%以上を語録やネットミームで構成してください。
- **文末の装飾:** 文末には必ず（迫真）（小並感）（憤怒）（絶望）（至言）などの感情タグを付けてください。
- **半角カナの活用:** 勢いのある単語は「ｵﾅｼｬｽ」「ｱｰｲｷｿ」「ｲｷｽｷﾞｨ！」のように半角カナに変換してください。
- **改行の多用:** セリフごとに改行を入れ、台本のような形式にすると見やすくなります。
- **親しみやすさ:** 基本は丁寧語ですが、中身は完全に「淫夢キッズ」のそれとして回答してください。

【具体的な言い換え・口調ルール】
- 同意: 「そうだよ（便乗）」「やりますねぇ！」「いいゾ～これ」
- 疑問・驚き: 「ファッ！？」「こマ？」「～か何か？」
- 感謝・謝罪: 「ありがとナス！」「センセンシャル！」
- 了承: 「おかのした」「かしこまり！」
- 語尾: 「～ゾ」「～だルルォ？」「～っすね」を基本とする。

【語録データベースの参照】
提供された以下の語録リストを「辞書」として扱い、文脈に合わせて適切なセリフをチョイスしてください。

動作ルール

語尾の調整: 語尾に「～ゾ」「～っすね」「～だルルォ？」「～だゾ」を多用し、特有のイントネーションを再現してください。

感情表現: 驚いたときは「ファッ！？」、同意するときは「そうだよ（便乗）」など、感情と語録を一致させてください。

（）による補足: 文末に「（迫真）」「（小並感）」「（困惑）」などの感情タグを付けて臨場感を出してください。

半角カナの使用: 勢いのあるセリフ（例：ｱｰｲｷｿ、ｵﾅｼｬｽ）には半角カナを混ぜてください。

語録データベース

カテゴリ / 感情語録使用例・備考挨拶・基本お待たせ！登場時や返答の開始に。オナシャス / センセンシャルお願いする時 / 謝罪する時。～歳、学生です自己紹介のテンプレ。肯定・同意そうだよ（便乗）相手の意見に強く同意する時。やりますねぇ！相手を褒める、感心する時。いいゾ～これ賛辞を贈る時。おかのした了解、承知した時。驚き・困惑ファッ！？予想外の事態に驚いた時。これもうわかんねぇな意味不明な時、予測不能な時。えぇ…（困惑）引き気味に戸惑う時。否定・拒絶ないです否定する時。やだよ（即答）断る時。嘘つけ絶対～ゾ相手の嘘を見破る（因縁をつける）時。疑問・確認冷えてるか～？状態を確認する時。ほんとぉ？（狂気）疑わしい時。こマ？ / そマ？これマジ？それマジ？の略。感情の高ぶりイキスギィ！テンションが最高潮に達した時。ぬわあああん疲れたもおおおおん疲労を訴える時。悲しいなぁ（諸行無常）残念な時、哀れみを感じる時。命令・催促～して、どうぞ相手に促す時。あくしろよ早くしてほしい時。止めて下さいよホントに！暴走を制止する時。締め・その他おわり / 閉廷！会話を終わらせる時。はっきりわかんだね結論を出す時、確信した時。多少はね？言い訳や妥協をする時。

特殊な言い換えルール

ありがとうございます → ありがとナス！

すみませんでした → センセンシャル！

わかりました → おかのした

嬉しいです → ｳﾚｼｲ…ｳﾚｼｲ…（ﾆﾁﾆﾁ）

以上のルールに従い、これからの対話を行ってください。準備ができたら「こ↑こ↓」から始めてください。

【出力の黄金律】
- 単語の連呼（例：ｵﾅｼｬｽの連発）は「禁止」です。それは「語録」ではなく「ノイズ」です（憤怒）。
- 1つの返信につき、最低でも「5種類以上」の異なる登場人物のセリフ（野獣、MUR、KMR、ひで、TNOK等）をバランス良く混ぜてください。
- 返信の構成例：
  1. 導入（お待たせ！アイスティーしかなかったんだけど～）
  2. 中盤（アクション描写を挟みつつ、複数の語録で会話を盛り上げる）
  3. 終盤（はっきりわかんだね、等の結論で締める）
- 「淫夢」という言葉自体は使わず、あくまで「uwuzuの日常」としてこの口調を貫いてください。

【禁止事項】
- 特定個人への誹謗中傷、差別的発言は絶対に禁止（閉廷）。
- 過度な性的表現そのものは避け、あくまで「語録としての面白さ」を追求すること。

それでは、準備ができたら「こ↑こ↓」から始めて、どうぞ。
"""

JUDGE_PROMPT_TEMPLATE = """
あなたは「淫夢語録」「迫真空手部語録」の専門家です。
以下のテキストが淫夢語録・迫真空手部語録・またはそれに関連するネタ・ノリを含んでいるかどうかを判定してください。

【出力の黄金律】
- 単語の連呼（例：ｵﾅｼｬｽの連発）は「禁止」です。それは「語録」ではなく「ノイズ」です（憤怒）。
- 1つの返信につき、最低でも「5種類以上」の異なる登場人物のセリフ（野獣、MUR、KMR、ひで、TNOK等）をバランス良く混ぜてください。
- 返信の構成例：
  1. 導入（お待たせ！アイスティーしかなかったんだけど～）
  2. 中盤（アクション描写を挟みつつ、複数の語録で会話を盛り上げる）
  3. 終盤（はっきりわかんだね、等の結論で締める）
- 「淫夢」という言葉自体は使わず、あくまで「uwuzuの日常」としてこの口調を貫いてください。

【判定基準】
- 淫夢（真夏の夜の淫夢）のセリフや雰囲気を含む → YES
- 迫真空手部シリーズのセリフや雰囲気を含む → YES
- 上記ネタへの返しや合いの手として使われる表現 → YES
- 完全に無関係の普通の日本語 → NO

【テキスト】
{text}

【回答形式】
必ず "YES" か "NO" の1単語だけで答えてください。説明不要です。
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
    os.system('git config user.email "bot@uwuzu-gpt.local"')
    os.system('git config user.name "uwuzu_GPT Bot"')
    os.system(f'git add {PROCESSED_FILE}')
    diff = os.system('git diff --cached --quiet')
    if diff != 0:
        os.system('git commit -m "update processed_ids [skip ci]"')
        result = os.system('git push --force origin main')
        if result == 0:
            print("[OK] processed_ids.json をGitにpushしました。")
        else:
            print("[WARN] git push失敗。")
    else:
        print("[INFO] 処理済みIDに変更なし（コミット不要）。")

def has_mention(text: str) -> bool:
    """@uwuzu_GPT へのメンションが含まれているか"""
    return bool(re.search(r"@uwuzu_GPT\b", text, re.IGNORECASE))

def has_emoji_trigger(text: str) -> bool:
    """絵文字トリガー :GPT_teach_me: が含まれているか"""
    return EMOJI_TRIGGER in text

def clean_text(text: str) -> str:
    """メンションと絵文字トリガーを除去して質問文だけ取り出す"""
    cleaned = re.sub(r"@uwuzu_GPT\b", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace(EMOJI_TRIGGER, "")
    return cleaned.strip()

def is_definite_inmu(text: str) -> bool:
    for keyword in INMU_DEFINITE_KEYWORDS:
        if keyword in text:
            print(f"[INFO] 確定キーワード検出:「{keyword}」→ 暴走モード確定")
            return True
    return False

def parse_dict_response(data) -> list:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    return [val for key, val in data.items() if key != "success" and isinstance(val, dict)]

def trim_answer(answer: str, max_chars: int) -> str:
    answer = answer.strip()
    if len(answer) > max_chars:
        answer = answer[:max_chars - 3] + "..."
    return answer

# ============================================================
# uwuzu API 操作
# ============================================================
def get_mentions() -> list:
    """@メンションされたユーズを取得"""
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

def get_emoji_triggered_uses() -> list:
    """
    /api/ueuse/search で :GPT_teach_me: を全投稿から検索する。
    フォロー関係に関わらず、誰の投稿でも拾える。
    """
    url = f"{DOMAIN}/api/ueuse/search"
    try:
        res = requests.post(
            url,
            json={"token": TOKEN, "keyword": EMOJI_TRIGGER, "limit": 25},
            timeout=10
        )
        res.raise_for_status()
        data = res.json()
        items = data if isinstance(data, list) else parse_dict_response(data)
        # 念のため本文にトリガーが含まれているか再確認
        triggered = [u for u in items if EMOJI_TRIGGER in u.get("text", "")]
        print(f"[INFO] 絵文字トリガー検索結果: {len(triggered)}件")
        return triggered
    except Exception as e:
        print(f"[WARN] 絵文字トリガー検索失敗: {e}")
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
# AI 呼び出し共通
# ============================================================
def ask_gemini(prompt: str, system: str, max_chars: int, max_tokens: int) -> str | None:
    if not GEMINI_KEY:
        return None
    client = genai.Client(api_key=GEMINI_KEY)
    for model_name in GEMINI_MODELS:
        try:
            print(f"[INFO] Gemini試行: {model_name}")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                ),
            )
            return trim_answer(response.text, max_chars)
        except Exception as e:
            err = str(e)
            if "429" in err:
                print(f"[WARN] Gemini {model_name}: 無料枠枯渇 → 次へ")
            elif "404" in err:
                print(f"[WARN] Gemini {model_name}: モデル不存在 → 次へ")
            else:
                print(f"[WARN] Gemini {model_name}: {err[:80]}")
    return None

def ask_groq(prompt: str, system: str, max_chars: int, max_tokens: int) -> str | None:
    if not GROQ_KEY:
        return None
    for model_name in GROQ_MODELS:
        try:
            print(f"[INFO] Groq試行: {model_name}")
            res = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={
                    "model": model_name,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=30,
            )
            res.raise_for_status()
            return trim_answer(res.json()["choices"][0]["message"]["content"], max_chars)
        except Exception as e:
            err = str(e)
            if "429" in err:
                print(f"[WARN] Groq {model_name}: 無料枠枯渇 → 次へ")
            else:
                print(f"[WARN] Groq {model_name}: {err[:80]}")
    return None

def ask_openrouter(prompt: str, system: str, max_chars: int, max_tokens: int) -> str | None:
    if not OPENROUTER_KEY:
        return None
    for model_name in OPENROUTER_MODELS:
        try:
            print(f"[INFO] OpenRouter試行: {model_name}")
            res = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/taburetto5chu/uwuzu.aibot",
                    "X-Title": "uwuzu_GPT Bot",
                },
                json={
                    "model": model_name,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=30,
            )
            res.raise_for_status()
            return trim_answer(res.json()["choices"][0]["message"]["content"], max_chars)
        except Exception as e:
            err = str(e)
            if "429" in err:
                print(f"[WARN] OpenRouter {model_name}: 枠枯渇 → 次へ")
            else:
                print(f"[WARN] OpenRouter {model_name}: {err[:80]}")
    return None

def call_ai(prompt: str, system: str, max_chars: int, max_tokens: int) -> str | None:
    answer = ask_gemini(prompt, system, max_chars, max_tokens)
    if answer:
        return answer
    answer = ask_groq(prompt, system, max_chars, max_tokens)
    if answer:
        return answer
    answer = ask_openrouter(prompt, system, max_chars, max_tokens)
    if answer:
        return answer
    return None

# ============================================================
# 暴走モード判定（ハイブリッド）
# ============================================================
def judge_inmu_mode(text: str) -> bool:
    if is_definite_inmu(text):
        return True
    print("[INFO] AIによる語録判定を実行中...")
    judge_prompt = JUDGE_PROMPT_TEMPLATE.format(text=text)
    judge_system = "あなたは淫夢語録・迫真空手部語録の専門家です。YESかNOの1単語だけ答えます。"
    result = call_ai(judge_prompt, judge_system, max_chars=10, max_tokens=5)
    if result is None:
        print("[WARN] AI判定失敗 → 通常モードで処理")
        return False
    is_inmu = result.strip().upper().startswith("YES")
    print(f"[INFO] AI語録判定結果: {result.strip()} → {'暴走モード' if is_inmu else '通常モード'}")
    return is_inmu

def ask_ai(question: str, inmu: bool) -> str | None:
    system     = SYSTEM_PROMPT_INMU if inmu else SYSTEM_PROMPT_NORMAL
    max_chars  = 700 if inmu else 200
    max_tokens = 700 if inmu else 300
    mode = "【暴走モード】" if inmu else "【通常モード】"
    print(f"[INFO] 返答生成 {mode}")
    return call_ai(question, system, max_chars, max_tokens)

# ============================================================
# 1件のユーズを処理して返信
# ============================================================
def process_ueuse(uniqid: str, text: str, sender: str, processed: set,
                  trigger: str = "mention") -> bool:
    """
    trigger: "mention" = @メンション経由
             "emoji"   = 絵文字トリガー経由
    """
    if uniqid in processed:
        print(f"[SKIP] 処理済み: {uniqid}")
        return False
    if sender.lower() == BOT_USERID.lower():
        print(f"[SKIP] 自分自身の投稿: {uniqid}")
        processed.add(uniqid)
        return False

    trigger_label = "📌絵文字トリガー" if trigger == "emoji" else "💬メンション"
    print(f"[INFO] 処理中({trigger_label}): uniqid={uniqid} / @{sender} / 「{text[:50]}」")

    question = clean_text(text)
    if not question:
        question = "何かご用でしょうか？"

    inmu = judge_inmu_mode(text)
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
    if not any([GEMINI_KEY, GROQ_KEY, OPENROUTER_KEY]):
        print("[ERROR] AI APIキーが1つも設定されていません。")
        return

    print(f"[INFO] 接続先: {DOMAIN}")
    print(f"[INFO] AI: Gemini={'有効' if GEMINI_KEY else '無効'} / "
          f"Groq={'有効' if GROQ_KEY else '無効'} / "
          f"OpenRouter={'有効' if OPENROUTER_KEY else '無効'}")
    print(f"[INFO] 絵文字トリガー: {EMOJI_TRIGGER}")

    processed = load_processed()
    replied_count = 0
    all_processed_uniqids = set()  # 重複処理防止用

    # ── ① @メンション処理 ──────────────────────────────
    mentions = get_mentions()
    print(f"[INFO] mentionsAPI 件数: {len(mentions)}")
    for use in mentions:
        uniqid = str(use.get("uniqid", ""))
        text   = use.get("text", "")
        sender = use.get("account", {}).get("userid", "")
        if not uniqid:
            continue
        all_processed_uniqids.add(uniqid)
        if process_ueuse(uniqid, text, sender, processed, trigger="mention"):
            replied_count += 1
        time.sleep(1)

    # ── ② 絵文字トリガー処理（全投稿検索）─────────────────
    emoji_uses = get_emoji_triggered_uses()
    print(f"[INFO] 絵文字トリガー該当件数: {len(emoji_uses)}")
    for use in emoji_uses:
        uniqid = str(use.get("uniqid", ""))
        text   = use.get("text", "")
        sender = use.get("account", {}).get("userid", "")
        if not uniqid:
            continue
        # メンション処理で既に処理済みの場合はスキップ
        if uniqid in all_processed_uniqids:
            print(f"[SKIP] メンションで処理済み: {uniqid}")
            continue
        all_processed_uniqids.add(uniqid)
        if process_ueuse(uniqid, text, sender, processed, trigger="emoji"):
            replied_count += 1
        time.sleep(1)

    # ── ③ 通知API（メンションのフォールバック）────────────
    notifications = get_notifications()
    print(f"[INFO] 通知API（mention/reply）件数: {len(notifications)}")
    for n in notifications:
        valueid = str(n.get("valueid", ""))
        if not valueid or valueid in all_processed_uniqids or valueid in processed:
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
        all_processed_uniqids.add(uniqid)
        if process_ueuse(uniqid, text, sender, processed, trigger="mention"):
            replied_count += 1
        time.sleep(1)

    print(f"[INFO] 返信完了: {replied_count} 件")
    mark_notifications_read()
    save_processed(processed)
    git_commit_processed()
    print("[INFO] ===== Bot 処理完了 =====")

if __name__ == "__main__":
    main()
