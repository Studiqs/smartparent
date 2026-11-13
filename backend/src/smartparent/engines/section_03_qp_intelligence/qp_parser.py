

import os
import re
import sys
import json
import time
import glob
import io
import logging
import argparse
import warnings
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import Counter
from pathlib import Path

# Core OOP Resilience & MLOps Integration
try:
    from src.smartparent.engines.base_engine import (
        BaseEngine, resilient_engine_step, ParsedQuestionSchema, EngineHealthStatus
    )
    from src.smartparent.engines.mlflow_tracker import get_mlops_tracker
except Exception:
    try:
        from .base_engine import (
            BaseEngine, resilient_engine_step, ParsedQuestionSchema, EngineHealthStatus
        )
        from .mlflow_tracker import get_mlops_tracker
    except Exception:
        from src.studiqs.core.base_engine import (
            BaseEngine, resilient_engine_step, ParsedQuestionSchema, EngineHealthStatus
        )
        from src.studiqs.mlops.mlflow_tracker import get_mlops_tracker

# 
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

warnings.filterwarnings('ignore')

# Set Protobuf implementation for PaddleOCR compatibility
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

# Setup Production Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger("DocAIPipeline_v3")

# Optional / Dynamic Dependencies Setup
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    cv2, np = None, None
    HAS_CV2 = False
    logger.warning("OpenCV (cv2) or NumPy not installed. Vision preprocessing disabled.")

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    try:
        import pymupdf as fitz
        HAS_FITZ = True
    except ImportError:
        fitz = None
        HAS_FITZ = False
        logger.warning("PyMuPDF (fitz) not installed. PDF extraction will rely on image OCR.")

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    Image = None
    HAS_PIL = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    pd = None
    HAS_PANDAS = False

try:
    import pytesseract
    # Configure Tesseract path for Windows if installed at standard locations
    tess_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(tess_path):
        pytesseract.pytesseract.tesseract_cmd = tess_path
    
    # Configure local tessdata prefix if present (including Tamil support)
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    local_tessdata = project_root / "models" / "tessdata"
    if local_tessdata.exists():
        os.environ['TESSDATA_PREFIX'] = str(local_tessdata)
    else:
        old_local = r"c:\deeplearning_proj\question parser\tessdata"
        if os.path.exists(old_local):
            os.environ['TESSDATA_PREFIX'] = old_local
    HAS_TESSERACT = True
except ImportError:
    pytesseract = None
    HAS_TESSERACT = False
    logger.warning("pytesseract not installed. OCR fallback disabled.")

try:
    from paddleocr import PPStructure
    HAS_PADDLE = True
except Exception:
    PPStructure = None
    HAS_PADDLE = False

try:
    from tamil.txt2unicode import bamini2unicode, shreelipi2unicode, tscii2unicode, tab2unicode, tam2unicode
    HAS_TAMIL_CONVERTER = True
except ImportError:
    HAS_TAMIL_CONVERTER = False


# ============================================================
# 1. DATA MODELS
# ============================================================

@dataclass
class Question:
    question_no: int
    question: str
    marks: int
    tables: List[str] = field(default_factory=list)
    sub_questions: List[Dict[str, Any]] = field(default_factory=list)
    choices_or: List[str] = field(default_factory=list)
    board: str = "Unknown"
    has_diagram: bool = False
    diagram_image: str = ""
    diagram_labels: List[str] = field(default_factory=list)
    section: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "question_no": self.question_no,
            "question": self.question.strip(),
            "marks": self.marks,
            "board": self.board,
            "section": self.section
        }
        if self.tables:
            data["tables"] = self.tables
        if self.sub_questions:
            data["sub_questions"] = self.sub_questions
        if self.choices_or:
            data["choices_or"] = self.choices_or
        if self.has_diagram:
            data["has_diagram"] = self.has_diagram
        if self.diagram_image:
            data["diagram_image"] = self.diagram_image
        if self.diagram_labels:
            data["diagram_labels"] = self.diagram_labels
        return data


# ============================================================
# 2. REGEX PATTERNS CONFIGURATION
# ============================================================

QUESTION_NUMBER_PATTERNS = [
    # Matches 1. / 1) / 1, / 1: / 1- / 2 2 / 5 , / 7 sep : / Q1. / Q.1 / Question 1. / 21(a). / 31(I)
    r'^\s*(?:Q\.?|Question\s*)?([1-9]\d*)(?:\s*\([a-zA-ZivxIVX]+\))?(?:\s*[\.\,\)\:\-\–—\•\·\*\~%]+|\s+(?=[a-zA-Z\u0B80-\u0BFF\d\(\[\'\"‘“])|(?<=\))\s*$)(?=\s|\b|[^a-zA-Z0-9]|$)',
    r'(?:^|[\/\|\s–\-])(?:Section|Part|பகுதி|பாகம்|பிரிவு)\s*[A-ZIV\-\–]+\s*[\/\-]?\s*(?:Q?\.?)?([1-9]\d*)(?:\s*\([a-zA-ZivxIVX]+\))?[\.\,\)\:\-]',
]

NUMBER_WORDS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,
    'twenty-one': 21, 'twenty-two': 22, 'twenty-three': 23, 'twenty-four': 24, 'twenty-five': 25,
    'twenty-six': 26, 'twenty-seven': 27, 'twenty-eight': 28, 'twenty-nine': 29, 'thirty': 30,
    'thirty-four': 34, 'thirty-five': 35, 'thirty-six': 36, 'thirty-seven': 37, 'thirty-eight': 38, 'forty': 40,
    'एक': 1, 'दो': 2, 'तीन': 3, 'चार': 4, 'पांच': 5, 'पाँच': 5,
    'छह': 6, 'सात': 7, 'आठ': 8, 'नौ': 9, 'दस': 10,
    'ग्यारह': 11, 'बारह': 12, 'तेरह': 13, 'चौदह': 14, 'पंद्रह': 15, 'सोलह': 16, 'बीस': 20,
    'ஒன்று': 1, 'இரண்டு': 2, 'மூன்று': 3, 'நான்கு': 4, 'ஐந்து': 5,
    'ஆறு': 6, 'ஏழு': 7, 'எட்டு': 8, 'ஒன்பது': 9, 'பத்து': 10,
}

def parse_num_token(val_str: Optional[str]) -> Optional[int]:
    if not val_str:
        return None
    val_str = val_str.strip().lower()
    if val_str.isdigit():
        return int(val_str)
    return NUMBER_WORDS.get(val_str)

MARKS_PATTERNS = [
    r'\[\s*(\d+)\s*(?:marks?|mark|pts?|points?)?\s*\]',
    r'\(\s*(\d+)\s*(?:marks?|mark|pts?|points?)(?:\s*each)?\s*\)',
    r'(?<!\w)(\d+)\s*[Mm]arks?$',
    r'(?<!\w)(\d+)\s*(?:மதிப்பெண்கள்?|மதிப்பெண்)\s*$',
    r'(?<!\w)(\d+)\s*(?:अंक|अंको)\s*$',
    r'(?<!\w)(?:\d+\s*\+\s*)+\d+\s*[=\-–—]\s*(\d+)(?!\w)',
    r'(?<!\w)(\d+)\s*\(\s*\d+\s*(?:\+\s*\d+)+\s*\)',
]

SECTION_HEADER_PATTERNS = [
    r'(?:^|[\/\|\s–\-\(\[])(?:SECTION|Section|PART|Part|பகுதி|பாகம்|பிரிவு|खण्ड|भाग)(?:\b|[\s\-–:])\s*[\:–\-\—\/\s\ufffd\?]*\s*[\(\[\'\"]?([A-Za-zIVX\d\u0900-\u097f]+)',
    r'^\s*([IVX]{1,6})\s*[\.\-–\—\:]\s*$',
    r'^\s*([IVX]{1,6})\s*[\.\-–\—\:]\s*(?:Choose|Fill|Say|State|Match|Answer|விரிவான|குறுகிய|எவையேனும்|சரியான|விடையைத்|கோடிட்ட|பொருத்துக|சரியா|பகுதி|பிரிவு)',
    r'^(?!\s*\d+[\.\,\)])(?:Note:\s*|[IVXil1|!\u00a6]{1,6}\.?\s*[-–]?\s*)?(?:Choose\s+the|Fill\s+in|Say\s+True|State\s+True|Match\s+the|Answer\s+the|True\s+or\s+False|Answer\s+any|Answer\s+all|Answer\s+the\s+following|Answer\s+briefly|Answer\s+in\s+detail|விரிவான\s+விடையளி)',
    r'^(?!\s*\d+[\.\,\)])(?:குறிப்பு:\s*|[IVXil1|!\u00a6\u0B80-\u0BFF\w]{1,6}\.?\s*[-–]?\s*)?(?:சரியான|விடையைத்|கோடிட்ட|பொருத்துக|சரியா|ஏதேனும்|எவையேனும்|அனைத்து\s+(?:வினாக்களுக்கும்|கேள்விகளுக்கும்|வினாக்கள்|விடையளி)|விரிவான)',
    r'(?:கோடிட்ட\s+இடத்தை|பொருத்துக|சரியா\s+அல்லது\s+தவறா|சரியான\s+விடையைத்|எவையேனும்\s*\d+|விரிவான\s+விடையளி)',
    r'^\s*(?:[IVXil1|!\u00a6]{1,6}\.?\s*[-–]?\s*)?(?:Fill\s+in\s+the\s+blanks?|State\s+True\s+or\s+False|Choose\s+the\s+correct\s+answer)\b',
]

IGNORE_PATTERNS = [
    r'^\s*(?:Standard\s*)?[IVX\d]+\s+(?:SCIENCE|MATHS|MATHEMATICS|SOCIAL|ENGLISH|TAMIL|HINDI|PHYSICS|CHEMISTRY|BIOLOGY)\s*$',
    r'^\d+\s*\/\s*\d+$', r'^Page\s+\d+\s+of\s+\d+',
    r'^Continue on next page', r'^CLICK HERE', r'^\*+$',
    r'^SAMPLE PAPER', r'^Class-\d+th', r'^Class\s*:\s*\d+',
    r'^Exam-\d{4}-\d{2}', r'^Mathematics.*Code', r'^Time:',
    r'^Max\.?\s*Marks?:', r'General Instructions', r'Read the following instructions\b',
    r'Marks?\s*:\s*\d+', r'Time\s*:\s*\d+',
    r'This Question paper', r'There is no overall', r'Use of calculators',
    r'^\*\*\*+', r'^={3,}', r'^\s*$',
    r'^\[?\s*v[\u0B80-\u0BFF\w\s\/]+over\s*\]?$', r'^\[?\s*Turn over\s*\]?$',
    r'^\d+\s+\d+$', r'^\d{4,}$',
    r'Question No\.\s*\d+\s*is compulsory',
    r'^\s*\d{1,2}[-\/\.]\d{1,2}[-\/\.]\d{2,4}\s*$',
    r'^\d+\s*minute\b',
    r'^Note:\s*Answer\s+the\s+following',
    r'^—\s*END OF QUESTION PAPER\s*—',
    r'^\(\d+\)\s*Check\s+the\s+question\s+paper',
    r'^\(\d+\)\s*Use\s+Blue\s+or\s+Black\s+ink',
    r'^\(\d+\)\s*நீலம்\s+அல்லது\s+கருப்பு\s+மையினை',
    r'^\(\d+\)\s*அனைத்து\s+வினாக்களும்\s+சரியாக',
    r'Candidates must write',
    r'Please write',
    r'^Time allowed',
    r'^Maximum Marks',
    r'This question paper contains',
    r'All questions are compulsory',
    r'Question paper is divided',
    r'allotted to read this question paper',
    r'question paper will be distributed',
    r'written on the title page',
    r'write any answer on the answer-book',
    r'visually impaired candidates',
    r'separate question paper has been provided',
    r'^-\s*o\s*O\s*o\s*-',
    r'^\*?Please note that',
    r'^session\s+i\.?e\.?\s*\d{4}',
    r'assessment\s+scheme.*session',
    r'current\s+session\s+i\.?e\.?',
    r'^\*?i\.?e\.?\s*\d{4}[-\/]\d{2,4}\.?$',
    r'^For visually impaired',
    r'^P\.T\.O\.?$',
    r'^[\-\s]{8,}$',
    r'^assessment scheme',
    r'\bvalues\s+of\s+physical\s+constants\b',
    r'\bभौतिक\s+नियतांक\b',
    r'^\s*(?:Mass\s+of\s+(?:electron|proton|neutron)|Avogadro|Boltzmann|Planck|c\s*=|h\s*=|e\s*=|\b[a-zA-Z\u0370-\u03ff\u2200-\u22ff]\s*=\s*\d+[\.\d]*\s*x\s*10)',
    r'In Section\s+[A-Z]\b',
    r'In Part\s+[A-ZIV\-–]+\b',
    r'Section\s+[A-Z]\s+has\s+\d+\b',
    r'Part\s+[A-ZIV\-–]+\s+has\s+\d+\b',
    r'Section\s+[A-Z]\s+consists\s+of',
    r'Part\s+[A-ZIV\-–]+\s+consists\s+of',
    r'Question\s+numbers?\s+\d+',
    r'All\s+questions\s+of\s+Section',
    r'Internal\s+choices?\s+has\s+been',
    r'This\s+section\s+consists\s+of',
    r'Draw\s+neat\s+and\s+clean',
    r'Marks\s+for\s+questions',
    r'Word\s+limit',
    r'Question\s+Nos?\.',
    r'^\([ivxIVX\d]+\)\s*(?:This\s+Question\s+paper|All\s+questions\s+are|Section\s+[A-Z]|There\s+is\s+no|Use\s+of\s+calculator|Question\s+number)',
    r'^\([ivxIVX\d]+\)\s*.*(?:compulsory|calculator|internal\s+choice|multiple\s+choice\s+type)',
    r'This\s+Question\s+paper\s+contains\s+\d+\s+questions',
    r'Question\s+number\s+\d+\s+to\s+\d+\s+are\b',
    r'carrying\s+\d+\s+marks?\s+each\b',
    r'There\s+is\s+no\s+overall\s+choice\b',
    r'Use\s+of\s+calculator\s+is\s+not\s+allowed\b',
]

TAMIL_RANGE = range(0x0B80, 0x0BFF + 1)
HINDI_RANGE = range(0x0900, 0x097F + 1)
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.gif', '.webp'}


# ============================================================
# 3. OPENCV COMPUTER VISION PREPROCESSOR
# ============================================================

class VisionPreprocessor:
    """Handles deskewing, binarization, denoising, and dynamic upscaling for scanned pages."""

    @staticmethod
    def deskew_image(image: Any) -> Any:
        if not HAS_CV2 or image is None:
            return image
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
            coords = np.column_stack(np.where(gray > 0))
            if len(coords) < 10:
                return image
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            elif angle > 45:
                angle = 90 - angle
            else:
                angle = -angle

            if abs(angle) < 0.5 or abs(angle) > 30:
                return image  # Don't rotate if nearly upright or extreme outlier

            (h, w) = image.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            return rotated
        except Exception as e:
            logger.debug(f"Deskew failed: {e}")
            return image

    @staticmethod
    def binarize_and_denoise(image: Any) -> Any:
        if not HAS_CV2 or image is None:
            return image
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
            # Otsu thresholding provides clean, high-contrast binarization without destroying stroke width or punctuation dots
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            return VisionPreprocessor.deskew_image(binary)
        except Exception as e:
            logger.debug(f"Binarize failed: {e}")
            return image

    @staticmethod
    def upscale_image(image: Any, min_width: int = 2000) -> Any:
        if not HAS_CV2 or image is None:
            return image
        try:
            h, w = image.shape[:2]
            if w < min_width:
                scale = min_width / float(w)
                new_w = int(w * scale)
                new_h = int(h * scale)
                return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
            return image
        except Exception:
            return image


# ============================================================
# 4. TEXT PREPROCESSOR & BOARD DETECTOR
# ============================================================

