def __getattr__(name):
    _lazy = {
        "read_excel": "parsers.excel",
        "read_pdf": "parsers.pdf",
        "read_docx": "parsers.word",
        "ocr_image": "parsers.image",
    }
    if name in _lazy:
        import importlib
        mod = importlib.import_module(_lazy[name])
        return getattr(mod, name)
    raise AttributeError(f"module 'parsers' has no attribute {name}")
