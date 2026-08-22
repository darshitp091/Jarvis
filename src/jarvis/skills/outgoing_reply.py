"""Replying to a message on the user's behalf, and pretending it was sent.

Two entry points, reached from the incoming-message handler: draft_and_send_style_reply
asks the local model to write something in the user's voice, and log_direct_reply
takes text the user dictated. Both then do the same two things -- append a record
to config/outgoing_replies.json and, for WhatsApp, open a desktop deep-link and
press Enter four and a half seconds later with pyautogui.

Which is worth stating plainly: nothing here confirms a message was delivered.
The JSON record is written with "status": "SENT" before any sending is attempted,
the ADB path is a `pass`, and the deep-link path checks nothing after pressing
Enter. Both functions then return a Hinglish sentence telling the user the
message has been sent. That sentence is the only thing the user hears, and it is
not evidence.

The last ~50 lines of each function are near-identical, differing in one variable
name and one log string. That duplication came along with the move so that the
gate could prove the move; it is removed in the commit after this one, which the
tests here exist to make safe.
"""
import json
import os
import time

from loguru import logger

def draft_and_send_style_reply(sender: str, channel: str, msg_body: str,
                              user_instruction: str, *, models: dict, phone) -> str:
    """Drafts a reply on behalf of the user using LLM styled after past tone, and records it to config/outgoing_replies.json."""
    logger.info(f"Drafting style-matched reply on behalf of user to {sender} on {channel}...")
    
    system_prompt = (
        "You are JARVIS. You draft text messages on behalf of the user (Darshit) matching his communication style. "
        "Darshit usually replies in a very natural, concise Hinglish WhatsApp style (e.g. 'haan abhi busy hu, free hoke call karta hu' or 'ab kya hua bro?'). "
        "Draft a response matching what Darshit instructed. Output ONLY the raw reply content, no quotes, no greeting, no punctuation formatting."
    )
    
    user_prompt = (
        f"Incoming Message from {sender} on {channel}: '{msg_body}'\n"
        f"User's Instruction: '{user_instruction}'\n\n"
        "Draft the casual message to send:"
    )
    
    draft = "Sir, thodi der me message karti hu."
    try:
        import ollama
        response = ollama.chat(
            model=models["main_brain"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            options={"temperature": 0.5}
        )
        draft = response["message"]["content"].strip().strip('"').strip("'")
    except Exception as e:
        logger.error(f"Failed to draft style response using local LLM: {e}")
        
    # Log/Save the message to outgoing JSON database (as if it was sent)
    out_db_path = "config/outgoing_replies.json"
    try:
        replies = []
        if os.path.exists(out_db_path):
            with open(out_db_path, "r", encoding="utf-8") as f:
                replies = json.load(f)
        
        replies.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": channel,
            "recipient": sender,
            "message_body": draft,
            "status": "SENT"
        })
        
        with open(out_db_path, "w", encoding="utf-8") as f:
            json.dump(replies, f, indent=2, ensure_ascii=False)
        logger.success(f"Message logged to outgoing database: {draft}")
    except Exception as err:
        logger.error(f"Failed to save outgoing message: {err}")

    # Automate WhatsApp Desktop or Android ADB sending
    if "WhatsApp" in channel:
        resolved_num = phone.get_contact_by_name(sender)
        if resolved_num:
            clean_phone = "".join(c for c in resolved_num if c.isdigit())
            if len(clean_phone) == 10:
                clean_phone = "91" + clean_phone
            
            if phone.is_device_connected():
                # Send via ADB is already handled in phone skill if active
                pass
            else:
                # Send via WhatsApp Desktop deep-link
                import urllib.parse
                import webbrowser
                import pyautogui
                import threading
                encoded_text = urllib.parse.quote(draft)
                desktop_url = f"whatsapp://send?phone={clean_phone}&text={encoded_text}"
                try:
                    logger.info(f"Opening desktop WhatsApp deep-link: {desktop_url}")
                    webbrowser.open(desktop_url)
                    def auto_press_enter():
                        time.sleep(4.5)
                        pyautogui.press('enter')
                    threading.Thread(target=auto_press_enter, daemon=True).start()
                except Exception as err:
                    logger.error(f"Failed to open desktop WhatsApp: {err}")

    return f"Sir, maine aapki taraf se {channel} par {sender} ko reply bhej diya hai. Message tha: '{draft}'."

def log_direct_reply(sender: str, channel: str, reply_text: str, *, phone) -> str:
    """Logs a direct text response to config/outgoing_replies.json on behalf of the user."""
    logger.info(f"Logging direct response on behalf of user to {sender} on {channel}: {reply_text}...")
    
    out_db_path = "config/outgoing_replies.json"
    try:
        replies = []
        if os.path.exists(out_db_path):
            with open(out_db_path, "r", encoding="utf-8") as f:
                replies = json.load(f)
        
        replies.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": channel,
            "recipient": sender,
            "message_body": reply_text,
            "status": "SENT"
        })
        
        with open(out_db_path, "w", encoding="utf-8") as f:
            json.dump(replies, f, indent=2, ensure_ascii=False)
        logger.success(f"Message logged to outgoing database: {reply_text}")
    except Exception as err:
        logger.error(f"Failed to save direct outgoing message: {err}")

    # Automate WhatsApp Desktop or Android ADB sending
    if "WhatsApp" in channel:
        resolved_num = phone.get_contact_by_name(sender)
        if resolved_num:
            clean_phone = "".join(c for c in resolved_num if c.isdigit())
            if len(clean_phone) == 10:
                clean_phone = "91" + clean_phone
            
            if phone.is_device_connected():
                # Send via ADB is already handled in phone skill if active
                pass
            else:
                # Send via WhatsApp Desktop deep-link
                import urllib.parse
                import webbrowser
                import pyautogui
                import threading
                encoded_text = urllib.parse.quote(reply_text)
                desktop_url = f"whatsapp://send?phone={clean_phone}&text={encoded_text}"
                try:
                    logger.info(f"Opening desktop WhatsApp deep-link: {desktop_url}")
                    webbrowser.open(desktop_url)
                    def auto_press_enter():
                        time.sleep(4.5)
                        pyautogui.press('enter')
                    threading.Thread(target=auto_press_enter, daemon=True).start()
                except Exception as err:
                    logger.error(f"Failed to open desktop WhatsApp: {err}")

    return f"Sir, maine {channel} par {sender} ko bol diya hai: '{reply_text}'."