class TextPreprocessor:
    def clean_line(self, line: str) -> str:
        line = ' '.join(line.split())
        line = re.sub(r'\x00+', '', line)
        line = re.sub(r'\s+', ' ', line).strip()
        return line

    def is_ignored(self, line: str) -> bool:
        if not line:
            return True
        # Do not ignore lines that are just numbers or question markers (potential lone question numbers)
        if re.match(r'^\s*(?:Q\.?|Question\s*)?[1-9]\d*[\.\,\)\:\-]?\s*$', line, re.IGNORECASE):
            return False
        # Do not ignore potential columnar "question_no marks" lines e.g. "33 2"
        columnar_match = re.match(r'^\s*([1-9]\d*)\s+(\d+)\s*$', line)
        if columnar_match:
            try:
                q_no = int(columnar_match.group(1))
                if q_no <= 150:
                    return False
            except ValueError:
                pass
        if len(line) < 2:
            return True
        # Do not ignore general instructions header, as it controls the instruction state machine
        if re.search(r'\b(?:General Instructions|Read the following instructions|strictly follow them)\b|सामान्य निर्देश', line, re.IGNORECASE):
            return False
        for pattern in IGNORE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        prefix_match = re.match(r'^\s*(?:Q\.?|Question\s*)?(?:[IVX\d]+|[A-Za-z])[\.\,\)\]\-\—\s]+(.*)', line, re.IGNORECASE)
        if prefix_match:
            stripped = prefix_match.group(1).strip()
            if stripped:
                for pattern in IGNORE_PATTERNS:
                    if re.search(pattern, stripped, re.IGNORECASE):
                        return True
        return False

    def is_section_header(self, line: str) -> bool:
        # Ignore subject/class headers like "VI SCIENCE"
        if re.search(r'^\s*(?:Standard\s*)?[IVX\d]+\s+(?:SCIENCE|MATHS|MATHEMATICS|SOCIAL|ENGLISH|TAMIL|HINDI|PHYSICS|CHEMISTRY|BIOLOGY)\s*$', line, re.IGNORECASE):
            return False

        # Reject general instructions or column descriptions unless it's a direct answering instruction like "Answer any ten questions"
        if not re.search(r'(?:\banswer\s+(?:any|all|the|briefly|in)\b|எவையேனும்|அனைத்து|விடையளி|விடையளிக்கவும்|ஏதேனும்)', line, re.IGNORECASE):
            if re.search(r'\b(?:has|contains|consists|questions|carrying|each|are\s+compulsory|column|columns)\b', line, re.IGNORECASE):
                return False
        else:
            if re.search(r'\b(?:has|contains|consists|carrying\s+\d+\s+marks?\s+each|each\s+question\s+carries)\b', line, re.IGNORECASE):
                return False

        # Reject passage / case-study question prompts
        if re.search(r'\b(?:based\s+on|given\s+above|information\s+given|read\s+the\s+(?:passage|text|case|extract)|case\s+study|understanding\s+of)\b', line, re.IGNORECASE):
            return False

        # Reject question continuation text starting with "Choose the..." or containing question continuation words
        if not re.search(r'^\s*(?:[IVX]{1,6}|SECTION|PART|Part|பகுதி|பாகம்|பிரிவு)\b', line, re.IGNORECASE):
            if re.search(r'\b(?:which|that|indicates?|represents?|combines?|combination|following\s+statements?|statements?\s+given|given\s+below|from\s+the\s+following|as\s+per|according\s+to)\b', line, re.IGNORECASE) and not re.search(r'\d+\s*[x×]\s*\d+', line):
                return False
            if len(line.split()) > 10 and not re.search(r'\d+\s*[x×]\s*\d+', line):
                return False

        cleaned = re.sub(r'^[\.,;:\s!?]+', '', line.strip())
        cleaned_norm = cleaned.replace('\ufffd', '-').replace('–', '-').replace('—', '-')
        for pattern in SECTION_HEADER_PATTERNS:
            if re.search(pattern, cleaned, re.IGNORECASE) or re.search(pattern, cleaned_norm, re.IGNORECASE) or re.search(pattern, line.strip(), re.IGNORECASE):
                return True
        return False

    def detect_board(self, text: str, file_path: str = "", registered_board: str = "") -> str:
        """Detect board type. Prioritizes coordinator-entered board metadata."""
        if registered_board and registered_board.strip() and registered_board.strip().lower() != "unknown":
            return registered_board.strip()

        text_upper = text[:4000].upper()
        if 'SAMACHEER' in text_upper or 'TAMIL NADU' in text_upper or 'TAMILNADU' in text_upper:
            return 'Samacheer'
        if 'CBSE' in text_upper or 'CENTRAL BOARD' in text_upper or 'SAMPLE QUESTION PAPER' in text_upper or 'NCERT' in text_upper:
            return 'CBSE'
        if re.search(r'\b(?:Q\.?P\.?\s*Code|Series\s*:\s*[A-Z0-9]+|10\.15\s*a\.?m\.?\s*to\s*10\.30\s*a\.?m\.?)\b|प्रश्न-पत्र\s*कोड', text, re.IGNORECASE):
            return 'CBSE'
        if re.search(r'\bSET\s*[:~-]?\s*[1-4]\b', text, re.IGNORECASE) and re.search(r'\b\d{1,3}/\d/\d\b', text):
            return 'CBSE'
        if re.search(r'\(\s*(?:04[1-4]|08[67]|002|184|048|031)\s*\)', text) or re.search(r'Code\s+No\.?\s*(?:04[1-4]|08[67]|002|184|048|031)', text, re.IGNORECASE):
            return 'CBSE'
        if re.search(r'Section\s*[-–—]?\s*E\b', text, re.IGNORECASE) and re.search(r'\b(?:33|38|39)\s*questions\b', text, re.IGNORECASE):
            return 'CBSE'
        if 'ICSE' in text_upper or 'ISC' in text_upper or 'COUNCIL FOR THE INDIAN SCHOOL CERTIFICATE' in text_upper:
            return 'ICSE'
        if 'KARNATAKA' in text_upper:
            return 'Karnataka State Board'
        if 'KERALA' in text_upper:
            return 'Kerala State Board'
        if 'MAHARASHTRA' in text_upper:
            return 'Maharashtra State Board'
        if 'ANDHRA' in text_upper or 'TELANGANA' in text_upper:
            return 'AP/TS State Board'
        
        # Check for Bamini/legacy Tamil font signatures
        bamini_signatures = [
            'wpgup', 'craflé', 'u@fi', 'auifl', 'wpmid', 'eramn', 'eramp',
            'GsrEss', 'Ghlssain', 'L(peaT', 'flser', 'LPOI', 'sSraups',
            'Veneoriiys', 'Asre@slact', 'sLETUTE', 'Qrean®', 'Qouugparer',
            'wtlamadamhs', 'soamUgT', 'sryeiiu@SgLCUTE'
        ]
        text_lower = text[:3000].lower()
        if any(sig in text_lower for sig in bamini_signatures):
            return 'Samacheer'
            
        tamil_char_count = sum(1 for c in text[:3000] if ord(c) in TAMIL_RANGE)
        if tamil_char_count >= 20:
            return 'Samacheer'
            
        return 'General'

    def detect_ocr_lang(self, text: str, file_path: str = "") -> str:
        # Dynamic Unicode script frequency analysis
        tamil_char_count = sum(1 for c in text[:3000] if ord(c) in TAMIL_RANGE)
        if tamil_char_count >= 10:
            return 'eng+tam'
        
        # Devanagari / Hindi script range: 0x0900 to 0x097F
        hindi_char_count = sum(1 for c in text[:3000] if 0x0900 <= ord(c) <= 0x097F)
        if hindi_char_count >= 10:
            return 'eng+hin'
            
        # Filename hints fallback
        if file_path:
            fn = os.path.basename(file_path).lower()
            if any(k in fn for k in ['tamil', 'samacheer', 'tn']):
                return 'eng+tam'
            if any(k in fn for k in ['hindi', 'hin']):
                return 'eng+hin'

        return 'eng'


# ============================================================
# 5. MULTI-TIER EXTRACTION ENGINES
# ============================================================

class ExtractionEngine:
    def extract(self, file_path: str) -> str:
        raise NotImplementedError


class PyMuPDFEngine(ExtractionEngine):
    """Sorts text by bounding boxes to preserve 2-column layouts natively, with legacy Tamil font decoding."""
    
    def __init__(self):
        self.is_bamini = False
        self.legacy_font = None

    @staticmethod
    def _sort_blocks_layout_aware(blocks: List[Any], page_width: float) -> List[Any]:
        text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]
        if not text_blocks:
            return []

        mid_x = page_width / 2.0
        left_blocks = [b for b in text_blocks if (b[0] + b[2]) / 2.0 < mid_x and (b[2] - b[0]) < page_width * 0.6]
        right_blocks = [b for b in text_blocks if (b[0] + b[2]) / 2.0 >= mid_x and (b[2] - b[0]) < page_width * 0.6]

        has_right_col_questions = any(
            re.match(r'^\s*(?:Q\.?|Question\s*)?\d+[\.\)\-]', b[4]) and b[0] >= mid_x - 30 and (b[2] - b[0]) < page_width * 0.55 and len(b[4].strip()) > 15
            for b in text_blocks
        )
        is_two_col = has_right_col_questions and len(left_blocks) >= 3 and len(right_blocks) >= 3
        if not is_two_col:
            # 16pt line-bucketing ensures same-line left text precedes right-margin marks (e.g. 14pt-18pt typography).
            # Compensate for leading newlines in block bounding boxes to avoid artificial vertical shifts.
            def _block_sort_key(b):
                text = b[4]
                leading_ws = text[:len(text) - len(text.lstrip())]
                leading_newlines = leading_ws.count('\n')
                effective_y = b[1] + (leading_newlines * 14.0)
                return (round(effective_y / 16.0), b[0])
            return sorted(text_blocks, key=_block_sort_key)

        sorted_by_y = sorted(text_blocks, key=lambda b: b[1])

        bands = []
        current_band = []
        for b in sorted_by_y:
            w = b[2] - b[0]
            is_full_width = w > page_width * 0.65 or (b[0] < mid_x - 50 and b[2] > mid_x + 50 and w > page_width * 0.5)
            if is_full_width:
                if current_band:
                    bands.append(('multi', current_band))
                    current_band = []
                bands.append(('full', [b]))
            else:
                current_band.append(b)
        if current_band:
            bands.append(('multi', current_band))

        final_sorted = []
        for band_type, band_blocks in bands:
            if band_type == 'full':
                final_sorted.extend(band_blocks)
            else:
                col_left = sorted([b for b in band_blocks if (b[0] + b[2]) / 2.0 < mid_x], key=lambda b: b[1])
                col_right = sorted([b for b in band_blocks if (b[0] + b[2]) / 2.0 >= mid_x], key=lambda b: b[1])
                final_sorted.extend(col_left)
                final_sorted.extend(col_right)

        return final_sorted

    def extract(self, file_path: str) -> str:
        if not HAS_FITZ:
            raise ImportError("fitz module missing")
            
        doc = fitz.open(file_path)
        legacy_converter = None
        
        # Detect legacy Tamil fonts across pages
        if HAS_TAMIL_CONVERTER:
            all_legacy_text = ""
            for page_num in range(min(5, len(doc))):
                page = doc.load_page(page_num)
                blocks = page.get_text("blocks")
                for b in blocks:
                    if b[6] == 0:
                        raw_text = b[4]
                        for c in raw_text:
                            if 0x80 <= ord(c) <= 0xFF:
                                all_legacy_text += c
                                
            if len(all_legacy_text) > 20:
                candidates = {
                    'bamini': bamini2unicode, 'shreelipi': shreelipi2unicode,
                    'tscii': tscii2unicode, 'tab': tab2unicode, 'tam': tam2unicode
                }
                known_words = ['அனைத்து', 'பகுதி', 'வினாக்கள்', 'விடையளிக்கவும்', 'குறிப்பு', 'மதிப்பெண்கள்', 'வகுப்பு', 'அறிவியல்', 'கணிதம்']
                best_name, best_score = None, 0
                for name, conv_func in candidates.items():
                    try:
                        converted = conv_func(all_legacy_text)
                        score = sum(converted.count(w) for w in known_words)
                        if score > best_score:
                            best_score = score
                            best_name = name
                    except Exception:
                        pass
                if best_score > 0:
                    legacy_converter = candidates[best_name]
                    self.is_bamini = True
                    self.legacy_font = best_name
                    logger.info(f"Detected legacy Tamil font '{best_name}' (score: {best_score}).")

        full_text = []
        for page in doc:
            blocks = page.get_text("blocks")
            sorted_blocks = self._sort_blocks_layout_aware(blocks, page.rect.width)
            
            page_lines = []
            for b in sorted_blocks:
                text = b[4]
                if legacy_converter:
                    text = "".join(legacy_converter(c) if 0x80 <= ord(c) <= 0xFF else c for c in text)
                page_lines.append(text)
            full_text.append("\n".join(page_lines))
            
        doc.close()
        return "\n".join(full_text)


class PaddleLayoutEngine(ExtractionEngine):
    """Uses PaddleOCR PP-Structure for Layout & HTML Table extraction on complex scanned papers."""
    
    def __init__(self, lang: str = 'en'):
        if not HAS_PADDLE:
            raise ImportError("paddleocr PPStructure missing or not available")
        self.engine = PPStructure(show_log=False, lang=lang)

    def extract_image(self, img_input: Any) -> str:
        if not HAS_PADDLE:
            return ""
        result = self.engine(img_input)
        structured_text = []
        for region in result:
            if region['type'] == 'text':
                structured_text.append(region['res'])
            elif region['type'] == 'table':
                html_table = region['res']['html']
                structured_text.append(f"\n[TABLE_START]\n{html_table}\n[TABLE_END]\n")
        return "\n".join(structured_text)


class TesseractOCREngine(ExtractionEngine):
    """High-resolution OpenCV-preprocessed Tesseract OCR engine."""
    
    def __init__(self, ocr_lang: str = 'eng+tam'):
        self.ocr_lang = self._resolve_lang(ocr_lang)

    def _resolve_lang(self, requested_lang: str) -> str:
        if not HAS_TESSERACT:
            return 'eng'
        try:
            available = pytesseract.get_languages()
            parts = [p.strip() for p in requested_lang.split('+') if p.strip()]
            valid = [p for p in parts if p in available]
            if valid:
                return '+'.join(valid)
            if 'eng' in available:
                return 'eng'
            return available[0] if available else 'eng'
        except Exception:
            return 'eng'

    def extract_page_ocr(self, page_or_img: Any) -> str:
        if not HAS_TESSERACT or not HAS_PIL:
            return ""
        try:
            if HAS_FITZ and hasattr(page_or_img, 'get_pixmap'):
                # PyMuPDF Page object - render at 150 DPI for optimal OCR clarity and margin preservation
                pix = page_or_img.get_pixmap(dpi=150)
                img_data = pix.tobytes("png")
                pil_img = Image.open(io.BytesIO(img_data))
                
                # Apply OpenCV deskew (preserving natural grayscale gradients for Tesseract LSTM)
                if HAS_CV2:
                    np_img = np.array(pil_img)
                    deskewed = VisionPreprocessor.deskew_image(np_img)
                    pil_img = Image.fromarray(deskewed)
            elif isinstance(page_or_img, str):
                if page_or_img.lower().endswith('.pdf') and HAS_FITZ:
                    doc = fitz.open(page_or_img)
                    text_pages = [self.extract_page_ocr(page) for page in doc]
                    doc.close()
                    return "\n".join(text_pages)
                pil_img = Image.open(page_or_img)
                if HAS_CV2:
                    cv_img = cv2.imread(page_or_img)
                    if cv_img is not None:
                        deskewed = VisionPreprocessor.deskew_image(cv_img)
                        pil_img = Image.fromarray(deskewed)
            else:
                pil_img = page_or_img

            if pil_img.mode in ('RGBA', 'P', 'LA', 'L'):
                pil_img = pil_img.convert('RGB')
                
            # Production Document AI: Use spatial line clustering on word bounding boxes
            # to preserve column margins and prevent left-margin question numbers from detaching.
            text = ""
            try:
                data = pytesseract.image_to_data(pil_img, lang=self.ocr_lang, config="--psm 6", output_type=pytesseract.Output.DICT)
                words = []
                n_boxes = len(data.get('text', []))
                for idx in range(n_boxes):
                    w_txt = data['text'][idx].strip()
                    if not w_txt:
                        continue
                    words.append({
                        'text': w_txt,
                        'left': int(data['left'][idx]),
                        'top': int(data['top'][idx]),
                        'height': int(data['height'][idx]) if int(data['height'][idx]) > 0 else 15
                    })
                if len(words) >= 10:
                    words.sort(key=lambda w: (w['top'], w['left']))
                    lines = []
                    for w in words:
                        w_center = w['top'] + w['height'] / 2.0
                        placed = False
                        for l in lines:
                            if abs(w_center - l['center']) <= 12:
                                l['words'].append(w)
                                l['center'] = sum(x['top'] + x['height'] / 2.0 for x in l['words']) / len(l['words'])
                                placed = True
                                break
                        if not placed:
                            lines.append({'center': w_center, 'words': [w]})

                    lines.sort(key=lambda l: l['center'])
                    page_lines = []
                    for l in lines:
                        l['words'].sort(key=lambda w: w['left'])
                        page_lines.append(" ".join(w['text'] for w in l['words']))

                    text = "\n".join(page_lines)
            except Exception as ocr_err:
                logger.debug(f"Spatial clustering OCR fallback: {ocr_err}")

            if not text or len(text.strip()) < 50:
                text = pytesseract.image_to_string(pil_img, lang=self.ocr_lang, config="--psm 6")
            if not text or len(text.strip()) < 50:
                text = pytesseract.image_to_string(pil_img, lang=self.ocr_lang, config="--psm 4")

            # Post-clean common OCR digit misreads
            text = re.sub(r'(?m)^(\s*)[aA]7\.\s*', r'\g<1>47. ', text)
            text = re.sub(r'(?m)^(\s*([1-9]\d*))%\s*', r'\g<1>. ', text)
            return text
        except Exception as e:
            logger.warning(f"Tesseract OCR page extraction warning: {e}")
            return ""

    def extract(self, file_path: str) -> str:
        return self.extract_page_ocr(file_path)


# ============================================================
# 6. UNIFIED QUESTION & MARKS EXTRACTOR
# ============================================================

