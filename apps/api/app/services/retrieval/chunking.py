import hashlib

BOUNDARIES = ["\n\n", "\n", " ", ""]


def split_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> list[str]:
    content = text.strip()
    if not content:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(content):
        end = min(start + chunk_size, len(content))
        window = content[start:end]
        if end < len(content):
            for boundary in BOUNDARIES:
                if not boundary:
                    break
                index = window.rfind(boundary)
                if index > chunk_size // 2:
                    end = start + index + len(boundary)
                    window = content[start:end]
                    break
        chunks.append(window.strip())
        if end >= len(content):
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def make_chunk_id(paper_id: str, chunk: str) -> str:
    return hashlib.sha256(f"{paper_id}:{chunk}".encode("utf-8")).hexdigest()
