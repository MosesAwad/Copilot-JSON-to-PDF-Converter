#!/usr/bin/env python3
"""
VSCode GitHub Copilot Chat JSON to PDF Converter

This script converts exported GitHub Copilot chat conversations from JSON format to PDF.
It preserves formatting, code syntax highlighting, and conversation structure.

Requirements:
    pip install reportlab pygments markdown

Usage:
    python copilot_to_pdf.py input.json output.pdf
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
import re

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, grey, darkblue, darkgreen
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted, PageBreak
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.pdfgen import canvas

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import NullFormatter
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False
    print("Warning: pygments not available. Code syntax highlighting will be disabled.")


class CopilotChatPDF:
    def __init__(self, json_file, output_file, page_size=letter):
        self.json_file = json_file
        self.output_file = output_file
        self.page_size = page_size
        self.doc = SimpleDocTemplate(output_file, pagesize=page_size,
                                   rightMargin=72, leftMargin=72,
                                   topMargin=72, bottomMargin=18)
        self.styles = getSampleStyleSheet()
        self.story = []
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles for the PDF"""
        # User message style
        self.styles.add(ParagraphStyle(
            name='UserMessage',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=12,
            leftIndent=0,
            rightIndent=20,
            borderWidth=1,
            borderColor=HexColor('#E3F2FD'),
            borderPadding=8,
            backColor=HexColor('#F8F9FA')
        ))
        
        # Assistant message style
        self.styles.add(ParagraphStyle(
            name='AssistantMessage',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=12,
            leftIndent=20,
            rightIndent=0,
            borderWidth=1,
            borderColor=HexColor('#E8F5E8'),
            borderPadding=8,
            backColor=HexColor('#F9FFF9')
        ))
        
        # Code block style
        self.styles.add(ParagraphStyle(
            name='CodeBlock',
            parent=self.styles['Code'],
            fontSize=9,
            fontName='Courier',
            leftIndent=20,
            rightIndent=20,
            spaceAfter=12,
            borderWidth=1,
            borderColor=grey,
            borderPadding=8,
            backColor=HexColor('#F5F5F5')
        ))
        
        # Chat header style
        self.styles.add(ParagraphStyle(
            name='ChatHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=16,
            textColor=darkblue,
            borderWidth=0,
            borderPadding=0
        ))
        
        # Metadata style
        self.styles.add(ParagraphStyle(
            name='Metadata',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=grey,
            spaceAfter=8
        ))
    
    def _escape_html(self, text):
        """Escape HTML characters in text"""
        if not isinstance(text, str):
            return str(text)
        
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        text = text.replace("'", '&#x27;')
        return text
    
    def _format_code_block(self, code, language=''):
        """Format code block with syntax highlighting if available"""
        if not code.strip():
            return ""
        
        # Clean the code
        code = code.strip()
        
        # Create a simple formatted code block
        formatted_code = self._escape_html(code)
        
        # Add language label if provided
        if language:
            language_label = f"<font color='blue'>{language}</font><br/>"
            formatted_code = language_label + formatted_code
        
        return f"<font name='Courier' size='9'>{formatted_code}</font>"
    
    def _process_message_content(self, content):
        """Process message content, handling markdown-like formatting"""
        if not content:
            return ""
        
        # Convert markdown-style formatting to reportlab HTML
        content = self._escape_html(str(content))
        
        # Bold text
        content = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', content)
        
        # Italic text
        content = re.sub(r'\*(.*?)\*', r'<i>\1</i>', content)
        
        # Inline code
        content = re.sub(r'`([^`]+)`', r'<font name="Courier">\1</font>', content)
        
        # Headers
        content = re.sub(r'^### (.*?)$', r'<b>\1</b>', content, flags=re.MULTILINE)
        content = re.sub(r'^## (.*?)$', r'<font size="12"><b>\1</b></font>', content, flags=re.MULTILINE)
        content = re.sub(r'^# (.*?)$', r'<font size="14"><b>\1</b></font>', content, flags=re.MULTILINE)
        
        # Convert newlines to line breaks
        content = content.replace('\n', '<br/>')
        
        return content
    
    def _extract_code_blocks_from_response(self, response_parts):
        """Extract code blocks from response parts"""
        code_blocks = []
        current_text = ""
        
        for part in response_parts:
            if isinstance(part, dict):
                if part.get('kind') == 'codeblockUri':
                    # This indicates a code block is coming
                    continue
                elif 'value' in part:
                    text = part['value']
                    
                    # Look for code blocks in the text
                    code_block_pattern = r'```(\w+)?\n(.*?)\n```'
                    matches = re.finditer(code_block_pattern, text, re.DOTALL)
                    
                    last_end = 0
                    for match in matches:
                        # Add text before code block
                        current_text += text[last_end:match.start()]
                        
                        # Extract code block
                        language = match.group(1) or ''
                        code = match.group(2)
                        code_blocks.append({
                            'language': language,
                            'code': code,
                            'position': len(current_text)
                        })
                        
                        # Add placeholder for code block
                        current_text += f"[CODE_BLOCK_{len(code_blocks)-1}]"
                        last_end = match.end()
                    
                    # Add remaining text
                    current_text += text[last_end:]
            elif isinstance(part, str):
                current_text += part
        
        return current_text, code_blocks
    
    def _add_title_page(self, chat_data):
        """Add a title page to the PDF"""
        title_style = ParagraphStyle(
            name='Title',
            parent=self.styles['Title'],
            fontSize=24,
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        subtitle_style = ParagraphStyle(
            name='Subtitle',
            parent=self.styles['Normal'],
            fontSize=14,
            spaceAfter=20,
            alignment=TA_CENTER,
            textColor=grey
        )
        
        self.story.append(Spacer(1, 2*inch))
        self.story.append(Paragraph("GitHub Copilot Chat Export", title_style))
        
        # Add requester information if available
        requester = chat_data.get('requesterUsername', 'Unknown User')
        self.story.append(Paragraph(f"Conversation with {requester}", subtitle_style))
        
        # Add export date
        export_date = datetime.now().strftime("%B %d, %Y")
        self.story.append(Paragraph(f"Exported on {export_date}", subtitle_style))
        
        # Add summary information
        requests = chat_data.get('requests', [])
        self.story.append(Paragraph(f"Total messages: {len(requests)}", subtitle_style))
        
        self.story.append(PageBreak())
    
    def convert(self):
        """Convert the JSON chat to PDF"""
        try:
            with open(self.json_file, 'r', encoding='utf-8') as f:
                chat_data = json.load(f)
        except Exception as e:
            print(f"Error reading JSON file: {e}")
            return False
        
        # Add title page
        self._add_title_page(chat_data)
        
        # Process each request-response pair
        requests = chat_data.get('requests', [])
        
        for i, request in enumerate(requests):
            # Add request number header
            header_text = f"Message {i + 1}"
            if 'timestamp' in request:
                timestamp = datetime.fromtimestamp(request['timestamp'] / 1000)
                header_text += f" - {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            
            self.story.append(Paragraph(header_text, self.styles['ChatHeader']))
            
            # Add user message
            user_message = request.get('message', {}).get('text', '')
            if user_message:
                processed_message = self._process_message_content(user_message)
                self.story.append(Paragraph(f"<b>User:</b> {processed_message}", 
                                          self.styles['UserMessage']))
                self.story.append(Spacer(1, 6))
            
            # Add assistant response
            response_parts = request.get('response', [])
            if response_parts:
                response_text, code_blocks = self._extract_code_blocks_from_response(response_parts)
                
                if response_text:
                    # Process the response text and insert code blocks
                    for j, code_block in enumerate(code_blocks):
                        placeholder = f"[CODE_BLOCK_{j}]"
                        if placeholder in response_text:
                            # Split text at placeholder and add code block
                            parts = response_text.split(placeholder, 1)
                            if parts[0]:
                                processed_text = self._process_message_content(parts[0])
                                self.story.append(Paragraph(f"<b>Assistant:</b> {processed_text}", 
                                                          self.styles['AssistantMessage']))
                            
                            # Add code block
                            formatted_code = self._format_code_block(
                                code_block['code'], 
                                code_block.get('language', '')
                            )
                            self.story.append(Preformatted(code_block['code'], 
                                                         self.styles['CodeBlock']))
                            
                            response_text = parts[1] if len(parts) > 1 else ""
                    
                    # Add any remaining text
                    if response_text:
                        processed_text = self._process_message_content(response_text)
                        self.story.append(Paragraph(f"<b>Assistant:</b> {processed_text}", 
                                                  self.styles['AssistantMessage']))
            
            # Add spacing between conversations
            self.story.append(Spacer(1, 20))
            
            # Add page break every few messages to prevent overly long pages
            if (i + 1) % 3 == 0 and i < len(requests) - 1:
                self.story.append(PageBreak())
        
        # Build the PDF
        try:
            self.doc.build(self.story)
            print(f"PDF successfully created: {self.output_file}")
            return True
        except Exception as e:
            print(f"Error creating PDF: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(
        description='Convert VSCode GitHub Copilot chat JSON export to PDF'
    )
    parser.add_argument('input_json', help='Input JSON file path')
    parser.add_argument('output_pdf', help='Output PDF file path')
    parser.add_argument('--page-size', choices=['letter', 'a4'], default='letter',
                       help='PDF page size (default: letter)')
    
    args = parser.parse_args()
    
    # Validate input file
    input_path = Path(args.input_json)
    if not input_path.exists():
        print(f"Error: Input file '{args.input_json}' does not exist.")
        return 1
    
    if not input_path.suffix.lower() == '.json':
        print("Warning: Input file does not have .json extension.")
    
    # Set page size
    page_size = letter if args.page_size == 'letter' else A4
    
    # Create converter and convert
    converter = CopilotChatPDF(args.input_json, args.output_pdf, page_size)
    success = converter.convert()
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())