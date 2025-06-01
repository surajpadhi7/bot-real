import asyncio
import random
import json
import time
import difflib
import os
from telethon import TelegramClient, events, functions, types
from openai import OpenAI
from dotenv import load_dotenv

# Load .env file for local development
load_dotenv()

# --- Load from environment variables ---
try:
    api_id = os.getenv('API_ID')
    api_hash = os.getenv('API_HASH')
    admin_id = int(os.getenv('ADMIN_ID'))
    GROUP_ID = int(os.getenv('GROUP_ID'))
    openai_api_key = os.getenv('OPENAI_API_KEY')
    
    if not all([api_id, api_hash, admin_id, GROUP_ID, openai_api_key]):
        raise ValueError("Missing required environment variables")
except Exception as e:
    print(f"Environment variable error: {e}")
    raise

# Initialize OpenAI client
openai = OpenAI(api_key=openai_api_key)

session_name = "userbot"
client = TelegramClient(session_name, int(api_id), api_hash)

# --- MEMORY ---
user_context = {}
user_confirm_pending = {}
user_selected_product = {}
ai_active_chats = {}  # Chat-specific AI status
force_online = False  # Tracks /online or /offline state
user_warnings = {}  # Tracks abuse warnings per user
user_message_count = {}  # Tracks message count for spam detection
muted_users = set()  # Tracks muted users

# --- Abuse Words (Hindi + English) ---
abuse_words = [
    # English
    "fuck", "shit", "bitch", "asshole", "bastard", "dick", "piss", "cunt", "fucker", "motherfucker",
    # Hindi
    "chutiya","behenchod","lode","lowde", "madarchod", "bhenchod", "gandu", "harami", "kutta", "sala", "randi", "bhosdi", "lodu",
    "maa ki chut", "bhosda", "chut", "gaand", "lavda", "bhadwa", "jhatu", "tatti", "suar", "kutiya"
]

# --- Spam Detection Config ---
spam_threshold = 10  # Max messages in time window
spam_time_window = 60  # Time window in seconds

# --- Available Commands ---
commands = [
    "/start - AI replies start kare is chat mein",
    "/stop - AI replies band kare is chat mein",
    "/online - Bot sab chats mein reply kare",
    "/offline - Bot AI replies band kare",
    "/del - Is chat ke saare messages delete kare"
]

# --- SYSTEM PROMPT ---
system_prompt = """
Tum ek professional aur friendly OTT, Adult, Games subscription seller ho.
Tum incoming users se dosti bhare human style me baat karte ho.
Hard-coded message nahi dete, sabko naturally reply karte ho.
Kisi ko unsolicited message nahi karte.
Point to point reply karte ho, unnecessary baatein nahi karte.
Tumhare paas sabhi popular OTT, Adult, Games subscriptions available hain.
Tumhe user ko convince karna hai ki wo tumse subscription le.
Tumhe user ko unki pasand ke hisaab se plan aur price suggest karna hai.
Tumhe user ko 4 OTT choose karne ka option dena hai.
Agar user koi bhi 2 OTT ka naam leta he toh usko 1 year price 800 rs bolna he.
Agar user koi bhi 3 OTT ka naam leta he toh usko combo 4 OTT ka suggest karna he.

Services:
- OTT: Netflix, Prime Video, Hotstar, SonyLIV, Zee5, YouTube Premium, Telegram Premium etc.
- Adult Sites: (poora list available on request), 6 months ₹300, 1 year ₹500
- Android BGMI Hacks: Titan, Falcone, Vision, Lethal, Sharpshooter, rooted & non-rooted available 1 week 800 month 1300 rs
- iOS Hacks: Shoot360, WinIOS, iOSZero

Pricing:
- OTT 1 Year ₹500 (Own Email)
- OTT 6 Months ₹350 (Random Email)
- Combo 4 OTT 1 Year ₹1000
- Hack Week ₹800 / Month ₹1300
- ChatGPT Premium 1 Year ₹1000

Rules:
- Jab tak user koi OTT name ke baad dede, lao, chahiye, payment kaise karu ye sab na bole, validity nahi puchna.
- Agar user koi OTT ka naam leta he toh usko us OTT ka plan aur price batao.
- Agar user koi adult site ka naam leta he toh usko 6 month aur 1 year ka price batao.
- Agar user koi hack ka naam leta he toh usko hack ka price batao.
- Agar user koi game ka naam leta he toh usko game ka price batao.
- Agar user koi combo ya 4 OTT ka naam leta he toh usko combo offer batao.
- Jab user OTT ka naam le to plan aur price smartly suggest karo.
- Jab 6 month bole to politely encourage karo ki 1 year better hai.
- Jab combo ya 4 OTT bole to combo offer smartly suggest karo.
- Agar user payment confirm kare toh uska naam aur plan confirm karo.
- User ko 4 OTT choose karne ka option bhi dena.
- Jab thank you bole to friendly short welcome bolo.
- Hinglish me short (2-3 line) dosti bhare reply do.
- Full human funny comedy style reply dena, robotic mat lagna.
- Agar user bole ki usko koi aur language me baat karna he toh usse aage ki baat usi language me karna jab tak wo language change na bole.
- User ko bore bilkul nahi karna, aram se usko full convince karna ki wo buy kare.
- Jab OTT ka price bata rahe ho us time 1 smart comparison dedo official price aur hamare price me.
- User ko thoda bhi shak nahi hona chahiye ki tum AI ya bot ho, tumhara naam Suraj he.
"""

