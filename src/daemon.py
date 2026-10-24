import re
import os
import json
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="VIZOR Local Daemon")
BASE_DIR = Path(__file__).resolve().parent.parent

class IngestRequest(BaseModel):
    source: str
    content: str
    target_dir: Optional[str] = None

def extract_code_blocks(text: str):
    """
    Извлекает блоки кода вида:
    ```lang:filepath
    code
    ```
    или с комментариями вида # File: filepath
    """
    pattern = r"```(?:[\w+-]+)?:?([^\n\r`]+)?\r?\n([\s\S]*?)```"
    matches = re.findall(pattern, text)
    extracted = []
    
    for path_hint, code in matches:
        path_hint = path_hint.strip() if path_hint else ""
        file_path = None
        
        # Проверка пути в заголовке блока
        if "/" in path_hint or "\\" in path_hint or "." in path_hint:
            file_path = path_hint
        else:
            # Поиск пути в первой строке кода (# File: ...)
            first_line = code.strip().split("\n")[0]
            comment_match = re.match(r"^(?:#|//|--)\s*(?:File|Path|Файл):\s*(.+)$", first_line, re.IGNORECASE)
            if comment_match:
                file_path = comment_match.group(1).strip()
                code = "\n".join(code.strip().split("\n")[1:])
        
        extracted.append({"path": file_path, "content": code})
    return extracted

@app.post("/api/ingest")
async def ingest_chat(payload: IngestRequest):
    work_dir = Path(payload.target_dir) if payload.target_dir else BASE_DIR
    blocks = extract_code_blocks(payload.content)
    applied_files = []

    for block in blocks:
        if block["path"]:
            # Защита от выхода за пределы директории
            clean_rel_path = block["path"].lstrip("\\/").replace("/", os.sep)
            full_path = (work_dir / clean_rel_path).resolve()
            
            if not str(full_path).startswith(str(work_dir)):
                continue
                
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(block["content"].strip() + "\n")
            applied_files.append(str(clean_rel_path))

    return {
        "status": "success",
        "applied_files": applied_files,
        "total_extracted": len(blocks)
    }

@app.get("/api/health")
async def health():
    return {"status": "ok", "base_dir": str(BASE_DIR)}

if __name__ == "__main__":
    uvicorn.run("daemon:app", host="127.0.0.1", port=8765, reload=True)
