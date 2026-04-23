import os
import requests
import google.generativeai as genai

# 設定の読み込み [cite: 91]
DOMAIN = os.getenv("UWUZU_DOMAIN")
TOKEN = os.getenv("UWUZU_TOKEN")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# AIの設定（あなたが用意したもの） [cite: 88]
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
    # 1. 通知をチェック [cite: 58, 126]
    notif_url = f"{DOMAIN}/api/me/notification/"
    res = requests.post(notif_url, json={"token": TOKEN})
    notifications = res.json()

    if not notifications.get("success"):
        return

    # 2. 未読の返信を処理
    for key in notifications:
        if key == "success": continue
        n = notifications[key]
        
        # 返信（reply）かつ未読（is_checkedがFalse）の場合のみ反応 [cite: 86, 126]
        if n.get("category") == "reply" and not n.get("is_checked"):
            user_text = n.get("text")
            reply_id = n.get("valueid") # 返信元の投稿ID [cite: 126]
            
            # AIで回答生成
            chat = model.start_chat(history=[])
            response = chat.send_message(f"{SYSTEM_PROMPT}\n\nユーザーからの投稿: {user_text}")
            ai_reply = response.text

            # 3. uwuzuに返信する [cite: 68]
            post_url = f"{DOMAIN}/api/ueuse/create"
            requests.post(post_url, json={
                "token": TOKEN,
                "text": ai_reply,
                "replyid": reply_id
            })

    # 4. 通知を一括既読にする（無限ループ防止） [cite: 86, 127]
    requests.post(f"{DOMAIN}/api/me/notification/read", json={"token": TOKEN})

if __name__ == "__main__":
    main()
