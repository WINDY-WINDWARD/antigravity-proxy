# 🚀 Antigravity OpenAI-Compatible Proxy

> ⚠️ **DISCLAIMER & WARNING**  
> This project intercepts and utilizes internal Google Cloud Code / Antigravity endpoints in a way they were not intended to be used. This is **against the Terms of Service (TOS)** and expected usage of the Antigravity API. By using this software, **you assume all risks** associated with your Google account, including potential rate-limiting, bans, or account suspension. Use at your own risk!

<div align="center">
  <h3>Bridge the gap between Google's internal Antigravity AI endpoints and OpenAI-compatible applications.</h3>
  
  <p>
    Seamlessly use cutting-edge Gemini Flash and Pro models right inside your favorite AI coding assistants (Cursor, Cline, LibreChat, and more!) via a lightweight, secure, local proxy with a built-in GUI.
  </p>
</div>

---

## ✨ Features

* 🔌 **100% OpenAI Compatible:** Spoofs headers, remaps message roles, injects cryptographic signatures, and patches schema mismatches so standard OpenAI tools can talk to Google's internal API effortlessly.
* 🖥️ **Built-in GUI Dashboard:** A sleek, native Tkinter interface to manage the proxy, track token usage, view request logs, and monitor errors in real-time.
* 💬 **Streaming & Tool Calling:** Fully supports OpenAI Server-Sent Events (SSE) streaming and complex, multi-turn tool calling without triggering Google's strict Protobuf validators.
* 🔐 **Secure Google OAuth:** Uses PKCE OAuth 2.0 flow to generate short-lived tokens on your machine securely. 
* 🌍 **LAN Accessible:** Serve the proxy over your local network (`0.0.0.0`) so other devices on your Wi-Fi can connect.
* 📊 **Token Analytics:** Accurately tracks `prompt` and `completion` tokens directly from Google's usage metadata.

## 📦 Supported Models

The proxy automatically exposes a `/v1/models` route with support for:

* `gemini-3.6-flash`
* `gemini-3.7-flash-low` (Fast)
* `gemini-3.7-flash-medium` (Balanced)
* `gemini-3.7-flash-high` (Reasoning)
* `gemini-3.8-flash`
* `gemini-3.1-pro` (Quality)

---

## 🚀 Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/antigravity-proxy.git
   cd antigravity-proxy
   ```
2. **Launch the Application:**
   Double-click the `start.bat` file.
   *It will automatically install Python dependencies into an isolated virtual environment and launch the UI.*
3. **Authenticate:**
   In the proxy window, click **"Login to Antigravity"**. Your browser will securely log you into your Google Account.
4. **Start the Proxy:**
   Click **"Start Server"**. The proxy is now listening on port `1337` (or your configured port).
5. **Connect your Apps:**
   Click **"Copy URL"** and paste `http://127.0.0.1:1337/v1` into the Base URL setting of your AI application (e.g., Cursor, Cline). Set the API Key to anything (e.g., `dummy`).

---

## 🏗️ Architecture

* **FastAPI:** Core routing and API translation.
* **Uvicorn:** High-performance async web server.
* **Tkinter:** Thread-safe graphical user interface.

## 🤝 Contributing

Pull requests are welcome! If you find a new Gemini model or an edge case with the Antigravity API, feel free to open an issue or submit a patch.

## ⚖️ License

MIT License. See `LICENSE` for details.
