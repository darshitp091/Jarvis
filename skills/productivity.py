import os
import sqlite3
import time
import json
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from loguru import logger
import sounddevice as sd
import numpy as np
import wave
from faster_whisper import WhisperModel
import pyautogui

class ProductivityPlanner:
    """Manages SQLite todo lists, SMTP/IMAP emails, meeting voice recordings, and workflow macro automation."""

    def __init__(self, db_path: str = "config/productivity.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            # Todos
            c.execute("""
                CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING'
                )
            """)
            # Macros
            c.execute("""
                CREATE TABLE IF NOT EXISTS macros (
                    name TEXT PRIMARY KEY,
                    steps TEXT NOT NULL
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize productivity database: {e}")

    # --- Todo List Management ---
    
    def add_todo(self, task: str) -> str:
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("INSERT INTO todos (task) VALUES (?)", (task,))
            conn.commit()
            conn.close()
            return f"I have added '{task}' to your todo list, sir."
        except Exception as e:
            return f"Failed to add todo: {e}"

    def list_todos(self) -> str:
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT id, task, status FROM todos WHERE status = 'PENDING'")
            rows = c.fetchall()
            conn.close()
            
            if not rows:
                return "Your todo list is currently empty, sir."
            
            summary = "Unfinished tasks on your list, sir:\n"
            for r in rows:
                summary += f" - [ID: {r[0]}] {r[1]}\n"
            return summary
        except Exception as e:
            return f"Failed to fetch todos: {e}"

    def complete_todo(self, todo_id: int) -> str:
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("UPDATE todos SET status = 'COMPLETED' WHERE id = ?", (todo_id,))
            conn.commit()
            conn.close()
            return f"Marked task ID {todo_id} as completed, sir."
        except Exception as e:
            return f"Failed to update todo: {e}"

    # --- Email Management ---
    
    def send_email(self, to_addr: str, subject: str, body: str) -> str:
        # Check env variables or local config for credentials
        smtp_server = os.environ.get("JARVIS_SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.environ.get("JARVIS_SMTP_PORT", "587"))
        email_user = os.environ.get("JARVIS_EMAIL_USER")
        email_pass = os.environ.get("JARVIS_EMAIL_PASS")
        
        if not email_user or not email_pass:
            return (
                "Sir, I lack the credentials to send emails. "
                "Please configure JARVIS_EMAIL_USER and JARVIS_EMAIL_PASS in your environment."
            )
            
        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = email_user
            msg["To"] = to_addr
            
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_user, email_pass)
            server.sendmail(email_user, [to_addr], msg.as_string())
            server.quit()
            logger.info(f"Email sent to {to_addr}")
            return f"Email sent successfully to {to_addr}, sir."
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return f"Failed to send email: {str(e)}"

    def check_inbox(self) -> str:
        imap_server = os.environ.get("JARVIS_IMAP_SERVER", "imap.gmail.com")
        email_user = os.environ.get("JARVIS_EMAIL_USER")
        email_pass = os.environ.get("JARVIS_EMAIL_PASS")
        
        if not email_user or not email_pass:
            return "Email credentials are not configured, sir."
            
        try:
            mail = imaplib.IMAP4_SSL(imap_server)
            mail.login(email_user, email_pass)
            mail.select("inbox")
            
            status, data = mail.search(None, "UNSEEN")
            mail_ids = data[0].split()
            
            if not mail_ids:
                return "You have no unread emails in your inbox, sir."
                
            summary = f"You have {len(mail_ids)} unread emails, sir. Top unread messages:\n"
            
            # Fetch last 3 unread emails
            for mid in mail_ids[-3:]:
                status, data = mail.fetch(mid, "(RFC822)")
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                subject = msg["Subject"]
                sender = msg["From"]
                summary += f"  - From: {sender} | Subject: {subject}\n"
                
            mail.logout()
            return summary
        except Exception as e:
            logger.error(f"Inbox read failed: {e}")
            return f"Failed to read inbox: {str(e)}"

    # --- Meeting Notes / Continuous Dictation ---
    
    def record_meeting_notes(self, duration_sec: int = 60, output_txt: str = "notes.txt") -> str:
        """Records microphone in background for duration_sec, transcribes, and writes to a text file."""
        logger.info(f"Recording dictation/meeting notes for {duration_sec} seconds...")
        sample_rate = 16000
        
        try:
            # Record
            recording = sd.rec(int(duration_sec * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
            sd.wait() # wait until recording is finished
            
            # Save to temporary WAV
            temp_wav = "config/meeting_temp.wav"
            os.makedirs("config", exist_ok=True)
            with wave.open(temp_wav, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                wav.writeframes(recording.tobytes())
                
            # Transcribe via Whisper
            logger.info("Transcribing recording...")
            whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
            segments, _ = whisper.transcribe(temp_wav)
            text = " ".join(s.text for s in segments).strip()
            
            # Cleanup WAV
            try: os.remove(temp_wav)
            except Exception: pass
            
            if not text:
                return "No speech was detected in the meeting recording, sir."
                
            # Save notes to text file
            with open(output_txt, "a", encoding="utf-8") as f:
                f.write(f"\n--- Meeting Note ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n{text}\n")
                
            return f"Dictation complete, sir. Notes successfully appended to {output_txt}. Contents:\n{text[:200]}..."
        except Exception as e:
            logger.error(f"Meeting notes recording failed: {e}")
            return f"Failed to record notes: {str(e)}"

    # --- Templates Generator ---
    
    def generate_document_template(self, template_type: str, args_dict: dict) -> str:
        """Generates structured content drafts (emails, NDA agreements) based on inputs."""
        template_type = template_type.lower().strip()
        
        if "nda" in template_type:
            party_a = args_dict.get("party_a", "Stark Industries")
            party_b = args_dict.get("party_b", "The Recipient")
            purpose = args_dict.get("purpose", "evaluating project details")
            nda_text = (
                f"MUTUAL NON-DISCLOSURE AGREEMENT\n\n"
                f"This Agreement is entered into by and between {party_a} and {party_b}.\n"
                f"1. Purpose: The parties wish to share confidential details relating to {purpose}.\n"
                f"2. Confidentiality: Both parties agree to protect proprietary information with reasonable care and "
                f"agree not to disclose it to third parties for a period of 5 years.\n\n"
                f"Executed on {time.strftime('%Y-%m-%d')}."
            )
            return nda_text
            
        elif "email" in template_type:
            recipient = args_dict.get("recipient", "Sir/Madam")
            sender = args_dict.get("sender", "Tony Stark")
            topic = args_dict.get("topic", "the project status")
            email_text = (
                f"Subject: Inquiry regarding {topic}\n\n"
                f"Dear {recipient},\n\n"
                f"I hope this message finds you well. I am writing to obtain a quick update regarding {topic}. "
                f"Please let me know your availability for a call later this week.\n\n"
                f"Best regards,\n{sender}"
            )
            return email_text
            
        else:
            return "Unknown template type requested. Supported formats are: 'nda' and 'email'."

    # --- Keyboard/Mouse Macros ---
    
    def save_macro(self, name: str, steps: list) -> str:
        """Saves a list of keyboard/mouse actions as a named macro."""
        try:
            steps_json = json.dumps(steps)
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO macros (name, steps) VALUES (?, ?)", (name, steps_json))
            conn.commit()
            conn.close()
            return f"Macro '{name}' saved successfully, sir."
        except Exception as e:
            return f"Failed to save macro: {e}"

    def run_macro(self, name: str) -> str:
        """Executes a saved macro step by step."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT steps FROM macros WHERE name = ?", (name,))
            row = c.fetchone()
            conn.close()
            
            if not row:
                return f"Macro '{name}' does not exist, sir."
                
            steps = json.loads(row[0])
            pyautogui.FAILSAFE = True
            
            for step in steps:
                action = step.get("action")
                param = step.get("param")
                
                if action == "click":
                    x, y = param
                    pyautogui.click(x, y)
                elif action == "type":
                    pyautogui.write(str(param), interval=0.02)
                elif action == "press":
                    pyautogui.press(str(param))
                elif action == "sleep":
                    time.sleep(float(param))
                    
            return f"Macro '{name}' executed successfully, sir."
        except Exception as e:
            logger.error(f"Macro execution failed: {e}")
            return f"Error executing macro: {str(e)}"

    def edit_pdf(self, action: str, files_list: list, output_path: str, page_num: int = 0, angle: int = 90) -> str:
        """Merges multiple PDFs, or rotates a specific page of a PDF using pypdf."""
        import pypdf
        act = action.lower().strip()
        out_p = os.path.abspath(os.path.expanduser(output_path))
        os.makedirs(os.path.dirname(out_p), exist_ok=True)
        
        try:
            if act == "merge":
                merger = pypdf.PdfMerger()
                for f in files_list:
                    fp = os.path.abspath(os.path.expanduser(f))
                    if os.path.exists(fp):
                        merger.append(fp)
                merger.write(out_p)
                merger.close()
                return f"Successfully merged {len(files_list)} PDFs into {output_path}, sir."
                
            elif act == "rotate":
                if not files_list:
                    return "Please specify a target PDF file, sir."
                fp = os.path.abspath(os.path.expanduser(files_list[0]))
                if not os.path.exists(fp):
                    return f"PDF file at {files_list[0]} does not exist."
                    
                reader = pypdf.PdfReader(fp)
                writer = pypdf.PdfWriter()
                for idx, page in enumerate(reader.pages):
                    if idx == page_num:
                        page.rotate(angle)
                    writer.add_page(page)
                with open(out_p, "wb") as f_out:
                    writer.write(f_out)
                return f"Successfully rotated page {page_num} of {files_list[0]} by {angle} degrees and saved to {output_path}, sir."
            else:
                return f"Unsupported PDF edit action '{action}', sir."
        except Exception as e:
            logger.error(f"PDF editing failed: {e}")
            return f"Failed to edit PDF: {str(e)}"

    def pptx_helper(self, title: str, subtitle: str, slides_content: list, output_path: str = "config/presentation.pptx") -> str:
        """Creates a PowerPoint presentation using python-pptx locally."""
        try:
            from pptx import Presentation
            prs = Presentation()
            
            # Title slide
            title_slide_layout = prs.slide_layouts[0]
            slide = prs.slides.add_slide(title_slide_layout)
            slide.shapes.title.text = title
            slide.placeholders[1].text = subtitle
            
            # Content slides
            bullet_slide_layout = prs.slide_layouts[1]
            for slide_data in slides_content:
                s_title = slide_data.get("title", "Topic")
                s_bullets = slide_data.get("bullets", [])
                
                slide = prs.slides.add_slide(bullet_slide_layout)
                slide.shapes.title.text = s_title
                tf = slide.placeholders[1].text_frame
                
                for i, bullet in enumerate(s_bullets):
                    if i == 0:
                        tf.text = bullet
                    else:
                        p = tf.add_paragraph()
                        p.text = bullet
                        
            out_p = os.path.abspath(os.path.expanduser(output_path))
            os.makedirs(os.path.dirname(out_p), exist_ok=True)
            prs.save(out_p)
            return f"Successfully created PowerPoint presentation at {output_path}, sir."
        except ImportError:
            return "Please install python-pptx first (`pip install python-pptx`) to generate presentations, sir."
        except Exception as e:
            return f"Failed to generate presentation: {str(e)}"

    def create_mind_map(self, central_idea: str, nodes: list, save_path: str = "config/mindmap.png") -> str:
        """Generates a node-link mind map visualization image using matplotlib and networkx."""
        try:
            import networkx as nx
            import matplotlib.pyplot as plt
            
            plt.clf()
            G = nx.DiGraph()
            G.add_node(central_idea)
            
            # Add node links
            for edge in nodes:
                if isinstance(edge, (list, tuple)) and len(edge) >= 2:
                    G.add_edge(edge[0], edge[1])
                elif isinstance(edge, str):
                    G.add_edge(central_idea, edge)
            
            # Layout node positioning
            pos = nx.spring_layout(G)
            nx.draw(G, pos, with_labels=True, node_color="skyblue", node_size=2000, font_size=10, font_weight="bold", edge_color="gray", width=2)
            
            out_p = os.path.abspath(os.path.expanduser(save_path))
            os.makedirs(os.path.dirname(out_p), exist_ok=True)
            plt.savefig(out_p, dpi=150)
            plt.close()
            return f"Mind map visualization successfully generated and saved to {save_path}, sir."
        except ImportError:
            return "Please install networkx and matplotlib (`pip install networkx matplotlib`) to draw mind maps, sir."
        except Exception as e:
            return f"Failed to generate mind map: {str(e)}"

    def block_distractions(self, domains_list: list, block: bool = True) -> str:
        """Blocks distracting websites by appending them to the Windows hosts file (requires admin)."""
        hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
        if not os.path.exists(hosts_path):
            hosts_path = "/etc/hosts" # Unix fallback
            
        if not os.path.exists(hosts_path):
            return "I could not find your system hosts file, sir."
            
        redirect_ip = "127.0.0.1"
        try:
            with open(hosts_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            new_lines = []
            blocked_domains = [d.strip().lower() for d in domains_list]
            
            # Read existing lines and filter out any domains we want to change/unblock
            for line in lines:
                is_target = False
                for d in blocked_domains:
                    if d in line.lower() and redirect_ip in line:
                        is_target = True
                        break
                if not is_target:
                    new_lines.append(line)
            
            # If blocking, append them at the end
            if block:
                if new_lines and not new_lines[-1].endswith("\n"):
                    new_lines.append("\n")
                for d in blocked_domains:
                    new_lines.append(f"{redirect_ip} {d}\n")
                    new_lines.append(f"{redirect_ip} www.{d}\n")
            
            with open(hosts_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
                
            state = "blocked" if block else "unblocked"
            return f"Successfully {state} {len(domains_list)} distracting domains in hosts file, sir."
        except PermissionError:
            return (
                "Permission denied, sir. Modifying the system hosts file requires Administrator privileges. "
                "Please restart JARVIS in an elevated (Admin) terminal window."
            )
        except Exception as e:
            return f"Failed to modify hosts file: {str(e)}"

    def sign_document(self, doc_path: str, sig_img_path: str, output_path: str, coords: tuple = (100, 100)) -> str:
        """Overlays a signature image PNG onto a document image or PDF page."""
        try:
            from PIL import Image
            doc_p = os.path.abspath(os.path.expanduser(doc_path))
            sig_p = os.path.abspath(os.path.expanduser(sig_img_path))
            out_p = os.path.abspath(os.path.expanduser(output_path))
            
            if not os.path.exists(doc_p):
                return f"Document at {doc_path} does not exist."
            if not os.path.exists(sig_p):
                return f"Signature image at {sig_img_path} does not exist."
                
            os.makedirs(os.path.dirname(out_p), exist_ok=True)
            
            # Open images
            doc_img = Image.open(doc_p).convert("RGBA")
            sig_img = Image.open(sig_p).convert("RGBA")
            
            # Resize signature image if it's too large (cap at 200x100)
            sig_img.thumbnail((200, 100))
            
            # Paste signature onto document
            doc_img.paste(sig_img, coords, sig_img)
            doc_img.convert("RGB").save(out_p)
            return f"Successfully signed document and saved to {output_path}, sir."
        except Exception as e:
            logger.error(f"Document signing failed: {e}")
            return f"Failed to sign document: {str(e)}"
