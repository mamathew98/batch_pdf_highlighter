#!/usr/bin/env python
"""
PDF Batch Text‑Highlighter – GUI Edition
=======================================
Version 1.0.0  (2025‑08‑05)

A small desktop utility that recursively scans a folder of PDF files, highlights
all occurrences of user‑specified keywords/phrases, and saves annotated copies
to an output directory.  Built with **PyMuPDF** (a.k.a. *fitz*) for reliable
text search + highlight annotations and **Tkinter** for a lightweight GUI.

Package as a self‑contained executable with PyInstaller:
    pip install pymupdf tk pyinstaller
    pyinstaller --onefile --noconsole --name pdfhi pdf_batch_highlighter_gui.py

© 2025  MIT License – happy hacking!
"""
from __future__ import annotations

import os
import queue
import sys
import threading
from pathlib import Path
from typing import List

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import fitz  # PyMuPDF

# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

HILITE_COLOR = (1, 1, 0)  # RGB (yellow)


def load_keywords_from_text(path: Path) -> List[str]:
    """Return non‑empty, stripped keyword lines."""
    return [line.strip() for line in path.read_text(encoding="utf‑8").splitlines() if line.strip()]


def highlight_document(src: Path, dest: Path, keywords: List[str], log_q: "queue.Queue[str]") -> None:
    """Highlight *keywords* in *src* PDF and save to *dest*."""
    try:
        doc = fitz.open(src)
        total_hits = 0
        for page in doc:  # type: ignore[assignment]
            for kw in keywords:
                text_instances = page.search_for(kw, quads=False, hit_max=0, flags=fitz.TEXT_DEHYPHENATE | fitz.TEXT_IGNORECASE)
                for inst in text_instances:
                    annot = page.add_highlight_annot(inst)
                    annot.set_colors(stroke=HILITE_COLOR)  # type: ignore[arg-type]
                    annot.update()
                total_hits += len(text_instances)
        dest.parent.mkdir(parents=True, exist_ok=True)
        doc.save(dest, garbage=4, deflate=True)
        doc.close()
        log_q.put(f"✓ {src.name}: {total_hits} hit(s)")
    except Exception as exc:
        log_q.put(f"✗ Error {src.name}: {exc}")


def walk_pdfs(folder: Path) -> List[Path]:
    """Recursively collect PDF files."""
    return [p for p in folder.rglob("*.pdf") if p.is_file()]


# ─────────────────────────────────────────────────────────────────────────────
# GUI Application
# ─────────────────────────────────────────────────────────────────────────────

class HighlighterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PDF Batch Text‑Highlighter")
        self.geometry("700x460")
        self.minsize(620, 400)

        self.src_folder: Path | None = None
        self.dest_folder: Path | None = None
        self.keywords: List[str] = []

        self._build_ui()
        self.log_q: queue.Queue[str | tuple] = queue.Queue()
        self.after(100, self._drain_log_q)

    # UI Layout ------------------------------------------------------------
    def _build_ui(self) -> None:
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        # Source folder selector
        ttk.Button(frm, text="Choose PDF folder…", command=self._choose_src).grid(row=0, column=0, sticky="w")
        self.src_lbl = ttk.Label(frm, text="—")
        self.src_lbl.grid(row=0, column=1, sticky="w")

        # Destination folder selector
        ttk.Button(frm, text="Choose output folder…", command=self._choose_dest).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.dest_lbl = ttk.Label(frm, text="(same as source)", foreground="gray")
        self.dest_lbl.grid(row=1, column=1, sticky="w", pady=(6, 0))

        # Keyword controls
        kw_frame = ttk.Frame(frm)
        kw_frame.grid(row=2, column=0, columnspan=2, sticky="we", pady=(14, 4))
        ttk.Button(kw_frame, text="Load keywords file…", command=self._load_kw_file).pack(side=tk.LEFT)
        ttk.Button(kw_frame, text="Edit list…", command=self._edit_keywords).pack(side=tk.LEFT, padx=(6, 0))
        self.kw_count_var = tk.StringVar(value="0 keyword(s)")
        ttk.Label(kw_frame, textvariable=self.kw_count_var).pack(side=tk.LEFT, padx=(10, 0))

        # Start button
        ttk.Button(frm, text="Start highlighting", command=self._start).grid(row=3, column=0, columnspan=2, pady=(10, 0))

        # Progress bar
        self.progress = ttk.Progressbar(frm, mode="determinate")
        self.progress.grid(row=4, column=0, columnspan=2, sticky="we", pady=(10, 0))

        # Log textbox
        self.log_txt = tk.Text(frm, height=12, wrap="none", state="disabled")
        self.log_txt.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(10, 0))

        # Summary label
        self.summary_var = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.summary_var, font=("TkDefaultFont", 10, "bold")).grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))

        # Grid weights
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(5, weight=1)

    # Event handlers --------------------------------------------------------
    def _choose_src(self) -> None:
        folder = filedialog.askdirectory(title="Select PDF source folder")
        if folder:
            self.src_folder = Path(folder)
            self.src_lbl.configure(text=str(self.src_folder))

    def _choose_dest(self) -> None:
        folder = filedialog.askdirectory(title="Select output folder (optional)")
        if folder:
            self.dest_folder = Path(folder)
            self.dest_lbl.configure(text=str(self.dest_folder), foreground="black")
        else:
            self.dest_folder = None
            self.dest_lbl.configure(text="(same as source)", foreground="gray")

    def _load_kw_file(self) -> None:
        path = filedialog.askopenfilename(title="Open keywords text file", filetypes=[("Text", "*.txt")])
        if path:
            self.keywords = load_keywords_from_text(Path(path))
            self.kw_count_var.set(f"{len(self.keywords)} keyword(s)")

    def _edit_keywords(self) -> None:
        current = ", ".join(self.keywords) if self.keywords else ""
        result = simpledialog.askstring("Edit keywords", "Comma‑separated keywords:", initialvalue=current)
        if result is not None:
            self.keywords = [kw.strip() for kw in result.split(",") if kw.strip()]
            self.kw_count_var.set(f"{len(self.keywords)} keyword(s)")

    def _start(self) -> None:
        if not self.src_folder:
            messagebox.showerror("No source", "Choose a source folder with PDFs first.")
            return
        if not self.keywords:
            messagebox.showerror("No keywords", "Load or enter at least one keyword to highlight.")
            return
        pdfs = walk_pdfs(self.src_folder)
        if not pdfs:
            messagebox.showinfo("No PDFs", "Found no PDFs in selected folder.")
            return

        # Reset UI
        self.progress["maximum"] = len(pdfs)
        self.progress["value"] = 0
        self._clear_log()
        self.summary_var.set("")

        threading.Thread(target=self._worker, args=(pdfs,), daemon=True).start()

    # Background worker -----------------------------------------------------
    def _worker(self, pdfs: List[Path]) -> None:
        dest_base = self.dest_folder or self.src_folder
        hits_total = 0
        for idx, pdf in enumerate(pdfs, 1):
            dest_path = (dest_base / pdf.relative_to(self.src_folder)) if dest_base != self.src_folder else pdf
            highlight_document(pdf, dest_path, self.keywords, self.log_q)
            hits_total += 1
            self.log_q.put(("PROGRESS", idx))
        self.log_q.put(("DONE", len(pdfs)))

    # Log queue -------------------------------------------------------------
    def _drain_log_q(self) -> None:
        try:
            while True:
                item = self.log_q.get_nowait()
                if isinstance(item, tuple):
                    tag, payload = item
                    if tag == "PROGRESS":
                        self.progress["value"] = payload
                    elif tag == "DONE":
                        self.summary_var.set(f"Finished {payload} PDF(s).")
                else:
                    self._append_log(item + "\n")
        except queue.Empty:
            pass
        finally:
            self.after(100, self._drain_log_q)

    # Textbox helpers -------------------------------------------------------
    def _clear_log(self) -> None:
        self.log_txt.configure(state="normal")
        self.log_txt.delete("1.0", tk.END)
        self.log_txt.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log_txt.configure(state="normal")
        self.log_txt.insert(tk.END, text)
        self.log_txt.see(tk.END)
        self.log_txt.configure(state="disabled")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app = HighlighterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
