import asyncio
import io
import json
import os
import re
import threading
import time
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

import edge_tts

VERSION = "1.0.1"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Boyan253/text-reader/master/"
CHECK_INTERVAL = 300  # check every 5 minutes
CHUNK_MAX_CHARS = 2000


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class TTSHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/tts':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))

            text = data.get('text', '')
            voice = data.get('voice', 'bg-BG-KalinaNeural')
            rate = data.get('rate', '+0%')

            chunks = split_text(text)
            print(f"[tts] Generating {len(chunks)} chunks for {len(text)} chars...")

            # Generate all audio first, then send
            audio_parts = []
            for i, chunk in enumerate(chunks):
                try:
                    audio = asyncio.run(generate_tts(chunk, voice, rate))
                    audio_parts.append(audio)
                    print(f"[tts] Chunk {i+1}/{len(chunks)} done ({len(audio)} bytes)")
                except Exception as e:
                    print(f"[tts] Error on chunk {i+1}: {e}")

            full_audio = b"".join(audio_parts)

            self.send_response(200)
            self.send_header('Content-Type', 'audio/mpeg')
            self.send_header('Content-Length', len(full_audio))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(full_audio)
            print(f"[tts] Sent {len(full_audio)} bytes total.")

        elif self.path == '/check-update':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            updated = check_and_update()
            self.wfile.write(json.dumps({"updated": updated, "version": VERSION}).encode())
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.path = '/text-reader.html'
        elif self.path == '/version':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"version": VERSION}).encode())
            return
        super().do_GET()

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def log_message(self, format, *args):
        if '/tts' not in str(args):
            super().log_message(format, *args)


def split_text(text):
    if len(text) <= CHUNK_MAX_CHARS:
        return [text]

    sentences = re.split(r'(?<=[.!?\n])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) > CHUNK_MAX_CHARS and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current += " " + sentence if current else sentence

    if current.strip():
        chunks.append(current.strip())

    final = []
    for chunk in chunks:
        if len(chunk) <= CHUNK_MAX_CHARS:
            final.append(chunk)
        else:
            words = chunk.split()
            part = ""
            for word in words:
                if len(part) + len(word) + 1 > CHUNK_MAX_CHARS and part:
                    final.append(part.strip())
                    part = word
                else:
                    part += " " + word if part else word
            if part.strip():
                final.append(part.strip())

    return final


async def generate_tts(text, voice, rate):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    buffer = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buffer.write(chunk["data"])
    return buffer.getvalue()


def fetch_remote_version():
    try:
        url = GITHUB_RAW_BASE + "version.txt"
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode().strip()
    except Exception as e:
        print(f"[updater] Could not check version: {e}")
        return None


def download_file(filename):
    try:
        url = GITHUB_RAW_BASE + filename
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        print(f"[updater] Failed to download {filename}: {e}")
        return None


def check_and_update():
    global VERSION
    remote_version = fetch_remote_version()
    if not remote_version:
        return False

    if remote_version == VERSION:
        return False

    print(f"[updater] New version available: {remote_version} (current: {VERSION})")
    base_dir = os.path.dirname(os.path.abspath(__file__))

    html_data = download_file("text-reader.html")
    if html_data:
        with open(os.path.join(base_dir, "text-reader.html"), "wb") as f:
            f.write(html_data)
        print("[updater] Updated text-reader.html")

    server_data = download_file("text-reader-server.py")
    if server_data:
        with open(os.path.join(base_dir, "text-reader-server.py"), "wb") as f:
            f.write(server_data)
        print("[updater] Updated text-reader-server.py (restart to apply)")

    ver_data = download_file("version.txt")
    if ver_data:
        with open(os.path.join(base_dir, "version.txt"), "wb") as f:
            f.write(ver_data)

    VERSION = remote_version
    print(f"[updater] Updated to v{VERSION}")
    return True


def updater_loop():
    time.sleep(10)
    while True:
        try:
            check_and_update()
        except Exception as e:
            print(f"[updater] Error: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    port = 8765

    updater_thread = threading.Thread(target=updater_loop, daemon=True)
    updater_thread.start()
    print(f"[updater] Auto-update enabled (checking every {CHECK_INTERVAL}s)")

    server = ThreadedHTTPServer(('localhost', port), TTSHandler)
    print(f'Text Reader v{VERSION} running at http://localhost:{port}')
    print('Press Ctrl+C to stop')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
        server.server_close()