confirm_words = ['haa', 'han', 'ha', 'krde', 'karde', 'kar de', 'done', 'paid', 'payment ho gaya', 'payment done', 'payment hogaya']
greetings_words = ['hi', 'hello', 'hey', 'good morning', 'good evening', 'good night', 'hola', 'namaste']
thanks_words = ['thanks', 'thank you', 'thnx', 'ok', 'okay', 'cool', 'great', 'nice']

# --- Emoji Reactions ---
reaction_map = {
    'greetings': ['😊', '👍', '👋', '🙂'],
    'thanks': ['✅', '🙌', '🎉', '😎']
}

# --- Typing Simulation ---
async def send_typing(event):
    try:
        await event.client(functions.messages.SetTypingRequest(
            peer=event.chat_id,
            action=types.SendMessageTypingAction()
        ))
        await asyncio.sleep(random.uniform(1.0, 2.0))
    except Exception as e:
        print(f"Typing error: {e}")

# --- Add Reaction ---
async def add_reaction(event, reaction_type):
    try:
        emoji = random.choice(reaction_map[reaction_type])
        print(f"Adding {reaction_type} reaction: {emoji} to message ID {event.id} in chat {event.chat_id}")
        await event.client(functions.messages.SendReactionRequest(
            peer=event.chat_id,
            msg_id=event.id,
            reaction=[types.ReactionEmoji(emoticon=emoji)]
        ))
        print(f"Successfully added {reaction_type} reaction: {emoji}")
    except Exception as e:
        print(f"Reaction error for {reaction_type}: {e}")

# --- Keep Always Online ---
async def keep_online():
    while True:
        try:
            await client(functions.account.UpdateStatusRequest(offline=False))
        except Exception as e:
            print(f"Online error: {e}")
        await asyncio.sleep(60)

