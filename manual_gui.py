#!/usr/bin/env python3
# ============================================================
#  manual_gui.py - Desktop GUI for Manual Intelligence Engine
# ============================================================

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import os
import sys
import subprocess
import platform
from typing import Optional

# Import the core functionality
from manual_core import (
    ingest, list_manuals, ask, gap, delete_manual, export_manual,
    preview_manual, show_chunk, load_db, ensure_dirs, MANUALS_DIR
)


class ManualGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Manual Intelligence Engine")
        self.root.geometry("1000x700")
        
        # Create main notebook (tabs)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create tabs
        self.create_ingest_tab()
        self.create_ask_tab()
        self.create_gap_tab()
        self.create_manage_tab()
        
        # Status bar
        self.status_bar = tk.Label(root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Ensure directories exist
        ensure_dirs()
    
    def create_ingest_tab(self):
        """Tab for ingesting manuals"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Ingest Manuals")
        
        # Instructions
        instructions = ttk.Label(frame, text="Place .txt or .md files in the 'manuals' folder, then click Ingest.", 
                                wraplength=900, justify=tk.LEFT)
        instructions.pack(pady=10, padx=10)
        
        # Manuals directory info
        dir_frame = ttk.Frame(frame)
        dir_frame.pack(pady=5, padx=10, fill=tk.X)
        ttk.Label(dir_frame, text=f"Manuals Directory: {os.path.abspath(MANUALS_DIR)}").pack(side=tk.LEFT)
        ttk.Button(dir_frame, text="Open Folder", command=self.open_manuals_folder).pack(side=tk.RIGHT)
        
        # Ingest button
        ttk.Button(frame, text="Ingest Manuals", command=self.do_ingest).pack(pady=10)
        
        # Output text area
        ttk.Label(frame, text="Output:").pack(anchor=tk.W, padx=10)
        self.ingest_output = scrolledtext.ScrolledText(frame, height=25, width=120)
        self.ingest_output.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
    
    def create_ask_tab(self):
        """Tab for asking questions"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Ask Questions")
        
        # Question input
        ttk.Label(frame, text="Question:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        self.question_entry = ttk.Entry(frame, width=100)
        self.question_entry.pack(pady=5, padx=10, fill=tk.X)
        
        # Options frame
        options_frame = ttk.Frame(frame)
        options_frame.pack(pady=5, padx=10, fill=tk.X)
        
        ttk.Label(options_frame, text="Include (filter):").pack(side=tk.LEFT)
        self.ask_include_entry = ttk.Entry(options_frame, width=30)
        self.ask_include_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(options_frame, text="Top K:").pack(side=tk.LEFT, padx=(20, 0))
        self.ask_topk_var = tk.StringVar(value="12")
        ttk.Entry(options_frame, textvariable=self.ask_topk_var, width=10).pack(side=tk.LEFT, padx=5)
        
        # Ask button
        ttk.Button(frame, text="Ask Question", command=self.do_ask).pack(pady=10)
        
        # Output text area
        ttk.Label(frame, text="Answer:").pack(anchor=tk.W, padx=10)
        self.ask_output = scrolledtext.ScrolledText(frame, height=25, width=120)
        self.ask_output.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
    
    def create_gap_tab(self):
        """Tab for gap analysis"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Gap Analysis")
        
        # Standard ID
        id_frame = ttk.Frame(frame)
        id_frame.pack(pady=10, padx=10, fill=tk.X)
        ttk.Label(id_frame, text="Standard ID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.gap_standard_entry = ttk.Entry(id_frame, width=50)
        self.gap_standard_entry.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # Manual ID
        ttk.Label(id_frame, text="Manual ID:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.gap_manual_entry = ttk.Entry(id_frame, width=50)
        self.gap_manual_entry.grid(row=1, column=1, sticky=tk.W, padx=5)
        
        # Options
        options_frame = ttk.Frame(frame)
        options_frame.pack(pady=5, padx=10, fill=tk.X)
        
        ttk.Label(options_frame, text="Max Clauses:").grid(row=0, column=0, sticky=tk.W)
        self.gap_max_clauses_var = tk.StringVar(value="5")
        ttk.Entry(options_frame, textvariable=self.gap_max_clauses_var, width=10).grid(row=0, column=1, padx=5)
        
        ttk.Label(options_frame, text="Top N:").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        self.gap_topn_var = tk.StringVar(value="5")
        ttk.Entry(options_frame, textvariable=self.gap_topn_var, width=10).grid(row=0, column=3, padx=5)
        
        ttk.Label(options_frame, text="Min Similarity:").grid(row=1, column=0, sticky=tk.W)
        self.gap_minsim_var = tk.StringVar(value="0.35")
        ttk.Entry(options_frame, textvariable=self.gap_minsim_var, width=10).grid(row=1, column=1, padx=5)
        
        ttk.Label(options_frame, text="Start Index:").grid(row=1, column=2, sticky=tk.W, padx=(20, 0))
        self.gap_start_var = tk.StringVar(value="0")
        ttk.Entry(options_frame, textvariable=self.gap_start_var, width=10).grid(row=1, column=3, padx=5)
        
        # Output options
        output_frame = ttk.Frame(frame)
        output_frame.pack(pady=5, padx=10, fill=tk.X)
        
        self.gap_csv_var = tk.BooleanVar()
        ttk.Checkbutton(output_frame, text="Export to CSV", variable=self.gap_csv_var).pack(side=tk.LEFT)
        
        self.gap_html_var = tk.BooleanVar()
        ttk.Checkbutton(output_frame, text="Export to HTML", variable=self.gap_html_var).pack(side=tk.LEFT, padx=20)
        
        # Run button
        ttk.Button(frame, text="Run Gap Analysis", command=self.do_gap).pack(pady=10)
        
        # Output text area
        ttk.Label(frame, text="Results:").pack(anchor=tk.W, padx=10)
        self.gap_output = scrolledtext.ScrolledText(frame, height=20, width=120)
        self.gap_output.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
    
    def create_manage_tab(self):
        """Tab for managing manuals"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Manage Manuals")
        
        # List manuals section
        list_frame = ttk.LabelFrame(frame, text="List Manuals", padding=10)
        list_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        
        ttk.Button(list_frame, text="Refresh List", command=self.do_list).pack(pady=5)
        
        self.list_output = scrolledtext.ScrolledText(list_frame, height=15, width=100)
        self.list_output.pack(pady=5, fill=tk.BOTH, expand=True)
        
        # Delete/Export section
        action_frame = ttk.Frame(frame)
        action_frame.pack(pady=5, padx=10, fill=tk.X)
        
        # Delete
        delete_frame = ttk.LabelFrame(action_frame, text="Delete Manual", padding=5)
        delete_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        ttk.Label(delete_frame, text="Manual ID:").pack(anchor=tk.W)
        self.delete_id_entry = ttk.Entry(delete_frame, width=40)
        self.delete_id_entry.pack(pady=2)
        
        self.delete_file_var = tk.BooleanVar()
        ttk.Checkbutton(delete_frame, text="Also delete file", variable=self.delete_file_var).pack(anchor=tk.W)
        
        ttk.Button(delete_frame, text="Delete", command=self.do_delete).pack(pady=5)
        
        # Export
        export_frame = ttk.LabelFrame(action_frame, text="Export Manual", padding=5)
        export_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        ttk.Label(export_frame, text="Manual ID:").pack(anchor=tk.W)
        self.export_id_entry = ttk.Entry(export_frame, width=40)
        self.export_id_entry.pack(pady=2)
        
        ttk.Button(export_frame, text="Export", command=self.do_export).pack(pady=5)
    
    def open_manuals_folder(self):
        """Open the manuals folder in file explorer"""
        path = os.path.abspath(MANUALS_DIR)
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":  # macOS
            subprocess.Popen(["open", path])
        else:  # Linux
            subprocess.Popen(["xdg-open", path])
    
    def run_in_thread(self, func, *args, **kwargs):
        """Run a function in a separate thread to prevent GUI freezing"""
        def wrapper():
            try:
                self.set_status("Processing...")
                func(*args, **kwargs)
                self.set_status("Done")
            except Exception as e:
                messagebox.showerror("Error", str(e))
                self.set_status("Error occurred")
        
        thread = threading.Thread(target=wrapper)
        thread.daemon = True
        thread.start()
    
    def set_status(self, text):
        """Update status bar"""
        self.status_bar.config(text=text)
        self.root.update_idletasks()
    
    def redirect_output(self, widget):
        """Context manager to redirect stdout to a text widget"""
        class RedirectText:
            def __init__(self, text_widget):
                self.text_widget = text_widget
            
            def write(self, string):
                self.text_widget.insert(tk.END, string)
                self.text_widget.see(tk.END)
                self.text_widget.update_idletasks()
            
            def flush(self):
                pass
        
        return RedirectText(widget)
    
    def do_ingest(self):
        """Ingest manuals"""
        self.ingest_output.delete(1.0, tk.END)
        
        def ingest_task():
            old_stdout = sys.stdout
            sys.stdout = self.redirect_output(self.ingest_output)
            try:
                ingest(use_hierarchy=True, max_chars=1400)
            finally:
                sys.stdout = old_stdout
        
        self.run_in_thread(ingest_task)
    
    def do_ask(self):
        """Ask a question"""
        question = self.question_entry.get().strip()
        if not question:
            messagebox.showwarning("Warning", "Please enter a question")
            return
        
        include_text = self.ask_include_entry.get().strip()
        include = [x.strip() for x in include_text.split(",")] if include_text else None
        
        try:
            top_k = int(self.ask_topk_var.get())
        except ValueError:
            messagebox.showerror("Error", "Top K must be a number")
            return
        
        self.ask_output.delete(1.0, tk.END)
        
        def ask_task():
            old_stdout = sys.stdout
            sys.stdout = self.redirect_output(self.ask_output)
            try:
                ask(question, include=include, top_k=top_k)
            finally:
                sys.stdout = old_stdout
        
        self.run_in_thread(ask_task)
    
    def do_gap(self):
        """Run gap analysis"""
        standard_id = self.gap_standard_entry.get().strip()
        manual_id = self.gap_manual_entry.get().strip()
        
        if not standard_id or not manual_id:
            messagebox.showwarning("Warning", "Please enter both Standard ID and Manual ID")
            return
        
        try:
            max_clauses = int(self.gap_max_clauses_var.get())
            top_n = int(self.gap_topn_var.get())
            start_index = int(self.gap_start_var.get())
            min_sim = float(self.gap_minsim_var.get())
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid parameter: {e}")
            return
        
        # Generate output file names if requested
        out_csv = None
        out_html = None
        if self.gap_csv_var.get():
            out_csv = f"gap_{standard_id}_vs_{manual_id}.csv"
        if self.gap_html_var.get():
            out_html = f"gap_{standard_id}_vs_{manual_id}.html"
        
        self.gap_output.delete(1.0, tk.END)
        
        def gap_task():
            old_stdout = sys.stdout
            sys.stdout = self.redirect_output(self.gap_output)
            try:
                gap(standard_id, manual_id, start_index=start_index, max_clauses=max_clauses,
                    top_n=top_n, min_sim=min_sim, out_csv=out_csv, out_html=out_html)
            finally:
                sys.stdout = old_stdout
        
        self.run_in_thread(gap_task)
    
    def do_list(self):
        """List all manuals"""
        self.list_output.delete(1.0, tk.END)
        
        def list_task():
            old_stdout = sys.stdout
            sys.stdout = self.redirect_output(self.list_output)
            try:
                list_manuals()
            finally:
                sys.stdout = old_stdout
        
        self.run_in_thread(list_task)
    
    def do_delete(self):
        """Delete a manual"""
        manual_id = self.delete_id_entry.get().strip()
        if not manual_id:
            messagebox.showwarning("Warning", "Please enter a Manual ID")
            return
        
        if not messagebox.askyesno("Confirm", f"Delete manual '{manual_id}'?"):
            return
        
        def delete_task():
            try:
                delete_manual(manual_id, delete_file=self.delete_file_var.get())
                messagebox.showinfo("Success", "Manual deleted")
                self.do_list()  # Refresh the list
            except Exception as e:
                messagebox.showerror("Error", str(e))
        
        self.run_in_thread(delete_task)
    
    def do_export(self):
        """Export a manual"""
        manual_id = self.export_id_entry.get().strip()
        if not manual_id:
            messagebox.showwarning("Warning", "Please enter a Manual ID")
            return
        
        # Ask for output file
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"{manual_id}_export.txt"
        )
        
        if not filename:
            return
        
        def export_task():
            try:
                export_manual(manual_id, out_path=filename)
                messagebox.showinfo("Success", f"Manual exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
        
        self.run_in_thread(export_task)


def main():
    root = tk.Tk()
    app = ManualGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
