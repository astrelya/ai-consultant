import os
import requests
from pypdf import PdfReader

class SpecParser:
    def parse_pdf(self, file_path: str) -> str:
        """
        Parses a PDF file and extracts text page by page.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found at {file_path}")
            
        print(f"[SpecParser] Parsing PDF: {file_path}")
        text_content = []
        try:
            reader = PdfReader(file_path)
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text_content.append(f"--- Page {page_num + 1} ---\n{page_text}")
            return "\n\n".join(text_content)
        except Exception as e:
            print(f"[SpecParser] Error parsing PDF {file_path}: {e}")
            raise RuntimeError(f"Failed to parse PDF: {e}")

    async def parse_url(self, url: str) -> str:
        """
        Parses a URL, retrieves HTML and parses it to clean text/markdown.
        """
        print(f"[SpecParser] Fetching URL: {url}")
        try:
            # We fetch url with timeout
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            })
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP error {resp.status_code} requesting {url}")
            
            html_content = resp.text
            # Basic parsing: extract body or text using simple regex or html to markdown.
            # Since we don't have BeautifulSoup pinned, we can do simple cleanups
            import re
            
            # Remove scripts and styles
            text = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', html_content)
            text = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', text)
            
            # Strip html tags
            text = re.sub(r'<[^>]+>', ' ', text)
            
            # Clean up white spaces
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Truncate content to keep it reasonable
            return f"Parsed URL: {url}\n\nContent:\n{text[:20000]}"
        except Exception as e:
            print(f"[SpecParser] Error fetching/parsing URL {url}: {e}")
            raise RuntimeError(f"Failed to parse URL: {e}")
            
    def parse_file(self, file_path: str) -> str:
        """
        Parses generic text/markdown file.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at {file_path}")
            
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