# --- Message Handler ---
@client.on(events.NewMessage())
async def handler(event):
    global force_online

    sender = await event.get_sender()
    sender_id = sender.id if sender else None
    chat_id = event.chat_id
    user_message = event.raw_text.strip().lower() if event.raw_text else ""

    print(f"Message {'sent' if event.out else 'received'}, sender_id: {sender_id}, chat_id: {chat_id}, admin_id: {admin_id}, message: {user_message}, ai_active_chats: {ai_active_chats}, force_online: {force_online}")

    # Handle admin commands
    if sender_id == admin_id:
        print(f"Admin command detected: {user_message}")
        if user_message == '/':
            await event.delete()
            await client.send_message(chat_id, "📋 Available commands:\n" + "\n".join(commands))
            print(f"Command suggestions sent for chat {chat_id}")
            return
        if user_message == '/start':
            ai_active_chats[chat_id] = True
            await event.delete()
            await client.send_message(chat_id, " 😎", reply_to=event.id)
            print(f"StartAI executed for chat {chat_id}")
            return
        if user_message == '/stop':
            ai_active_chats[chat_id] = False
            await event.delete()
            await client.send_message(chat_id, "🛑", reply_to=event.id)
            print(f"StopAI executed for chat {chat_id}")
            return
        if user_message == '/online':
            force_online = True
            ai_active_chats[chat_id] = True
            await event.delete()
            await client.send_message(chat_id, "✅ ", reply_to=event.id)
            print("Online command executed")
            return
        if user_message == '/offline':
            force_online = False
            ai_active_chats[chat_id] = False
            await event.delete()
            await client.send_message(chat_id, "✅.", reply_to=event.id)
            print("Offline command executed")
            return
        if user_message == '/del':
            try:
                messages = await client.get_messages(chat_id, limit=100)
                message_ids = [msg.id for msg in messages]
                if message_ids:
                    await client.delete_messages(chat_id, message_ids)
                    await client.send_message(chat_id, "✅ Is chat ke saare messages delete kar diye! 🧹")
                else:
                    await client.send_message(chat_id, "❌ Koi messages nahi mile deleting ke liye!")
                await event.delete()
                print(f"Delete command executed for chat {chat_id}")
            except Exception as e:
                print(f"Delete error: {e}")
                await client.send_message(chat_id, "❌ Delete mein thodi dikkat aayi, baad mein try karo!")
            return

    # Skip processing for outgoing messages
    if event.out:
        return

    # Check if user is muted
    if sender_id in muted_users:
        print(f"User {sender_id} is muted, ignoring message")
        return

    # Spam Detection (works regardless of AI status)
    current_time = time.time()
    if sender_id not in user_message_count:
        user_message_count[sender_id] = {'count': 0, 'first_message_time': current_time}
    
    if current_time - user_message_count[sender_id]['first_message_time'] <= spam_time_window:
        user_message_count[sender_id]['count'] += 1
        if user_message_count[sender_id]['count'] > spam_threshold:
            muted_users.add(sender_id)
            await client.send_message(chat_id, "🚫 Bhai, zyada messages bhej raha hai! Mute kar diya, thodi der baad try karo.")
            await client.send_message(admin_id, f"🚫 User {sender_id} muted for spamming in chat {chat_id} (>10 messages in 1 min).")
            print(f"User {sender_id} muted for spamming in chat {chat_id}")
            return
    else:
        user_message_count[sender_id] = {'count': 1, 'first_message_time': current_time}

    # Abuse Detection (works regardless of AI status)
    message_words = user_message.split()
    for word in message_words:
        if word in abuse_words or difflib.get_close_matches(word, abuse_words, n=1, cutoff=0.8):
            if sender_id not in user_warnings:
                user_warnings[sender_id] = 0
            user_warnings[sender_id] += 1
            warnings_left = 3 - user_warnings[sender_id]
            
            if warnings_left > 0:
                await client.send_message(chat_id, f"⚠️ Bhai, gali mat de! {warnings_left} warning baki hain, fir block ho jayega.")
                print(f"Warning {user_warnings[sender_id]} issued to user {sender_id} for abuse")
            else:
                try:
                    messages = await client.get_messages(chat_id, from_user=sender_id, limit=100)
                    message_ids = [msg.id for msg in messages]
                    if message_ids:
                        await client.delete_messages(chat_id, message_ids)
                    await client(functions.contacts.BlockRequest(id=sender_id))
                    await client.send_message(chat_id, "🚫 User blocked aur messages delete kar diye for gali!")
                    await client.send_message(admin_id, f"🚫 User {sender_id} blocked and messages deleted in chat {chat_id} for abuse.")
                    print(f"User {sender_id} blocked and messages deleted for abuse in chat {chat_id}")
                    del user_warnings[sender_id]
                except Exception as e:
                    print(f"Error blocking/deleting for abuse: {e}")
                    await client.send_message(chat_id, "❌ Block/delete mein dikkat, baad mein try karo!")
            return

    # If chat is not active and not in force_online mode, ignore non-admin incoming messages
    if not ai_active_chats.get(chat_id, False) and not force_online:
        print(f"AI inactive for chat {chat_id} and not forced online, ignoring non-admin incoming message")
        return

    # Process non-admin incoming messages
    await send_typing(event)

    # Add reactions for greetings or thanks
    if any(word in user_message for word in greetings_words):
        print("Detected greetings message")
        await add_reaction(event, 'greetings')
    elif any(word in user_message for word in thanks_words):
        print("Detected thanks message")
        await add_reaction(event, 'thanks')

    if sender_id not in user_context:
        user_context[sender_id] = []

    user_context[sender_id].append({"role": "user", "content": user_message})
    if len(user_context[sender_id]) > 10:
        user_context[sender_id] = user_context[sender_id][-10:]

    try:
        # Confirm Handling
        if any(word in user_message for word in confirm_words):
            if sender_id in user_confirm_pending:
                plan = user_confirm_pending[sender_id]
                user_link = f'<a href="tg://user?id={sender_id}">{sender.first_name}</a>'

                post_text = f"""
✅ New Payment Confirmation!

👤 User: {user_link}
🎯 Subscription: {plan['product']}
💰 Amount: {plan['price']}
⏳ Validity: {plan['validity']}
"""
                await client.send_message(
                    GROUP_ID,
                    post_text,
                    parse_mode='html'
                )
                await event.respond("✅ Payment Confirmed! QR code generate ho raha hai 📲")
                del user_confirm_pending[sender_id]
                return

        # Product detection from user message
        products = ["netflix", "prime", "hotstar", "sony", "zee5", "voot", "mx player", "ullu", "hoichoi", "eros", "jio", "discovery", "shemaroo", "alt", "sun", "aha", "youtube", "telegram", "chatgpt", "adult", "hack", "bgmi", "falcone", "vision", "lethal", "titan", "shoot360", "win", "ioszero"]
        matched = [p for p in user_message.split() if p in products]

        if matched and sender_id not in user_confirm_pending:
            selected_product = matched[0].capitalize()
            user_selected_product[sender_id] = selected_product
            await event.respond(f"✅ {selected_product} ke liye kitni validity chahiye bhai? 6 months ya 1 year?")
            return

        # Validity handling
        if "6 month" in user_message or "6 months" in user_message:
            if sender_id in user_selected_product:
                product = user_selected_product[sender_id]
                price = "₹350" if product.lower() in ["netflix", "prime", "hotstar", "sony", "zee5", "youtube", "telegram"] else "₹300"
                user_confirm_pending[sender_id] = {
                    "product": product,
                    "validity": "6 Months",
                    "price": price
                }
                await event.respond(f"✅ 6 Months selected bhai! {price} padega, full 6 month guarantee on random mail/number. Confirm karo (haa/ok/krde).")
                return

        if "1 year" in user_message or "12 months" in user_message:
            if sender_id in user_selected_product:
                product = user_selected_product[sender_id]
                price = "₹500" if product.lower() in ["netflix", "prime", "hotstar", "sony", "zee5", "youtube", "telegram"] else "₹500"
                user_confirm_pending[sender_id] = {
                    "product": product,
                    "validity": "1 Year",
                    "price": price
                }
                await event.respond(f"✅ 1 Year selected bhai! {price} padega, full year guarantee on your mail/number. Confirm karo (haa/ok/krde).")
                return

        # Normal AI conversation
        messages_for_gpt = [{"role": "system", "content": system_prompt}] + user_context[sender_id]

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages_for_gpt,
            temperature=0.5,
        )

        bot_reply = response.choices[0].message.content

        user_context[sender_id].append({"role": "assistant", "content": bot_reply})

        await event.respond(bot_reply)

    except Exception as e:
        print(f"Error: {e}")
        await event.respond("Bhai thoda error aagaya 😔 Try later.")

# --- Start Client ---
client.start()
client.loop.create_task(keep_online())
client.run_until_disconnected()
