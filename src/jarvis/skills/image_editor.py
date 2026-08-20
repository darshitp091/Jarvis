"""
JARVIS Image Editor & Vector Designer Skill
Wraps GIMP CLI (Script-Fu batch), Inkscape CLI, and Pillow fallback
for voice-controlled image editing and vector design operations.
"""
import os
import re
import subprocess
import shutil
from pathlib import Path
from loguru import logger


# ──────────────────────────────────────────────────────────────────
#  Helper: locate tool executables
# ──────────────────────────────────────────────────────────────────

def _find_gimp() -> str | None:
    """Locate the GIMP executable on Windows."""
    candidates = [
        shutil.which("gimp"),
        shutil.which("gimp-3"),
        shutil.which("gimp-2.10"),
        # GIMP 3.x user-level install (winget default on Windows)
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\GIMP 3\bin\gimp-3.2.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\GIMP 3\bin\gimp-3.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\GIMP 3\bin\gimp.exe"),
        # GIMP 2.x system-level install
        r"C:\Program Files\GIMP 2\bin\gimp-2.10.exe",
        r"C:\Program Files\GIMP 2\bin\gimp-2.99.exe",
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    # Search dynamically in Program Files and AppData
    for root in [r"C:\Program Files", r"C:\Program Files (x86)",
                 os.path.expandvars(r"%LOCALAPPDATA%\Programs")]:
        for d in Path(root).glob("GIMP*"):
            for exe in d.rglob("gimp-*.exe"):
                if "console" not in exe.name and "debug" not in exe.name and "tool" not in exe.name:
                    return str(exe)
    return None


def _find_inkscape() -> str | None:
    """Locate the Inkscape executable on Windows."""
    candidates = [
        shutil.which("inkscape"),
        r"C:\Program Files\Inkscape\bin\inkscape.exe",
        r"C:\Program Files\Inkscape\inkscape.exe",
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    for root in [r"C:\Program Files", r"C:\Program Files (x86)"]:
        for d in Path(root).glob("Inkscape*"):
            for exe in d.rglob("inkscape.exe"):
                return str(exe)
    return None


def _safe_path(path: str) -> str:
    """Return an absolute path string, expanding ~ and env vars."""
    return str(Path(path).expanduser().resolve())


# ──────────────────────────────────────────────────────────────────
#  ImageEditor Skill
# ──────────────────────────────────────────────────────────────────

class ImageEditor:
    """
    Voice-controlled image editing skill for JARVIS.
    Uses GIMP Script-Fu for advanced operations and Pillow as fallback.
    Also handles Inkscape CLI for SVG / vector operations.
    """

    def __init__(self):
        self.gimp_exe = _find_gimp()
        self.inkscape_exe = _find_inkscape()

        if self.gimp_exe:
            logger.success(f"ImageEditor: GIMP found at {self.gimp_exe}")
        else:
            logger.warning("ImageEditor: GIMP not found — using Pillow fallback for basic operations.")

        if self.inkscape_exe:
            logger.success(f"ImageEditor: Inkscape found at {self.inkscape_exe}")
        else:
            logger.warning("ImageEditor: Inkscape not found — SVG operations unavailable.")

    # ────────────────────────────────────────
    #  Internal helpers
    # ────────────────────────────────────────

    def _run_gimp_script(self, script: str) -> tuple[bool, str]:
        """Execute a GIMP Script-Fu batch command."""
        if not self.gimp_exe:
            return False, "GIMP install nahi hai, sir. Pillow fallback use ho raha hai."
        try:
            result = subprocess.run(
                [self.gimp_exe, "-i", "--batch-interpreter", "plug-in-script-fu-eval",
                 "-b", script, "-b", "(gimp-quit 0)"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                return True, "Success"
            return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "GIMP timeout ho gaya — image bahut badi hai ya script slow hai."
        except Exception as e:
            return False, str(e)

    def _run_inkscape(self, args: list) -> tuple[bool, str]:
        """Execute an Inkscape CLI command."""
        if not self.inkscape_exe:
            return False, "Inkscape install nahi hai, sir."
        try:
            result = subprocess.run(
                [self.inkscape_exe] + args,
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                return True, "Success"
            return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "Inkscape timeout ho gaya."
        except Exception as e:
            return False, str(e)

    def _pillow_available(self) -> bool:
        try:
            import PIL
            return True
        except ImportError:
            return False

    def _derive_output(self, input_path: str, suffix: str = "", ext: str = None) -> str:
        """Derive an output filename from an input path."""
        p = Path(_safe_path(input_path))
        out_ext = ext if ext else p.suffix
        return str(p.parent / f"{p.stem}{suffix}{out_ext}")

    # ════════════════════════════════════════
    #  🖼️  GIMP Operations
    # ════════════════════════════════════════

    def resize_image(self, input_path: str, width: int, height: int, output_path: str = None) -> str:
        """Resize an image to the given dimensions."""
        inp = _safe_path(input_path)
        out = _safe_path(output_path) if output_path else self._derive_output(inp, f"_{width}x{height}")

        if self.gimp_exe:
            script = (
                f'(let* ((img (car (gimp-file-load RUN-NONINTERACTIVE "{inp}" "{inp}")))'
                f'       (drw (car (gimp-image-get-active-drawable img))))'
                f'  (gimp-image-scale-full img {width} {height} INTERPOLATION-LINEAR)'
                f'  (file-png-save RUN-NONINTERACTIVE img (car (gimp-image-get-active-drawable img)) "{out}" "{out}" 0 9 1 1 1 1 1))'
            )
            ok, msg = self._run_gimp_script(script)
            if ok:
                return f"Image resize ho gayi — {width}x{height} px. Saved: {out}"
            logger.warning(f"GIMP resize failed: {msg}. Falling back to Pillow.")

        # Pillow fallback
        if self._pillow_available():
            from PIL import Image
            img = Image.open(inp)
            img = img.resize((width, height), Image.LANCZOS)
            img.save(out)
            return f"Image resize ho gayi (Pillow) — {width}x{height} px. Saved: {out}"
        return "Sir, na GIMP hai na Pillow — image resize nahi ho sakta."

    def convert_format(self, input_path: str, output_format: str, output_path: str = None) -> str:
        """Convert image to a different format (PNG, JPG, WEBP, BMP, TIFF)."""
        inp = _safe_path(input_path)
        fmt = output_format.lower().strip(".")
        ext_map = {"jpg": ".jpg", "jpeg": ".jpg", "png": ".png", "webp": ".webp", "bmp": ".bmp", "tiff": ".tiff", "gif": ".gif"}
        out_ext = ext_map.get(fmt, f".{fmt}")
        out = _safe_path(output_path) if output_path else self._derive_output(inp, "", out_ext)

        if self._pillow_available():
            from PIL import Image
            img = Image.open(inp)
            pil_fmt = fmt.upper().replace("JPG", "JPEG")
            if pil_fmt == "JPEG" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(out, format=pil_fmt)
            return f"Image convert ho gayi {output_format.upper()} mein. Saved: {out}"

        if self.gimp_exe:
            if fmt in ("jpg", "jpeg"):
                script = (
                    f'(let* ((img (car (gimp-file-load RUN-NONINTERACTIVE "{inp}" "{inp}")))'
                    f'       (drw (car (gimp-image-get-active-drawable img))))'
                    f'  (gimp-image-flatten img)'
                    f'  (file-jpeg-save RUN-NONINTERACTIVE img (car (gimp-image-get-active-drawable img)) "{out}" "{out}" 0.9 0 0 0 "" 0 1 0 2 0))'
                )
            else:
                script = (
                    f'(let* ((img (car (gimp-file-load RUN-NONINTERACTIVE "{inp}" "{inp}")))'
                    f'       (drw (car (gimp-image-get-active-drawable img))))'
                    f'  (file-png-save RUN-NONINTERACTIVE img drw "{out}" "{out}" 0 9 1 1 1 1 1))'
                )
            ok, msg = self._run_gimp_script(script)
            if ok:
                return f"Image {output_format.upper()} mein convert ho gayi. Saved: {out}"
        return f"Sir, conversion fail ho gayi: format '{output_format}' support nahi hua."

    def apply_grayscale(self, input_path: str, output_path: str = None) -> str:
        """Convert image to grayscale / black & white."""
        inp = _safe_path(input_path)
        out = _safe_path(output_path) if output_path else self._derive_output(inp, "_bw")

        if self._pillow_available():
            from PIL import Image
            img = Image.open(inp).convert("L").convert("RGB")
            img.save(out)
            return f"Image black & white ho gayi. Saved: {out}"

        if self.gimp_exe:
            script = (
                f'(let* ((img (car (gimp-file-load RUN-NONINTERACTIVE "{inp}" "{inp}")))'
                f'       (drw (car (gimp-image-get-active-drawable img))))'
                f'  (gimp-image-convert-grayscale img)'
                f'  (file-png-save RUN-NONINTERACTIVE img (car (gimp-image-get-active-drawable img)) "{out}" "{out}" 0 9 1 1 1 1 1))'
            )
            ok, msg = self._run_gimp_script(script)
            if ok:
                return f"Image grayscale ho gayi. Saved: {out}"
        return "Sir, grayscale conversion fail ho gayi."

    def apply_blur(self, input_path: str, radius: int = 5, output_path: str = None) -> str:
        """Apply Gaussian blur to an image."""
        inp = _safe_path(input_path)
        out = _safe_path(output_path) if output_path else self._derive_output(inp, "_blurred")

        if self._pillow_available():
            from PIL import Image, ImageFilter
            img = Image.open(inp).filter(ImageFilter.GaussianBlur(radius=radius))
            img.save(out)
            return f"Image blur ho gayi (radius={radius}). Saved: {out}"

        if self.gimp_exe:
            script = (
                f'(let* ((img (car (gimp-file-load RUN-NONINTERACTIVE "{inp}" "{inp}")))'
                f'       (drw (car (gimp-image-get-active-drawable img))))'
                f'  (plug-in-gauss RUN-NONINTERACTIVE img drw {radius*2+1} {radius*2+1} 0)'
                f'  (file-png-save RUN-NONINTERACTIVE img drw "{out}" "{out}" 0 9 1 1 1 1 1))'
            )
            ok, msg = self._run_gimp_script(script)
            if ok:
                return f"Image blur apply ho gayi. Saved: {out}"
        return "Sir, blur operation fail ho gayi."

    def apply_sharpen(self, input_path: str, output_path: str = None) -> str:
        """Sharpen an image."""
        inp = _safe_path(input_path)
        out = _safe_path(output_path) if output_path else self._derive_output(inp, "_sharp")

        if self._pillow_available():
            from PIL import Image, ImageFilter
            img = Image.open(inp).filter(ImageFilter.SHARPEN)
            img.save(out)
            return f"Image sharpen ho gayi. Saved: {out}"
        return "Sir, sharpen ke liye Pillow chahiye (`pip install Pillow`)."

    def crop_image(self, input_path: str, x: int, y: int, width: int, height: int, output_path: str = None) -> str:
        """Crop an image to a specific region."""
        inp = _safe_path(input_path)
        out = _safe_path(output_path) if output_path else self._derive_output(inp, "_cropped")

        if self._pillow_available():
            from PIL import Image
            img = Image.open(inp)
            img = img.crop((x, y, x + width, y + height))
            img.save(out)
            return f"Image crop ho gayi ({x},{y}) size {width}x{height}. Saved: {out}"

        if self.gimp_exe:
            script = (
                f'(let* ((img (car (gimp-file-load RUN-NONINTERACTIVE "{inp}" "{inp}")))'
                f'       (drw (car (gimp-image-get-active-drawable img))))'
                f'  (gimp-image-crop img {width} {height} {x} {y})'
                f'  (file-png-save RUN-NONINTERACTIVE img (car (gimp-image-get-active-drawable img)) "{out}" "{out}" 0 9 1 1 1 1 1))'
            )
            ok, msg = self._run_gimp_script(script)
            if ok:
                return f"Image crop ho gayi. Saved: {out}"
        return "Sir, crop fail ho gayi."

    def add_watermark(self, input_path: str, watermark_text: str, output_path: str = None) -> str:
        """Add a text watermark to an image."""
        inp = _safe_path(input_path)
        out = _safe_path(output_path) if output_path else self._derive_output(inp, "_watermarked")

        if self._pillow_available():
            from PIL import Image, ImageDraw, ImageFont
            img = Image.open(inp).convert("RGBA")
            overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)
            # Position: bottom-right corner
            w, h = img.size
            try:
                font = ImageFont.truetype("arial.ttf", size=max(20, w // 30))
            except Exception:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), watermark_text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((w - tw - 20, h - th - 20), watermark_text, fill=(255, 255, 255, 128), font=font)
            combined = Image.alpha_composite(img, overlay).convert("RGB")
            combined.save(out)
            return f"Watermark '{watermark_text}' add ho gaya. Saved: {out}"
        return "Sir, watermark ke liye Pillow chahiye (`pip install Pillow`)."

    def remove_background(self, input_path: str, output_path: str = None) -> str:
        """
        Remove the background from an image.
        Uses rembg (best) → GIMP Script-Fu (intermediate) → Pillow threshold (basic).
        """
        inp = _safe_path(input_path)
        out_path = _safe_path(output_path) if output_path else self._derive_output(inp, "_nobg", ".png")

        # Best: rembg (AI-based, if installed)
        try:
            from rembg import remove
            from PIL import Image
            import io
            with open(inp, "rb") as f:
                data = f.read()
            result = remove(data)
            with open(out_path, "wb") as f:
                f.write(result)
            return f"Background remove ho gaya (AI-based rembg). Saved: {out_path}"
        except ImportError:
            logger.info("rembg not found, trying GIMP Script-Fu for background removal.")
        except Exception as e:
            logger.warning(f"rembg failed: {e}")

        # Intermediate: GIMP fuzzy select background removal
        if self.gimp_exe:
            script = (
                f'(let* ((img (car (gimp-file-load RUN-NONINTERACTIVE "{inp}" "{inp}")))'
                f'       (drw (car (gimp-image-get-active-drawable img))))'
                f'  (gimp-context-set-sample-threshold 0.3)'
                f'  (gimp-context-set-sample-merged TRUE)'
                f'  (gimp-by-color-select drw (car (gimp-drawable-get-pixel drw 0 0)) 50 CHANNEL-OP-REPLACE TRUE FALSE 0 FALSE)'
                f'  (gimp-edit-clear drw)'
                f'  (gimp-selection-none img)'
                f'  (file-png-save RUN-NONINTERACTIVE img drw "{out_path}" "{out_path}" 0 9 1 1 1 1 1))'
            )
            ok, msg = self._run_gimp_script(script)
            if ok:
                return f"Background remove ho gaya (GIMP). Saved: {out_path}"

        return (
            "Sir, AI background removal ke liye `pip install rembg` install karein — "
            "bahut better results milenge. Basic removal ke liye GIMP bhi use ho sakta hai."
        )

    def rotate_image(self, input_path: str, degrees: int, output_path: str = None) -> str:
        """Rotate an image by given degrees (90, 180, 270, or any angle)."""
        inp = _safe_path(input_path)
        out = _safe_path(output_path) if output_path else self._derive_output(inp, f"_rot{degrees}")

        if self._pillow_available():
            from PIL import Image
            img = Image.open(inp).rotate(-degrees, expand=True)
            img.save(out)
            return f"Image {degrees}° rotate ho gayi. Saved: {out}"
        return "Sir, rotate ke liye Pillow chahiye (`pip install Pillow`)."

    def get_image_info(self, input_path: str) -> str:
        """Return image dimensions, format, and file size."""
        inp = _safe_path(input_path)
        if not os.path.exists(inp):
            return f"Sir, file nahi mili: {input_path}"
        size_kb = os.path.getsize(inp) // 1024
        if self._pillow_available():
            from PIL import Image
            img = Image.open(inp)
            w, h = img.size
            fmt = img.format or Path(inp).suffix.upper().strip(".")
            mode = img.mode
            return f"Image info: {w}×{h} px | Format: {fmt} | Mode: {mode} | Size: {size_kb} KB"
        return f"File size: {size_kb} KB. Pillow install karein detailed info ke liye."

    # ════════════════════════════════════════
    #  ✏️  Inkscape / Vector Operations
    # ════════════════════════════════════════

    def svg_to_png(self, svg_path: str, dpi: int = 300, output_path: str = None) -> str:
        """Export an SVG file to a high-resolution PNG."""
        inp = _safe_path(svg_path)
        out = _safe_path(output_path) if output_path else self._derive_output(inp, "", ".png")

        if not self.inkscape_exe:
            return "Sir, Inkscape install nahi hai. SVG to PNG ke liye Inkscape chahiye."
        ok, msg = self._run_inkscape([inp, f"--export-filename={out}", f"--export-dpi={dpi}"])
        if ok:
            return f"SVG successfully PNG mein export ho gaya ({dpi} DPI). Saved: {out}"
        return f"Sir, SVG export fail ho gayi: {msg}"

    def svg_to_pdf(self, svg_path: str, output_path: str = None) -> str:
        """Export an SVG file to PDF."""
        inp = _safe_path(svg_path)
        out = _safe_path(output_path) if output_path else self._derive_output(inp, "", ".pdf")

        if not self.inkscape_exe:
            return "Sir, Inkscape install nahi hai. SVG to PDF ke liye Inkscape chahiye."
        ok, msg = self._run_inkscape([inp, f"--export-filename={out}"])
        if ok:
            return f"SVG PDF mein convert ho gaya. Saved: {out}"
        return f"Sir, PDF export fail ho gayi: {msg}"

    def png_to_svg(self, png_path: str, output_path: str = None) -> str:
        """
        Trace a bitmap PNG to an SVG vector using Inkscape's built-in Potrace tracer.
        Best for logos, icons, or high-contrast images.
        """
        inp = _safe_path(png_path)
        out = _safe_path(output_path) if output_path else self._derive_output(inp, "", ".svg")

        if not self.inkscape_exe:
            return "Sir, Inkscape install nahi hai. PNG to SVG trace ke liye Inkscape chahiye."
        ok, msg = self._run_inkscape([inp, "--export-filename=" + out,
                                      "--export-plain-svg", "--actions=select-all;org.inkscape.effect.path.trace_bitmap;export-do"])
        if ok:
            return f"PNG successfully SVG mein trace ho gaya. Saved: {out}"
        # Try alternative Inkscape 1.x tracing syntax
        ok2, msg2 = self._run_inkscape(["--actions=file-open:" + inp +
                                         ";select-all;org.inkscape.effect.path.trace-bitmap;export-filename:" + out +
                                         ";export-do;file-close"])
        if ok2:
            return f"PNG SVG mein convert ho gaya. Saved: {out}"
        return f"Sir, bitmap trace fail ho gayi: {msg2}"

    def check_tools_status(self) -> str:
        """Return a status report of all available tools."""
        lines = ["Creative Tools Status:"]
        lines.append(f"  [IMG] GIMP: {'OK - ' + self.gimp_exe if self.gimp_exe else 'NOT INSTALLED'}") 
        lines.append(f"  [VEC] Inkscape: {'OK - ' + self.inkscape_exe if self.inkscape_exe else 'NOT INSTALLED'}")
        lines.append(f"  [PKG] Pillow: {'Available' if self._pillow_available() else 'Not installed'}")
        try:
            import rembg
            lines.append("  [AI] rembg (AI bg removal): Available")
        except ImportError:
            lines.append("  [AI] rembg (AI bg removal): Not installed (optional - pip install rembg)")
        return "\n".join(lines)
