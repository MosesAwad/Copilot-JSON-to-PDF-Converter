# 📄 Copilot Chat JSON → PDF Converter

Convert your exported **GitHub Copilot Chat** JSON files into professional-looking PDFs with preserved formatting, syntax highlighting, and a clean conversation flow.

---

## ✨ Features

- **JSON Parsing**  
  Handles Copilot's nested request–response structure, including timestamps, user messages, and assistant responses.

- **Rich Formatting**  
  - Preserves markdown (bold, italic, headers)  
  - Styles **user** vs **assistant** messages distinctly  
  - Formats code blocks in monospace with borders  
  - Maintains proper spacing and layout for readability  

- **PDF Output**  
  - Title page with conversation metadata  
  - Chronological message flow  
  - Code blocks styled separately  
  - Automatic page breaks for long messages  
  - Clean, professional styling with subtle borders & highlights  

- **Robust & Flexible**  
  - Gracefully handles malformed or missing fields  
  - Supports multiple page sizes (`letter`, `A4`)  
  - Produces shareable, archive-friendly PDFs  

---

## ⚙️ Installation

Make sure you have Python 3 installed. Then install dependencies:

```bash
pip install reportlab pygments
```

---

## 🚀 Usage

Convert a JSON export to PDF:

```bash
python copilot_to_pdf.py your_chat.json output.pdf
```

---

## 🛠️ Script Highlights

- **Robust JSON Parsing** → Handles Copilot's nested structure
- **Message Processing** → Extracts user & assistant content with formatting
- **Code Block Handling** → Monospace font, borders, syntax placeholders
- **Error Handling** → Safe fallback for malformed JSON
- **Flexible Output** → Clean layout with multiple page options