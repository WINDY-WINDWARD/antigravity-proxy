import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import queue
import uvicorn
import asyncio
import sys

from proxy import create_app
from auth import trigger_login_flow

class ProxyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Antigravity OpenAI Proxy")
        self.root.geometry("700x500")
        
        self.q = queue.Queue()
        self.server_thread = None
        self.server = None
        self.is_running = False
        
        self.stats = {
            "incoming": 0,
            "success": 0,
            "error": 0,
            "prompt_tokens": 0,
            "comp_tokens": 0
        }
        
        self.create_widgets()
        self.root.after(100, self.process_queue)
        
    def create_widgets(self):
        # Top Frame for Controls
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)
        
        ttk.Label(top_frame, text="Port:").pack(side=tk.LEFT, padx=(0, 5))
        self.port_var = tk.StringVar(value="1337")
        self.port_entry = ttk.Entry(top_frame, textvariable=self.port_var, width=10)
        self.port_entry.pack(side=tk.LEFT, padx=(0, 15))
        
        self.start_btn = ttk.Button(top_frame, text="Start Server", command=self.start_server)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(top_frame, text="Stop Server", command=self.stop_server, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.copy_btn = ttk.Button(top_frame, text="Copy URL", command=self.copy_url)
        self.copy_btn.pack(side=tk.LEFT, padx=5)
        
        self.login_btn = ttk.Button(top_frame, text="Login to Antigravity", command=self.start_login)
        self.login_btn.pack(side=tk.RIGHT, padx=5)
        
        # Stats Frame (Requests)
        stats_frame = ttk.Frame(self.root, padding=10)
        stats_frame.pack(fill=tk.X)
        
        ttk.Label(stats_frame, text="Requests:", font=("Arial", 9, "italic")).pack(side=tk.LEFT, padx=(0, 10))
        
        self.incoming_lbl = ttk.Label(stats_frame, text="Incoming: 0", font=("Arial", 10, "bold"))
        self.incoming_lbl.pack(side=tk.LEFT, padx=10)
        
        self.success_lbl = ttk.Label(stats_frame, text="Successful: 0", font=("Arial", 10, "bold"), foreground="green")
        self.success_lbl.pack(side=tk.LEFT, padx=10)
        
        self.error_lbl = ttk.Label(stats_frame, text="Errors: 0", font=("Arial", 10, "bold"), foreground="red")
        self.error_lbl.pack(side=tk.LEFT, padx=10)

        # Token Stats Frame
        token_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        token_frame.pack(fill=tk.X)
        
        ttk.Label(token_frame, text="Tokens:", font=("Arial", 9, "italic")).pack(side=tk.LEFT, padx=(0, 20))
        
        self.prompt_lbl = ttk.Label(token_frame, text="Incoming (Prompt): 0", font=("Arial", 10))
        self.prompt_lbl.pack(side=tk.LEFT, padx=10)
        
        self.comp_lbl = ttk.Label(token_frame, text="Outgoing (Completion): 0", font=("Arial", 10))
        self.comp_lbl.pack(side=tk.LEFT, padx=10)
        
        self.total_lbl = ttk.Label(token_frame, text="Total: 0", font=("Arial", 10, "bold"), foreground="blue")
        self.total_lbl.pack(side=tk.LEFT, padx=10)
        
        # Console Frame
        console_frame = ttk.Frame(self.root, padding=10)
        console_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(console_frame, text="Live Console:").pack(anchor=tk.W)
        self.console = scrolledtext.ScrolledText(console_frame, wrap=tk.WORD, bg="black", fg="white", font=("Consolas", 9))
        self.console.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_message("Welcome to Antigravity Proxy.")
        self.log_message("Click 'Login to Antigravity' if you haven't authenticated yet.")
        self.log_message("Then click 'Start Server' and point your AI apps to http://localhost:1337/v1")

    def log_message(self, msg):
        self.console.insert(tk.END, msg + "\n")
        self.console.see(tk.END)

    def process_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item["type"] == "log":
                    self.log_message(item["message"])
                elif item["type"] == "token_stat":
                    self.stats["prompt_tokens"] += item.get("prompt", 0)
                    self.stats["comp_tokens"] += item.get("completion", 0)
                    self.update_stats_labels()
                elif item["type"] == "stat":
                    metric = item["metric"]
                    if metric in self.stats:
                        self.stats[metric] += 1
                        self.update_stats_labels()
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)
            
    def update_stats_labels(self):
        self.incoming_lbl.config(text=f"Incoming: {self.stats['incoming']}")
        self.success_lbl.config(text=f"Successful: {self.stats['success']}")
        self.error_lbl.config(text=f"Errors: {self.stats['error']}")
        
        pt = self.stats["prompt_tokens"]
        ct = self.stats["comp_tokens"]
        self.prompt_lbl.config(text=f"Incoming (Prompt): {pt:,}")
        self.comp_lbl.config(text=f"Outgoing (Completion): {ct:,}")
        self.total_lbl.config(text=f"Total: {(pt + ct):,}")

    def run_uvicorn(self, port):
        # We must create the app here inside the thread so it gets the queue reference
        app = create_app(self.q)
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="error")
        self.server = uvicorn.Server(config)
        self.q.put({"type": "log", "message": f"🚀 Proxy started. Local: http://127.0.0.1:{port} | LAN: http://<your-ip-address>:{port}"})
        self.server.run()
        self.q.put({"type": "log", "message": "🛑 Server stopped."})

    def start_server(self):
        if self.is_running: return
        
        try:
            port = int(self.port_var.get())
        except ValueError:
            self.log_message("[ERROR] Invalid port number.")
            return
            
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.port_entry.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        self.server_thread = threading.Thread(target=self.run_uvicorn, args=(port,), daemon=True)
        self.server_thread.start()

    def stop_server(self):
        if not self.is_running or not self.server: return
        
        self.q.put({"type": "log", "message": "Stopping server..."})
        self.server.should_exit = True
        
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.port_entry.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        
    def copy_url(self):
        url = f"http://127.0.0.1:{self.port_var.get()}/v1"
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self.root.update() # Keep clipboard contents after window might lose focus
        self.q.put({"type": "log", "message": f"[INFO] Copied to clipboard: {url}"})

    def start_login(self):
        def login_thread():
            self.q.put({"type": "log", "message": "Starting OAuth flow... Check your browser."})
            
            def log_callback(msg):
                self.q.put({"type": "log", "message": msg})
                
            trigger_login_flow(log_callback)
            
        threading.Thread(target=login_thread, daemon=True).start()

    def on_closing(self):
        if self.is_running and self.server:
            self.server.should_exit = True
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ProxyApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
