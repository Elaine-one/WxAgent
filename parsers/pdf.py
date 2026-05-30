import pdfplumber


def read_pdf(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n\n".join(
            page.extract_text() or f"[第{i+1}页无可提取文本]"
            for i, page in enumerate(pdf.pages)
        )
