from fastapi import HTTPException, UploadFile, status


UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


async def read_upload_limited(
    file: UploadFile, max_bytes: int, too_large_detail: str = "File is too large"
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(UPLOAD_READ_CHUNK_BYTES):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, too_large_detail)
        chunks.append(chunk)
    return b"".join(chunks)
