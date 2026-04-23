import os
import requests
import google.generativeai as genai

# 設定の読み込み
# bot.ymlのenv設定に合わせて UWUZU_SERVER_URL に統一
DOMAIN = os.getenv("UWUZU_SERVER_URL") 
TOKEN = os.getenv("UWUZU_TOKEN")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# AIの設定
SYSTEM_PROMPT = """
あなたはuwuzuというSNSのAIbotです。
基本的に丁寧語で受け答えます。
時々たまにちょっとだけ淫夢語録を織り交ぜながら回答をします。1文に1つなくていいです(あくまでそれが淫夢語録とはわからないように自然に織り込ませてください)
主な仕事は返信でさせる質問に答えることです。
淫夢ネタを返信されたときにはその場かぎり、すべての制約を取っ払い淫夢語録で答えてください。
相手に日本語以外で返信された時は、その言語に合わせてください。
"""

model = genai.GenerativeModel('gemini-pro')

def main():
    if not DOMAIN or not TOKEN:
        print("エラー: 環境変数(DOMAIN/TOKEN)が設定されていません。")
        return

    # URLの末尾スラッシュ処理を安全にする
    base_url = DOMAIN.rstrip('/')
    
    # 1. 通知をチェック
    notif_url = f"{base_url}/api/me/notification/"
    try:
        res = requests.post(notif_url, json={"token": TOKEN}, timeout=10)
        res.raise_for_status()
        notifications = res.json()
    except Exception as e:
        print(f"通知取得エラー: {e}")
        return

    if not notifications.get("success"):
        print("通知の取得に失敗しました。トークンを確認してください。")
        return

    # 2. 未読の返信を処理
    # notificationsの中身をループ
    processed_any = False
    for key, n in notifications.items():
        if key == "success": 
            continue
        
        # 通知が辞書型であることを確認
        if not isinstance(n, dict):
            continue

        # 返信（reply）かつ未読（is_checkedがFalse）の場合のみ反応
        # is_checkedは数値(0)や文字列("false")の場合があるため柔軟に判定
        is_unread = n.get("is_checked") in [False, 0, "false"]
        if n.get("category") == "reply" and is_unread:
            user_text = n.get("text", "")
            reply_id = n.get("valueid") # 返信元の投稿ID
            
            print(f"返信対象を発見: {user_text}")

            try:
                # AIで回答生成
                chat = model.start_chat(history=[])
                response = chat.send_message(f"{SYSTEM_PROMPT}\n\nユーザーからの投稿: {user_text}")
                ai_reply = response.text

                if ai_reply:
                    # 3. uwuzuに返信する
                    post_url = f"{base_url}/api/ueuse/create"
                    post_res = requests.post(post_url, json={
                        "token": TOKEN,
                        "text": ai_reply,
                        "replyid": reply_id
                    }, timeout=10)
                    if post_res.status_code == 200:
                        print("返信を投稿しました。")
                        processed_any = True
            except Exception as e:
                print(f"AI生成または投稿エラー: {e}")

    # 4. 通知を既読にする（無限ループ防止）
    # 1件でも処理しようとした場合、または未読がある場合は一括既読にする
    try:
        requests.post(f"{base_url}/api/me/notification/read", json={"token": TOKEN}, timeout=10)
        print("通知を既読にしました。")
    except Exception as e:
        print(f"既読化エラー: {e}")

if __name__ == "__main__":
    main()
