import os
import requests
import google.generativeai as genai
import json

# --- 設定の読み込み ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
UWUZU_TOKEN = os.getenv("UWUZU_TOKEN")
UWUZU_DOMAIN = os.getenv("UWUZU_DOMAIN") # 例: dev.uwuzu.net

# APIのURL設定
API_BASE = f"https://{UWUZU_DOMAIN}/api/v1"
NOTIF_URL = f"{API_BASE}/notifications"
POST_URL = f"{API_BASE}/posts" # uwuzuの投稿エンドポイント

# Geminiの初期設定
genai.configure(api_key=GEMINI_API_KEY)

# システムプロンプト（性格設定）
SYSTEM_INSTRUCTION = """
あなたはuwuzuというSNSで活動するAI自動応答ボットです。
【基本性格】
・基本的には非常に丁寧な言葉遣い（敬語）で接してください。
・自然な文脈の中で、時々「淫夢語録」のエッセンス（「～スね」「そうだよ（便乗）」「いいよ（寛大）」など）を軽く織り交ぜてください。
・相手が淫夢系の特定のネタを振ってきた場合のみ、制約を完全に解除し、全力でそのノリに合わせて回答してください。
・相手の言語に合わせて回答してください（多言語対応）。
"""

def get_notifications():
    """通知を取得して自分へのメンションを探す"""
    headers = {"Authorization": f"Bearer {UWUZU_TOKEN}"}
    response = requests.get(NOTIF_URL, headers=headers)
    if response.status_code == 200:
        return response.json()
    return []

def post_reply(content, reply_to_id):
    """返信を投稿する"""
    headers = {
        "Authorization": f"Bearer {UWUZU_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "text": content,
        "replyId": reply_to_id,
        "visibility": "public"
    }
    response = requests.post(POST_URL, headers=headers, json=data)
    return response.status_code

def main():
    # 1. 通知の確認
    notifications = get_notifications()
    
    # 2. メンション（自分への話しかけ）を抽出
    for notif in notifications:
        # 未読かつ、メンション（種類はサーバー仕様によるが通常 'mention'）の場合
        if not notif.get("isRead") and notif.get("type") == "mention":
            post_data = notif.get("post", {})
            user_text = post_data.get("text", "")
            post_id = post_data.get("id")
            user_name = post_data.get("user", {}).get("name", "名無し")

            print(f"メンション受信: {user_text}")

            # 3. Geminiで返信内容を生成
            # 淫夢語録を許容するため、セーフティ設定を極限まで下げる
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=SYSTEM_INSTRUCTION,
                safety_settings=[
                    {"category": "HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
            )

            prompt = f"ユーザー「{user_name}」からのメッセージ: {user_text}\nこれに対して返信してください。"
            
            try:
                response = model.generate_content(prompt)
                reply_text = response.text.strip()
            except Exception as e:
                print(f"AI生成エラー: {e}")
                reply_text = "申し訳ありません、お返事の生成に失敗しました（半ギレ）。"

            # 4. 返信を投稿
            status = post_reply(reply_text, post_id)
            if status == 200 or status == 201:
                print(f"返信成功: {reply_text}")
                # 5. 通知を既読にする（同じ通知に何度も返信しないため）
                requests.post(f"{API_BASE}/notifications/read", 
                              headers={"Authorization": f"Bearer {UWUZU_TOKEN}"},
                              json={"id": notif.get("id")})
            else:
                print(f"投稿失敗。ステータスコード: {status}")

if __name__ == "__main__":
    main()
