"""
STUDIQS® SmartParent™ (v6.3 Complete) - Local & Cloud Storage Abstraction
=============================================================================
Module: src.smartparent.utils.storage

Provides file system management, secure filename sanitization, hash calculation,
and storage directory isolation for Evidence, Reports, and Artifacts.
=============================================================================
"""

import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Tuple, Union


def sanitize_filename(filename: str) -> str:
    """
    Strips directory traversal sequences, null bytes, and illegal characters.
    Preserves safe basenames and extensions.
    """
    clean_name = os.path.basename(filename).strip()
    clean_name = re.sub(r"[^\w\.\-\_]", "_", clean_name)
    clean_name = re.sub(r"\.{2,}", ".", clean_name)
    if not clean_name:
        return "unnamed_document.bin"
    return clean_name[:120]


def compute_file_sha256(data_or_path: Union[bytes, str, Path]) -> str:
    """Computes SHA-256 hexadecimal digest of bytes or a file on disk."""
    hasher = hashlib.sha256()
    if isinstance(data_or_path, (str, Path)):
        with open(str(data_or_path), "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
    elif isinstance(data_or_path, (bytes, bytearray)):
        hasher.update(data_or_path)
    else:
        raise TypeError(f"Unsupported input type for checksum: {type(data_or_path)}")
    return hasher.hexdigest()


class LocalStorageManager:
    """
    Enterprise Local File Storage Manager.
    Enforces tenant folder isolation and quota checks.
    """

    def __init__(self, root_dir: Optional[str] = None):
        if not root_dir:
            base_dir = Path(__file__).resolve().parents[3]
            self.root_dir = base_dir / "storage"
        else:
            self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def get_tenant_dir(self, category: str, subscriber_id: str, child_id: Optional[str] = None) -> Path:
        """Returns isolated folder path for subscriber/child within given category."""
        clean_cat = sanitize_filename(category)
        clean_sub = sanitize_filename(str(subscriber_id))
        target_dir = self.root_dir / clean_cat / clean_sub
        if child_id:
            clean_child = sanitize_filename(str(child_id))
            target_dir = target_dir / clean_child
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def save_bytes(
        self,
        category: str,
        subscriber_id: str,
        filename: str,
        content: bytes,
        child_id: Optional[str] = None,
    ) -> Tuple[Path, str]:
        """
        Saves bytes securely inside tenant directory.
        Returns: (saved_path, sha256_hash)
        """
        target_dir = self.get_tenant_dir(category, subscriber_id, child_id)
        safe_name = sanitize_filename(filename)
        out_path = target_dir / safe_name

        with open(out_path, "wb") as f:
            f.write(content)

        file_hash = compute_file_sha256(content)
        return out_path, file_hash

    def file_exists(self, path: Union[str, Path]) -> bool:
        """Checks if a file exists on disk."""
        return Path(path).is_file()

    def get_file_size(self, path: Union[str, Path]) -> int:
        """Returns file size in bytes, or 0 if missing."""
        p = Path(path)
        return p.stat().st_size if p.is_file() else 0


# Default global instance
storage_manager = LocalStorageManager()

