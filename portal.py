"""Container-local synthetic portal. No application services or patient data."""
import html
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class Portal(BaseHTTPRequestHandler):
    def do_GET(self):
        documents = json.loads(Path('/lab-data/documents.json').read_text())
        if self.path == '/':
            body = '<h1>Synthetic evidence library</h1><p>Training fixtures; not clinical guidelines.</p>'
            body += ''.join(f'<p><a href="/documents/{d["id"]}">{html.escape(d["title"])}</a></p>' for d in documents)
        else:
            document = next((d for d in documents if self.path == '/documents/' + d['id']), None)
            if document is None:
                self.send_error(404)
                return
            body = f'<h1>{html.escape(document["title"])}</h1><p>Evidence ID: {document["id"]}</p><pre>{html.escape(document["text"])}</pre><a href="/">Library</a>'
        page = ('<!doctype html><html><head><title>Synthetic research portal</title><style>body{font:18px system-ui;margin:40px;max-width:1000px}pre{white-space:pre-wrap}</style></head><body>' + body + '</body></html>').encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    HTTPServer(('127.0.0.1', 8765), Portal).serve_forever()
