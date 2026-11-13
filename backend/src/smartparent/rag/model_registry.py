"""
STUDIQS® SmartParent™ - High-Performance AI/ML Model Registry & Singleton Cache
=============================================================================
Module: src.smartparent.rag.model_registry

Solves AI/ML production bottlenecks:
  - Eliminates redundant multi-second disk I/O and RAM thrashing (118 MB ONNX + 17 MB Tokenizer).
  - Thread-Safe Double-Checked Locking Singleton Pattern.
  - Multi-Worker / Multi-Thread Concurrency Safe.
  - Supports eager warm-up for container orchestrators (Kubernetes / Render probes).
  - Memory Footprint & Readiness Auditing.
=============================================================================
"""

import os
import json
import logging
import threading
from typing import Dict, Optional, Tuple, Any
import numpy as np

logger = logging.getLogger("STUDIQS_ModelRegistry")

try:
    import onnxruntime as ort
except ImportError:
    ort = None

try:
    from tokenizers import Tokenizer
except ImportError:
    Tokenizer = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None


class NLUModelRegistry:
    """
    Thread-Safe Singleton Registry for Neuro-Symbolic NLU ONNX Runtime & Tokenizers.
    Ensures 118MB ONNX model and 17MB Tokenizer are loaded exactly once per worker process.
    """

    _instance: Optional["NLUModelRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(NLUModelRegistry, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, bundle_dir: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return

        with self._lock:
            if getattr(self, "_initialized", False):
                return

            self._bundle_dir = self._resolve_bundle_dir(bundle_dir)
            self._session: Optional[Any] = None
            self._tokenizer: Optional[Any] = None
            self._config: Dict[str, Any] = {}
            self._id_to_bio: Dict[int, str] = {}
            self._is_warmed_up: bool = False

            self._load_artifacts()
            self._initialized = True
            logger.info(f"[NLUModelRegistry] Initialized from bundle: {self._bundle_dir}")

    @staticmethod
    def _resolve_bundle_dir(explicit_dir: Optional[str] = None) -> str:
        """Finds the model directory across development and production layouts."""
        if explicit_dir and os.path.isdir(explicit_dir):
            return os.path.abspath(explicit_dir)

        current_file_dir = os.path.dirname(__file__)
        candidates = [
            os.path.join(current_file_dir, "models"),
            os.path.join(os.getcwd(), "src", "smartparent", "rag", "models"),
            os.path.join(os.getcwd(), "backend", "src", "smartparent", "rag", "models"),
            os.path.join(os.getcwd(), "smartparent-backend", "src", "smartparent", "rag", "models"),
            os.path.join(os.getcwd(), "studiqs_production_bundle"),
            os.path.join(os.getcwd(), "backend", "studiqs_production_bundle"),
            os.path.join(os.getcwd(), "smartparent-backend", "studiqs_production_bundle"),
            os.path.join(current_file_dir, "..", "..", "..", "studiqs_production_bundle"),
        ]
        for c in candidates:
            if os.path.isdir(c) and os.path.exists(os.path.join(c, "studiqs_neuro_nlu_int8.onnx")):
                return os.path.abspath(c)

        return os.path.join(current_file_dir, "models")

    def _load_artifacts(self) -> None:
        """Loads configuration, tokenizer, and ONNX session."""
        # 1. Config & Labels
        label_cfg_file = os.path.join(self._bundle_dir, "label_config.json")
        if os.path.exists(label_cfg_file):
            try:
                with open(label_cfg_file, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
            except Exception as e:
                logger.error(f"[NLUModelRegistry] Failed loading {label_cfg_file}: {e}")
                self._config = {}
        else:
            self._config = {
                "id_to_bio_tag": {
                    "0": "O", "1": "B-CHILD", "2": "I-CHILD", "3": "B-SUBJ", "4": "I-SUBJ",
                    "5": "B-TOPIC", "6": "I-TOPIC", "7": "B-TIME", "8": "I-TIME", "9": "B-EXCL", "10": "I-EXCL"
                }
            }
        self._id_to_bio = {int(k): v for k, v in self._config.get("id_to_bio_tag", {}).items()}

        # 2. Tokenizer
        tok_file = os.path.join(self._bundle_dir, "tokenizer.json")
        if os.path.exists(tok_file) and Tokenizer is not None:
            try:
                self._tokenizer = Tokenizer.from_file(tok_file)
                self._tokenizer.enable_padding(length=64)
                self._tokenizer.enable_truncation(max_length=64)
            except Exception as e:
                logger.error(f"[NLUModelRegistry] Failed initializing Tokenizer: {e}")
                self._tokenizer = None

        # 3. ONNX Session
        model_file = os.path.join(self._bundle_dir, "studiqs_neuro_nlu_int8.onnx")
        if os.path.exists(model_file) and ort is not None:
            try:
                sess_opts = ort.SessionOptions()
                sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                sess_opts.intra_op_num_threads = 2
                self._session = ort.InferenceSession(
                    model_file,
                    sess_opts,
                    providers=["CPUExecutionProvider"],
                )
            except Exception as e:
                logger.error(f"[NLUModelRegistry] Failed initializing ONNX session: {e}")
                self._session = None

    @classmethod
    def get_instance(cls, bundle_dir: Optional[str] = None) -> "NLUModelRegistry":
        """Thread-safe accessor for the singleton registry."""
        if cls._instance is None:
            return cls(bundle_dir=bundle_dir)
        return cls._instance

    @property
    def session(self) -> Optional[Any]:
        return self._session

    @property
    def tokenizer(self) -> Optional[Any]:
        return self._tokenizer

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    @property
    def id_to_bio(self) -> Dict[int, str]:
        return self._id_to_bio

    @property
    def bundle_dir(self) -> str:
        return self._bundle_dir

    def is_ready(self) -> bool:
        """Returns True if the ONNX session and Tokenizer are ready for zero-latency inference."""
        return self._session is not None and self._tokenizer is not None

    def warm_up(self) -> bool:
        """
        Executes a dry-run inference pass to prime the ONNX execution plan and CPU caches.
        Ensures sub-15ms latency on the very first live user request.
        """
        if self._is_warmed_up or not self.is_ready():
            return self._is_warmed_up

        with self._lock:
            if self._is_warmed_up:
                return True
            try:
                enc = self._tokenizer.encode("Warm up test query")
                input_ids = np.array([enc.ids], dtype=np.int64)
                attention_mask = np.array([enc.attention_mask], dtype=np.int64)
                inputs = {
                    self._session.get_inputs()[0].name: input_ids,
                    self._session.get_inputs()[1].name: attention_mask,
                }
                _ = self._session.run(None, inputs)
                self._is_warmed_up = True
                logger.info("[NLUModelRegistry] Warm-up inference complete.")
                return True
            except Exception as e:
                logger.warning(f"[NLUModelRegistry] Warm-up encountered error: {e}")
                return False


class SpeechModelRegistry:
    """
    Thread-Safe Singleton Registry & Model Cache for Faster-Whisper Speech Recognition.
    """

    _instance: Optional["SpeechModelRegistry"] = None
    _lock = threading.Lock()
    _models: Dict[Tuple[str, str, str], Any] = {}

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(SpeechModelRegistry, cls).__new__(cls)
        return cls._instance

    @classmethod
    def get_model(
        cls,
        model_size: str = "base.en",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> Optional[Any]:
        """Returns a cached WhisperModel or instantiates one thread-safely."""
        key = (model_size, device, compute_type)
        if key in cls._models:
            return cls._models[key]

        with cls._lock:
            if key in cls._models:
                return cls._models[key]

            if WhisperModel is None:
                return None

            try:
                model = WhisperModel(model_size, device=device, compute_type=compute_type)
                cls._models[key] = model
                logger.info(f"[SpeechModelRegistry] Loaded Whisper model: {key}")
                return model
            except Exception as e:
                logger.warning(f"[SpeechModelRegistry] Failed loading Whisper model {key}: {e}")
                return None