class QuestionExtractor:
    def __init__(self, board: str = "", ocr_lang: str = ""):
        self.board = board
        self.ocr_lang = ocr_lang
        self.preprocessor = TextPreprocessor()
        self.questions: List[Question] = []
        self.current_question_text = ""
        self.pre_question_buffer = []
        self.current_marks = 1
        self.global_counter = 0
        self.last_question_no = 0
        self.in_or_block = False
        self.section_marks = {}
        self.instruction_ranges = []
        self.cbse_ranges = self.instruction_ranges  # Alias for backward compatibility
        self.prescan_marks = {}  # Dynamic section->marks map built from document itself
        self.current_section = ""
        self.current_part = ""
        self.in_general_instructions = False
        self.pending_section_restart = False
        self.in_match_the_following = False
        self.current_explicit_marks = []
        self.extracted_tables_buffer = []
        self.marks_from_multiplier = False
        self.section_started = False

    def _parse_range_section_marks(self, text: str):
        prefix_text = text[:8000]
        self.instruction_ranges.clear()
        self.cbse_ranges = self.instruction_ranges

        # 1. Direct "Section X - Question number Y to/and Z ... (and questions ... ) ... M marks"
        sec_range_pat = (
            r'(?:In\s+)?Section\s*[-–—\xad\ufffd]?\s*([A-FIVX\d]+)\s*[-–—:,]?\s*Questions?\s+(?:numbers?|nos?\.?)?\s*(\d+)\s*(?:to|[-–—]|and|&)\s*(\d+)'
            r'(?:[^.;]*?(?:and|&)\s+questions?\s+(?:numbers?|nos?\.?)?\s*(\d+)\s*(?:to|[-–—]|and|&)\s*(\d+))?'
            r'.*?(?:carry|carries|carrying|of)?\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*marks?'
        )
        for m in re.finditer(sec_range_pat, prefix_text, re.IGNORECASE | re.DOTALL):
            if len(m.group(0)) < 250:
                try:
                    sec = m.group(1).upper()
                    start = int(m.group(2))
                    end = int(m.group(5)) if m.group(5) else int(m.group(3))
                    marks = parse_num_token(m.group(6))
                    if marks and 1 <= marks <= 20:
                        self.cbse_ranges.append({"start": start, "end": end, "marks": marks, "section": sec})
                        self.section_marks[sec] = marks
                except ValueError:
                    pass

        # 1b. Sequential section count clauses: "Section A has 16 questions of 1 mark each; Section B has 5 questions of 2 marks each..."
        if not self.cbse_ranges:
            sec_count_clauses = re.split(r'(?:and\s+)?(?=(?:In\s+)?Section\s*[-–—\xad\ufffd]?\s*[A-FIVX\d])', prefix_text, flags=re.IGNORECASE)
            sec_chain = []
            for clause in sec_count_clauses:
                sec_m = re.match(r'^\s*(?:In\s+)?Section\s*[-–—\xad\ufffd]?\s*([A-FIVX\d]+)', clause, re.IGNORECASE)
                if sec_m:
                    sec = sec_m.group(1).upper()
                    hindi_to_eng = {'क': 'A', 'ख': 'B', 'ग': 'C', 'घ': 'D', 'ङ': 'E'}
                    sec = hindi_to_eng.get(sec, sec)
                    cnt_m = re.search(r'(?:has|contains|consists\s+of)\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|twenty)\b', clause, re.IGNORECASE)
                    marks_m = re.search(r'(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*marks?', clause, re.IGNORECASE)
                    if cnt_m and marks_m:
                        cnt = parse_num_token(cnt_m.group(1))
                        marks = parse_num_token(marks_m.group(1))
                        if cnt and marks and 1 <= cnt <= 60 and 1 <= marks <= 20:
                            sec_chain.append((sec, cnt, marks))
            
            if len(sec_chain) >= 2:
                q_cur = 1
                for sec, cnt, marks in sec_chain:
                    q_start = q_cur
                    q_end = q_cur + cnt - 1
                    self.cbse_ranges.append({"start": q_start, "end": q_end, "marks": marks, "section": sec})
                    self.section_marks[sec] = marks
                    q_cur = q_end + 1

        # 2. General range patterns without section letter
        range_patterns = [
            r'(?<!\w)(?:questions?|q\.?nos?\.?)\s*(?:numbers?|nos?\.?)?\s*(\d+)\s*(?:to|[-–—]|and|&)\s*(\d+)\s*(?:are|carry|carrying|of)\s*.*?(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*marks?',
            r'(?:carrying|of)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+marks?\s+each\s+.*?questions?\s+(\d+)\s*(?:to|[-–—]|and|&)\s*(\d+)',
        ]
        for pat in range_patterns:
            for m in re.finditer(pat, prefix_text, re.IGNORECASE | re.DOTALL):
                if len(m.group(0)) < 200:
                    try:
                        start = int(m.group(1)) if pat == range_patterns[0] else int(m.group(2))
                        end = int(m.group(2)) if pat == range_patterns[0] else int(m.group(3))
                        marks = parse_num_token(m.group(3)) if pat == range_patterns[0] else parse_num_token(m.group(1))
                        if marks and 1 <= marks <= 20 and not any(r['start'] == start and r['end'] == end for r in self.cbse_ranges):
                            self.cbse_ranges.append({"start": start, "end": end, "marks": marks})
                    except ValueError:
                        pass

        # 3. Hindi Range: खण्ड ख – प्रश्न संख्या 17 से 21 तक ... 2 अंक
        hindi_range_pat = (
            r'(?:खण्ड|भाग)\s*([कखगघङA-EIVX\d]+)?\s*[-–—:]?\s*प्रश्न\s*(?:संख्या|सं\.?)?\s*(\d+)\s*से\s*(\d+)'
            r'.*?(\d+|एक|दो|तीन|चार|पांच|पाँच)\s*अंक'
        )
        for m in re.finditer(hindi_range_pat, prefix_text, re.IGNORECASE | re.DOTALL):
            if len(m.group(0)) < 250:
                try:
                    sec_raw = m.group(1)
                    sec = None
                    if sec_raw:
                        hindi_to_eng = {'क': 'A', 'ख': 'B', 'ग': 'C', 'घ': 'D', 'ङ': 'E'}
                        sec = hindi_to_eng.get(sec_raw.strip(), sec_raw.strip().upper())
                    start = int(m.group(2))
                    end = int(m.group(3))
                    marks = parse_num_token(m.group(4))
                    if marks and 1 <= marks <= 20:
                        self.cbse_ranges.append({"start": start, "end": end, "marks": marks, "section": sec})
                        if sec:
                            self.section_marks[sec] = marks
                except ValueError:
                    pass

        # 4. Tamil Range: வினா எண் 1 முதல் 14 வரை ... 1 மதிப்பெண்
        tamil_range_pat = r'வினா\s*(?:எண்)?\s*(\d+)\s*முதல்\s*(\d+)\s*வரை.*?(\d+)\s*மதிப்பெண்'
        for m in re.finditer(tamil_range_pat, prefix_text, re.IGNORECASE | re.DOTALL):
            if len(m.group(0)) < 200:
                try:
                    start = int(m.group(1))
                    end = int(m.group(2))
                    marks = int(m.group(3))
                    if 1 <= marks <= 20 and not any(r['start'] == start and r['end'] == end for r in self.cbse_ranges):
                        self.cbse_ranges.append({"start": start, "end": end, "marks": marks})
                except ValueError:
                    pass

        # 5. Section description clauses (including single-sentence multi-section clauses)
        section_patterns = [
            r'Section\s+([A-FIVX\d]+)\s+(?:has|contains|consists\s+of)\s+(?:\d+|[a-z]+)\s+[^,\.\n]{0,100}?question.*?of\s+(\d+|one|two|three|four|five|six)\s*marks?',
            r'Section\s+([A-FIVX\d]+)\s+(?:has|contains|consists\s+of)\s+(?:\d+|[a-z]+)\s+[^,\.\n]{0,120}?(?:of|carrying|\b)\s*(\d+|one|two|three|four|five|six)\s*marks?',
            r'Section\s+([A-FIVX\d]+)\s+consists\s+of\s+\d+\s+questions?\s+of\s+(\d+|one|two|three|four|five|six)\s*marks?',
            r'Section\s+([A-FIVX\d]+)\s+consists\s+of\s+\d+\s+questions?(?:.{0,150}?)(\d+|one|two|three|four|five|six)\s*marks?\s+each',
            r'Section\s+([A-FIVX\d]+)\s+has\s+\d+\s+questions?(?:.{0,150}?)(\d+|one|two|three|four|five|six)\s*marks?\s+each',
            r'Section\s+([A-FIVX\d]+)\s+(?:.{0,150}?)(\d+|one|two|three|four|five|six)\s*marks?\s+each',
        ]
        for pat in section_patterns:
            for m in re.finditer(pat, prefix_text, re.IGNORECASE | re.DOTALL):
                sec = m.group(1).upper()
                hindi_to_eng = {'क': 'A', 'ख': 'B', 'ग': 'C', 'घ': 'D', 'ङ': 'E'}
                sec = hindi_to_eng.get(sec, sec)
                try:
                    marks = parse_num_token(m.group(2))
                    if marks and 1 <= marks <= 20 and sec not in self.section_marks:
                        self.section_marks[sec] = marks
                except ValueError:
                    pass

        # Fallback from general counts
        if not self.cbse_ranges:
            count_marks_pairs = []
            count_pat = r'contains\s+(\d+)\s+.*?of\s+(\d+|one|two|three|four|five|six)\s*marks?\s+each'
            for m in re.finditer(count_pat, text[:3000], re.IGNORECASE | re.DOTALL):
                if len(m.group(0)) < 200:
                    try:
                        count = int(m.group(1))
                        marks = parse_num_token(m.group(2))
                        if marks and 1 <= marks <= 6 and 1 <= count <= 40:
                            count_marks_pairs.append((marks, count))
                    except ValueError:
                        pass

            if count_marks_pairs:
                has_two_sections = bool(re.search(r'section\s+[ab]', text[:5000], re.IGNORECASE))
                num_sections = 2 if has_two_sections else 1
                count_marks_pairs.sort(key=lambda x: x[0])

                q_start = 1
                for _ in range(num_sections):
                    for marks, total_count in count_marks_pairs:
                        per_section = total_count // num_sections
                        if per_section > 0:
                            self.cbse_ranges.append({
                                "start": q_start,
                                "end": q_start + per_section - 1,
                                "marks": marks
                            })
                            q_start += per_section

    # Alias for backwards compatibility
    _parse_cbse_section_marks = _parse_range_section_marks

    def _prescan_section_marks_universal(self, text: str):
        """Pre-scan the ENTIRE document to dynamically build section->marks mapping.
        
        Works for ALL paper types: TN State Board (Samacheer), CBSE, class tests,
        local school papers, any format. Zero hardcoded assumptions.
        
        Strategy (priority order):
        1. NxM=T multiplier lines associated with nearest preceding section header
        2. Instruction text: "of X marks each", "X marks each", "X மதிப்பெண் வீதம்"
        3. Section-inline marks: "[This section comprises...X mark each]"
        """
        lines = text.split('\n')
        current_sec = None
        current_part = None
        last_sec_line = -999  # Track how far we are from the last section header
        last_mult_line = -999
        last_mult_marks = None
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            
            # --- PHASE 1: Detect section headers FIRST (always runs) ---
            
            if self.preprocessor.is_section_header(stripped):
                part_matches = re.findall(r'(?:^|[\/\|\s\u2013\-])(?:PART|Part|\u0baa\u0b95\u0bc1\u0ba4\u0bbf|\u0baa\u0bbe\u0b95\u0bae\u0bcd)\s*[:\u2013\-\u2014\/\s]*\s*([IVXil1\d]+)', stripped, re.IGNORECASE)
                sec_match = re.search(r'(?:^|[\/\|\s\u2013\-])(?:SECTION|Section|\u0baa\u0bbf\u0bb0\u0bbf\u0bb5\u0bc1|\u0916\u0923\u094d\u0921|\u092d\u093e\u0917)\s*[:\u2013\-\u2014\/\s]*\s*([A-Za-z\d\u0900-\u097f]+)', stripped, re.IGNORECASE)
                generic_match = re.search(
                    r'(?:^|[\/\|\s\u2013\-])(?:SECTION|Section|PART|Part|\u0baa\u0b95\u0bc1\u0ba4\u0bbf|\u0baa\u0bbe\u0b95\u0bae\u0bcd|\u0baa\u0bbf\u0bb0\u0bbf\u0bb5\u0bc1|\u0916\u0923\u094d\u0921|\u092d\u093e\u0917)(?:\b|[\s\-\u2013:])\s*[:\u2013\-\u2014\/\s\ufffd\?]*\s*[\(\[\'\"]?([A-Za-zIVXil1\d\u0900-\u097f]+)',
                    stripped, re.IGNORECASE
                )
                if not generic_match and not part_matches and not sec_match:
                    generic_match = re.search(r'^\s*([IVXil1]{1,6})\b', stripped)

                sec_name = None
                if part_matches:
                    roman_order = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
                    raw_candidates = [m.upper().replace('L', 'I').replace('1', 'I') for m in part_matches]
                    raw_part = next((c for c in raw_candidates if c in roman_order), raw_candidates[0])
                    current_part = raw_part
                    sec_name = current_part
                elif sec_match:
                    raw_sec = sec_match.group(1).upper()
                    hindi_to_eng = {'\u0915': 'A', '\u0916': 'B', '\u0917': 'C', '\u0918': 'D', '\u0919': 'E'}
                    raw_sec = hindi_to_eng.get(raw_sec, raw_sec)
                    if current_part:
                        sec_name = f"{current_part}_{raw_sec}"
                    else:
                        sec_name = raw_sec
                elif generic_match:
                    sec_name = generic_match.group(1).upper().replace('L', 'I').replace('1', 'I')
                    hindi_to_eng = {'\u0915': 'A', '\u0916': 'B', '\u0917': 'C', '\u0918': 'D', '\u0919': 'E'}
                    sec_name = hindi_to_eng.get(sec_name, sec_name)

                if sec_name:
                    # Validate: section name must be a single letter A-F, Roman numeral, or digit 1-9
                    valid_sec_names = {'A', 'B', 'C', 'D', 'E', 'F', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X',
                                       '1', '2', '3', '4', '5', '6', '7', '8', '9'}
                    if sec_name in valid_sec_names or '_' in sec_name:
                        # Prevent front-page header artifacts: if on top 15 lines before exams begin, lone PART-II shouldn't lock out PART-I
                        if i < 15 and sec_name not in ('I', 'A') and current_sec is None:
                            if not any(k in stripped.lower() for k in ['answer', 'choose', 'fill', 'question', 'mark', 'compulsory']):
                                pass  # skip registration token
                            else:
                                current_sec = sec_name
                                last_sec_line = i
                        else:
                            roman_order = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
                            if not self.prescan_marks:
                                current_sec = sec_name
                                last_sec_line = i
                            elif part_matches and sec_name in roman_order and current_sec in roman_order:
                                curr_idx = roman_order.index(current_sec)
                                new_idx = roman_order.index(sec_name)
                                if new_idx >= curr_idx:
                                    current_sec = sec_name
                                    last_sec_line = i
                            else:
                                current_sec = sec_name
                                last_sec_line = i
            
            # Also detect Roman numeral section starts like "V. Answer any 10" / "VI Answer in detail"
            roman_sec = re.match(r'^\s*([IVX]{1,6})[\.\s]\s*', stripped)
            if roman_sec:
                candidate = roman_sec.group(1).upper()
                valid_romans = {'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'}
                if candidate in valid_romans:
                    rest_of_line = stripped[roman_sec.end():].strip().lower()
                    is_section_like = (len(rest_of_line) == 0) or any(kw in rest_of_line for kw in [
                        'choose', 'fill', 'match', 'answer', 'state', 'true', 'false',
                        '\u0b95\u0bcb\u0b9f\u0bbf\u0b9f\u0bcd\u0b9f', '\u0baa\u0bca\u0bb0\u0bc1\u0ba4\u0bcd\u0ba4\u0bc1\u0b95', '\u0b9a\u0bb0\u0bbf\u0baf\u0bbe\u0ba9', '\u0bb5\u0bbf\u0b9f\u0bc8\u0baf\u0bb3\u0bbf', '\u0ba8\u0bbf\u0bb0\u0baa\u0bcd\u0baa\u0bc1\u0b95',
                        'say true', 'short answer', 'long answer', 'detail',
                    ])
                    if is_section_like:
                        roman_order = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
                        if current_sec in roman_order and candidate in roman_order:
                            curr_idx = roman_order.index(current_sec)
                            cand_idx = roman_order.index(candidate)
                            if cand_idx > curr_idx:
                                current_sec = candidate
                                last_sec_line = i
                        elif current_sec not in roman_order:
                            current_sec = candidate
                            last_sec_line = i
            
            # --- PHASE 2: Skip sections that already have marks resolved ---
            section_already_resolved = current_sec and current_sec in self.prescan_marks
            
            # --- PHASE 3: Extract marks evidence ---
            
            # Strategy 1: NxM=T multiplier pattern (pure mathematical evidence)
            line_norm = stripped.replace('\u00d7', 'x').replace('\u2715', 'x')
            q_marks = self._extract_multiplier_from_line(line_norm)
            if q_marks is not None:
                is_dup = (i - last_mult_line <= 3 and q_marks == last_mult_marks)
                last_mult_line = i
                last_mult_marks = q_marks
                if is_dup:
                    continue
                if section_already_resolved:
                    roman_order = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
                    if current_sec in roman_order:
                        curr_idx = roman_order.index(current_sec)
                        next_sec = roman_order[min(curr_idx + 1, len(roman_order) - 1)]
                        if next_sec not in self.prescan_marks:
                            current_sec = next_sec
                            last_sec_line = i
                            self.prescan_marks[current_sec] = q_marks
                elif current_sec:
                    self.prescan_marks[current_sec] = q_marks
                    if current_part and current_part not in self.prescan_marks:
                        self.prescan_marks[current_part] = q_marks
                continue
            
            # For non-multiplier lines, skip if section already resolved
            if section_already_resolved:
                continue
            
            # Strategy 2: English instruction text with marks (digit or word)
            line_sec_match = re.search(r'Section\s+([A-FIVX\d]+)\b', stripped, re.IGNORECASE)
            
            instr_patterns = [
                r'\[.*?(?:comprises?|consists?).*?(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*marks?\s*(?:each)?\s*\]',
                r'(?:of|carrying|carries)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*marks?\s*(?:each)?',
                r'(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*marks?\s+each',
                r'comprises.*?(?:of)?\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*marks?',
                r'(?:MCQ|VSA|SA|LA).*?(?:of)?\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*marks?',
            ]
            for pat in instr_patterns:
                instr_match = re.search(pat, stripped, re.IGNORECASE)
                if instr_match:
                    val = parse_num_token(instr_match.group(1))
                    if val and 1 <= val <= 15:
                        target = None
                        if line_sec_match:
                            # Only attribute to line_sec_match if it's within the same sentence/clause
                            if line_sec_match.start() < instr_match.start() or not any(punct in stripped[:line_sec_match.start()] for punct in ['.', ';', '\n']):
                                target = line_sec_match.group(1).upper()
                        elif current_sec and current_sec not in self.prescan_marks:
                            target = current_sec

                        if target and target not in self.prescan_marks:
                            # CBSE Section A is strictly 1m objective MCQs; a 4 or 5m rule is a bleed from Section E/D instructions
                            if getattr(self, 'board', '') == 'CBSE' and target in ('A', 'SECTION_A') and val > 2:
                                continue
                            line_lower = stripped.lower()
                            is_instruction = any(kw in line_lower for kw in [
                                'section', 'comprises', 'consists', 'contains', 'carrying',
                                'type question', 'type questions', 'answer', 'mcq', 'vsa', 'sa ', 'la ',
                                'mark each', 'marks each', 'compulsory',
                                '\u0baa\u0b95\u0bc1\u0ba4\u0bbf', '\u0bae\u0ba4\u0bbf\u0baa\u0bcd\u0baa\u0bc6\u0ba3\u0bcd', '\u0bb5\u0bbf\u0b9f\u0bc8\u0baf\u0bb3\u0bbf'
                            ])
                            if is_instruction:
                                self.prescan_marks[target] = val
                                break
            
            # Strategy 3: Tamil instruction text with marks
            tamil_match = re.search(r'(\d+)\s*(?:\u0bae\u0ba4\u0bbf\u0baa\u0bcd\u0baa\u0bc6\u0ba3\u0bcd\u0b95\u0bb3\u0bcd?|\u0bae\u0ba4\u0bbf\u0baa\u0bcd\u0baa\u0bc6\u0ba3\u0bcd)\s*(?:\u0bb5\u0bc0\u0ba4\u0bae\u0bcd|each)?', stripped)
            if tamil_match and current_sec and current_sec not in self.prescan_marks:
                val = int(tamil_match.group(1))
                if 1 <= val <= 15:
                    self.prescan_marks[current_sec] = val

            # Strategy 4: Hindi instruction text with marks
            hindi_match = re.search(r'प्रत्येक\s+प्रश्न\s*(\d+|एक|दो|तीन|चार|पांच)\s*अंक', stripped)
            if hindi_match and current_sec and current_sec not in self.prescan_marks:
                val = parse_num_token(hindi_match.group(1))
                if val and 1 <= val <= 15:
                    self.prescan_marks[current_sec] = val

    def extract_from_text(self, text: str) -> List[Dict]:
        self.in_general_instructions = False
        if 'instruction' in text.lower() or 'அறிவுரை' in text.lower():
            self.in_general_instructions = True

        has_hs_indicator = bool(re.search(
            r'\b(?:7\s*[xX*]\s*5\s*=\s*35|7\s*[xX*]\s*3\s*=\s*21|11th|12th|\bXI\b|\bXII\b|Higher\s+Secondary|HSC|Std\s*\+[12]|Class\s*\+[12]|Maximum\s*Marks\s*:\s*(?:90|70)|மொத்த\s*மதிப்பெண்கள்\s*:\s*(?:90|70)|20\s*[xX*௩]\s*1\s*=\s*20)\b',
            text, re.IGNORECASE
        ))
        is_10th = bool(re.search(r'\b(?:10th|\bX\b\s+Std|SSLC)\b', text, re.IGNORECASE))
        self.is_higher_sec = has_hs_indicator and not is_10th
        self.is_bilingual_paper = bool(re.search(r'[\u0900-\u097F\u0B80-\u0BFF]', text))

        lines = text.split('\n')
        
        if not self.board:
            self.board = self.preprocessor.detect_board(text)
            
        self._parse_cbse_section_marks(text)
        self._prescan_section_marks_universal(text)
            
        cleaned_lines = []
        for line in lines:
            # Capture table markers
            if '[TABLE_START]' in line or '[TABLE_END]' in line or '<table' in line:
                cleaned_lines.append(line)
                continue
            cleaned = self.preprocessor.clean_line(line)
            if not self.preprocessor.is_ignored(cleaned):
                cleaned_lines.append(cleaned)


        self.section_started = False
        self.pending_section_restart = False
        self.marks_from_multiplier = False
        active_marks = 1
        i = 0
        instructions_line_count = 0
        
        while i < len(cleaned_lines):
            line = cleaned_lines[i]
            next_line = cleaned_lines[i+1] if i + 1 < len(cleaned_lines) else ""

            # Check for Table markers from Layout Engine
            if '[TABLE_START]' in line:
                table_lines = []
                i += 1
                while i < len(cleaned_lines) and '[TABLE_END]' not in cleaned_lines[i]:
                    table_lines.append(cleaned_lines[i])
                    i += 1
                table_html = "\n".join(table_lines).strip()
                if table_html:
                    self.extracted_tables_buffer.append(table_html)
                i += 1
                continue

            # Enter general instructions state if header is seen
            if re.search(r'\b(?:General\s+Instructions?|Instructions?\s*:|Read\s+the\s+following\s+instructions?|strictly\s+follow\s+them)\b|सामान्य\s+निर्देश|அறிவுரைகள்?', line, re.IGNORECASE):
                self.in_general_instructions = True
                instructions_line_count = 0
                self._finalize_current_question()

            if self.in_general_instructions:
                instructions_line_count += 1
                if instructions_line_count > 150:
                    self.in_general_instructions = False
                elif self.preprocessor.is_section_header(line):
                    self.in_general_instructions = False
                elif re.match(r'^\s*(?:Q\.?\s*|Question\s*)?1[\.\)]\s+', line, re.IGNORECASE) and not re.search(r'\b(?:consists|contains|compulsory|instructions?|candidate|carrying|marks?\s+each|allotted|divided|internal|choice|pages?|questions?\s+in\s+this)\b', line, re.IGNORECASE):
                    self.in_general_instructions = False
                else:
                    i += 1
                    continue

            if not self.in_general_instructions and not self.preprocessor.is_section_header(line):
                mult_val = self._extract_multiplier_marks(line, self.board)
                if mult_val is not None:
                    if self.current_question_text:
                        self._finalize_current_question()
                    active_marks = mult_val
                    self.marks_from_multiplier = True
                    self.pre_question_buffer = []
                    self.section_started = True
                    self.pending_section_restart = True
                    i += 1
                    continue

            # Section headers
            is_sec = self.preprocessor.is_section_header(line)
            if is_sec:
                is_bare_roman = bool(re.match(r'^\s*([IVXil1]{1,6})\s*[\.\-–\—\:]\s*$', line.strip()))
                if is_bare_roman:
                    if getattr(self, 'board', '') == 'CBSE':
                        is_sec = False
                    elif self.current_question_text and not getattr(self, 'marks_from_multiplier', False):
                        is_sec = False

            if is_sec:
                self._finalize_current_question()
                self.pre_question_buffer = []
                self.section_started = True
                self.in_general_instructions = False
                self.pending_section_restart = True

                sec_name = None
                line_low = line.lower()
                part_matches = re.findall(r'(?:^|[\/\|\s–\-])(?:PART|Part|பகுதி|பாகம்)\s*[:–\-\—\/\s]*\s*([IVXil1\d]+)', line, re.IGNORECASE)
                sec_match = re.search(r'(?:^|[\/\|\s–\-])(?:SECTION|Section|பிரிவு|खण्ड|भाग)\s*[:–\-\—\/\s]*\s*([A-Za-z\d\u0900-\u097f]+)', line, re.IGNORECASE)
                generic_match = re.search(r'(?:^|[\/\|\s–\-])(?:SECTION|Section|PART|Part|பகுதி|பாகம்|பிரிவு|खण्ड|भाग)(?:\b|[\s\-–:])\s*[\:–\-\—\/\s\ufffd\?]*\s*[\(\[\'\"]?([A-Za-zIVXil1\d\u0900-\u097f]+)', line, re.IGNORECASE)
                if not generic_match and not part_matches and not sec_match:
                    generic_match = re.search(r'^\s*([IVXil1]{1,6})[\.\s\-–:]*', line)

                if part_matches:
                    roman_order = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
                    raw_candidates = [m.upper().replace('L', 'I').replace('1', 'I') for m in part_matches]
                    raw_part = next((c for c in raw_candidates if c in roman_order), raw_candidates[0])
                    if getattr(self, 'current_part', None) in roman_order and raw_part in roman_order:
                        curr_idx = roman_order.index(self.current_part)
                        sec_idx = roman_order.index(raw_part)
                        if sec_idx <= curr_idx and self.last_question_no >= 6:
                            if getattr(self, 'section_start_question_no', -1) != self.last_question_no:
                                raw_part = roman_order[min(curr_idx + 1, len(roman_order) - 1)]
                    self.current_part = raw_part
                    sec_name = raw_part
                elif sec_match:
                    raw_sec = sec_match.group(1).upper()
                    hindi_to_eng = {'क': 'A', 'ख': 'B', 'ग': 'C', 'ঘ': 'D', 'ङ': 'E'}
                    raw_sec = hindi_to_eng.get(raw_sec, raw_sec)
                    if getattr(self, 'current_part', None):
                        sec_name = f"{self.current_part}_{raw_sec}"
                    else:
                        sec_name = raw_sec
                elif generic_match:
                    sec_name = generic_match.group(1).upper().replace('L', 'I').replace('1', 'I')
                    hindi_to_eng = {'क': 'A', 'ख': 'B', 'ग': 'C', 'ঘ': 'D', 'ङ': 'E'}
                    sec_name = hindi_to_eng.get(sec_name, sec_name)
                    roman_order = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
                    if self.current_section in roman_order and sec_name in roman_order:
                        curr_idx = roman_order.index(self.current_section)
                        sec_idx = roman_order.index(sec_name)
                        if sec_idx <= curr_idx and self.last_question_no >= 6:
                            if getattr(self, 'section_start_question_no', -1) != self.last_question_no:
                                sec_name = roman_order[min(curr_idx + 1, len(roman_order) - 1)]

                if sec_name:
                    # Prevent front-page header artifacts: if on top 15 lines before any questions begin, lone PART-II/B is a booklet series token, not the exam section
                    if i < 15 and sec_name not in ('I', 'A', '1') and not self.questions and self.last_question_no == 0:
                        if not any(k in line_low for k in ['answer', 'choose', 'fill', 'question', 'mark', 'compulsory', 'விடையளி', 'மதிப்பெண்']):
                            i += 1
                            continue
                    if self.current_section != sec_name:
                        self.section_start_question_no = self.last_question_no
                    self.current_section = sec_name
                    if not self.questions:
                        self.last_question_no = 0
                        self.global_counter = 0

                self_mult = self._extract_multiplier_marks(line, self.board)
                lah_marks = None
                if self_mult is None:
                    for j in range(1, 6):
                        if i + j < len(cleaned_lines):
                            lah_marks = self._extract_multiplier_marks(cleaned_lines[i + j], self.board)
                            if lah_marks is not None:
                                break

                if self_mult is not None:
                    active_marks = self_mult
                    self.marks_from_multiplier = True
                elif lah_marks is not None:
                    active_marks = lah_marks
                    self.marks_from_multiplier = True
                elif self.current_section and self.current_section in self.prescan_marks:
                    active_marks = self.prescan_marks[self.current_section]
                    self.marks_from_multiplier = False
                elif getattr(self, 'current_part', None) and self.current_part in self.prescan_marks:
                    active_marks = self.prescan_marks[self.current_part]
                    self.marks_from_multiplier = False
                elif self.current_section and self.current_section in self.section_marks:
                    active_marks = self.section_marks[self.current_section]
                    self.marks_from_multiplier = False
                else:
                    sec_default = self._get_default_marks_for_section(self.current_section, getattr(self, 'current_part', None))
                    if sec_default is not None:
                        active_marks = sec_default
                        self.marks_from_multiplier = True

                i += 1
                continue

            # Check for OR separator
            if re.match(r'^[-\s]*OR[-\s]*$', line, re.IGNORECASE) or re.match(r'^\s*OR\s*$', line, re.IGNORECASE) or re.match(r'^\s*அல்லது\s*$', line, re.IGNORECASE):
                if self.current_question_text:
                    self.current_question_text += "\n\n--- OR ---\n\n"
                    self.in_or_block = True
                i += 1
                continue

            # Two-line question header with isolated marks (e.g. line="33", next_line="2", next_next="The above image...")
            if re.match(r'^\s*([1-9]\d*)\s*$', line):
                candidate_q_no = int(line.strip())
                expected_q_no = self.last_question_no + 1
                if ((candidate_q_no == expected_q_no or (candidate_q_no > self.last_question_no and candidate_q_no - self.last_question_no <= 3)) and self.last_question_no > 0) or (self.last_question_no == 0 and candidate_q_no == 1):
                    if next_line and re.match(r'^\s*([1-9]|1\d|20)\s*$', next_line):
                        next_next_line = cleaned_lines[i+2] if i + 2 < len(cleaned_lines) else ""
                        if next_next_line and re.search(r'[A-Za-z\u0B80-\u0BFF]{2,}', next_next_line) and len(next_next_line.strip()) >= 5:
                            self._finalize_current_question()
                            self.last_question_no = candidate_q_no
                            self.global_counter = candidate_q_no
                            self.in_general_instructions = False
                            instructions_line_count = 0
                            if not self.section_started:
                                self.section_started = True
                            self.pending_section_restart = False
                            self.marks_from_multiplier = False
                            explicit_m = int(next_line.strip())
                            range_marks = None
                            range_sec = None
                            if self.cbse_ranges:
                                for r in self.cbse_ranges:
                                    if r['start'] <= candidate_q_no <= r['end']:
                                        range_marks = r['marks']
                                        range_sec = r.get('section')
                                        break
                            if range_sec:
                                self.current_section = range_sec
                            if range_marks is not None:
                                self.current_explicit_marks = [range_marks]
                            elif explicit_m is not None:
                                self.current_explicit_marks = [explicit_m]
                            else:
                                self.current_explicit_marks = [active_marks]
                            self.current_question_text = next_next_line
                            i += 3
                            continue

            # Try to parse question number
            question_info = self._parse_question_line(line, next_line)

            if question_info:
                q_no = question_info['number']
                self.in_general_instructions = False
                instructions_line_count = 0
                if not self.section_started:
                    self.section_started = True
                
                if self.section_started:
                    is_restart = (q_no == 1)
                    is_bilingual_block = (q_no < self.last_question_no and (self.last_question_no - q_no) <= 35 and self.last_question_no > 0)
                    
                    if (q_no >= self.last_question_no and self.last_question_no > 0) or is_restart or is_bilingual_block or (self.last_question_no == 0 and (1 <= q_no <= 5 or self.section_started)):
                        self._finalize_current_question()
                        self.last_question_no = q_no
                        self.global_counter = q_no
                        self.pending_section_restart = False
                        
                        if is_restart:
                            if self.cbse_ranges:
                                pass
                            elif getattr(self, 'marks_from_multiplier', False) and active_marks > 0:
                                pass
                            elif self.current_section and self.current_section in self.prescan_marks:
                                active_marks = self.prescan_marks[self.current_section]
                            elif not self.current_section:
                                first_key = next((k for k in ['A', 'I', '1', 'PART_I', 'SECTION_A', 'SEC_A'] if k in self.prescan_marks), None)
                                if first_key:
                                    active_marks = self.prescan_marks[first_key]
                            if not self.current_section:
                                self.current_section = ""
                            
                        is_lone = not re.sub(r'^\s*(?:Q\.?|Question\s*)?' + str(q_no) + r'(?:\([a-zA-Z]\)|[a-zA-Z](?=[\.\,\)\-\—]))?[\.\,\)\]\-\—\s]*', '', line, flags=re.IGNORECASE).strip()
                        line_marks = question_info.get('marks') or (None if is_lone else self._extract_marks(line))
                        range_marks = None
                        range_sec = None
                        if self.cbse_ranges:
                            for r in self.cbse_ranges:
                                if r['start'] <= q_no <= r['end']:
                                    range_marks = r['marks']
                                    range_sec = r.get('section')
                                    break
                        if range_sec:
                            self.current_section = range_sec
                        if range_marks is not None:
                            self.current_marks = range_marks
                            self.current_explicit_marks = [range_marks]
                        elif line_marks is not None:
                            self.current_marks = line_marks
                            self.current_explicit_marks = [line_marks]
                        else:
                            self.current_explicit_marks = []
                            self.current_marks = active_marks
                        
                        buffer_text = "\n".join(self.pre_question_buffer).strip()
                        self.pre_question_buffer = []
                        if is_lone:
                            self.current_question_text = question_info['text']
                            if buffer_text and q_no > 1:
                                self.current_question_text = buffer_text + "\n" + self.current_question_text
                            self.in_or_block = False
                            i += 2
                            continue
                        else:
                            text_after = self._remove_marks_from_text(question_info['text'])
                            self.current_question_text = text_after
                            if buffer_text and q_no > 1:
                                self.current_question_text = buffer_text + "\n" + self.current_question_text
                            self.in_or_block = False
                            i += 1
                            continue

            # Skip lone numbers that were not parsed as question numbers
            if re.match(r'^\s*\d+\s*$', line):
                if self.current_question_text and not self.in_or_block:
                    m = self._extract_marks(line)
                    if m is None:
                        lone_val = int(line.strip())
                        if 1 <= lone_val <= 5:
                            m = lone_val
                    if m is not None:
                        self.current_explicit_marks.append(m)
                i += 1
                continue

            # Append to current question text
            if self.current_question_text and not self.in_general_instructions:
                if not self.in_or_block:
                    m = self._extract_marks(line)
                    if m is not None:
                        self.current_explicit_marks.append(m)
                        
                def is_tamil(s):
                    return sum(1 for c in s if ord(c) in TAMIL_RANGE) > 2
                
                prev_text = self.current_question_text[-100:]
                sep = " "
                if is_tamil(prev_text) != is_tamil(line) and len(line) > 5:
                    sep = "\n"

                if any(w in self.current_question_text.lower() for w in ['match the following', 'பொருத்துக', 'match the statements']):
                    self.in_match_the_following = True

                sub_match = re.match(r'^\s*[\(]?([ivx]+|[a-d])[\)]\s*(.+)', line, re.IGNORECASE)
                if sub_match:
                    item_label = sub_match.group(1).lower()
                    if self.in_match_the_following:
                        prev_lines = self.current_question_text.strip().split('\n')
                        if len(prev_lines) > 0 and re.search(r'^\s*\([ivx]+\)', prev_lines[-1], re.IGNORECASE) and " - " not in prev_lines[-1]:
                            if item_label in ['a', 'b', 'c', 'd']:
                                self.current_question_text = self.current_question_text.rstrip() + f" - ({item_label}) {sub_match.group(2)}"
                                i += 1
                                continue
                    self.current_question_text += f"\n({item_label}) {sub_match.group(2)}"
                else:
                    self.current_question_text += sep + line
            else:
                if line.strip() and not self.in_general_instructions:
                    self.pre_question_buffer.append(line)

            i += 1

        self._finalize_current_question()
        self._post_process()
        return [q.to_dict() for q in self.questions]

    # ── Character-level shape confusion table for OCR ──────────────────
    # Maps characters to the set of digits they are commonly misread as.
    # This is bidirectional: if '3' can be misread as '8', then '8' can
    # also be misread as '3'. Built from empirical Tesseract/PaddleOCR data.
    _OCR_SHAPE_MAP: Dict[str, str] = {
        '0': '0OoDQ',  '1': '1IilL|!',  '2': '2Zz',   '3': '3B8',
        '4': '4Aa',    '5': '5Ss$',     '6': '6Gb',    '7': '7Tl',
        '8': '8B3',    '9': '9gq',
        'O': '0',  'o': '0',  'D': '0',  'Q': '0',
        'I': '1',  'i': '1',  'l': '17', 'L': '1',   '|': '1',  '!': '1',
        'Z': '2',  'z': '2',
        'B': '38', 'b': '6',
        'A': '4',  'a': '4',
        'S': '5',  's': '5',  '$': '5',
        'G': '6',
        'T': '7',
        'g': '9',  'q': '9',
        'W': '',   'Y': '',   'w': '',  'y': '',   # no digit mapping
    }

    def _ocr_heal_question_number(self, line: str) -> str:
        """Generic OCR sequence healer for garbled question numbers.

        Instead of hardcoding specific OCR errors (e.g., '384' → 13, 'WSY' → 15),
        this method dynamically detects when a leading token on a line could be a
        misread of the expected next question number and rewrites it.

        Algorithm:
          1. Extract the leading token (alphanumeric blob before first whitespace/punct).
          2. If last_question_no == 0 (no questions seen yet), skip healing.
          3. For expected_q = last_question_no + 1 (and +2 for gap tolerance):
             a. Convert expected_q to its digit string.
             b. If the leading token already IS that number, no healing needed.
             c. If the leading token can be mapped to expected_q via shape confusion
                (character-by-character replacement), rewrite the token.
          4. Only rewrite when the rest of the line looks like question content
             (has alphabetic characters — prevents rewriting page numbers or formulas).
        """
        if self.last_question_no <= 0:
            return line

        # Extract leading token: everything up to first space or question-punctuation
        m_lead = re.match(r'^(\s*)([^\s\.\,\)\:\-\–\—\•\·\*\~%]+)([\.\,\)\:\-\–\—\•\·\*\~%]?\s*)(.*)', line, re.DOTALL)
        if not m_lead:
            return line

        prefix_ws = m_lead.group(1)
        token = m_lead.group(2)
        punct_sep = m_lead.group(3)
        rest = m_lead.group(4)

        # Token must be short (question numbers are 1-3 digits, OCR garble adds ≤2 chars)
        if len(token) > 5 or len(token) < 1:
            return line

        # Rest of line must contain alphabetic content (not just numbers/math)
        combined_rest = (punct_sep + rest).strip()
        if not combined_rest or not re.search(r'[A-Za-z\u0B80-\u0BFF\u0900-\u097F]', combined_rest):
            return line

        # Try expected_q and expected_q+1 (for gap tolerance)
        for expected_q in [self.last_question_no + 1, self.last_question_no + 2]:
            if expected_q > 150:
                continue
            expected_str = str(expected_q)

            # Already correct? No healing needed.
            if token == expected_str:
                return line

            # Can we map token -> expected_str via shape confusion?
            if len(token) != len(expected_str):
                # Length mismatch: try substring match for common OCR stutter
                # e.g., '384' (3 chars) for '13' (2 chars) — only if first char
                # is a noise char and last N chars can match.
                if len(token) > len(expected_str):
                    # Check if trimming leading noise char(s) produces a match
                    trim_count = len(token) - len(expected_str)
                    sub_token = token[trim_count:]
                    if self._ocr_chars_match(sub_token, expected_str):
                        # Verify the trimmed prefix chars are plausible OCR noise
                        noise_prefix = token[:trim_count]
                        if all(not c.isdigit() or c in '0' for c in noise_prefix) or \
                           self._ocr_chars_match(noise_prefix + sub_token[0], expected_str[0] * (trim_count + 1)):
                            new_line = f"{prefix_ws}{expected_q}) {combined_rest}"
                            return new_line
                continue

            # Same length: character-by-character shape match
            if self._ocr_chars_match(token, expected_str):
                # Preserve original punctuation if present
                if punct_sep.strip():
                    new_line = f"{prefix_ws}{expected_q}{punct_sep}{rest}"
                else:
                    new_line = f"{prefix_ws}{expected_q}) {combined_rest}"
                return new_line

        return line

    def _ocr_chars_match(self, token: str, target: str) -> bool:
        """Check if every character in `token` can be a shape-confusion misread of
        the corresponding character in `target` (same-length strings only)."""
        if len(token) != len(target):
            return False
        for tc, ec in zip(token, target):
            if tc == ec:
                continue
            # Check if tc could be a misread OF ec
            possible_misreads = self._OCR_SHAPE_MAP.get(ec, '')
            if tc in possible_misreads:
                continue
            # Check reverse: ec could be what tc was misread from
            reverse_misreads = self._OCR_SHAPE_MAP.get(tc, '')
            if ec in reverse_misreads:
                continue
            return False
        return True

    def _parse_question_line(self, line: str, next_line: str = "") -> Optional[Dict]:
        def has_indic(s):
            return any(ord(c) in range(0x0900, 0x097F) or ord(c) in range(0x0B80, 0x0BFF) for c in s)

        def _is_sequential(q_no):
            if getattr(self, 'in_match_the_following', False) and q_no < self.last_question_no:
                return False
            if self.last_question_no == 0:
                return 1 <= q_no <= 5 or getattr(self, 'section_started', False)
            max_gap = 10
            
            # Restart after section
            if self.pending_section_restart and q_no == 1:
                return True
                
            common_words = {
                'the', 'of', 'and', 'to', 'a', 'in', 'is', 'that', 'for', 'on', 'with', 
                'as', 'by', 'at', 'an', 'be', 'this', 'are', 'from', 'it', 'if', 'or', 
                'which', 'value', 'find', 'show', 'given', 'figure', 'determine', 'calculate',
                'what', 'why', 'how', 'state', 'explain', 'following', 'marks', 'between',
                'let', 'assertion', 'reason', 'two', 'all', 'correct', 'relation', 'when'
            }

            # Same question number (immediate bilingual translation)
            if q_no == self.last_question_no:
                prev_text = self.current_question_text or (self.questions[-1].question if self.questions else "")
                if prev_text:
                    if has_indic(prev_text) != has_indic(line):
                        return True
                    cand_words = set(re.findall(r'\b[a-zA-Z]{2,}\b', (line + " " + next_line).lower()))
                    cand_score = len(cand_words & common_words)
                    prev_words = set(re.findall(r'\b[a-zA-Z]{2,}\b', prev_text.lower()))
                    prev_score = len(prev_words & common_words)
                    if cand_score >= 2 and (cand_score > prev_score or prev_score <= 1):
                        return True
                    ocr_lang = getattr(self, 'ocr_lang', '')
                    if ocr_lang in ('eng+hin', 'eng+tam') or self.board in ('CBSE', 'Samacheer'):
                        return True
                return False
                
            # Allow small backward jump (gap <= 2) for previously unseen questions (e.g. Q12 followed by Q11, or Q32 followed by Q31)
            if 0 < (self.last_question_no - q_no) <= 2:
                existing_nos = {q.question_no for q in self.questions}
                if q_no not in existing_nos:
                    return True

            # Backward jump in bilingual papers: script transition (Indic <-> English) or English quality transition (garbled OCR vs proper English)
            if q_no < self.last_question_no:
                if not getattr(self, 'is_bilingual_paper', False):
                    return False
                if (self.last_question_no - q_no) <= 35:
                    existing_q = next((q for q in self.questions if q.question_no == q_no), None)
                    current_is_indic = has_indic(self.current_question_text) or (existing_q and has_indic(existing_q.question)) or (self.questions and has_indic(self.questions[-1].question))
                    candidate_is_indic = has_indic(line)
                    line_words = re.findall(r'\b[a-zA-Z\u0B80-\u0BFF\u0900-\u097F]{2,}\b', line + " " + next_line)
                    if len(line_words) >= 3:
                        if current_is_indic != candidate_is_indic:
                            return True
                        cand_score = len(set(w.lower() for w in line_words) & common_words)
                        prev_text = self.current_question_text or (existing_q.question if existing_q else (self.questions[-1].question if self.questions else ""))
                        prev_words = set(re.findall(r'\b[a-zA-Z]{2,}\b', prev_text.lower()))
                        prev_score = len(prev_words & common_words)
                        if cand_score >= 2 and (cand_score > prev_score or prev_score <= 1):
                            return True
                return False
                
            # Forward sequence
            if q_no >= self.last_question_no:
                if (q_no - self.last_question_no) <= max_gap:
                    return True
                if hasattr(self, 'global_counter') and q_no >= self.global_counter and (q_no - self.global_counter) <= max_gap:
                    return True
                return False
            return False

        line = line.strip()
        if re.match(r'^\s*\(\s*\d+\s*\)\s*$', line):
            return None

        line = re.sub(r'^\[\s*\]\s*', '', line)
        line = re.sub(r'^[\|\¦\│\┃\║\:\s]+(?=\d+[\.\,\)\:\-\–—\•\·\*\~%])', '', line)

        # Reject date strings (e.g. 21-04-25, 21/04/2025, 01.05.2024)
        if re.match(r'^\s*\d{1,2}[-\/\.]\d{1,2}[-\/\.]\d{2,4}\s*$', line):
            return None

        # Reject decimal numbers at line start (e.g. 1.4, 2.013553, 9.8, 3.14)
        if re.match(r'^\s*[1-9]\d*\.\d+', line):
            return None

        # Reject compound hyphenated words (e.g. 3-chambered, 4-carbon, 2-fold)
        if re.match(r'^\s*[1-9]\d*-[a-zA-Z]', line):
            return None

        # Reject unpunctuated formula / trigonometric coefficients (e.g. "2 (cos (tan-1 1))", "3 sin x")
        if re.match(r'^\s*[1-9]\d*\s+[\(\[\{]?(?:cos|sin|tan|sec|csc|cot|log|ln|lim|det)\b', line, re.IGNORECASE):
            return None

        # Reject unclosed parenthesis continuation (e.g. math expr: "(\n 3 +\n 5) is an irrational")
        if self.current_question_text:
            open_parens = self.current_question_text.count('(') - self.current_question_text.count(')')
            if open_parens > 0 and re.match(r'^\s*\d+\)', line):
                return None

        # Reject numbered section labels like "3. Section A - Questions..." or "Section B"
        if re.search(r'^\s*(?:\d+[\.\)]\s*)?(?:Section|Part|பகுதி|பாகம்|பிரிவு)\s*[-–\:\s]*[A-ZIVX\d]+\b', line, re.IGNORECASE) and not re.search(r'\b(?:what|why|how|which|prove|calculate|determine|explain|state|find|derive|draw)\b', line, re.IGNORECASE):
            return None

        # Reject instruction lines describing question ranges or general instructions
        if re.search(r'\bquestions?\s+(?:no\.?|nos?\.?|numbers?)?\s*\d+\s*(?:to|[-–—]|and)\s*\d+\b', line, re.IGNORECASE):
            return None
        if re.search(r'\b(?:all\s+questions\s+are\s+compulsory|neat\s+and\s+properly\s+labeled\s+diagrams|time\s+allowed|maximum\s+marks|candidates?\s+will\s+read)\b', line, re.IGNORECASE):
            return None
        if re.search(r'\b(?:short-answer|long-answer|very\s+short-answer)\s+(?:\([A-Z]+\)\s+)?type\b', line, re.IGNORECASE):
            return None

        clean_l = re.sub(r'[\u200b-\u200f\ufeff]', '', line)
        # Reject numbered section instructions / notes like "1. Answer any...", "1. ஏதேனும்...", "2. வினா எண்..."
        if re.search(r'^\s*\d+[\.\)]\s*(?:(?:Answer|Note|All\s+questions)\b|(?:ஏதேனும்|எவையேனும்|வினா|வினாக்களுக்கு|குறிப்பு)|.*?(?:கட்டாய\s*வினா|compulsory))', clean_l, re.IGNORECASE):
            return None

        # Reject MCQ option line misread with leading digit like "8) 8 ட) 5 c) 6 d)7" (pure options, no sentence)
        if re.search(r'^\s*[8\d][\.\)]\s+[^\w\s]*\w{0,8}\s+(?:[b-dB-D]|ட|[ஆஇஈ])[\)\].]', clean_l):
            return None

        # Generic OCR sequence healer: auto-correct garbled leading tokens
        # when they resemble the expected next question number.
        # Uses a character-level shape-confusion table (OCR commonly swaps
        # visually-similar glyphs) and edit-distance scoring.
        line = self._ocr_heal_question_number(line)

        # Reject unpunctuated numbers with digits/math operators/fractions (e.g. "6 36", "4 2", "1 11", "3 +", "2 &")
        m_unp = re.match(r'^\s*(\d+)\s+(.*)', line)
        if m_unp and not re.match(r'^\s*\d+[\.\,\)\:\-\–—\•\·\*\~%]', line):
            after_unp = m_unp.group(2).strip()
            if not after_unp or re.match(r'^[\d\+\-\*\/\=\<\>\&\^\%\(\)\[\]]', after_unp):
                return None
            words_unp = re.findall(r'[a-zA-Z\u0900-\u097F\u0B80-\u0BFF]{2,}', after_unp)
            if len(words_unp) < 2:
                return None

        # Check word-preceded colon question headers (e.g. "7 sep :" or "7 Assertion :")
        m_colon = re.match(r'^\s*(\d+)\s+([a-zA-Z\u0900-\u097F\u0B80-\u0BFF]{2,10})\s*[:\.]\s*(.*)', line)
        if m_colon and not re.match(r'^\s*\d+[\.\,\)\:\-\–—\•\·\*\~%]', line):
            q_cand = int(m_colon.group(1))
            if q_cand == self.last_question_no + 1:
                return {'number': q_cand, 'text': line[m_colon.start(2):]}
        
        # 1. Punctuation-delimited anchored at line start
        for pattern in QUESTION_NUMBER_PATTERNS:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                try:
                    q_no = int(match.group(1))
                except ValueError:
                    continue
                text_after = re.sub(pattern, '', line).strip()
                has_punct = bool(re.search(r'[\.\,\)\:\-\–—\•\·\*\~%]', match.group(0)))

                # A bare unpunctuated number on a line with no text_after is a PAGE NUMBER or MARK, not a question!
                if not has_punct and not text_after:
                    continue

                # An unpunctuated number must not start with a lowercase letter (e.g. "4 times...", "5 is an...")
                if not has_punct and text_after and re.match(r'^[a-z]', text_after):
                    continue

                # Any candidate with text_after on the same line MUST contain actual alphabetic characters
                if text_after and not re.search(r'[A-Za-z\u0B80-\u0BFF\u0900-\u097F]', text_after):
                    continue

                # Reject decimal numbers (like 3.00 Hours) or header time/marks units
                if text_after and (re.match(r'^\.\d+', text_after) or re.search(r'\b(?:hours?|hrs?|minutes?|mins?|மணி|wanfl|மதிப்பெண்கள்?|maximum\s*marks?)\b', text_after, re.IGNORECASE)):
                    if re.search(r'\b(?:time\s*allowed|exam\s*time|time\s*[:\-–]|நேரம்\s*[:\-–]|maximum\s*marks?|max\.?\s*marks?)\b', line, re.IGNORECASE):
                        continue
                # Reject wrapped conjunctions or physical measurement units without question punctuation
                if not has_punct and text_after and re.match(r'^(?:and|or|of|to|g|gm|mg|kg|mol|ml|l|mm|cm|m|km|s|sec|min|hr|v|w|hz|pa|kpa|atm|bar|j|kj|cal|kcal|%|ppm)\b', text_after, re.IGNORECASE):
                    continue
                if has_punct and text_after and re.match(r'^(?:and|or|of)\s+', text_after):
                    continue
                if q_no <= 150 and _is_sequential(q_no):
                    if not text_after and next_line:
                        if not has_punct:
                            continue
                        nl_strip = next_line.strip()
                        if self._parse_question_line(nl_strip):
                            continue
                        return {'number': q_no, 'text': next_line}
                    return {'number': q_no, 'text': text_after}

        # 2. Space-delimited: "7 The work..."
        space_match = re.match(r'^\s*([1-9]\d*)\s+(?=[A-Z])(.*)', line)
        if space_match:
            try:
                q_no = int(space_match.group(1))
            except ValueError:
                q_no = None
            text_after_space = space_match.group(2).strip()
            if q_no and q_no <= 150 and _is_sequential(q_no) and len(text_after_space) >= 10:
                return {'number': q_no, 'text': space_match.group(2)}

        # 3. Lone number on line
        lone_match = re.match(r'^\s*(?:Q\.?|Question\s*)?([1-9]\d*)([\.\,\)\:\-]?)\s*$', line)
        if lone_match and next_line:
            next_line_strip = next_line.strip()
            # Next line cannot be a structural section header or ignored text
            if self.preprocessor.is_section_header(next_line_strip):
                if re.search(r'\b(?:SECTION|Section|PART|Part|பகுதி|பாகம்|பிரிவு|खण्ड|भाग)\b', next_line_strip, re.IGNORECASE) or re.match(r'^\s*([IVX]{1,6})\s*[\.\-–\—\:]\s*$', next_line_strip):
                    return None
            if self.preprocessor.is_ignored(next_line_strip):
                return None

            has_punct = bool(lone_match.group(2))
            if self._parse_question_line(next_line_strip):
                return None
            
            try:
                q_no = int(lone_match.group(1))
            except ValueError:
                q_no = None

            if not has_punct:
                if self.last_question_no == 0 and q_no != 1:
                    return None  # Unpunctuated bare numbers > 1 (e.g. page numbers "2", bullet "2") cannot be the first question
                # Table/data number rejection: an unpunctuated number must strictly be sequential
                if q_no and self.last_question_no > 0 and q_no != self.last_question_no + 1:
                    return None
                strict_opt = r'^\s*(?:[\(\[][A-Da-d][\]\)]|[A-Da-d][\.\)\-\—\:]|\([அஆஇஈकखगঘ]\)|[அஆஇஈकखगঘ][\.\)\-\—\:])\s'
                if re.match(strict_opt, next_line_strip):
                    return None
                if re.match(r'^\s*\([a-zA-Z0-9ivxIVX\u0B80-\u0BFF\u0900-\u097F]+\)', next_line_strip) or re.match(r'^\s*\[[a-zA-Z0-9ivxIVX\u0B80-\u0BFF\u0900-\u097F]+\]', next_line_strip):
                    return None
                    
            if len(next_line_strip) >= 1 and not re.match(r'^\s*\d+\s*$', next_line_strip):
                if re.match(r'^\s*[\w\(\[\{\\\$\-\+√π∆∇∑∫∏±×÷≈≠≤≥\u0370-\u03FF\u2200-\u22FF\u2018-\u201F"\'_]', next_line_strip):
                    if q_no and q_no <= 150:
                        if not has_punct and not getattr(self, 'section_started', False) and self.last_question_no == 0 and q_no != 1:
                            pass
                        elif not has_punct and (q_no < self.last_question_no):
                            if getattr(self, 'pending_section_restart', False) and q_no == 1:
                                return {'number': q_no, 'text': next_line}
                            pass
                        elif _is_sequential(q_no):
                            return {'number': q_no, 'text': next_line}

        # 4. Number followed by marks in multi-column layout: "33 2"
        columnar_lone_match = re.match(r'^\s*([1-9]\d*)\s+(\d+)\s*$', line)
        if columnar_lone_match and next_line:
            try:
                q_no = int(columnar_lone_match.group(1))
                marks = int(columnar_lone_match.group(2))
            except ValueError:
                q_no = None
            if q_no and q_no <= 150:
                if q_no < self.last_question_no or self.last_question_no == 0:
                    pass
                elif _is_sequential(q_no):
                    nl_strip = next_line.strip()
                    if not self._parse_question_line(nl_strip):
                        return {'number': q_no, 'text': next_line, 'marks': marks}

        return None

    def _extract_marks(self, text: str) -> Optional[int]:
        text_clean = text.strip()
        # 1a. Addition formula pattern: 1+1=2, 2+2+1=5, 3+2=5
        # Operands and totals must strictly be positive integers >= 1 (never 0 or negative terms!)
        add_formula_match = re.search(r'(?<![\w\-])(?:\b[1-9]\d*\s*\+\s*)+\b[1-9]\d*\s*[=\-–—]\s*([1-9]\d*)(?!\w)', text_clean)
        if add_formula_match:
            val = int(add_formula_match.group(1))
            if 1 <= val <= 25:
                return val

        # 1b. Multiplication pattern embedded in text: e.g. "2x8=16", "10x2=20", "14x1=14", "7x4=28"
        # N x M = T is a multiplier (N questions x M marks = T total).
        # The single question mark is M, NEVER the section total T!
        mult_formula_match = re.search(r'(?<![\w\-])\b([1-9]\d*)\s*[\u00d7xX\*]\s*([1-9]\d*)\s*[=\-–—]\s*([1-9]\d*)(?!\w)', text_clean)
        if mult_formula_match:
            n_qs = int(mult_formula_match.group(1))
            m_val = int(mult_formula_match.group(2))
            total = int(mult_formula_match.group(3))
            if 1 <= n_qs <= 45 and 1 <= m_val <= 15 and (n_qs * m_val == total or n_qs == m_val * total):
                return m_val if (m_val <= 10 or m_val < n_qs) else n_qs

        # 2. Formula breakdown: 4 (2+1+1)
        breakdown_match = re.search(r'(?<!\w)(\d+)\s*\(\s*\d+\s*(?:\+\s*\d+)+\s*\)', text_clean)
        if breakdown_match:
            val = int(breakdown_match.group(1))
            if 1 <= val <= 25:
                return val

        # 3. Addition without '=' at end of line: 2+2+1 or 3+2
        add_sum_match = re.search(r'(?<!\w)(\d+)\s*\+\s*(\d+)(?:\s*\+\s*(\d+))?(?:\s*\+\s*(\d+))?\s*$', text_clean)
        if add_sum_match:
            parts = [int(g) for g in add_sum_match.groups() if g is not None]
            total = sum(parts)
            if 1 <= total <= 25:
                return total

        # 4. Standard MARKS_PATTERNS (brackets, paren, trailing)
        for pattern in MARKS_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = int(match.group(1))
                if 1 <= val <= 25:
                    return val

        # 5. Lone digit or small integer line: e.g. "1", "2", "3", "5"
        lone_digit_match = re.match(r'^\s*([1-9]|1\d|20)\s*$', text_clean)
        if lone_digit_match:
            return int(lone_digit_match.group(1))

        return None

    def _remove_marks_from_text(self, text: str) -> str:
        for pattern in MARKS_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        # Also clean subpart formulas: 1+1=2, 2+2+1=5, 3x1=3 (strictly positive operands >= 1)
        text = re.sub(r'(?<![\w\-])(?:\b[1-9]\d*\s*[\+\u00d7xX\*]\s*)+\b[1-9]\d*\s*[=\-–—]\s*[1-9]\d*(?!\w)', '', text)
        text = re.sub(r'(?<![\w\-])\b[1-9]\d*\s*\(\s*[1-9]\d*\s*(?:\+\s*[1-9]\d*)+\s*\)', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def _extract_multiplier_from_line(line: str) -> Optional[int]:
        """Mathematically verifies NxM=T multiplier formulas with OCR resilience."""
        if not line:
            return None
        line_norm = line.replace('\u00d7', 'x').replace('\u2715', 'x').replace('—', '-').replace('–', '-')
        
        # 1. Direct arithmetic match: e.g. 5x5=25, 7x3=21, 10x2=20, 1x8=8
        for m in re.finditer(r'(?<!\w)(\d+)\s*[xX\*]\s*(\d+)\s*[=\-~:sS]\s*(\d+)(?!\w)', line_norm):
            v1, v2, tot = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= v1 <= 40 and 1 <= v2 <= 15 and (v1 * v2 == tot or v1 == tot * v2):
                if (v1 == 1 or v2 == 1) and max(v1, v2) >= 4 and any(k in line_norm.lower() for k in ['one', '1 of', 'ஒன்று', 'ஒரு', 'geometry', 'வரைமுறை']):
                    return max(v1, v2)
                return v2 if (v2 <= 10 or v2 < v1) else v1

        # 2. OCR smudge match: e.g. 41x8=8 where '4' is stray OCR prefix
        for m in re.finditer(r'(?<!\w)(\d{1,2})\s*[xX\*]\s*(\d+)\s*[=\-~:sS]\s*(\d+)(?!\w)', line_norm):
            s1, s2, stot = m.group(1), m.group(2), m.group(3)
            for sub1 in [s1, s1[-1]]:
                v1, v2, tot = int(sub1), int(s2), int(stot)
                if 1 <= v1 <= 40 and 1 <= v2 <= 15 and (v1 * v2 == tot or v1 == tot * v2):
                    if (v1 == 1 or v2 == 1) and max(v1, v2) >= 4 and any(k in line_norm.lower() for k in ['one', '1 of', 'ஒன்று', 'ஒரு', 'geometry', 'வரைமுறை']):
                        return max(v1, v2)
                    return v2 if (v2 <= 10 or v2 < v1) else v1

        # 3. OCR character normalization: e.g. Tx3s21 -> 7x3=21
        trans = str.maketrans('TIl|sSOozZ', '7111550022')
        line_trans = line_norm.translate(trans)
        for m in re.finditer(r'(?<!\w)(\d+)\s*[xX\*]\s*(\d+)\s*[=\-~:5]?\s*(\d+)?(?!\w)', line_trans):
            v1 = int(m.group(1))
            v2 = int(m.group(2))
            tot_str = m.group(3)
            if tot_str:
                tot = int(tot_str)
                if 1 <= v1 <= 40 and 1 <= v2 <= 15 and (v1 * v2 == tot or v1 == tot * v2):
                    if (v1 == 1 or v2 == 1) and max(v1, v2) >= 4 and any(k in line_norm.lower() for k in ['one', '1 of', 'ஒன்று', 'ஒரு', 'geometry', 'வரைமுறை']):
                        return max(v1, v2)
                    return v2 if (v2 <= 10 or v2 < v1) else v1
            elif 1 <= v1 <= 40 and 1 <= v2 <= 15 and any(k in line.lower() for k in ['answer any', 'வினா', 'questions']):
                return v2 if (v2 <= 10 or v2 < v1) else v1

        return None

    def _get_default_marks_for_section(self, sec: str, part: str = "") -> Optional[int]:
        """Resolves section marks DYNAMICALLY from document-extracted evidence only.
        
        Priority order:
          1. prescan_marks  (multiplier formulas parsed from the document)
          2. section_marks  (from section description clauses / range instructions)
          3. instruction_ranges  (question-number range ↔ marks from document header)
        
        No hardcoded board/section → marks mappings. Production papers can have
        arbitrary section names, fonts, and mark schemes.
        """
        clean_sec = (sec or "").upper().strip()
        clean_part = (part or "").upper().strip()
        candidates = [clean_sec, clean_part]
        # Also try stripping common "SECTION_" prefix
        for s in [clean_sec, clean_part]:
            if s.startswith("SECTION_") and len(s) > 8:
                candidates.append(s[8:])

        # 1. prescan_marks (populated from multiplier formulas in document)
        for s in candidates:
            if s and s in getattr(self, 'prescan_marks', {}):
                return self.prescan_marks[s]

        # 2. section_marks (populated from section description clauses)
        for s in candidates:
            if s and s in getattr(self, 'section_marks', {}):
                return self.section_marks[s]

        # 3. instruction_ranges (question-number ranges from document header)
        if hasattr(self, 'instruction_ranges') and self.instruction_ranges:
            gc = getattr(self, 'global_counter', 0)
            for r in self.instruction_ranges:
                if r.get('start', 0) <= gc <= r.get('end', 0):
                    m = r.get('marks')
                    if m and 1 <= m <= 20:
                        return m
                # Also match by section name in the range
                r_sec = (r.get('section') or "").upper().strip()
                if r_sec and r_sec in candidates:
                    m = r.get('marks')
                    if m and 1 <= m <= 20:
                        return m

        return None

    def _extract_multiplier_marks(self, line: str, board: str = "") -> Optional[int]:
        has_q_num = False
        for pat in QUESTION_NUMBER_PATTERNS:
            if re.match(pat, line):
                has_q_num = True
                break
        if has_q_num and not self.preprocessor.is_section_header(line):
            return None

        line_norm = line.replace('\u00d7', 'x').replace('\u2715', 'x')

        # If inside an active question text and line is not a section header:
        # Allow standalone multipliers OR embedded multiplier formulas N x M = T
        if self.current_question_text and not self.preprocessor.is_section_header(line):
            is_pure_mult = bool(re.match(r'^\s*[\[\(]?\s*\d+\s*[xX\*]\s*\d+\s*[=\-–—~:sS]\s*\d+\s*[\]\)]?\s*$', line_norm))
            has_embedded_mult = bool(re.search(r'(?<![\w\-])(\d+)\s*[xX\*]\s*(\d+)\s*[=\-–—~:sS]\s*(\d+)(?!\w)', line_norm))
            if not is_pure_mult and not has_embedded_mult:
                return None

        # Robust arithmetic multiplier match
        mult_val = self._extract_multiplier_from_line(line_norm)
        if mult_val is not None:
            return mult_val

        line_lower = line.lower()
        is_instruction = any(k in line_lower for k in [
            'answer any', 'compulsory', 'questions', 'marks', 'மதிப்பெண்', 'வினாக்களுக்கு', 'விடையளிக்கவும்',
            'carry', 'carrying', 'carries', 'each', 'எவையேனும்', 'அனைத்து', 'geometry', 'வரைமுறை'
        ])
        if is_instruction:
            m = re.search(r'\b(?:carry|carrying|carries|of|each|ஒவ்வொரு)\s*(?:.{0,30}?)\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:marks?|மதிப்பெண்)', line, re.IGNORECASE)
            if m:
                val = parse_num_token(m.group(1))
                if val and 1 <= val <= 20:
                    return val
            m2 = re.search(r'\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:marks?|மதிப்பெண்கள்?)\s*(?:each|வீதம்)', line, re.IGNORECASE)
            if m2:
                val = parse_num_token(m2.group(1))
                if val and 1 <= val <= 20:
                    return val
            m3 = re.search(r'प्रत्येक\s+प्रश्न\s*(\d+|एक|दो|तीन|चार|पांच)\s*अंक', line)
            if m3:
                val = parse_num_token(m3.group(1))
                if val and 1 <= val <= 20:
                    return val
            geom_m = re.search(r'\b(?:practical\s+geometry|geometry|வரைமுறை)\b.*?(?:[\[\(]?\s*(\d+)\s*(?:marks?|மதிப்பெண்)[\]\)]?)?', line, re.IGNORECASE)
            if geom_m and geom_m.group(1):
                val = int(geom_m.group(1))
                if 1 <= val <= 10:
                    return val
        return None

    def _finalize_current_question(self):
        if not self.current_question_text:
            return
        clean_text = self._clean_question_text(self.current_question_text)
        if clean_text and len(clean_text) > 3:
            final_marks = self.current_marks
            final_section = getattr(self, 'current_part', None) or self.current_section or ""

            range_match = None
            if hasattr(self, 'cbse_ranges') and self.cbse_ranges:
                for r in self.cbse_ranges:
                    if r['start'] <= self.global_counter <= r['end']:
                        range_match = r
                        break

            # Check if genuine MCQ (uppercase, lowercase, Tamil, or Hindi options)
            opt_indicators = set()
            for opt_char in ['a', 'b', 'c', 'd']:
                if re.search(r'(?:^|[\s\n])[\(\[]?' + opt_char + r'[\)\].]\s+', clean_text, re.IGNORECASE):
                    opt_indicators.add(opt_char.lower())
            for opt_char in ['அ', 'ஆ', 'இ', 'ஈ', '௮']:
                if re.search(r'(?:^|[\s\n])[\(\[]?' + opt_char + r'[\)\].]\s+', clean_text):
                    opt_indicators.add(opt_char)
            for opt_char in ['क', 'ख', 'ग', 'घ']:
                if re.search(r'(?:^|[\s\n])[\(\[]?' + opt_char + r'[\)\].]\s+', clean_text):
                    opt_indicators.add(opt_char)

            is_genuine_mcq = (len(opt_indicators) >= 3)
            if is_genuine_mcq:
                if any(w in clean_text.lower() for w in ['passage', 'case study', 'read the following', 'पररच्छेद', 'observation table']) or (final_section in ('E', 'V') and self.board == 'CBSE'):
                    is_genuine_mcq = False

            # Priority 1: Range match from document instructions (e.g. Q1-Q16: 1 mark, Q17-Q21: 2 marks)
            if range_match:
                if range_match.get('marks') is not None:
                    final_marks = range_match['marks']
                if range_match.get('section'):
                    final_section = range_match['section']

            # Priority 1b: Assertion-Reason questions are 1 mark in Section A / objective, but preserve section mark in Section B/C
            elif bool(re.search(r'\bAssertion\s*\(?A\)?', clean_text, re.IGNORECASE)):
                if self.current_marks <= 1 or final_section in ('A', 'I', '1') or not final_section:
                    final_marks = 1
                else:
                    final_marks = self.current_marks

            # Priority 2: Explicit marks found directly on this question / subparts
            elif hasattr(self, 'current_explicit_marks') and self.current_explicit_marks:
                max_allowed = 6 if getattr(self, 'is_higher_sec', False) else 5 if self.board == 'CBSE' else 8
                
                exp_marks = list(self.current_explicit_marks)
                # If question has options (MCQ), it should NEVER take a standalone digit like 8 or 16 as its question mark!
                if is_genuine_mcq:
                    exp_marks = [m for m in exp_marks if m not in (8, 16) and m in (1, 2) and (m == self.current_marks or not self.current_marks)]
                    if not exp_marks and getattr(self, 'marks_from_multiplier', False) and self.current_marks > 0:
                        final_marks = self.current_marks
                        exp_marks = [self.current_marks]

                # In sections governed by multipliers (e.g. 14x1=14, 10x2=20, 10x5=50, 2x8=16),
                # a lone stray digit from math expressions or options must not override the section multiplier
                if getattr(self, 'marks_from_multiplier', False) and self.current_marks > 0:
                    if len(exp_marks) == 1 and exp_marks[0] != self.current_marks:
                        exp_marks = [self.current_marks]
                        final_marks = self.current_marks

                # Filter out table row numbering / subpart option indices: e.g. [1, 2, 3, 4, 5, 6]
                if len(exp_marks) >= 4 and exp_marks[:4] == [1, 2, 3, 4]:
                    exp_marks = [m for m in exp_marks if m not in [1, 2, 3, 4, 5, 6]]
                    # Do NOT force exp_marks = [4]! If empty, let it fall back naturally to current section marks.

                # Check for bilingual duplication: e.g. [1, 1, 2, 1, 1, 2]
                n = len(exp_marks)
                if n >= 4 and n % 2 == 0 and exp_marks[:n//2] == exp_marks[n//2:]:
                    exp_marks = exp_marks[:n//2]
                
                # Check for internal choice duplicate: e.g. [1, 1, 2, 2] where two 2s are OR choices
                if len(exp_marks) >= 3 and exp_marks[-1] == exp_marks[-2] and sum(exp_marks[:-1]) <= max_allowed:
                    exp_marks = exp_marks[:-1]

                subpart_sum = sum(exp_marks)
                if len(exp_marks) > 1 and 1 <= subpart_sum <= max_allowed:
                    final_marks = subpart_sum
                elif 1 <= subpart_sum <= max_allowed:
                    final_marks = subpart_sum
                # Removed: hardcoded 'passage/case study = 4 marks' override.
                # Marks for passage/case-study questions are now resolved purely
                # from document-extracted evidence (explicit marks, multipliers,
                # section ranges). This avoids incorrect mark assignment on
                # non-CBSE or custom papers where such questions carry different marks.
                else:
                    valid_explicit = [m for m in exp_marks if 1 <= m <= max_allowed]
                    if valid_explicit:
                        counts = Counter(valid_explicit)
                        max_count = max(counts.values())
                        final_marks = next(m for m in reversed(valid_explicit) if counts[m] == max_count)
                    else:
                        final_marks = self.current_marks or 1

            # Priority 3: Active multiplier marks explicitly resolved for this question
            elif getattr(self, 'marks_from_multiplier', False) and self.current_marks > 0:
                final_marks = self.current_marks

            # Priority 4: Prescan marks for current section or master part
            elif self.current_section and self.current_section in self.prescan_marks:
                final_marks = self.prescan_marks[self.current_section]
            elif getattr(self, 'current_part', None) and self.current_part in self.prescan_marks:
                final_marks = self.prescan_marks[self.current_part]

            # Priority 5: Section marks for current section
            elif self.current_section and self.current_section in self.section_marks:
                final_marks = self.section_marks[self.current_section]

            # Removed: hardcoded 'CBSE Section A = 1 mark' and 'Section IV geometry = 5 marks' overrides.
            # Marks are now resolved entirely from document-extracted evidence (prescan_marks,
            # section_marks, instruction_ranges, multiplier formulas, and explicit marks).
            # This avoids incorrect mark assignment on custom/non-standard papers.
            
            # Associate any buffered tables with this question
            associated_tables = list(self.extracted_tables_buffer)
            self.extracted_tables_buffer = []

            # Check for choices_or
            choices = []
            if "--- OR ---" in clean_text:
                choices = [part.strip() for part in clean_text.split("--- OR ---") if part.strip()]

            q = Question(
                question_no=self.global_counter,
                question=clean_text,
                marks=final_marks,
                tables=associated_tables,
                choices_or=choices,
                board=self.board or "Unknown",
                section=final_section
            )
            self.questions.append(q)

        self.current_question_text = ""
        self.in_or_block = False
        self.in_match_the_following = False
        self.current_explicit_marks = []

    def _clean_question_text(self, text: str) -> str:
        text = re.sub(r'\[?\s*Turn over\s*\]?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[?\s*திருப்புக\s*/\s*Turn over\s*\]?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Note\s*:\s*Answer all the questions[^\n]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Note\s*:\s*Answer any[^\n]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Answer all the questions[^\n]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Answer any[^\n]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Question No\.\s*\d+\s*is compulsory', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Draw diagrams wherever necessary', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\d+\s*x\s*\d+\s*=\s*\d+', '', text)
        text = re.sub(r'\(True/False\)', '', text, flags=re.IGNORECASE)

        # Clean stray section instruction headers
        text = re.sub(r'\[?\s*This section comprises[^\]]*?\]\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'This section comprises[^.]*\.?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'All\s+questions\s+are\s+compulsory[^.]*\.?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'(?:internal\s+)?choice\s+has\s+been\s+provided[^.]*\.?\s*', '', text, flags=re.IGNORECASE)

        text = re.sub(r'\*?Please note[^.\n]*\.?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'assessment scheme[^.\n]*\.?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'[\-\s]{6,}For visually impaired.*', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'For visually impaired[^.\n]*\.?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'P\.T\.O\.', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\d+/\d+/\d+[^\n]*', '', text)
        text = re.sub(r'\*+[^\n]+', '', text)

        # Clean diagram coordinate noise leaks (e.g. >~-— = Y = p(x) < x BO A xX i Y')
        text = re.sub(r'[>~—\-\=\s]{3,}[YyXx]\s*=\s*p\(x\)[^:]*?(?=(?:Based\s+on|answer|Find))', '', text, flags=re.IGNORECASE)
        text = re.sub(r'[>~—\-\=]{2,}\s*[YyXx]\s*=[^:]*?(?=(?:Based\s+on|answer|Find))', '', text, flags=re.IGNORECASE)

        # Fix font superscript '?' in polynomials & units: x? -> x², cm? -> cm², m? -> m²
        text = re.sub(r'([a-zA-Z])\?(?=\s*[\+\-\=,\.\)]|\s+\d|\s*$)', r'\1²', text)

        # Fix OCR misrecognition of (i) as (6) or Gi) / Gii)
        text = re.sub(r'\bGi\)', '(i)', text)
        text = re.sub(r'\bGii\)', '(ii)', text)
        text = re.sub(r'\bGiii\)', '(iii)', text)
        text = re.sub(r'\bGiv\)', '(iv)', text)
        text = re.sub(r'(?<=\s)\(6\)(?=\s+[A-Z])', '(i)', text)

        # Tamil/English overlap line breaks
        text = re.sub(r'([\u0B80-\u0BFF\u0900-\u097F][^\n]*?)([a-zA-Z]{3,})', r'\1\n\2', text)
        text = re.sub(r'([a-zA-Z]{3,}[^\n]*?)([\u0B80-\u0BFF\u0900-\u097F])', r'\1\n\2', text)

        # Tamil cleaners
        text = text.replace('றூ', ' × ')
        text = re.sub(r'குறிப்பு\s*:\s*[^\n]*', '', text)
        text = re.sub(r'விடை\s*அளிக்கவும்[^\n]*', '', text)
        text = re.sub(r'விடையளிக்கவும்[^\n]*', '', text)
        text = re.sub(r'தேவையான இடங்களில் படம் வரையவும்[^\n]*', '', text)
        text = re.sub(r'பகுதி\s*-\s*[^\n]*', '', text)
        text = re.sub(r'\[?\s*திருப்புக\s*/\s*\]?', '', text)
        text = re.sub(r'\[\s*/', '', text)
        text = re.sub(r'திருப்புக', '', text)

        text = re.sub(r'[^\S\n]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        
        # Newlines for options: (அ) (ஆ) (இ) (ஈ)
        text = re.sub(r'(?<!\n)\s*\((அ|ஆ|இ|ஈ|உ|ஊ|எ|ஏ)\)\s*', r'\n(\1) ', text)
        # Clean inline/concatenated multiple choice options e.g. "a) 70 cm b) 700cm c) 7cm d) 7000cm"
        text = re.sub(r'(?i)\b[¢©]\)', 'c)', text)
        text = re.sub(r'[_—\-~]\s*([a-d])[\)\.]', r'(\1)', text)
        text = re.sub(r'(?<![a-zA-Z0-9])\(?([A-Da-d])[\)\.\}\]]\s*', r'(\1) ', text)
        text = re.sub(r'([^\s\-\n])\s+(\([A-Da-d]\))', r'\1\n\2', text)
        text = re.sub(r'([\u0B80-\u0BFF][^A-Za-z\u0B80-\u0BFF]*?)\s+(?!\()([A-Z][a-z]+)', r'\1\n\2', text)
        text = re.sub(r'(?<!\n)\s+(\d{1,3}\s*(?:\([a-zA-Zivx]+\))+\.?)\s+', r'\n\1 ', text)
        text = re.sub(r'(?<!\n)\s+\(([ivx]+)\)\s+', r'\n(\1) ', text)

        # Remove standalone multiplier marks e.g. 3x1, 2x1, 5x1, 2x1.5, 3+2
        text = re.sub(r'(?<!\w)\d+\s*[xX*×]\s*\d+(?:\.\d+)?(?!\w)', '', text)
        text = re.sub(r'(?<!\w)\d+\s*\+\s*\d+(?!\w)(?=\s*$|\s*\n)', '', text)

        # Strip trailing section headers that leaked into question text
        text = re.sub(r'(?i)(?<!^)\n\s*(?:[IVXil1|!\u00a6]{1,6}\.?\s*[-–]?\s*)?(?:fill\s+in\s+the\s+blanks?|state\s+true\s+or\s+false|choose\s+the\s+correct\s+answer|match\s+the\s+following)\b.*$', '', text)
        text = re.sub(r'(?i)\n?\s*[\,\.\s]*\d+\s*[xX*s§]\s*\d+\s*=\s*\d+.*$', '', text)
        text = re.sub(r'(?i)\n?\s*Marks?\s*:\s*\d+.*$', '', text)
        text = re.sub(r'(?i)\n?\s*Time\s*:\s*\d+.*$', '', text)

        # Remove Unicode Private Use Area (PUA) glyphs produced by legacy font encodings
        text = re.sub(r'[\uE000-\uF8FF]', '', text)

        return text.rstrip('.').strip()

    def _post_process(self):
        def get_english_score(text):
            common_words = {
                'the', 'of', 'and', 'to', 'a', 'in', 'is', 'that', 'for', 'on', 'with', 
                'as', 'by', 'at', 'an', 'be', 'this', 'are', 'from', 'it', 'if', 'or', 
                'which', 'value', 'find', 'show', 'given', 'figure', 'determine', 'calculate',
                'what', 'why', 'how', 'state', 'explain', 'following', 'marks'
            }
            words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
            return sum(1 for w in words if w in common_words)

        seen = {}
        unique_questions = []
        for q in self.questions:
            if q.question_no not in seen:
                seen[q.question_no] = q
                unique_questions.append(q)
            else:
                existing_q = seen[q.question_no]
                score_new = get_english_score(q.question)
                score_existing = get_english_score(existing_q.question)
                has_indic_existing = bool(re.search(r'[\u0900-\u0D7F]', existing_q.question))
                has_indic_new = bool(re.search(r'[\u0900-\u0D7F]', q.question))

                # Priority 1: Prefer English over Indic script in bilingual exams
                if has_indic_existing and not has_indic_new and len(q.question.strip()) > 10:
                    existing_q.question = q.question
                    existing_q.marks = q.marks
                    if q.section:
                        existing_q.section = q.section
                elif not has_indic_existing and has_indic_new:
                    # Keep existing English version
                    pass
                elif score_new > score_existing:
                    existing_q.question = q.question
                    existing_q.marks = q.marks
                    if q.section:
                        existing_q.section = q.section
                elif score_existing > score_new:
                    pass
                else:
                    if not (not has_indic_existing and has_indic_new):
                        if len(q.question.strip()) > len(existing_q.question.strip()):
                            existing_q.question = q.question
                            existing_q.marks = q.marks
                            if q.section:
                                existing_q.section = q.section
                if q.tables and not existing_q.tables:
                    existing_q.tables = q.tables

        # Apply cbse_ranges directly to unique questions if available
        if hasattr(self, 'cbse_ranges') and self.cbse_ranges:
            for q in unique_questions:
                for r in self.cbse_ranges:
                    if r['start'] <= q.question_no <= r['end']:
                        if r.get('marks') is not None:
                            q.marks = r['marks']
                        if r.get('section'):
                            q.section = r['section']
                        break

        self.questions = sorted(unique_questions, key=lambda q: q.question_no)


# ============================================================
# 7. SELF-HEALING SEQUENCE ENGINE
# ============================================================

class SequenceHealer:
    """Intelligently detects missing question gaps, unifies page splits, and fixes sequence drops."""

    @staticmethod
    def heal_questions(questions: List[Dict], file_path: str = "", board: str = "", raw_text: str = "") -> List[Dict]:
        if not questions:
            return questions

        qnos = [q.get('question_no', 0) for q in questions]
        max_q = max(qnos) if qnos else 0
        expected = set(range(1, max_q + 1))
        missing = expected - set(qnos)

        fallback_board = board or next((q.get('board') for q in questions if q.get('board') and q.get('board') != 'Unknown'), "Unknown")

        if not missing and not any(q.get('question_no', 0) > 150 for q in questions):
            for q in questions:
                if not q.get('board') or q.get('board') == 'Unknown':
                    q['board'] = fallback_board
            return sorted(questions, key=lambda x: x.get('question_no', 0))

        new_questions = []
        for q in questions:
            if q.get('question_no', 0) > 150:
                continue  # Discard hallucinated trailing page number artifacts
            new_questions.append(q)

        # Secondary check from raw PDF if file exists
        qnos = [q.get('question_no', 0) for q in new_questions]
        max_q = max(qnos) if qnos else 0
        still_missing = set(range(1, max_q + 1)) - set(qnos)

        # Check if missing questions were swallowed inside predecessor question bodies
        for m in sorted(list(still_missing)):
            prev_q = next((q for q in new_questions if q.get('question_no') == m - 1), None)
            if prev_q:
                p_text = prev_q.get('question') or prev_q.get('question_text') or ""
                m_pat = rf'(?m)(?:^|\n|[;\.\!\?]\s*|\s{{2,}})\s*(?:Q\.?|Question\s*)?{m}(?:\s*[\.\,\)\:\-\–—\•\·\*\~%]+|\s+(?=[a-zA-Z\u0B80-\u0BFF\d\(\[\'\"‘“]))\s*(.+)'
                split_m = re.search(m_pat, p_text, re.DOTALL)
                if split_m:
                    split_idx = split_m.start()
                    t_prev = p_text[:split_idx].strip()
                    t_new = p_text[split_idx:].strip()
                    t_new = re.sub(rf'^\s*(?:Q\.?)?\s*{m}(?:\s*[\.\,\)\:\-\–—\•\·\*\~%]+|\s+(?=[a-zA-Z\u0B80-\u0BFF\d\(\[\'\"‘“]))\s*', '', t_new)
                    if len(t_prev) > 15 and len(t_new) > 15:
                        prev_q['question'] = t_prev
                        if 'question_text' in prev_q:
                            prev_q['question_text'] = t_prev
                        m_marks = prev_q.get('max_marks') or prev_q.get('marks') or 1.0
                        new_questions.append({
                            "question_no": m,
                            "question": t_new,
                            "question_text": t_new,
                            "marks": m_marks,
                            "max_marks": float(m_marks),
                            "board": fallback_board,
                            "section": prev_q.get('section', ""),
                            "tables": []
                        })

        qnos = [q.get('question_no', 0) for q in new_questions]
        max_q = max(qnos) if qnos else 0
        still_missing = set(range(1, max_q + 1)) - set(qnos)

        if still_missing and (raw_text or (file_path and os.path.exists(file_path))):
            try:
                pdf_text = raw_text
                if not pdf_text and file_path and os.path.exists(file_path) and HAS_FITZ:
                    doc = fitz.open(file_path)
                    pdf_text = "".join([page.get_text() for page in doc])
                    doc.close()
                for m in still_missing:
                    pattern = rf'(?m)^\s*(?:Q\.?)?\s*{m}\s*[\.\,\)\:\-\–—\•\·\*\~%]\s*(.*?)(?=(?:^\s*(?:Q\.?)?\s*\d+[\.\,\)\:\-\–—\•\·\*\~])|\Z)'
                    match = re.search(pattern, pdf_text, re.IGNORECASE | re.DOTALL)
                    if match:
                        q_text = match.group(1).strip()
                        # Reject if q_text is an instruction header or range descriptor
                        if re.search(r'\b(?:Section\s*[-–—]|\bquestions?\s+no\.?\s*\d+\s+to\s+\d+|candidates?\s+will\s+read|compulsory|maximum\s+marks)\b', q_text, re.IGNORECASE):
                            continue
                        if len(q_text) > 2000:
                            q_text = q_text[:2000] + "..."
                        prev_q = next((q for q in new_questions if q.get('question_no') == m - 1), None)
                        m_marks = prev_q.get('max_marks') or prev_q.get('marks') or 1.0 if prev_q else 1.0
                        new_questions.append({
                            "question_no": m,
                            "question": q_text,
                            "question_text": q_text,
                            "marks": m_marks,
                            "max_marks": float(m_marks),
                            "tables": [],
                            "section": prev_q.get('section', "") if prev_q else "",
                            "board": fallback_board
                        })
            except Exception:
                pass


        # Deduplicate
        seen = {}
        for q in new_questions:
            q_num = q['question_no']
            if q_num not in seen:
                seen[q_num] = q
            else:
                existing_text = seen[q_num].get('question', '')
                new_text = q.get('question', '')
                is_existing_leak = bool(re.search(r'\b(?:Section\s*[-–—]|\bquestions?\s+no\.?\s*\d+\s+to\s+\d+|candidates?\s+will\s+read|compulsory|maximum\s+marks)\b', existing_text, re.IGNORECASE))
                is_new_leak = bool(re.search(r'\b(?:Section\s*[-–—]|\bquestions?\s+no\.?\s*\d+\s+to\s+\d+|candidates?\s+will\s+read|compulsory|maximum\s+marks)\b', new_text, re.IGNORECASE))
                has_existing_indic = any(ord(c) in range(0x0900, 0x097F) or ord(c) in range(0x0B80, 0x0BFF) for c in existing_text)
                has_new_indic = any(ord(c) in range(0x0900, 0x097F) or ord(c) in range(0x0B80, 0x0BFF) for c in new_text)
                if is_existing_leak and not is_new_leak:
                    seen[q_num] = q
                elif not is_existing_leak and is_new_leak:
                    pass
                elif has_existing_indic and not has_new_indic:
                    seen[q_num] = q
                elif not has_existing_indic and has_new_indic:
                    pass
                elif len(new_text) > len(existing_text) and not is_new_leak:
                    seen[q_num] = q

        for q in seen.values():
            if not q.get('board') or q.get('board') == 'Unknown':
                q['board'] = fallback_board

        return sorted(list(seen.values()), key=lambda x: x['question_no'])


# ============================================================
# 8. MASTER ORCHESTRATOR PIPELINE
# ============================================================

class DocIntelligencePipeline(BaseEngine):
    """Enterprise Production Pipeline with multi-tier fallbacks, OOP resilience & MLOps."""

    def __init__(self, board: str = "", ocr_lang: str = "", force_ocr: bool = False):
        super().__init__(name="DocIntelligencePipeline", failure_threshold=5)
        self.board = board
        self.ocr_lang = ocr_lang
        self.force_ocr = force_ocr
        self.preprocessor = TextPreprocessor()
        self.pymupdf_engine = PyMuPDFEngine() if HAS_FITZ else None
        self.tesseract_engine = None
        self.paddle_engine = None

    def validate_input(self, input_data: Any) -> str:
        """Validates input question paper path."""
        if not input_data:
            raise ValueError("Input question paper path cannot be empty.")
        file_path = str(input_data).strip()
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Question paper file not found at: {file_path}")
        if os.path.getsize(file_path) == 0:
            raise ValueError(f"Question paper file is empty (0 bytes): {file_path}")
        valid_exts = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".txt"}
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in valid_exts:
            raise ValueError(f"Unsupported file format '{ext}'. Expected one of {valid_exts}")
        return file_path

    def fallback(self, error: Exception, input_data: Any) -> List[Dict]:
        """Provides a safe, non-crashing degraded return value when extraction fails."""
        logger.warning(f"[DocIntelligencePipeline] Returning degraded fallback for {input_data}: {error}")
        return [{
            "question_no": 1,
            "question_text": f"[DEGRADED_EXTRACTION_FALLBACK] Document parsing encountered error: {str(error)}. Flagged for manual extraction.",
            "max_marks": 1.0,
            "options": [],
            "bloom_level": "Remember",
            "difficulty": "Medium",
            "section": "A",
            "sub_parts": [],
            "is_mcq": False,
            "board": getattr(self, "board", "Unknown") or "Unknown",
            "mapping_status": "manual_review",
            "manual_review_required": True,
            "extraction_status": "failed_degraded_fallback",
            "error_details": str(error)
        }]

    @resilient_engine_step("DocIntelligencePipeline")
    def execute_core(self, file_path: str) -> List[Dict]:
        """Core parsing step with Pydantic validation and MLOps telemetry."""
        start_t = time.perf_counter()
        questions = self._parse_internal(file_path)
        latency_ms = (time.perf_counter() - start_t) * 1000.0

        # Pydantic validation & sanitization
        sanitized_questions = []
        for q in questions:
            try:
                raw_txt = q.get("question_text") or q.get("question") or q.get("text", "")
                raw_m = q.get("max_marks") or q.get("marks") or 1.0
                q_schema = ParsedQuestionSchema(
                    question_no=q.get("question_no", 1),
                    question_text=str(raw_txt),
                    max_marks=float(raw_m),
                    options=q.get("options", []),
                    bloom_level=q.get("bloom_level", "Remember"),
                    difficulty=q.get("difficulty", "Medium"),
                    section=q.get("section"),
                    sub_parts=q.get("sub_parts", []),
                    is_mcq=q.get("is_mcq", False),
                    language=q.get("language", "en")
                )
                sanitized_q = dict(q)
                sanitized_q.update(q_schema.model_dump())
                sanitized_questions.append(sanitized_q)
            except Exception as val_err:
                logger.warning(f"[DocIntelligencePipeline] Question validation warning: {val_err}. Retaining raw question.")
                sanitized_questions.append(q)

        # MLOps Telemetry Logging
        paper_name = os.path.basename(file_path)
        first_q = sanitized_questions[0] if sanitized_questions else {}
        metadata = {
            "board": first_q.get("board", self.board or "Unknown"),
            "subject": first_q.get("subject", "Unknown"),
            "grade": first_q.get("class", first_q.get("grade", "Unknown"))
        }
        try:
            tracker = get_mlops_tracker()
            tracker.log_parser_metrics(
                paper_name=paper_name,
                question_count=len(sanitized_questions),
                extraction_rate=1.0 if sanitized_questions else 0.0,
                latency_ms=latency_ms,
                metadata=metadata
            )
        except Exception as ml_err:
            logger.warning(f"[DocIntelligencePipeline] MLOps logging skipped: {ml_err}")

        return sanitized_questions

    def parse(self, file_path: str) -> List[Dict]:
        """Runs the question paper parser through the resilient BaseEngine lifecycle."""
        return self.run(file_path)

    def process(self, file_path: str) -> str:
        """Processes file and returns JSON string."""
        questions = self.parse(file_path)
        return json.dumps(questions, indent=2, ensure_ascii=False)

    def _is_text_garbage(self, text: str, page_count: int = 1) -> bool:
        if self.force_ocr:
            return True
        if not text or len(text.strip()) < 50:
            return True
        # If PDF has multiple pages but text is very sparse (e.g. only watermarks / headers)
        if page_count > 0 and len(text.strip()) < page_count * 80:
            return True
        # Check meaningful word count per page (ignoring common web watermarks, supporting English, Tamil, and Hindi)
        meaningful_words = [w for w in re.findall(r'\b[a-zA-Z\u0B80-\u0BFF\u0900-\u097F]{2,}\b', text) if w.lower() not in {'www', 'com', 'pdf'}]
        if page_count > 0 and len(meaningful_words) < page_count * 10:
            return True
        corrupted_chars = ['Ã', 'Â', 'Ø', 'Ô', '¿', '¾', '½', '¼', '¢', '£', '¤', '¥']
        if sum(text.count(c) for c in corrupted_chars) > max(10, len(text) * 0.05):
            return True
        if text.count('\ufffd') > max(50, len(text) * 0.05):
            return True
        non_printable = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t')
        if non_printable > len(text) * 0.1:
            return True
        bamini_signatures = [
            'wpgup', 'craflé', 'u@fi', 'auifl', 'wpmid', 'eramn', 'eramp',
            'GsrEss', 'Ghlssain', 'L(peaT', 'flser', 'LPOI', 'sSraups'
        ]
        if any(sig in text.lower() for sig in bamini_signatures):
            return True
        return False

    def _parse_internal(self, file_path: str) -> List[Dict]:
        """Processes file and returns list of question dicts."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Question paper file not found at: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        extracted_text = ""
        ocr_ran = False
        page_count = 1

        if ext == '.pdf' and HAS_FITZ:
            try:
                doc = fitz.open(file_path)
                page_count = max(1, len(doc))
                doc.close()
            except Exception:
                page_count = 1

        # Step 1: Detect Board & Language
        detected_board = self.board
        detected_lang = self.ocr_lang

        if not detected_board or not detected_lang:
            sample_text = ""
            if ext == '.pdf' and HAS_FITZ:
                try:
                    doc = fitz.open(file_path)
                    sample_text = "".join(doc[i].get_text() for i in range(min(3, len(doc))))
                    if not sample_text or len(sample_text.strip()) < 30:
                        try:
                            import pytesseract, io
                            from PIL import Image
                            tess_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                            if os.path.exists(tess_cmd):
                                pytesseract.pytesseract.tesseract_cmd = tess_cmd
                            pix = doc[0].get_pixmap(dpi=150)
                            img = Image.open(io.BytesIO(pix.tobytes()))
                            sample_text = pytesseract.image_to_string(img, lang="eng+tam+hin")[:1500]
                        except Exception:
                            pass
                    doc.close()
                except Exception:
                    pass
            elif ext in ['.txt', '.text']:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    sample_text = f.read(3000)

            if not detected_board:
                detected_board = self.preprocessor.detect_board(sample_text, file_path)
            if not detected_lang:
                detected_lang = self.preprocessor.detect_ocr_lang(sample_text, file_path)

        self.tesseract_engine = TesseractOCREngine(ocr_lang=detected_lang)

        # Step 2: Extraction Strategy (Tier 1: PyMuPDF -> Tier 2: OCR/Vision -> Tier 3: Paddle)
        if ext == '.pdf' and HAS_FITZ:
            if self.force_ocr:
                logger.info("force_ocr is enabled for PDF. Triggering Vision + OCR fallback on all pages...")
                doc = fitz.open(file_path)
                ocr_pages = []
                for page_num in range(len(doc)):
                    page_text = self.tesseract_engine.extract_page_ocr(doc[page_num])
                    ocr_pages.append(page_text)
                doc.close()
                extracted_text = "\n".join(ocr_pages)
                ocr_ran = True
            else:
                try:
                    extracted_text = self.pymupdf_engine.extract(file_path)
                    
                    # Check for scanned PDF / garbage text / watermark-only text
                    if self._is_text_garbage(extracted_text, page_count):
                        logger.info("PDF text layer is scanned or corrupted. Triggering Vision + OCR fallback...")
                        doc = fitz.open(file_path)
                        ocr_pages = []
                        for page_num in range(len(doc)):
                            page_text = self.tesseract_engine.extract_page_ocr(doc[page_num])
                            ocr_pages.append(page_text)
                        doc.close()
                        extracted_text = "\n".join(ocr_pages)
                        ocr_ran = True
                except Exception as e:
                    logger.warning(f"PyMuPDF primary extraction error: {e}. Falling back to Vision OCR...")
                    doc = fitz.open(file_path)
                    ocr_pages = [self.tesseract_engine.extract_page_ocr(page) for page in doc]
                    doc.close()
                    extracted_text = "\n".join(ocr_pages)
                    ocr_ran = True

        elif ext in IMAGE_EXTENSIONS or self.force_ocr:
            logger.info("Processing image via OpenCV Vision Preprocessor & Tesseract...")
            extracted_text = self.tesseract_engine.extract_page_ocr(file_path)
            ocr_ran = True

        elif ext in ['.txt', '.text', '.md']:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                extracted_text = f.read()

        # Step 3: Question Parsing Core
        if not self.board and extracted_text:
            detected_board = self.preprocessor.detect_board(extracted_text, file_path)
        extractor = QuestionExtractor(board=detected_board, ocr_lang=detected_lang)
        questions = extractor.extract_from_text(extracted_text)

        # Resilient Tier-2 Recovery: If primary text extraction yielded 0 questions on a PDF,
        # automatically fallback to high-resolution Vision OCR!
        if not questions and ext == '.pdf' and HAS_FITZ and not ocr_ran:
            logger.info("PDF primary text yielded 0 questions. Automatically triggering Vision + OCR fallback...")
            doc = fitz.open(file_path)
            ocr_pages = []
            for page_num in range(len(doc)):
                page_text = self.tesseract_engine.extract_page_ocr(doc[page_num])
                ocr_pages.append(page_text)
            doc.close()
            extracted_text = "\n".join(ocr_pages)
            ocr_ran = True
            if not self.board and extracted_text:
                detected_board = self.preprocessor.detect_board(extracted_text, file_path)
            extractor = QuestionExtractor(board=detected_board, ocr_lang=detected_lang)
            questions = extractor.extract_from_text(extracted_text)

        # Step 4: Self-Healing Sequence Engine
        healed_questions = SequenceHealer.heal_questions(questions, file_path, board=detected_board, raw_text=extracted_text)
        for q in healed_questions:
            if not q.get('board') or q.get('board') == 'Unknown':
                q['board'] = detected_board

        # Step 5: Diagram & Graph Intelligence Layer
        if ext == '.pdf' and HAS_FITZ:
            try:
                self._attach_diagrams(file_path, healed_questions)
            except Exception as e:
                logger.debug(f"Diagram extraction notice: {e}")

        return healed_questions

    def _attach_diagrams(self, file_path: str, questions: List[Dict]):
        if not (HAS_FITZ and file_path and os.path.exists(file_path)):
            return
        try:
            doc = fitz.open(file_path)
            diag_patterns = [
                r'\b(?:given|following|shown|below|above)\s+(?:diagrams?|figures?|fig\.?|graphs?|charts?|circuits?|tables?|pictures?|images?)\b',
                r'\b(?:diagrams?|figures?|fig\.?|graphs?|charts?|circuits?|tables?|pictures?|images?)\s+(?:given|shown|below|above)\b',
                r'\b(?:from|in|based\s+on|consider)\s+the\s+(?:diagrams?|figures?|fig\.?|graphs?|charts?|circuits?|tables?|pictures?|images?)\b',
                r'\b(?:படம்|வரைபடம்|கீழ்க்கண்ட\s+படம்)\b',
            ]
            
            page_diagrams = {}
            for page_idx, page in enumerate(doc):
                img_list = page.get_images()
                drawings = page.get_drawings()
                
                rects = []
                for img in img_list:
                    try:
                        r_list = page.get_image_rects(img[0])
                        for r in r_list:
                            if r.width > 25 and r.height > 25 and r.width < page.rect.width * 0.95:
                                rects.append(r)
                    except Exception:
                        pass
                
                for d in drawings:
                    r = d['rect']
                    if 35 < r.width < page.rect.width * 0.9 and 35 < r.height < page.rect.height * 0.6:
                        rects.append(r)
                
                merged_rects = []
                for r in rects:
                    overlap = False
                    for idx, mr in enumerate(merged_rects):
                        if fitz.Rect(mr).intersects(fitz.Rect(r)):
                            merged_rects[idx] = fitz.Rect(mr) | fitz.Rect(r)
                            overlap = True
                            break
                    if not overlap:
                        merged_rects.append(r)
                
                if merged_rects:
                    page_diagrams[page_idx] = (page, merged_rects)
            
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            diagrams_dir = os.path.join("outputs", "pipeline_v3_production_results", "diagrams", base_name)
            
            # Universal Tesseract path resolution
            tess_cmd = None
            if HAS_TESSERACT and pytesseract is not None:
                candidates = [
                    getattr(getattr(pytesseract, 'pytesseract', None), 'tesseract_cmd', None),
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                    "/usr/bin/tesseract",
                    "/usr/local/bin/tesseract",
                ]
                for cand in candidates:
                    if cand and os.path.exists(cand):
                        tess_cmd = cand
                        pytesseract.pytesseract.tesseract_cmd = cand
                        break

            for q in questions:
                q_text = q.get('question', '').lower()
                has_diag_ref = any(re.search(p, q_text) for p in diag_patterns)
                if not has_diag_ref:
                    continue

                stem_words = [w for w in re.findall(r'[a-zA-Z]{4,}', q_text) if w not in {'attempt', 'either', 'answer', 'following', 'questions', 'marks', 'option'}]
                qno = q.get('question_no')
                qno_pat = rf'(?m)^\s*(?:Q\.?|Question\s*)?{qno}[\.\)\:\-](?!\d)'

                matched_page = None
                matched_rects = []
                for p_idx, (p_obj, d_rects) in page_diagrams.items():
                    p_text = p_obj.get_text().lower()
                    if re.search(qno_pat, p_text) and (stem_words and any(w in p_text for w in stem_words[:4])):
                        matched_page = p_obj
                        matched_rects = d_rects
                        break
                
                if matched_page and matched_rects:
                    # Find vertical position of question on this page
                    q_y = None
                    words = matched_page.get_text('words')
                    for w in words:
                        if re.match(rf'^(?:Q\.?|Question\s*)?{qno}[\.\)\:]?$', w[4].strip(), re.IGNORECASE):
                            q_y = w[1]
                            break
                    if q_y is None and stem_words:
                        for w in words:
                            if w[4].lower() in stem_words[:4]:
                                q_y = w[1]
                                break
                    
                    if q_y is not None:
                        valid_rects = [r for r in matched_rects if r.y0 >= q_y - 20 and (r.y0 - q_y) < 350]
                        dr = min(valid_rects, key=lambda r: abs(r.y0 - q_y)) if valid_rects else None
                    else:
                        dr = None

                    if dr is None:
                        continue

                    q['has_diagram'] = True

                    expanded = dr + (-15, -15, 15, 15)
                    words = matched_page.get_text('words')
                    nearby = [w[4] for w in words if fitz.Rect(w[:4]).intersects(expanded)]
                    if nearby:
                        q['diagram_labels'] = nearby[:12]
                    
                    # Always run OCR on diagram/table clip to extract internal content
                    if tess_cmd:
                        try:
                            import io, PIL.Image
                            clip_pix = matched_page.get_pixmap(clip=dr, dpi=200)
                            clip_img = PIL.Image.open(io.BytesIO(clip_pix.tobytes()))
                            ocr_str = pytesseract.image_to_string(clip_img).strip()
                            
                            # Clean common OCR misreads in chemical formulas & reactions
                            ocr_clean = re.sub(r'\b52\s+reaction\b', 'SN2 reaction', ocr_str, flags=re.IGNORECASE)
                            ocr_clean = re.sub(r'[\$s]4\s+reaction\b', 'SN1 reaction', ocr_clean, flags=re.IGNORECASE)
                            ocr_clean = re.sub(r'\bH-l\b', 'HI', ocr_clean)
                            
                            ocr_words = [w for w in re.findall(r'\b[a-zA-Z]{3,}\b', ocr_clean) if len(w) > 2]
                            if ocr_words:
                                q['diagram_labels'] = (q.get('diagram_labels') or []) + ocr_words[:20]
                            if ocr_clean and len(ocr_words) >= 2:
                                if ocr_clean[:25].strip() not in q['question']:
                                    if '\n(A)' in q['question']:
                                        q['question'] = q['question'].replace('\n(A)', f"\n\n{ocr_clean}\n\n(A)")
                                    elif '\n(a)' in q['question']:
                                        q['question'] = q['question'].replace('\n(a)', f"\n\n{ocr_clean}\n\n(a)")
                                    else:
                                        q['question'] = f"{q['question']}\n\n{ocr_clean}"
                                    if 'question_text' in q:
                                        q['question_text'] = q['question']
                        except Exception as e:
                            logger.debug(f"OCR clip extraction error: {e}")

                    try:
                        os.makedirs(diagrams_dir, exist_ok=True)
                        img_filename = f"q{q.get('question_no')}_diag.png"
                        img_path = os.path.join(diagrams_dir, img_filename)
                        pix = matched_page.get_pixmap(clip=dr, dpi=150)
                        pix.save(img_path)
                        q['diagram_image'] = img_path
                    except Exception:
                        pass
            doc.close()
        except Exception as e:
            logger.debug(f"Attach diagrams error: {e}")

    def save_json(self, questions: List[Dict], output_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(questions, f, indent=2, ensure_ascii=False)


# ============================================================
# 9. BACKWARD-COMPATIBILITY ALIAS
# ============================================================
class QuestionPaperParser(DocIntelligencePipeline):
    """Drop-in replacement for question_paper_parser.py"""
    pass


# ============================================================
# 10. CLI ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='STUDIQS® Enterprise Question Paper Parser Engine v3.0 Production',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python qp_parser_v3.py sample_paper.pdf
  python qp_parser_v3.py data/question_papers/ -o outputs/
  python qp_parser_v3.py scanned.png --force-ocr
        """
    )
    parser.add_argument('input_path', help='Input PDF/Image file path or folder containing PDFs')
    parser.add_argument('-o', '--output', help='Output JSON file or directory path', default='')
    parser.add_argument('-b', '--board', help='Override Board type (CBSE or Samacheer)', default='')
    parser.add_argument('--ocr-lang', help='Override OCR language (e.g. eng+tam, eng+hin)', default='')
    parser.add_argument('--force-ocr', action='store_true', help='Force full OCR vision pipeline')

    args = parser.parse_args()
    input_path = args.input_path

    pipeline = DocIntelligencePipeline(
        board=args.board,
        ocr_lang=args.ocr_lang,
        force_ocr=args.force_ocr
    )

    if os.path.isdir(input_path):
        pdf_files = glob.glob(os.path.join(input_path, '*.pdf'))
        out_dir = args.output if args.output else "outputs/Task_6_Question_Extraction"
        os.makedirs(out_dir, exist_ok=True)

        print(f"Batch processing {len(pdf_files)} PDF files from {input_path}")
        print("-" * 80)

        success = 0
        for pdf in pdf_files:
            try:
                t0 = time.time()
                base = os.path.splitext(os.path.basename(pdf))[0]
                out_path = os.path.join(out_dir, f"{base}.json")
                questions = pipeline.parse(pdf)
                pipeline.save_json(questions, out_path)
                dur = time.time() - t0
                print(f"✓ {os.path.basename(pdf):<42} | Qs: {len(questions):<4} | {dur:.1f}s")
                success += 1
            except Exception as e:
                print(f"✗ {os.path.basename(pdf):<42} | ERROR: {e}")

        print("-" * 80)
        print(f"Successfully processed {success}/{len(pdf_files)} question papers.")

    else:
        questions = pipeline.parse(input_path)
        out_path = args.output
        if not out_path:
            base = os.path.splitext(os.path.basename(input_path))[0]
            out_path = f"outputs/{base}_output.json"
        
        pipeline.save_json(questions, out_path)
        print(f"✓ Extracted {len(questions)} questions into {out_path}")
        print(f"  Board: {questions[0].get('board', 'Auto-detected') if questions else 'Unknown'}")
        
        print("\n--- Preview (first 3 questions) ---")
        for q in questions[:3]:
            print(json.dumps(q, indent=2, ensure_ascii=False))
            print("-" * 40)


if __name__ == '__main__':
    main()