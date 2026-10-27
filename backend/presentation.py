"""Readable description blocks; raw source markup is never rendered in the browser."""
import re
from html import unescape
from html.parser import HTMLParser

class DescriptionParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'template'):
            self.hidden += 1
        if self.hidden:
            return
        if tag in ('p', 'div', 'section', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'tr'):
            self.parts.append('\n')
        if tag == 'li':
            self.parts.append('• ')
        elif tag in ('h1', 'h2', 'h3', 'h4'):
            self.parts.append('## ')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'template'):
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in ('p', 'div', 'section', 'li', 'h1', 'h2', 'h3', 'h4', 'tr'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(re.sub(r'\s+', ' ', data))

def description_blocks(raw):
    text = str(raw or '')
    if re.search(r'</?(?:p|div|br|li|ul|h[1-6]|span|strong|script|section)\b', text, re.I):
        parser = DescriptionParser()
        parser.feed(text)
        text = ''.join(parser.parts)
    text = unescape(text).replace('\r\n', '\n').replace('\r', '\n')
    blocks = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        bullet = re.match(r'^(?:[•●▪*+-]|\d+[.)])\s+(.+)', line)
        if bullet:
            if not blocks or blocks[-1]['kind'] != 'list':
                blocks.append({'kind':'list', 'items':[]})
            blocks[-1]['items'].append(bullet[1])
        elif re.match(r'^#{1,6}\s', line) or (len(line) < 100 and line.endswith(':')):
            blocks.append({'kind':'heading', 'text':re.sub(r'^#{1,6}\s+', '', line)})
        else:
            # Flat source text still gets readable paragraphs without dropping words.
            sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZÄÖÜ])', line) if len(line) > 600 else [line]
            blocks.extend({'kind':'paragraph', 'text':' '.join(sentences[i:i + 3])} for i in range(0, len(sentences), 3))
    return blocks
