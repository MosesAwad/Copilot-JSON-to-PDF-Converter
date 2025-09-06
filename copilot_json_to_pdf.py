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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Preformatted, PageBreak, Flowable
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


class CodeBlockFlowable(Flowable):
    """A custom flowable that renders code blocks with proper formatting and borders"""
    
    def __init__(self, code_text, language=None, width=500, font_name='Courier', font_size=9, indent=0):
        Flowable.__init__(self)
        self.code_text = code_text
        self.language = language
        self.width = width
        self.font_name = font_name
        self.font_size = font_size
        self.indent = indent  # Store the indentation value
        
        # Calculate height based on number of lines and font size
        self.lines = code_text.split('\n')
        line_height = font_size * 1.2  # 1.2 is a common line height multiplier
        self.height = (len(self.lines) + 2) * line_height + 20  # +2 for padding and extra for safety
        
        # Border and background colors - distinctive dark green
        self.border_color = HexColor('#2E8B57')  # Dark green border
        self.background_color = HexColor('#D4E9D4')  # Lighter green background
    
    def draw(self):
        """Draw the code block with border and background"""
        canvas = self.canv
        
        # Save canvas state
        canvas.saveState()
        
        # Apply horizontal indentation to match assistant messages - no extra indentation
        canvas.translate(self.indent, 0)
        
        # Draw background
        canvas.setFillColor(self.background_color)
        canvas.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        
        # Draw border - thick and visible
        canvas.setStrokeColor(self.border_color)
        canvas.setLineWidth(2)
        canvas.rect(0, 0, self.width, self.height, fill=0, stroke=1)
        
        # Draw language label if provided
        if self.language:
            canvas.setFont('Helvetica-Oblique', self.font_size)
            canvas.setFillColor(HexColor('#2C5282'))  # Dark blue for language label
            canvas.drawString(10, self.height - 15, self.language)
        
        # Draw code text
        y = self.height - 30 if self.language else self.height - 15
        canvas.setFont(self.font_name, self.font_size)
        canvas.setFillColor(HexColor('#333333'))  # Dark gray for code
        
        # Draw each line of code with no extra indentation beyond what's in the code
        for line in self.lines:
            # Calculate proper indentation from the code itself
            code_indent = 0
            for char in line:
                if char == ' ':
                    code_indent += 1
                elif char == '\t':
                    code_indent += 4  # Standard tab width
                else:
                    break
                    
            # Draw the line with proper indentation - use minimal indent
            canvas.drawString(10 + code_indent * 4, y, line.lstrip())
            y -= self.font_size * 1.2
        
        # Restore canvas state
        canvas.restoreState()
    
    def wrap(self, availWidth, availHeight):
        """Return the size this flowable will take up"""
        self.width = min(self.width, availWidth - self.indent)
        return (self.width + self.indent, self.height)


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
        self.code_counter = 0  # Counter to track code blocks
        self.processed_metadata_blocks = set()  # Keep track of processed metadata blocks
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
        
        # Assistant message style - updated to handle code blocks properly
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
        
        # Nested code block style - for code within the assistant message
        self.styles.add(ParagraphStyle(
            name='NestedCodeBlock',
            parent=self.styles['Code'],
            fontSize=9,
            fontName='Courier',
            leftIndent=0,
            rightIndent=0,
            spaceBefore=6,
            spaceAfter=6,
            backColor=HexColor('#F5F5F5'),
            borderColor=grey,
            borderWidth=1,
            borderPadding=6,
            firstLineIndent=0  # Important for indentation
        ))
        
        # Code block style - updated for proper indentation
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
            backColor=HexColor('#F5F5F5'),
            firstLineIndent=0  # Crucial for indentation
        ))
        
        # Language label style
        self.styles.add(ParagraphStyle(
            name='CodeLanguage',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=HexColor('#555555'),
            leftIndent=20,
            spaceAfter=3
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
        
        # Headers - process in order from most specific to least specific to avoid conflicts
        content = re.sub(r'^#### (.*?)$', r'<font size="10"><b>\1</b></font>', content, flags=re.MULTILINE)
        content = re.sub(r'^### (.*?)$', r'<font size="11"><b>\1</b></font>', content, flags=re.MULTILINE)
        content = re.sub(r'^## (.*?)$', r'<font size="12"><b>\1</b></font>', content, flags=re.MULTILINE)
        content = re.sub(r'^# (.*?)$', r'<font size="14"><b>\1</b></font>', content, flags=re.MULTILINE)
        
        # Convert newlines to line breaks
        content = content.replace('\n', '<br/>')
        
        return content
    
    def _extract_code_blocks_from_text(self, text):
        """Extract code blocks from text content with proper indentation preservation"""
        code_blocks = []
        remaining_text = text
        
        # Pattern to match code blocks with triple backticks
        pattern = r'```(\w*)\n(.*?)\n```'
        
        # Find all code blocks in the text
        for match in re.finditer(pattern, text, re.DOTALL):
            # Get the parts before and after the code block
            start = match.start()
            end = match.end()
            # Extract language and code, preserving whitespace
            language = match.group(1).strip() if match.group(1) else ''
            code = match.group(2)  # This preserves indentation
            # Create a unique ID for this block
            block_id = f"TEXT_{self.code_counter}"
            self.code_counter += 1
            # Store the code block
            code_blocks.append({
                'id': block_id,
                'code': code,
                'language': language,
                'source': 'text',
                'start_pos': start,
                'end_pos': end
            })
        return code_blocks
    
    def _extract_code_blocks_from_response(self, response_parts):
        """Process response parts to extract text content and code blocks"""
        full_text = ""
        for part in response_parts:
            if isinstance(part, dict) and 'value' in part:
                full_text += part['value']
            elif isinstance(part, str):
                full_text += part
        
        # Extract code blocks from the full text
        code_blocks = self._extract_code_blocks_from_text(full_text)
        
        # Replace code blocks with placeholders
        processed_text = full_text
        for block in reversed(code_blocks):  # Process in reverse to maintain positions
            start = block['start_pos']
            end = block['end_pos']
            placeholder = f"[CODE_BLOCK_{block['id']}]"
            processed_text = processed_text[:start] + placeholder + processed_text[end:]
        
        return processed_text, code_blocks
    
    def _get_code_blocks_from_metadata(self, request):
        """Extract code blocks from request metadata"""
        code_blocks = []
        
        # Check if there's metadata with code blocks
        if ('result' in request and 'metadata' in request['result'] and 
            'codeBlocks' in request['result']['metadata']):
            metadata_blocks = request['result']['metadata']['codeBlocks']
            for block in metadata_blocks:
                if 'code' in block:
                    block_id = f"META_{self.code_counter}"
                    self.code_counter += 1
                    
                    code_blocks.append({
                        'id': block_id,
                        'code': block['code'],
                        'language': block.get('language', ''),
                        'source': 'metadata',
                        'markdownBeforeBlock': block.get('markdownBeforeBlock', ''),
                        'resource': block.get('resource', None)
                    })
        return code_blocks
    
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
    
    def _add_code_block_flowable(self, code, language=None):
        """Add a custom code block flowable to the story"""
        # Get the assistant message style
        assistant_style = self.styles['AssistantMessage']
        
        # EXACT MATCH FIX: We need to make the code block EXACTLY the same width
        # Calculate the total document width
        doc_width = self.doc.width
        
        # Account for border padding in the assistant style
        border_padding = assistant_style.borderPadding * 2 if hasattr(assistant_style, 'borderPadding') else 0
        
        # Precisely calculate content width to match assistant messages exactly
        # Increase the compensation from +2 to +8 for better width matching
        content_width = doc_width - assistant_style.leftIndent - assistant_style.rightIndent + 8
        
        # Create code block with perfect width and positioning
        code_block = CodeBlockFlowable(
            code, 
            language, 
            width=content_width,
            indent=assistant_style.leftIndent
        )
        
        # Add the code block directly
        self.story.append(code_block)
        self.story.append(Spacer(1, 6))
    
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
            # Reset code counter for each message
            self.code_counter = 0
            self.processed_metadata_blocks.clear()
            
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
            
            # Process assistant response
            response_parts = request.get('response', [])
            if response_parts:
                # Extract text and code blocks from response
                text, text_code_blocks = self._extract_code_blocks_from_response(response_parts)
                
                # Get metadata code blocks
                metadata_code_blocks = self._get_code_blocks_from_metadata(request)
                
                # Handle text and code blocks in separate elements
                if text:
                    # Create a map of block IDs to blocks
                    block_map = {block['id']: block for block in text_code_blocks}
                    
                    # Split the text at code block placeholders
                    segments = []
                    current_pos = 0
                    
                    # Find all code block placeholders in the text
                    for match in re.finditer(r'\[CODE_BLOCK_(TEXT_\d+)\]', text):
                        # Add text before the placeholder
                        if match.start() > current_pos:
                            segments.append({
                                'type': 'text',
                                'content': text[current_pos:match.start()]
                            })
                        # Add the code block
                        block_id = match.group(1)
                        if block_id in block_map:
                            segments.append({
                                'type': 'code',
                                'block': block_map[block_id]
                            })
                        
                        current_pos = match.end()
                    
                    # Add any remaining text
                    if current_pos < len(text):
                        segments.append({
                            'type': 'text',
                            'content': text[current_pos:]
                        })
                    
                    # Start with assistant intro
                    self.story.append(Paragraph("<b>Assistant:</b>", self.styles['AssistantMessage']))
                    
                    # Process segments in order
                    for segment in segments:
                        if segment['type'] == 'text':
                            processed_text = self._process_message_content(segment['content'])
                            if processed_text.strip():  # Only add non-empty text
                                self.story.append(Paragraph(processed_text, self.styles['AssistantMessage']))
                        elif segment['type'] == 'code':
                            code = segment['block']['code']
                            language = segment['block'].get('language', '')
                            self._add_code_block_flowable(code, language)
                elif metadata_code_blocks:
                    self.story.append(Paragraph("<b>Assistant:</b>", self.styles['AssistantMessage']))
                    for block in metadata_code_blocks:
                        # Add code block using the custom flowable
                        code = block['code']
                        language = block.get('language', '')
                        self._add_code_block_flowable(code, language)
            
            # Add spacing between conversations
            self.story.append(Spacer(1, 20))
            
            # Add page break every few messages
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
        description='Convert VSCode GitHub Copilot chat JSON export to PDF')
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
