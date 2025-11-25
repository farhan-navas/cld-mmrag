import hashlib
from typing import Optional

# Mapping from MIME types to file extensions
MIME_TO_EXTENSION = {
    "text/plain": ".txt",
    "text/html": ".html",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "video/mp4": ".mp4",
    "video/x-msvideo": ".avi",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/zip": ".zip",
    "message/rfc822": ".eml"
}


def get_file_extension(mime_type: str) -> Optional[str]:
    """
    Get the file extension for a given MIME type.

    :param mime_type: The MIME type as a string.
    :return: The corresponding file extension or None if not found.
    """
    return MIME_TO_EXTENSION.get(mime_type, None)


def sha1(s: str) -> str:
    """
    Generate SHA1 hash for a string.
    
    :param s: String to hash
    :return: SHA1 hash as hex string
    """
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def stable_id(filepath: str, content: str) -> str:
    """
    Generate stable ID for a chunk based on filepath and content.
    
    :param filepath: Path to the source file
    :param content: Chunk content
    :return: SHA1 hash as hex string
    """
    return hashlib.sha1((filepath + "\n" + content).encode("utf-8")).hexdigest()
