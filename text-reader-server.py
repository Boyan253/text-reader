import asyncio
import io
import json
import os
import re
import threading
import time
import uuid
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

import edge_tts

VERSION = "1.0.2"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Boyan253/text-reader/master/"
CHECK_INTERVAL = 300
CHUNK_MAX_CHARS = 2000

jobs = {}


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class TTSHandler(SimpleHTTPRequestHandler):
    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == '/tts':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length))

            text = data.get('text', '')
            voice = data.get('voice', 'bg-BG-KalinaNeural')
            rate = data.get('rate', '+0%')

            job_id = uuid.uuid4().hex[:8]
            chunks = split_text(text)
            jobs[job_id] = {
                "status": "generating",
                "progress": 0,
                "total": len(chunks),
                "audio": None,
                "error": None,
            }

            t = threading.Thread(
                target=generate_job, args=(job_id, chunks, voice, rate), daemon=True
            )
            t.start()

            self._json({"job_id": job_id, "chunks": len(chunks)})

        elif self.path == '/check-update':
            updated = check_and_update()
            self._json({"updated": updated, "version": VERSION})
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
            super().do_GET()
        elif self.path.startswith('/status/'):
            job_id = self.path[8:]
            job = jobs.get(job_id)
            if not job:
                self._json({"error": "not found"}, 404)
            else:
                self._json({
                    "status": job["status"],
                    "progress": job["progress"],
                    "total": job["total"],
                    "error": job["error"],
                })
        elif self.path.startswith('/audio/'):
            job_id = self.path[7:]
            job = jobs.get(job_id)
            if not job or job["status"] != "done":
                self.send_error(404)
                return
            audio = job["audio"]
            self.send_response(200)
            self.send_header('Content-Type', 'audio/mpeg')
            self.send_header('Content-Length', len(audio))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(audio)
            del jobs[job_id]
        elif self.path == '/version':
            self._json({"version": VERSION})
        else:
            super().do_GET()

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def log_message(self, format, *args):
        pass


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


def generate_job(job_id, chunks, voice, rate):
    audio_parts = []
    for i, chunk in enumerate(chunks):
        try:
            audio = asyncio.run(generate_tts(chunk, voice, rate))
            audio_parts.append(audio)
            jobs[job_id]["progress"] = i + 1
            print(f"[tts:{job_id}] Chunk {i+1}/{len(chunks)} done")
        except Exception as e:
            print(f"[tts:{job_id}] Error on chunk {i+1}: {e}")
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)
            return

    jobs[job_id]["audio"] = b"".join(audio_parts)
    jobs[job_id]["status"] = "done"
    print(f"[tts:{job_id}] All done, {len(jobs[job_id]['audio'])} bytes")


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
    except Exception:
        return None


def download_file(filename):
    try:
        url = GITHUB_RAW_BASE + filename
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception:
        return None


def check_and_update():
    global VERSION
    remote_version = fetch_remote_version()
    if not remote_version or remote_version == VERSION:
        return False

    base_dir = os.path.dirname(os.path.abspath(__file__))
    for fname in ["text-reader.html", "text-reader-server.py", "version.txt"]:
        data = download_file(fname)
        if data:
            with open(os.path.join(base_dir, fname), "wb") as f:
                f.write(data)

    VERSION = remote_version
    print(f"[updater] Updated to v{VERSION}")
    return True


def updater_loop():
    time.sleep(30)
    while True:
        try:
            check_and_update()
        except Exception:
            pass
        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    port = 8765

    threading.Thread(target=updater_loop, daemon=True).start()

    server = ThreadedHTTPServer(('localhost', port), TTSHandler)
    print(f'Text Reader v{VERSION} running at http://localhost:{port}')
    print('Press Ctrl+C to stop')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
        server.server_close()
