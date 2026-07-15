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

    def _search_images(self, query: str, max_results: int = 3) -> list:
        """Queries Bing Images, decodes HTML entities, and extracts high-resolution image URLs."""
        import requests
        import re
        import html
        import urllib.parse
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        search_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(query)}"
        try:
            r = requests.get(search_url, headers=headers, timeout=10)
            r.raise_for_status()
            unescaped_html = html.unescape(r.text)
            img_urls = []
            matches = re.findall(r'"murl":"(http[^"]+)"', unescaped_html)
            for m in matches:
                if m not in img_urls:
                    img_urls.append(m)
                    if len(img_urls) >= max_results:
                        break
            return img_urls
        except Exception as e:
            logger.warning(f"Bing Image search failed for '{query}': {e}")
            return []

    def _download_image(self, url: str, save_path: str) -> bool:
        """Downloads an image URL and validates its integrity using PIL."""
        import requests
        from PIL import Image
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            with open(save_path, "wb") as f:
                f.write(r.content)
            # Verify image is valid
            with Image.open(save_path) as img:
                img.verify()
            return True
        except Exception as e:
            logger.warning(f"Failed to download or verify image {url} to {save_path}: {e}")
            if os.path.exists(save_path):
                try: os.remove(save_path)
                except Exception: pass
            return False

    def pptx_helper(self, title: str, subtitle: str, theme: str, slides_content: list, output_path: str = "config/presentation.pptx") -> str:
        """Creates a professional PowerPoint presentation with dynamic theme layouts and images using python-pptx locally."""
        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt
            from pptx.dml.color import RGBColor
            from pptx.enum.shapes import MSO_SHAPE
            from pptx.enum.text import PP_ALIGN
            
            prs = Presentation()
            prs.slide_width = Inches(13.333)
            prs.slide_height = Inches(7.5)

            # Theme parameters
            THEMES = {
                "stark_tech": {
                    "bg": RGBColor(17, 24, 39),          # Dark gray
                    "title_color": RGBColor(249, 115, 22), # Orange
                    "body_color": RGBColor(243, 244, 246), # Light gray
                    "accent": RGBColor(239, 68, 68),      # Red
                    "font_title": "Trebuchet MS",
                    "font_body": "Arial"
                },
                "midnight_cyberpunk": {
                    "bg": RGBColor(15, 23, 42),           # Slate dark
                    "title_color": RGBColor(56, 189, 248), # Cyan
                    "body_color": RGBColor(255, 255, 255), # White
                    "accent": RGBColor(236, 72, 153),      # Hot Pink
                    "font_title": "Georgia",
                    "font_body": "Calibri"
                },
                "light_professional": {
                    "bg": RGBColor(248, 250, 252),        # Off-white
                    "title_color": RGBColor(15, 23, 42),   # Deep Slate
                    "body_color": RGBColor(71, 85, 105),   # Slate gray
                    "accent": RGBColor(59, 130, 246),      # Cool Blue
                    "font_title": "Arial",
                    "font_body": "Arial"
                },
                "forest_minimalist": {
                    "bg": RGBColor(244, 244, 245),        # Warm gray
                    "title_color": RGBColor(6, 78, 59),    # Emerald
                    "body_color": RGBColor(31, 41, 55),    # Dark gray
                    "accent": RGBColor(120, 113, 108),     # Muted stone
                    "font_title": "Georgia",
                    "font_body": "Calibri"
                }
            }

            style = THEMES.get(theme.lower(), THEMES["stark_tech"])

            # 1. Slide 1: Title Slide (Full Layout custom styling)
            blank_layout = prs.slide_layouts[6] # Blank slide
            slide = prs.slides.add_slide(blank_layout)

            # Set background color by drawing a full-slide rectangle
            bg_rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
            bg_rect.fill.solid()
            bg_rect.fill.fore_color.rgb = style["bg"]
            bg_rect.line.fill.background()

            # Decorative accent shape (a vertical colored line on the left side)
            accent_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(2.2), Inches(0.1), Inches(3.2))
            accent_bar.fill.solid()
            accent_bar.fill.fore_color.rgb = style["accent"]
            accent_bar.line.fill.background()

            # Add Title Text Frame
            tx_title = slide.shapes.add_textbox(Inches(1.2), Inches(2.0), Inches(11.0), Inches(2.0))
            tf_title = tx_title.text_frame
            tf_title.word_wrap = True
            p_title = tf_title.paragraphs[0]
            p_title.text = title
            p_title.font.name = style["font_title"]
            p_title.font.size = Pt(54)
            p_title.font.bold = True
            p_title.font.color.rgb = style["title_color"]

            # Add Subtitle Text Frame
            tx_sub = slide.shapes.add_textbox(Inches(1.2), Inches(3.8), Inches(11.0), Inches(1.5))
            tf_sub = tx_sub.text_frame
            tf_sub.word_wrap = True
            p_sub = tf_sub.paragraphs[0]
            p_sub.text = subtitle
            p_sub.font.name = style["font_body"]
            p_sub.font.size = Pt(22)
            p_sub.font.color.rgb = style["body_color"]

            # 2. Slides 2+: Content Slides
            for slide_data in slides_content:
                s_title = slide_data.get("title", "Topic")
                s_bullets = slide_data.get("bullets", [])
                image_path = slide_data.get("image_path", "")

                slide = prs.slides.add_slide(blank_layout)

                # Set background
                bg_rect = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
                bg_rect.fill.solid()
                bg_rect.fill.fore_color.rgb = style["bg"]
                bg_rect.line.fill.background()

                # Title Text Box
                tx_header = slide.shapes.add_textbox(Inches(0.8), Inches(0.6), Inches(11.7), Inches(1.0))
                tf_header = tx_header.text_frame
                tf_header.word_wrap = True
                p_header = tf_header.paragraphs[0]
                p_header.text = s_title
                p_header.font.name = style["font_title"]
                p_header.font.size = Pt(36)
                p_header.font.bold = True
                p_header.font.color.rgb = style["title_color"]

                # Accent line separator under header
                sep_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.5), Inches(11.7), Inches(0.04))
                sep_line.fill.solid()
                sep_line.fill.fore_color.rgb = style["accent"]
                sep_line.line.fill.background()

                # Check if image is available and valid
                has_image = image_path and os.path.exists(image_path)

                # Content layout bounding box
                if has_image:
                    # Side-by-side layout: Text on left, Image on right
                    tx_content = slide.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(5.8), Inches(5.0))
                    try:
                        slide.shapes.add_picture(image_path, Inches(7.0), Inches(1.8), width=Inches(5.5), height=Inches(4.8))
                    except Exception as img_err:
                        logger.warning(f"Error adding image to slide '{s_title}': {img_err}")
                        # Fallback to full width if image fails to render
                        tx_content.width = Inches(11.7)
                else:
                    # Full width layout
                    tx_content = slide.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(11.7), Inches(5.0))

                tf_content = tx_content.text_frame
                tf_content.word_wrap = True

                for idx, bullet in enumerate(s_bullets):
                    if idx == 0:
                        p_bullet = tf_content.paragraphs[0]
                    else:
                        p_bullet = tf_content.add_paragraph()

                    p_bullet.text = "•  " + bullet
                    p_bullet.font.name = style["font_body"]
                    p_bullet.font.size = Pt(18 if has_image else 20)  # slightly smaller text if side-by-side
                    p_bullet.font.color.rgb = style["body_color"]
                    p_bullet.space_after = Pt(12)
                    p_bullet.line_spacing = 1.2

            out_p = os.path.abspath(os.path.expanduser(output_path))
            os.makedirs(os.path.dirname(out_p), exist_ok=True)
            prs.save(out_p)
            logger.success(f"PowerPoint generated successfully at {output_path} with theme '{theme}'.")
            return f"Successfully created PowerPoint presentation at {output_path} using theme '{theme}', sir."
        except ImportError:
            return "Please install python-pptx first (`pip install python-pptx`) to generate presentations, sir."
        except Exception as e:
            logger.error(f"Failed to generate presentation: {e}")
            return f"Failed to generate presentation: {str(e)}"
        except ImportError:
            return "Please install python-pptx first (`pip install python-pptx`) to generate presentations, sir."
        except Exception as e:
            logger.error(f"Failed to generate presentation: {e}")
            return f"Failed to generate presentation: {str(e)}"

    def open_presentation(self, filepath: str = "config/presentation.pptx") -> str:
        """Opens the generated presentation locally on Windows."""
        try:
            out_p = os.path.abspath(os.path.expanduser(filepath))
            if os.path.exists(out_p):
                os.startfile(out_p)
                return f"Opening the presentation for you now, sir."
            else:
                return "Sir, I could not find the presentation file. Please create it first."
        except Exception as e:
            logger.error(f"Failed to open presentation: {e}")
            return f"Failed to open the presentation: {e}"

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
