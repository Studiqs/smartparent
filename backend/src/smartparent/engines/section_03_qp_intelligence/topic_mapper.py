import os
import re
import time 
import sys
import json
import numpy as np  
import pandas as pd 
from typing import List,Dict,Any,Optional,Set,Tuple
from pathlib import Path

try:
    from src.smartparent.engines.base_engine import (
        BaseEngine, resilient_engine_step, TopicMappingSchema, EngineHealthStatus
    )
    from src.smartparent.engines.mlflow_tracker import get_mlops_tracker
except Exception:
    try:
        from .base_engine import (
            BaseEngine, resilient_engine_step, TopicMappingSchema, EngineHealthStatus
        )
        from .mlflow_tracker import get_mlops_tracker
    except Exception:
        from src.studiqs.core.base_engine import (
            BaseEngine, resilient_engine_step, TopicMappingSchema, EngineHealthStatus
        )
        from src.studiqs.mlops.mlflow_tracker import get_mlops_tracker

def _find_workspace_root() -> Path:
    current = Path(__file__).resolve()
    for p in current.parents:
        if (p / "data" / "inputs").exists():
            return p
        if (p / "data" / "curriculum_repository").exists():
            return p
        if p.name in ("smartparent-backend", "backend"):
            return p
    for p in current.parents:
        if (p / "models").exists() and (p / "data").exists():
            return p
    return current.parents[4] if len(current.parents) > 4 else current.parents[3]

import onnxruntime as ort  
from tokenizers import Tokenizer
from rank_bm25 import BM25Okapi
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords

# Ensure NLTK data
for res, pkg in [('corpora/stopwords', 'stopwords'), ('tokenizers/punkt', 'punkt'), ('tokenizers/punkt_tab', 'punkt_tab')]:
    try:
        nltk.data.find(res)
    except LookupError:
        nltk.download(pkg, quiet=True)

class ONNXEmbeddingEngine:
    
    DEFAULT_ONNX_DIR = "models/all_minilm_l6_v2_onnx"
    DEFAULT_MODEL_FILE = "model_quantized.onnx"
    DEFAULT_TOKENIZER_FILE = "tokenizer.json"

    ONNX_URL = "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_quantized.onnx"
    TOKENIZER_URL = "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json"

    def __init__(self,model_dir:Optional[str]=None):
        if model_dir is None:
            project_root = _find_workspace_root()
            bge_cand=project_root/'models'/'bge_small_en_v1_5_onnx'

            if bge_cand.exists()and (bge_cand/self.DEFAULT_MODEL_FILE).exists():
                model_dir=str(bge_cand)
            else:
                model_dir=str(project_root/self.DEFAULT_ONNX_DIR)
            
        self.model_dir=Path(model_dir)
        self.onnx_path=self.model_dir/self.DEFAULT_MODEL_FILE
        self.tokenizer_path=self.model_dir/self.DEFAULT_TOKENIZER_FILE
        self.embed_dim=384
        self.is_bge='bge' in str(self.model_dir).lower()

        self._ensure_model_files()

        self.session=ort.InferenceSession(
            str(self.onnx_path),
            providers=['CPUExecutionProvider']
        )

        self.tokenizer=Tokenizer.from_file(str(self.tokenizer_path))
        self.tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')
        self.tokenizer.enable_truncation(max_length=128)

    def _ensure_model_files(self):
        import urllib.request
        self.model_dir.mkdir(parents=True,exist_ok=True)

        if not self.onnx_path.exists():
            download_url="https://huggingface.co/Xenova/bge-small-en-v1.5/resolve/main/onnx/model_quantized.onnx" if self.is_bge else self.ONNX_URL
            print(f"[ONNXEmbed] Downloading quantized model ({download_url})...")
            urllib.request.urlretrieve(download_url, str(self.onnx_path))
            print(f"[ONNXEmbed] Downloaded: {os.path.getsize(self.onnx_path) / (1024*1024):.1f} MB")
        if not self.tokenizer_path.exists():
            tok_download_url = "https://huggingface.co/Xenova/bge-small-en-v1.5/resolve/main/tokenizer.json" if self.is_bge else self.TOKENIZER_URL
            print(f"[ONNXEmbed] Downloading tokenizer...")
            urllib.request.urlretrieve(tok_download_url, str(self.tokenizer_path))

    def encode(self,texts:List[str],batch_size:int=64,normalize:bool=True)->np.ndarray:
        all_embs=[]
        for i in range(0,len(texts),batch_size):
            batch=texts[i:i+batch_size]
            encoded=self.tokenizer.encode_batch(batch)

            input_ids=np.array([e.ids for e in encoded], dtype=np.int64)
            attention_mask=np.array([e.attention_mask for e in encoded],dtype=np.int64)
            token_type_ids=np.array([e.type_ids for e in encoded],dtype=np.int64)

            outputs=self.session.run(None,{'input_ids':input_ids,
            'attention_mask':attention_mask,
            'token_type_ids':token_type_ids})

            if self.is_bge:
                embs=outputs[0][:,0]
                if normalize:
                    norms=np.linalg.norm(embs,axis=1,keepdims=True)
                    embs=embs/np.clip(norms,a_min=1e-12,a_max=None)

            else:  
                last_hidden_state=outputs[0]
                mask_expanded=np.expand_dims(attention_mask,-1).astype(np.float32)
                sum_embs=np.sum(last_hidden_state*mask_expanded,axis=1)
                sum_mask=np.clip(mask_expanded.sum(axis=1),a_min=1e-9,a_max=None)
                embs=sum_embs/sum_mask

                if normalize:
                    norms=np.linalg.norm(embs,axis=1,keepdims=True)

                    embs=embs/np.clip(norms,a_min=1e-12,a_max=None)

            all_embs.append(embs)

        return np.vstack(all_embs).astype('float32')



class SubjectCompatibilityEngine:
   

    INCOMPATIBLE = {
        "maths":            {"science", "physics", "chemistry", "biology", "evs", "economics", "accountancy", "business studies", "english", "general awareness"},
        "science":          {"maths", "mathematics", "business maths and statistics", "economics", "accountancy", "business studies", "english"},
        "physics":          {"chemistry", "biology", "maths", "mathematics", "business maths and statistics", "economics", "accountancy", "business studies", "english"},
        "chemistry":        {"physics", "biology", "maths", "mathematics", "business maths and statistics", "economics", "accountancy", "business studies", "english"},
        "biology":          {"physics", "chemistry", "maths", "mathematics", "business maths and statistics", "economics", "accountancy", "business studies", "english"},
        "economics":        {"maths", "mathematics", "science", "physics", "chemistry", "biology", "accountancy", "business studies", "english"},
        "business studies":  {"maths", "mathematics", "science", "physics", "chemistry", "biology", "accountancy", "economics", "english"},
        "accountancy":      {"maths", "mathematics", "science", "physics", "chemistry", "biology", "business studies", "economics", "english"},
        "english":          {"maths", "mathematics", "science", "physics", "chemistry", "biology", "accountancy", "business studies", "economics"},
    }

    @classmethod
    def classify(cls, raw_subj: str) -> Optional[str]:
        s = str(raw_subj).strip().lower()
        if "math" in s: return "maths"
        if "phys" in s: return "physics"
        if "chem" in s: return "chemistry"
        if "bio" in s: return "biology"
        if any(k in s for k in ["sci", "evs"]): return "science"
        if "eco" in s: return "economics"
        if "bus" in s: return "business studies"
        if "acc" in s: return "accountancy"
        if "eng" in s: return "english"
        return None

    @classmethod
    def is_compatible(cls, paper_subj: str, cand_subj: str, paper_grade: str = "Unknown") -> bool:
        """Returns True if candidate topic subject is compatible with the exam paper subject."""
        if not paper_subj or not cand_subj:
            return True
        p_cat = cls.classify(paper_subj)
        if not p_cat or p_cat not in cls.INCOMPATIBLE:
            return True
        c_lower = str(cand_subj).strip().lower()
        for incomp in cls.INCOMPATIBLE[p_cat]:
            if incomp in c_lower:
                return False
        # Senior Secondary science subject isolation (11th/12th)
        is_senior = str(paper_grade).strip() in ("11", "12", "XI", "XII")
        if is_senior:
            if p_cat == "physics" and not ("phys" in c_lower or c_lower == "science"):
                return False
            if p_cat == "chemistry" and not ("chem" in c_lower or c_lower == "science"):
                return False
            if p_cat == "biology" and not ("bio" in c_lower or c_lower == "science"):
                return False
        return True


# =============================================================================
# 1. QUESTION STEM CLEANER & MCQ OPTION ISOLATOR
# =============================================================================

class QuestionStemCleaner:
    """
    Cleans raw parsed question text, extracts the central conceptual stem,
    and isolates MCQ options to prevent distractor noise in semantic retrieval.
    """

    # MCQ Option regex patterns: English (A/B/C/D), Lowercase (a/b/c/d), Roman (i/ii/iii/iv), Tamil (அ/ஆ/இ/ஈ)
    OPTION_SPLIT_RE = re.compile(
        r'(?:\s+|^)(?:[\(\[]?[A-Da-d][\.\)]|[\(\[]?[அஆஇஈ][\.\)]|[\(\[]?[ivxIVX]+[\.\)])\s+',
        re.MULTILINE
    )

    # Marks patterns at end or inline e.g. [1], (2 Marks), [5 marks], 5 Marks
    MARKS_STRIP_RE = re.compile(
        r'(?:[\(\[]\s*\d+(?:\.\d+)?\s*(?:marks?|mark|மதிப்பெண்கள்?|மதிப்பெண்)?\s*[\)\]]|\b\d+(?:\.\d+)?\s*(?:marks?|mark|மதிப்பெண்கள்?|மதிப்பெண்)\b)',
        re.IGNORECASE
    )

    # Generic question boilerplate instructions
    BOILERPLATE_PATTERNS = [
        r'^\s*Choose the correct answer(?:\s*:)?',
        r'^\s*Answer any\s+\w+\s+questions?(?:\s*:)?',
        r'^\s*Fill in the blanks(?:\s*:)?',
        r'^\s*Match the following(?:\s*:)?',
        r'^\s*State True or False(?:\s*:)?',
        r'^\s*சரியான விடையைத் தேர்ந்தெடு(?:\s*:)?',
        r'^\s*கோடிட்ட இடத்தை நிரப்புக(?:\s*:)?',
        r'^\s*பொருத்துக(?:\s*:)?',
    ]

    @classmethod
    def clean(cls, raw_text: str) -> Dict[str, str]:
        """
        Processes a raw question string.
        Returns:
            {
                "cleaned_stem": The core concept statement (distractors stripped),
                "options_text": Joined text of options if MCQ,
                "full_clean": Cleaned overall question,
                "is_mcq": Boolean
            }
        """
        text = raw_text.strip()
        
        # 1. Clean boilerplate prefixes
        for pat in cls.BOILERPLATE_PATTERNS:
            text = re.sub(pat, '', text, flags=re.IGNORECASE).strip()

        # 2. Check for Assertion-Reason structure
        if re.search(r'\b(?:Assertion|க்கூற்று|கூற்று|अभिकथन)\b', text, re.IGNORECASE):
            # Clean off boilerplate MCQ options if present at the end
            clean_ar = re.sub(r'(?:\s+|^)\([a-d]\)\s+(?:Both\s+[AR]|Assertion\s+and\s+Reason|[AR]\s+is\s+true|[AR]\s+is\s+false).*$', '', text, flags=re.IGNORECASE | re.DOTALL)
            clean_ar = re.sub(r'\bAssertion\s*(?:\([Aa]\))?\s*[:\.\-]?', '', clean_ar, flags=re.IGNORECASE)
            clean_ar = re.sub(r'\bReason\s*(?:\([Rr]\))?\s*[:\.\-]?', ' ', clean_ar, flags=re.IGNORECASE)
            clean_ar = re.sub(r'\b(?:கூற்று|காரணம்|अभिकथन|कारण)\s*[:\.\-]?', ' ', clean_ar)
            cleaned_stem = cls.MARKS_STRIP_RE.sub('', clean_ar).strip()
            cleaned_stem = re.sub(r'\s+', ' ', cleaned_stem)
            return {
                "cleaned_stem": cleaned_stem,
                "options_text": "",
                "full_clean": text,
                "is_mcq": True
            }

        # 3. Check if question is a multi-part question rather than MCQ
        is_multipart = any(phrase in text.lower()[:55] for phrase in [
            "what happens", "explain the", "give reason", "distinguish", "write the",
            "differentiate", "convert the", "following", "identify the", "state the",
            "solve the", "find the", "calculate the", "பின்வரும்", "விவரிக்க", "எழுதுக"
        ]) and any(marker in text for marker in ["(a)", "(b)", "(i)", "(ii)", "அ)", "ஆ)"])

        # 4. Check for MCQ options
        if not is_multipart:
            parts = cls.OPTION_SPLIT_RE.split(text)
            if len(parts) > 1 and len(parts[0].strip()) >= 25:
                stem = parts[0].strip()
                options = " ".join(p.strip() for p in parts[1:] if p.strip())
                is_mcq = True
            else:
                stem = text
                options = ""
                is_mcq = False
        else:
            stem = text
            options = ""
            is_mcq = False

        # 5. Clean marks markers from stem
        cleaned_stem = cls.MARKS_STRIP_RE.sub('', stem).strip()
        cleaned_stem = re.sub(r'\s+', ' ', cleaned_stem)

        # 6. Retain MCQ options in semantic context so domain entities are preserved
        if is_mcq and options:
            cleaned_stem = f"{cleaned_stem} {options}"

        # 7. If stem became too short or empty, fallback to full text
        if len(cleaned_stem) < 15 and len(text) >= 15:
            cleaned_stem = text

        # 5. Concept cue enrichment for standard curriculum phrasing
        cues = []
        lower_stem = cleaned_stem.lower()
        if any(w in lower_stem for w in ["altogether", "in all", "gives more", "total pencils", "total apples"]):
            cues.append("addition single digit sum")
        if "fraction" in lower_stem:
            cues.append("fractions half quarter one-fourth parts")
        if "breakdown of glucose" in lower_stem or "lactic acid" in lower_stem or "lack of oxygen" in lower_stem:
            cues.append("respiration cellular respiration life processes")
        if "(-" in lower_stem and "x" in lower_stem:
            cues.append("multiplication integers product")
        if re.search(r'\b\d+\s*m\b.*\bcm\b|\bcm\b.*\bm\b|\bconvert\b.*\b(metre|centimetre|meter)\b|\bconversion of\b.*\bm\b', lower_stem):
            cues.append("measurements length standard units metre centimetre conversion")

        if cues:
            cleaned_stem = f"{cleaned_stem} {' '.join(cues)}"

        return {
            "cleaned_stem": cleaned_stem,
            "options_text": options,
            "full_clean": text,
            "is_mcq": is_mcq
        }


# =============================================================================
# 2. SUBJECT SUB-DOMAIN ROUTER
# =============================================================================

class SubjectDomainRouter:
    """
    Identifies academic sub-domain to prevent cross-branch candidate pollution
    (e.g., preventing a Biology 'brain blood pressure' question from matching Physics 'Pressure').
    """

    SCIENCE_SUBDOMAINS = {
        "Biology": [
            "cell", "cells", "glucose", "insulin", "pancreas", "pituitary", "hormone", "hormones",
            "brain", "medulla", "cerebrum", "cerebellum", "hindbrain", "forebrain", "neuron", "nerve",
            "respiration", "aerobic", "anaerobic", "lactic acid", "photosynthesis", "chlorophyll",
            "stomata", "xylem", "phloem", "nutrition", "autotrophic", "heterotrophic", "digestive",
            "digestion", "enzyme", "heart", "artery", "vein", "blood", "kidney", "nephron", "excretion",
            "reproduction", "asexual", "gamete", "ovary", "testis", "dna", "heredity", "gene", "genes",
            "mendel", "chromosome", "ecosystem", "food chain", "food web", "biodiversity", "tissues",
            "plant", "plants", "animal", "animals", "root", "leaf", "leaves", "stem", "flower",
            "organism", "organisms", "bacteria", "fungi", "virus", "infection", "disease"
        ],
        "Chemistry": [
            "acid", "acids", "base", "bases", "salt", "salts", "ph", "litmus", "neutralization",
            "atom", "atoms", "molecule", "molecules", "electron", "proton", "neutron", "atomic",
            "chemical equation", "reaction", "reacts", "reactants", "products", "oxidation", "reduction",
            "redox", "combustion", "corrosion", "rusting", "periodic table", "element", "elements",
            "compound", "compounds", "valency", "ionic", "covalent", "metal", "metals", "non-metal",
            "metalloid", "carbon", "hydrocarbon", "alkane", "alkene", "alkyne", "ethanol", "ethanoic",
            "mixture", "mixtures", "solution", "filtration", "decantation", "distillation", "colloid",
            "gas", "solid", "liquid", "precipitate", "catalyst"
        ],
        "Physics": [
            "force", "forces", "newton", "velocity", "speed", "acceleration", "momentum", "inertia",
            "friction", "frictional", "gravitation", "gravity", "weight", "mass", "work done", "energy",
            "kinetic", "potential", "power", "motion", "distance", "displacement", "light", "reflection",
            "refraction", "lens", "convex", "concave", "mirror", "focal length", "dioptre", "prism",
            "dispersion", "spectrum", "current", "electric", "electricity", "circuit", "voltage",
            "resistance", "resistor", "ohm", "ampere", "volt", "watt", "joule", "magnetic", "magnet",
            "electromagnet", "electromagnetic", "induction", "solenoid", "transformer", "galvanometer",
            "motor", "generator", "sound", "frequency", "wavelength", "amplitude",
            "echo", "ultrasound", "pressure", "pascal", "atmospheric pressure", "buoyancy", "float",
            "radius", "circumference", "circular", "particle", "diameter", "moving", "metre",
            "centimetre", "measurement", "density", "volume", "thermocouple", "thermodynamics",
            "calorimetry", "heat", "temperature", "conduction", "convection", "radiation"
        ]
    }

    MATHS_SUBDOMAINS = {
        "Algebra": [
            "solve", "equation", "equations", "quadratic", "linear", "polynomial", "polynomials",
            "roots", "zeroes", "zeros", "discriminant", "factor", "factorisation", "factorize",
            "variable", "variables", "x²", "x^2", "algebraic", "identity", "identities", "ap", "gp",
            "arithmetic progression", "geometric progression", "common difference", "nth term"
        ],
        "Geometry": [
            "triangle", "triangles", "circle", "circles", "angle", "angles", "tangent", "tangents",
            "secant", "chord", "similarity", "congruence", "pythagoras", "theorem", "quadrilateral",
            "polygon", "parallel", "perpendicular", "intersecting", "vertex", "vertices"
        ],
        "Coordinate Geometry": [
            "coordinate", "coordinates", "abscissa", "ordinate", "distance formula", "midpoint",
            "section formula", "collinear", "slope", "origin", "axes", "x-axis", "y-axis"
        ],
        "Trigonometry": [
            "sin", "cos", "tan", "sec", "cosec", "cot", "trigonometric", "trigonometry",
            "ratios", "identities", "elevation", "depression", "heights and distances"
        ],
        "Mensuration": [
            "area", "volume", "surface area", "perimeter", "circumference", "radius", "diameter",
            "cylinder", "cylindrical", "cone", "conical", "sphere", "spherical", "hemisphere",
            "cube", "cuboid", "frustum", "capacity"
        ],
        "Statistics & Probability": [
            "mean", "median", "mode", "frequency distribution", "grouped data", "class interval",
            "standard deviation", "variance", "probability", "die", "dice", "coin", "pack of cards",
            "random experiment", "sample space", "event"
        ]
    }

    HIGH_SPECIFICITY_ANCHORS = {
        "Physics": [
            "charge", "charges", "coulomb", "coulombs", "electrostatic", "point charges",
            "electric flux", "potential difference", "emf", "dioptre", "refraction",
            "convex lens", "concave lens", "focal length", "galvanometer", "solenoid",
            "magnetic dipole", "pascal's law", "pascals law", "resistance", "resistor",
            "ohm", "amphere", "current", "circuit"
        ],
        "Biology": [
            "typhoid", "hepatitis", "tuberculosis", "cholera", "pathogen", "pathogens",
            "climbing roots", "betel", "photosynthesis", "chlorophyll", "stomata", "xylem",
            "phloem", "nephron", "neuron", "alveoli", "pancreas", "insulin", "mendel",
            "chromosome", "reproduction", "infection", "bacteria", "fungi", "virus"
        ],
        "Chemistry": [
            "chemical reaction", "periodic table", "valency", "covalent", "ionic bond",
            "redox", "oxidation", "reduction", "alkane", "alkene", "alkyne", "ethanol",
            "ethanoic", "precipitate", "neutralization", "litmus", "atomic number", "mass number"
        ],
        "Trigonometry": [
            "sin", "cos", "tan", "sec", "cosec", "cot", "cot-1", "tan-1", "sin-1", "cos-1",
            "trigonometric", "trigonometry"
        ],
        "Geometry": [
            "triangle", "circle", "rhombus", "perpendicular bisector", "tangent", "secant",
            "parallel lines", "collinear"
        ],
        "Algebra": [
            "solve", "quadratic", "polynomial", "derivative", "integral", "dy/dx", "dx",
            "vector", "matrices", "matrix", "determinant", "differential equation"
        ]
    }

    @classmethod
    def detect_subdomain(cls, subject: str, text: str) -> Optional[str]:
        """
        Detects the academic sub-domain from question text.
        Returns sub-domain name or None if generic.
        """
        t = text.lower()

        # Check high-specificity anchors first (1 single hit is decisive)
        for domain, anchors in cls.HIGH_SPECIFICITY_ANCHORS.items():
            for anchor in anchors:
                if re.search(r'\b' + re.escape(anchor) + r'\b', t):
                    return domain

        sub_map = None
        subj_lower = subject.lower()
        if "sci" in subj_lower or "phy" in subj_lower or "chem" in subj_lower or "bio" in subj_lower:
            sub_map = cls.SCIENCE_SUBDOMAINS
        elif "math" in subj_lower:
            sub_map = cls.MATHS_SUBDOMAINS

        if not sub_map:
            return None

        best_domain = None
        best_count = 0

        for domain, keywords in sub_map.items():
            count = sum(1 for kw in keywords if re.search(r'\b' + re.escape(kw) + r'\b', t))
            if count > best_count and count >= 1:
                best_count = count
                best_domain = domain

        return best_domain


# =============================================================================
# 3. ACADEMIC CONCEPT BRIDGE (STEM Glossary & Entity Disambiguation)
# =============================================================================

class AcademicConceptBridge:
    """
    Curriculum-grounded academic concept bridge for STEM subjects.
    Expands question queries with domain-standard conceptual anchors.
    """

    CHEMISTRY_GLOSSARY = {
        # Biomolecules
        r'\b(?:glucose|fructose|sucrose|maltose|lactose|starch|cellulose|glycogen|monosaccharide|disaccharide|polysaccharide|laevorotatory|dextrorotatory|mutarotation|reducing\s+sugar)\b':
            'Biomolecules Carbohydrates',
        r'\b(?:amino\s+acid|peptide|polypeptide|denaturation|zwitterion|globular\s+protein|fibrous\s+protein)\b':
            'Biomolecules Proteins',
        r'\b(?:dna|rna|nucleotide|nucleoside|phosphodiester|purine|pyrimidine)\b':
            'Biomolecules Nucleic Acids',
        r'\b(?:vitamin|vitamins|deficiency\s+disease|scurvy|rickets|beriberi)\b':
            'Biomolecules Vitamins',

        # d and f Block & Coordination
        r'\b(?:inner\s+transition|lanthanoid|actinoid|lanthanide|actinide|lanthanoid\s+contraction|mischmetal|permanganate|mno4|dichromate|k2cr2o7|enthalp(?:y|ies)\s+of\s+atomisation|atomisation\s+of\s+(?:zinc|copper|transition)|transition\s+metals?)\b':
            'The d-and f-Block Elements',
        r'\b(?:coordination\s+compound|coordination\s+complex|counter\s+ion|ligand|chelating|ambidentate|coordination\s+number|crystal\s+field|d-d\s+transition)\b':
            'Coordination Compounds',

        # Electrochemistry
        r'\b(?:kohlrausch|molar\s+conductivity|equivalent\s+conductivity|limiting\s+molar|nernst|cell\s+potential|standard\s+electrode|fuel\s+cell|secondary\s+cell|storage\s+battery|lead\s+storage|electrochemical\s+series|electrolytic\s+solution|conductivity\s+of|ch3cooh|acetic\s+acid)\b|[Λ\u039B\u03BB]\s*[m\U0001D45A]?':
            'Electrochemistry',

        # Solutions
        r'\b(?:azeotrop|azeotropic|colligative|van\'t\s+hoff|elevation\s+in\s+boiling|depression\s+in\s+freezing|osmotic\s+pressure|reverse\s+osmosis|raoult|ideal\s+solution|non-ideal\s+solution|henry\'s\s+law|molality|molarity|mole\s+fraction)\b':
            'Solutions',

        # Chemical Kinetics
        r'\b(?:rate\s+of\s+reaction|rate\s+constant|half\s+life|order\s+of\s+reaction|molecularity|activation\s+energy|arrhenius|collision\s+theory|rate\s+law|pseudo\s+first\s+order)\b':
            'Chemical Kinetics',

        # Haloalkanes and Haloarenes
        r'\b(?:alkyl\s+halide|aryl\s+halide|benzylic\s+halide|allylic\s+halide|haloalkane|haloarene|sandmeyer|finkelstein|swarts|sn1|sn2|s_n1|s_n2|addition\s+reaction|elimination\s+reaction|dehydrohalogenation|saytzeff|markovnikov|ambident\s+nucleophile|freon|chlorobenzene|benzyl\s+chloride|chlorotoluene|toluene\s+on\s+treatment\s+with\s+cl2|cl2\s+in\s+sunlight)\b':
            'Haloalkanes and Haloarenes Chemical Reactions nucleophilic substitution',

        # Alcohols, Phenols and Ethers
        r'\b(?:cresol|o-cresol|m-cresol|p-cresol|phenol|phenols|ether|ethers|anisole|resorcinol|williamson|kolbe|reimer\s*[-–]?\s*tiemann|hydroboration)\b':
            'Alcohols, Phenols and Ethers',

        # Aldehydes, Ketones and Carboxylic Acids
        r'\b(?:propanal|propanone|butanone|acetaldehyde|benzaldehyde|acetone|acetophenone|benzophenone|2,4\s*[-–]?\s*dnp|tollens|fehling|cannizzaro|aldol|rosenmund|clemmensen|wolff\s*[-–]?\s*kishner|etard|hell\s*[-–]?\s*volhard|decarboxylation)\b':
            'Aldehydes, Ketones and Carboxylic Acids',

        # Amines / Organic Nitrogen
        r'\b(?:ethanamine|benzenamine|aniline|aliphatic\s+amine|aromatic\s+amine|diazonium|diazo|gabriel\s+phthalimide|hoffmann\s+bromamide|carbylamine|hinsberg)\b':
            'Amines',
    }

    PHYSICS_GLOSSARY = {
        # Optics
        r'\b(?:refraction|reflection|focal\s+length|convex\s+lens|concave\s+lens|prism|dispersion|magnifying\s+power|telescope|microscope|snell\'s\s+law)\b':
            'Ray Optics and Optical Instruments',
        r'\b(?:interference|diffraction|polarization|young\'s\s+double\s+slit|fringe\s+width|coherent\s+sources|brewster|wavefront|huygens)\b':
            'Wave Optics',

        # Electrostatics & Current
        r'\b(?:coulomb|electric\s+field|electric\s+flux|gauss\'s\s+law|equipotential|capacitance|dielectric|parallel\s+plate\s+capacitor)\b':
            'Electric Charges and Fields Electrostatic Potential and Capacitance',
        r'\b(?:drift\s+velocity|ohm\'s\s+law|resistivity|wheatstone\s+bridge|potentiometer|internal\s+resistance|kirchhoff\'s\s+laws)\b':
            'Current Electricity',

        # Magnetism & EMI
        r'\b(?:biot\s*[-–]?\s*savart|ampere\'s\s+circuital|lorentz\s+force|cyclotron|galvanometer|toroid|solenoid)\b':
            'Moving Charges and Magnetism',
        r'\b(?:faraday\'s\s+law|lenz\'s\s+law|eddy\s+currents|self\s+induction|mutual\s+induction|alternating\s+current|transformer|resonance|lcr\s+circuit)\b':
            'Electromagnetic Induction Alternating Current',

        # Modern Physics
        r'\b(?:photoelectric\s+effect|work\s+function|stopping\s+potential|threshold\s+frequency|de\s+broglie)\b':
            'Dual Nature of Radiation and Matter',
        r'\b(?:bohr\s+model|rydberg|energy\s+levels|hydrogen\s+spectrum|mass\s+defect|binding\s+energy|nuclear\s+fission|nuclear\s+fusion)\b':
            'Atoms Nuclei',
        r'\b(?:p-n\s+junction|diode|rectifier|solar\s+cell|photodiode|led|semiconductor|extrinsic\s+semiconductor)\b':
            'Semiconductor Electronics',
    }

    BIOLOGY_GLOSSARY = {
        # Control and Coordination / Nervous System
        r'\b(?:brain|cerebrum|cerebellum|medulla|pons|neuron|synapse|reflex\s+arc|reflex\s+action|spinal\s+cord|nervous\s+tissue|dendrite|axon|sensory\s+neuron|motor\s+neuron)\b':
            'Control and Coordination Animals Nervous System Human Brain Reflex Actions',
        r'\b(?:phototropism|geotropism|hydrotropism|chemotropism|thigmotropism|auxin|gibberellin|cytokinin|abscisic\s+acid|ethylene|plant\s+hormones?)\b':
            'Control and Coordination Coordination in Plants',
        # Life Processes
        r'\b(?:photosynthesis|chlorophyll|stomata|guard\s+cells|transpiration|xylem|phloem|nephron|dialysis|alveoli|hemoglobin|pepsin|trypsin|bile|villi)\b':
            'Life Processes Nutrition Respiration Transportation Excretion',
        # Reproduction
        r'\b(?:pollination|microsporogenesis|megasporogenesis|embryo\s+sac|endosperm|double\s+fertilization|apomixis)\b':
            'Sexual Reproduction in Flowering Plants How do Organisms Reproduce',
        r'\b(?:spermatogenesis|oogenesis|menstrual\s+cycle|placenta|parturition|lactation|cleavage|blastocyst)\b':
            'Human Reproduction How do Organisms Reproduce',
        r'\b(?:contraception|iud|ivf|art|amniocentesis|std|mtp)\b':
            'Reproductive Health',
        # Genetics & Inheritance
        r'\b(?:monohybrid|dihybrid|incomplete\s+dominance|codominance|linkage|hemophilia|color\s+blindness|down\'s\s+syndrome|turner\'s\s+syndrome|pedigree|mendel|allele|phenotype|genotype|sex\s+determination)\b':
            'Principles of Inheritance and Variation Heredity',
        r'\b(?:replication|transcription|translation|lac\s+operon|human\s+genome|dna\s+fingerprinting)\b':
            'Molecular Basis of Inheritance Heredity',
        r'\b(?:recombinant\s+dna|restriction\s+enzyme|plasmid|pcr|gel\s+electrophoresis|bioreactor|bt\s+cotton|gene\s+therapy)\b':
            'Biotechnology Principles and Processes Biotechnology and its Applications',
    }

    MATHEMATICS_GLOSSARY = {
        r'\b(?:differentiab|derivative|continuity|chain\s+rule|rolle\'s|mean\s+value\s+theorem|increasing\s+decreasing|maxima\s+minima)\b':
            'Continuity and Differentiability Application of Derivatives',
        r'\b(?:integration|antiderivative|substitution|partial\s+fractions|definite\s+integral|area\s+under\s+curve)\b':
            'Integrals Application of Integrals',
        r'\b(?:differential\s+equation|order\s+and\s+degree|general\s+solution|integrating\s+factor)\b':
            'Differential Equations',
        r'\b(?:matrix|matrices|symmetric\s+matrix|skew-symmetric|determinant|minors\s+and\s+cofactors|adjoint|inverse\s+of\s+matrix)\b':
            'Matrices Determinants',
        r'\b(?:collinear\s+vectors|unit\s+vector|dot\s+product|cross\s+product|direction\s+cosines|skew\s+lines)\b':
            'Vector Algebra Three Dimensional Geometry',
        r'\b(?:conditional\s+probability|bayes\'\s+theorem|independent\s+events|probability\s+distribution|binomial\s+distribution)\b':
            'Probability',
    }

    BUSINESS_STUDIES_GLOSSARY = {
        r'\b(?:consumerism|consumer\s+rights?|john\s+f\.?\s*kennedy|consumer\s+protection\s+act|unpaid\s+seller|redressal)\b':
            'Consumer Protection Consumer Rights The Consumer Protection Act',
        r'\b(?:stock\s+exchange|securities|sebi|treasury\s+bill|secondary\s+market|capital\s+market|dematerialization|speculation|amsterdam\s+stock|london\s+stock|bombay\s+stock|national\s+stock)\b':
            'Financial Markets Financial Management',
        r'\b(?:scientific\s+management|taylor|fayol|principles\s+of\s+management|mbo|mbe|concept\s+of\s+management|management\s+tools|functions\s+of\s+management)\b':
            'Principles of Management Nature and Significance of Management',
        r'\b(?:recruitment|sources\s+of\s+recruitment|transfer|selection|stress\s+interview|human\s+resource|hrm)\b':
            'Staffing Directing',
        r'\b(?:delegation\s+of\s+authority|organising|directors|board\s+of\s+directors)\b':
            'Organising Principles of Management',
        r'\b(?:business\s+environment|micro\s+environmental|macro\s+environmental|globalisation|liberalisation|privatisation|lpg\s+policy|new\s+economic\s+policy)\b':
            'Business Environment',
        r'\b(?:marketing|marketing\s+mix|barter\s+system|green\s+marketing|viral\s+marketing|e-marketing|marketer|functions\s+of\s+marketing)\b':
            'Marketing',
        r'\b(?:shares\s+and\s+debentures|companies\s+act|share\s+holder|statutory\s+meeting|quorum|annual\s+general\s+meeting|extraordinary\s+general)\b':
            'Forms of Business Organisation Formation of a Company',
        r'\b(?:entrepreneur|imitative\s+entrepreneur|agricultural\s+entrepreneur|women\s+entrepreneur|navratnas)\b':
            'MSME and Business Entrepreneurship Entrepreneurship Development',
        r'\b(?:contract\s+of\s+sale|negotiable\s+instruments|promissory\s+note|bills\s+of\s+exchange|cheque)\b':
            'Business, Trade and Commerce Internal Trade',
    }

    @classmethod
    def enrich_academic_query(cls, text: str, subject: str = "Unknown") -> str:
        """
        Enriches a question text query with domain-specific conceptual anchor terms.
        Selects glossary based on normalized subject or checks all relevant STEM glossaries.
        """
        if not text:
            return text

        subj_lower = str(subject).strip().lower()
        active_glossaries = []

        if any(k in subj_lower for k in ["business", "commerce", "bst"]):
            active_glossaries.append(cls.BUSINESS_STUDIES_GLOSSARY)
        elif "chem" in subj_lower:
            active_glossaries.append(cls.CHEMISTRY_GLOSSARY)
        elif "phys" in subj_lower:
            active_glossaries.append(cls.PHYSICS_GLOSSARY)
        elif "bio" in subj_lower:
            active_glossaries.append(cls.BIOLOGY_GLOSSARY)
        elif "math" in subj_lower:
            active_glossaries.append(cls.MATHEMATICS_GLOSSARY)
        elif any(k in subj_lower for k in ["sci", "evs"]):
            active_glossaries.extend([cls.CHEMISTRY_GLOSSARY, cls.PHYSICS_GLOSSARY, cls.BIOLOGY_GLOSSARY])
        else:
            # Fallback check all STEM & Business
            active_glossaries.extend([cls.CHEMISTRY_GLOSSARY, cls.PHYSICS_GLOSSARY, cls.BIOLOGY_GLOSSARY, cls.MATHEMATICS_GLOSSARY, cls.BUSINESS_STUDIES_GLOSSARY])

        expansions = []
        for gloss in active_glossaries:
            for pat, exp in gloss.items():
                if re.search(pat, text, re.IGNORECASE):
                    expansions.append(exp)

        if expansions:
            # De-duplicate terms while preserving order
            unique_expansions = []
            seen = set()
            for exp in expansions:
                for token in exp.split():
                    if token.lower() not in seen:
                        seen.add(token.lower())
                        unique_expansions.append(token)
            return text + " " + " ".join(unique_expansions)

        return text


# =============================================================================
# 4. BILINGUAL CONCEPT BRIDGE (Tamil & Hindi Curriculum Translation Dictionary)
# =============================================================================

class BilingualConceptBridge:
    """
    Bilingual concept dictionary and transliteration-aware bridge for Indian regional,
    Tamil, and Hindi question papers.
    """

    # Comprehensive Tamil Academic Vocabulary to Curriculum English Concepts
    TAMIL_ACADEMIC_GLOSSARY = {
        # Physics / Mechanics / Measurement
        "மீ": "Metre Measurement Units Length SI Unit",
        "செ.மீ": "Centimetre Length Measurement Units",
        "சென்டிமீட்டர்": "Centimetre Length Measurement Units",
        "மீட்டர்": "Metre Length Measurement Units",
        "மில்லிமீட்டர்": "Millimetre Length Measurement Units",
        "நானோமீட்டர்": "Nanometre Length Measurement",
        "கிலோகிராம்": "Kilogram Mass Measurement",
        "வினாடி": "Seconds Time Measurement Units",
        "நிமிடம்": "Minute Time Measurement",
        "மீ/வி": "Metre per second Speed Velocity Units",
        "வேகம்": "Speed Velocity Motion",
        "வேகத்தின்": "Speed Velocity Motion",
        "தொலைவு": "Distance Displacement Motion",
        "காலம்": "Time Interval Motion",
        "முடுக்கம்": "Acceleration Motion",
        "விசை": "Force Newton Laws of Motion",
        "அடர்த்தி": "Density Mass Volume",
        "நிறை": "Mass Weight",
        "ஈர்ப்பு": "Gravitation Gravity",
        "புவியீர்ப்பு": "Gravitational Force Gravity",
        "உராய்வு": "Friction Frictional Force",
        "வேலை": "Work Done Energy",
        "ஆற்றல்": "Energy Kinetic Potential",
        "திறன்": "Power Work Energy",
        "அளவீடு": "Measurements Units SI Unit",
        "அளவீட்டியல்": "Measurement Units Metre Centimetre",
        "வளைகோடு": "Curved Line Measuring Length of Curved Line",
        "அதிர்வு இயக்கம்": "Vibratory Oscillatory Motion Periodic Motion",
        "சுழற்சி இயக்கம்": "Rotational Circular Motion",
        "கால ஒழுங்கு": "Periodic Motion Time Intervals",
        "கால ஒழுங்கற்ற": "Non-periodic Motion",
        "இயக்கம்": "Motion Types of Motion",

        # Physics / Optics / Sound / Electricity
        "ஒளி": "Light Reflection Refraction",
        "ஒளிவிலகல்": "Refraction of Light Lens",
        "எதிரொளிப்பு": "Reflection of Light Mirror",
        "குவிலென்ஸ்": "Convex Lens Refraction",
        "குழிலென்ஸ்": "Concave Lens",
        "குவிஆடி": "Convex Mirror",
        "குழிஆடி": "Concave Mirror",
        "மின்னோட்டம்": "Electric Current Electricity",
        "மின்னழுத்தம்": "Voltage Potential Difference",
        "மின்தடை": "Resistance Ohm's Law Resistor",
        "மின்சுற்று": "Electric Circuit Diagram",
        "மின்காந்தம்": "Electromagnetism Magnetic Effect",
        "ஒலி": "Sound Sound Waves Frequency",
        "அலைநீளம்": "Wavelength Frequency Sound Wave",
        "அதிர்வெண்": "Frequency Pitch Sound",

        # Chemistry / Matter / Separation of Substances
        "கலவை": "Mixtures Separation of Substances",
        "கலவைகள்": "Mixtures Separation of Substances",
        "பிரித்தெடுத்தல்": "Separation of Substances Filtration Methods",
        "வடிகட்டுதல்": "Filtration Separation of Mixtures",
        "புடைத்தல்": "Winnowing Separation of Substances",
        "படியவைத்தல்": "Sedimentation Decantation Separation of Substances",
        "படிய வைத்தல்": "Sedimentation Decantation Separation of Substances",
        "தெளிய வைத்து": "Decantation Separation of Mixtures",
        "தெளிய வைத்து இறுத்தல்": "Decantation Separation",
        "அரிசி": "Separation of Substances Winnowing",
        "பருப்பு": "Separation of Substances Winnowing",
        "மாசுக்களை நீக்கும்": "Separation of Substances Winnowing",
        "நீக்கும் முறை": "Separation of Substances Winnowing Methods",
        "தூய பொருள்": "Pure Substance Elements Compounds",
        "அணு": "Atom Atomic Structure",
        "மூலக்கூறு": "Molecule Molecular Mass",
        "புரோட்டான்": "Proton Atomic Structure",
        "எலக்ட்ரான்": "Electron Electronic Configuration",
        "நியூட்ரான்": "Neutron Atomic Nucleus",
        "அமிலம்": "Acids Chemical Reactions",
        "காரம்": "Bases Alkaline Solutions",
        "உப்பு": "Salts Neutralization",
        "வேதிவினை": "Chemical Reaction Equations",
        "துருப்பிடித்தல்": "Corrosion Rusting Oxidation",
        "தனிம வரிசை": "Periodic Table Classification of Elements",

        # Biology / Life Science / Botany / Zoology / Health
        "ஒளிச்சேர்க்கை": "Photosynthesis Plant Nutrition Autotrophic Getting to know plants",
        "சுவாசம்": "Respiration Breathing Cellular Respiration Organisms",
        "சுவாச நுண்குழல்": "Trachea Respiratory System",
        "நுரையீரல்": "Lungs Respiratory Organ Respiration",
        "நுரையீரல்கள்": "Lungs Respiratory Organ Respiration",
        "செவுள்கள்": "Gills Aquatic Respiration Fish Living Organisms",
        "தோல்": "Skin Respiration Excretion Living Organisms",
        "பல்லி": "Lizard Reptile Respiration Living Organisms",
        "பல்லிகள்": "Lizard Reptile Respiration Living Organisms",
        "தாவரம்": "Plants Flora Plant Life Getting to know plants",
        "தாவரங்கள்": "Plants Flora Plant Life Getting to know plants",
        "வேர்": "Root Plant Roots Water Absorption Root System",
        "நீரை உறிஞ்சும்": "Plant Roots Water Absorption Getting to know plants",
        "உறிஞ்சும் பகுதி": "Root Plant Water Absorption Getting to know plants",
        "தண்டு": "Stem Shoot Plant System Getting to know plants",
        "இலை": "Leaf Leaves Photosynthesis Stomata Getting to know plants",
        "இலைகள்": "Leaves Photosynthesis Stomata Getting to know plants",
        "மலர்": "Flower Reproduction in Plants Getting to know plants",
        "சல்லி வேர்த்தொகுப்பு": "Fibrous Root System Types of Roots",
        "ஆணிவேர்": "Tap Root System Types of Roots",
        "ஒரு வித்திலை": "Monocotyledon Monocot Plants Seed",
        "இரு வித்திலை": "Dicotyledon Dicot Plants Seed",
        "பாலைவனம்": "Desert Habitat Terrestrial Habitat Living Organisms Adaptations",
        "பாலைவனத் தாவரங்கள்": "Desert Plants Adaptations Living Organisms Habitat",
        "நீர்நிலைகள்": "Aquatic Habitat Living Organisms Characteristics and Habitats",
        "மலைகள்": "Mountain Habitat Living Organisms Characteristics and Habitats",
        "ஒட்டகம்": "Camel Desert Habitat Adaptations Living Organisms",
        "ஒட்டகங்களை": "Camel Desert Habitat Adaptations Living Organisms",
        "வைட்டமின்": "Vitamins Deficiency Diseases Components of Food Nutrition",
        "வைட்டமின் A": "Vitamin A Night blindness Deficiency Diseases Components of Food",
        "வைட்டமின் B": "Vitamin B Beri Beri Deficiency Diseases Components of Food",
        "வைட்டமின் C": "Vitamin C Scurvy Deficiency Diseases Components of Food",
        "வைட்டமின் D": "Vitamin D Rickets Deficiency Diseases Components of Food",
        "பெரி பெரி": "Beri Beri Vitamin B Deficiency Diseases Components of Food",
        "ஸ்கர்வி": "Scurvy Vitamin C Deficiency Diseases Components of Food",
        "ரிக்கெட்ஸ்": "Rickets Vitamin D Deficiency Diseases Components of Food",
        "கால்சியம்": "Calcium Minerals Components of Food Nutrition",
        "கார்போஹைட்ரேட்": "Carbohydrates Nutrients Components of Food",
        "புரதம்": "Proteins Nutrients Components of Food",
        "கொழுப்பு": "Fats Lipids Components of Food",
        "கொழுப்புச்சத்து": "Fats Lipids Components of Food Nutrition",
        "சரிவிகித உணவு": "Balanced Diet Components of Food Nutrition",
        "ஊட்டச்சத்து": "Nutrition Nutrients Components of Food",
        "தாது உப்புகள்": "Minerals Nutrition Components of Food",
        "பாரமீசியம்": "Paramecium Unicellular Organisms Cell Living Organisms",
        "அமீபா": "Amoeba Pseudopodia Locomotion Unicellular Living Organisms",
        "அமீபாவின்": "Amoeba Pseudopodia Locomotion Unicellular Living Organisms",
        "செல்": "Cell Structure and Functions Microscopic Organisms",
        "வைரஸ்": "Virus Microorganisms Disease",
        "வைரஸ்களால்": "Virus Microorganisms Disease",
        "ஓம்புயிரி": "Host Organism Virus Living Organisms",
        "செரிமானம்": "Digestive System Nutrition Digestion",
        "இதயம்": "Heart Circulatory System Blood Circulation",
        "இரத்தம்": "Blood Circulatory System",
        "நரம்பு": "Nervous System Nerves Brain",
        "மூளை": "Brain Nervous System Control Coordination",
        "ஹார்மோன்": "Hormones Endocrine System",
        "மரபியல்": "Genetics Heredity DNA Mendel",
        "சூழலியல்": "Ecosystem Environment Food Web",
        "அமில மழை": "Acid Rain Environmental Issues Pollution",
        "மகரந்தச் சேர்க்கை": "Pollination Reproduction in Plants Pollinators",
        "முதலுதவி": "First Aid Health and Hygiene Safety",
        "சுகாதாரம்": "Health and Hygiene Sanitation Cleanliness",
        "சுத்தம்": "Cleanliness Health and Hygiene Sanitation",
        "சுத்தமாகவும்": "Cleanliness Health and Hygiene Sanitation",
        "ஆரோக்கியம்": "Healthy Lifestyle Health and Hygiene Nutrition",
        "ஆரோக்கியமாகவும்": "Healthy Lifestyle Health and Hygiene Nutrition",
        "டெரிடோஃபைட்டுகள்": "Pteridophytes Plant Kingdom Cryptogams",
        "டெரிடோஃபைட்டுகளின்": "Pteridophytes Plant Kingdom Cryptogams",
        "உட்சுவாசம்": "Inhalation Breathing Respiration in Organisms",
        "உட்சுவாசத்திற்கும்": "Inhalation Breathing Respiration in Organisms",
        "வெளிச்சுவாசம்": "Exhalation Breathing Respiration in Organisms",
        "வெளிச்சுவாசத்திற்கும்": "Exhalation Breathing Respiration in Organisms",
        "பற்றுக் கம்பிகள்": "Tendrils Plant Adaptations Modifications of Stem Leaf",
        "பற்றுக்கம்பி": "Tendrils Plant Adaptations Modifications of Stem Leaf",
        "மாற்றுருக்கள்": "Modifications of Plants Root Stem Leaf Modifications Adaptations",
        "தாவரங்களின் மாற்றுருக்களை": "Modifications of Plants Root Stem Leaf Modifications Adaptations",
        "ஆலமரம்": "Banyan Tree Prop Roots Aerial Roots Root Modifications",
        "நெப்பன்தஸ்": "Nepenthes Pitcher Plant Insectivorous Plants Nutrition",
        "வெங்காயத்தாமரை": "Water Hyacinth Aquatic Plants Hydrophytes Adaptations",
        "தரைகீழ்த்தண்டு": "Underground Stem Modifications Vegetative Propagation Rhizome Tuber",
        "தரைகீழ்த்தண்டின்": "Underground Stem Modifications Vegetative Propagation Rhizome Tuber",
        "புகையிலை": "Tobacco Smoking Health Hazards Disease",
        "காசநோய்": "Tuberculosis Bacterial Disease Communicable Diseases Health and Hygiene",
        "பற்குழிகள்": "Dental Caries Tooth Decay Health and Hygiene",
        "இரத்தசோகை": "Anaemia Iron Deficiency Diseases Nutrition",
        "தொற்று நோய்கள்": "Infectious Diseases Communicable Diseases Health and Hygiene",
        "தொற்று நோய்": "Infectious Diseases Communicable Diseases Health and Hygiene",
        "காற்றேற்றம்": "Aeration Carbonated Water Solutions",
        "வழி அளவு": "Derived Quantities Derived Units Physical Quantities Measurement",
        "வழி அளவுகள்": "Derived Quantities Derived Units Physical Quantities Measurement",
        "வழி அலகுகள்": "Derived Quantities Derived Units Physical Quantities Measurement",
        "சேர்மங்களின் பண்புகள்": "Properties of Compounds Elements and Compounds",
        "சேர்மங்கள்": "Compounds Pure Substances Chemical Classification",
        "சேர்ம": "Compounds Pure Substances Chemical Classification",
        "தாவர": "Plants Plant Kingdom Botany Getting to know plants",
        "குப்பை": "Waste Management Garbage Disposal Biodegradable Non-biodegradable",
        "குப்பைகளோடு": "Waste Management Garbage Disposal Biodegradable Non-biodegradable",
        "பாக்டீரியா": "Bacteria Microorganisms Infectious Diseases Health and Hygiene",
        "பூஞ்சை": "Fungi Microorganisms Plant Kingdom Mycology",
        "ஆல்கா": "Algae Microorganisms Thallophyta Cryptogams",
        "புரோட்டோசோவா": "Protozoa Amoeba Paramecium Microorganisms",

        # Computer Science / ICT
        "கணினி": "Computers Introduction to Computers Hardware",
        "மின்னணு இயந்திரம்": "Electronic Machine Computer Fundamentals",
        "உள்ளீட்டு": "Input Devices Computer Hardware Keyboard Mouse",
        "உள்ளீட்டுக் கருவி": "Input Devices Computer Hardware Keyboard Mouse",
        "உள்ளீட்டுக் கருவிகள்": "Input Devices Computer Hardware Keyboard Mouse",
        "வெளியீட்டுக் கருவிகள்": "Output Devices Monitor Printer Computer",
        "நினைவகம்": "Computer Memory Storage RAM ROM",
        "ராஸ்டர்": "Raster Graphics Visual Communication Scratch",
        "வரைகலை": "Visual Communication Scratch Computer Science",

        # Heat and Thermal Physics
        "வெப்பக் கடத்த": "Heat Transfer Conduction Convection Radiation",
        "வெப்பக் கடத்தல்": "Heat Transfer Conduction Convection Radiation",
        "கலோரி": "Calorie Heat Heat and Temperature Measurement Thermal",
        "வெப்பம்": "Heat Temperature Thermal Energy",

        # Elements & Compounds
        "தாமிரம்": "Copper Metals Matter Around Us Elements",
        "அலுமினியம்": "Aluminium Metals Matter Around Us Elements",
        "தங்கம்": "Gold Metals Matter Around Us Elements",
        "இரும்பு": "Iron Metals Matter Around Us Elements",
        "பொட்டாசியம்": "Potassium Chemical Symbols Elements Periodic Table",
        "உட்கரு": "Nucleus Atomic Structure Solar System Model Electrons",

        # Mathematics
        "கூட்டல்": "Addition Arithmetic Sum",
        "கழித்தல்": "Subtraction Arithmetic Difference",
        "பெருக்கல்": "Multiplication Product Times",
        "வகுத்தல்": "Division Arithmetic Quotient Remainder",
        "பின்னம்": "Fractions Like Fractions",
        "தசமம்": "Decimals Decimal Fraction",
        "இயற்கணிதம்": "Algebra Expressions Polynomials",
        "இருபடிச் சமன்பாடு": "Quadratic Equations Roots",
        "நேரியல் சமன்பாடு": "Linear Equations Variables",
        "வடிவியல்": "Geometry Shapes Angles Lines",
        "முக்கோணம்": "Triangles Similarity Congruence",
        "வட்டம்": "Circles Tangents Radius Area",
        "பரப்பளவு": "Area Surface Area Mensuration",
        "சுற்றளவு": "Perimeter Circumference",
        "கனஅளவு": "Volume Mensuration Solids",
        "புள்ளியியல்": "Statistics Mean Median Mode",
        "நிகழ்தகவு": "Probability Random Events",
        "ஆயத்தொலை வடிவியல்": "Coordinate Geometry Distance Formula Midpoint",
        "முக்கோணவியல்": "Trigonometry Ratios Identities",
    }

    # Hindi Academic Vocabulary to Curriculum English Concepts
    HINDI_ACADEMIC_GLOSSARY = {
        # Chemistry
        "विलयन": "Solutions Raoult's Law Concentration",
        "अणुसंख्य गुणधर्म": "Colligative Properties Elevation of Boiling Point",
        "क्वथनांक": "Boiling Point Elevation Solutions",
        "हिमांक": "Freezing Point Depression Solutions",
        "परासरण दाब": "Osmotic Pressure Solutions",
        "वैद्युतरसायन": "Electrochemistry Galvanic Cell Nernst Equation",
        "रासायनिक बलगतिकी": "Chemical Kinetics Rate of Reaction Order",
        "संक्रमण तत्व": "Transition Elements d-Block Elements Sc Ti V Cr Mn Fe",
        "संक्रमण धातु": "Transition Metals d-Block Elements Sc Ti V Cr Mn Fe",
        "ऑक्सीकरण अवस्था": "Oxidation State Transition Metals d-Block",
        "उपसहसंयोजन": "Coordination Compounds Ligands Crystal Field",
        "हैलोऐल्केन": "Haloalkanes and Haloarenes Alkyl Halide Nucleophilic Substitution",
        "ऐल्कोहॉल": "Alcohols Phenols and Ethers",
        "ईथर": "Ethers Alcohols Phenols Boiling Points",
        "ऐल्डिहाइड": "Aldehydes Ketones Carboxylic Acids",
        "ऐमीन": "Amines Gabriel Phthalimide Synthesis Primary Amines",
        "ऐनिलीन": "Aniline Amines Bromination Acetylation",
        "अभिकथन": "Assertion Reason",
        "कारण": "Assertion Reason",
        "जैव-अणु": "Biomolecules Carbohydrates Polysaccharide Glucose Cellulose",
        "पॉलीसैकेराइड": "Polysaccharide Biomolecules Carbohydrates Cellulose",
        "बहुलक": "Polymers Synthetic Polymers",

        # Physics
        "विद्युत आवेश": "Electric Charges and Fields Coulomb's Law",
        "स्थिरविद्युत विभव": "Electrostatic Potential and Capacitance",
        "विद्युत धारा": "Current Electricity Ohm's Law Resistors",
        "गतिमान आवेश": "Moving Charges and Magnetism Biot-Savart Law",
        "चुंबकत्व": "Magnetism and Matter Magnetic Field Lines",
        "वैद्युतचुंबकीय प्रेरण": "Electromagnetic Induction Faraday's Law",
        "प्रत्यावर्ती धारा": "Alternating Current AC Voltage Phasor Diagram",
        "किरण प्रकाशिकी": "Ray Optics and Optical Instruments Reflection Refraction Lens",
        "तरंग प्रकाशिकी": "Wave Optics Interference Diffraction Young's Double Slit",
        "विकिरण तथा द्रव्य": "Dual Nature of Radiation and Matter Photoelectric Effect",
        "परमाणु": "Atoms Bohr Model Hydrogen Spectrum",
        "नाभिक": "Nuclei Mass Defect Binding Energy Nuclear Fission",
        "अर्धचालक": "Semiconductor Electronics p-n Junction Diode Logic Gates",

        # Mathematics
        "संबंध एवं फलन": "Relations and Functions",
        "प्रतिलोम त्रिकोणमितीय": "Inverse Trigonometric Functions",
        "आव्यूह": "Matrices Matrix Operations",
        "सारणिक": "Determinants Properties Area of Triangle",
        "सांतत्य तथा अवकलनीयता": "Continuity and Differentiability Derivatives",
        "अवकलज के अनुप्रयोग": "Applications of Derivatives Maxima Minima Tangent",
        "समाकलन": "Integrals Definite Integrals Integration",
        "समाकलनों के अनुप्रयोग": "Applications of the Integrals Area under Curves",
        "अवकल समीकरण": "Differential Equations Order Degree",
        "सदिश बीजगणित": "Vector Algebra Dot Product Cross Product",
        "त्रिविमीय ज्यामिति": "Three Dimensional Geometry Direction Cosines Lines Planes",
        "रैखिक प्रोग्रामन": "Linear Programming Constraints Feasible Region",
        "प्रायिकता": "Probability Conditional Probability Bayes Theorem",
    }

    TAMIL_CHAR_RE = re.compile(r'[\u0B80-\u0BFF]')
    HINDI_CHAR_RE = re.compile(r'[\u0900-\u097F]')

    @classmethod
    def is_tamil(cls, text: str) -> bool:
        """Check if text contains Tamil characters."""
        return bool(cls.TAMIL_CHAR_RE.search(text))

    @classmethod
    def is_hindi(cls, text: str) -> bool:
        """Check if text contains Hindi characters."""
        return bool(cls.HINDI_CHAR_RE.search(text))

    @classmethod
    def enrich_regional_query(cls, text: str) -> Tuple[str, List[str]]:
        """
        Extract Tamil or Hindi academic terms and augment query with corresponding English concept tokens.
        Returns: (augmented_query, matched_terms)
        """
        matched_concepts = []
        matched_terms = []

        if cls.is_tamil(text):
            # Sort keys by length descending to match longest phrases first
            sorted_tamil = sorted(cls.TAMIL_ACADEMIC_GLOSSARY.keys(), key=len, reverse=True)
            for tamil_term in sorted_tamil:
                if tamil_term in text:
                    matched_terms.append(tamil_term)
                    matched_concepts.append(cls.TAMIL_ACADEMIC_GLOSSARY[tamil_term])

        if cls.is_hindi(text):
            sorted_hindi = sorted(cls.HINDI_ACADEMIC_GLOSSARY.keys(), key=len, reverse=True)
            for hindi_term in sorted_hindi:
                if hindi_term in text:
                    matched_terms.append(hindi_term)
                    matched_concepts.append(cls.HINDI_ACADEMIC_GLOSSARY[hindi_term])

        if matched_concepts:
            # Deduplicate concept tokens while preserving order
            unique_concept_tokens = []
            seen_tokens = set()
            for concept_block in matched_concepts:
                for token in concept_block.split():
                    token_lower = token.lower()
                    if token_lower not in seen_tokens:
                        seen_tokens.add(token_lower)
                        unique_concept_tokens.append(token)

            concept_str = " ".join(unique_concept_tokens)
            augmented = f"{text} [Academic Concepts: {concept_str}]"
            return augmented, matched_terms

        return text, []

    @classmethod
    def enrich_tamil_query(cls, text: str) -> Tuple[str, List[str]]:
        """Backward compatibility alias."""
        return cls.enrich_regional_query(text)


# =============================================================================
# QP TOPIC MAPPER V3 — Main Engine
# =============================================================================

class QPTopicMapperV3(BaseEngine):
   

    def __init__(self, repo_path: Optional[str] = None, onnx_model_dir: Optional[str] = None,
                 cache_path: Optional[str] = None, use_pytorch_fallback: bool = True):
        super().__init__(name="QPTopicMapperV3", failure_threshold=5)
      
        project_root = _find_workspace_root()

        # Resolve repository path - Strictly topic_repository_complete.xlsx or master taxonomy
        if repo_path is None:
            env_repo = os.environ.get("STUDIQS_TOPIC_REPO")
            if env_repo and os.path.exists(env_repo):
                repo_path = env_repo
            else:
                candidate_paths = [
                    project_root / "data" / "inputs" / "topic_repository_complete.xlsx",
                    project_root / "data" / "curriculum_repository" / "master" / "master_curriculum_classes_1_to_12.xlsx",
                    project_root / "src" / "smartparent" / "db" / "smartparent_master_repository_kb.xlsx",
                ]
                repo_path = None
                for cand in candidate_paths:
                    if cand.exists():
                        repo_path = str(cand)
                        break
                if repo_path is None:
                    repo_path = str(candidate_paths[0])
        self.repo_path = repo_path

        # Check BGE model
        bge_dir = project_root / "models" / "bge_small_en_v1_5_onnx"
        bge_cache = project_root / "cache" / "topic_embeddings_bge_small.npy"
        if onnx_model_dir is None and bge_dir.exists() and bge_cache.exists():
            onnx_model_dir = str(bge_dir)
            cache_path = str(bge_cache)
            print(f"[QPMapperV3] Using BAAI/bge-small-en-v1.5 INT8 ONNX Engine with precomputed cache ({bge_cache.name})")

        # Resolve cache path - topic_repository_complete_embeddings_onnx.npy
        if cache_path is None:
            repo_base = os.path.splitext(os.path.basename(self.repo_path))[0]
            cache_path = str(project_root / "data" / "inputs" / f"{repo_base}_embeddings_onnx.npy")
        self.cache_path = cache_path

        # Stopwords
        self._stop = set(stopwords.words("english"))
        self._stop.update({
            'find', 'what', 'the', 'and', 'for', 'with', 'give', 'write',
            'explain', 'define', 'state', 'describe', 'calculate', 'prove',
            'that', 'how', 'does', 'are', 'example', 'its', 'from', 'this',
            'which', 'following', 'following:', 'below', 'answer', 'question',
            'mark', 'marks', 'given', 'show', 'also', 'using', 'hence'
        })

        # Initialize ONNX Embedding Engine
        self._use_onnx = True
        self._embed_engine = None
        try:
            print(f"[QPMapperV3] Loading ONNX embedding engine (INT8 quantized, ~22-34 MB)...")
            self._embed_engine = ONNXEmbeddingEngine(model_dir=onnx_model_dir)
            self.embed_dim = self._embed_engine.embed_dim
            print(f"[QPMapperV3] ONNX engine loaded successfully.")
        except Exception as e:
            print(f"[QPMapperV3] ONNX load failed: {e}")
            if use_pytorch_fallback:
                print(f"[QPMapperV3] Falling back to SentenceTransformers (PyTorch)...")
                from sentence_transformers import SentenceTransformer
                self._st_model = SentenceTransformer("all-MiniLM-L6-v2")
                self.embed_dim = self._st_model.get_embedding_dimension() if hasattr(self._st_model, 'get_embedding_dimension') else self._st_model.get_sentence_embedding_dimension()
                self._use_onnx = False
            else:
                raise RuntimeError(f"ONNX engine failed and PyTorch fallback disabled: {e}")

        # Load topic repository
        print(f"[QPMapperV3] Loading repository: {os.path.basename(self.repo_path)}")
        self._load_repository()
        print(f"[QPMapperV3] Ready: {len(self.topics_metadata)} topics | "
              f"Grades: {sorted(set(t['class'] for t in self.topics_metadata))} | "
              f"Engine: {'ONNX (BGE)' if (self._use_onnx and getattr(self._embed_engine, 'is_bge', False)) else ('ONNX (MiniLM)' if self._use_onnx else 'PyTorch')}")

    def _encode(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        """Unified encoding interface — uses ONNX or PyTorch fallback with BGE query instruction support."""
        if self._use_onnx and self._embed_engine:
            if getattr(self._embed_engine, 'is_bge', False):
                bge_texts = [
                    f"Represent this sentence for searching relevant passages: {t}"
                    if not t.startswith("Represent this sentence") else t
                    for t in texts
                ]
                return self._embed_engine.encode(bge_texts, batch_size=batch_size, normalize=True)
            return self._embed_engine.encode(texts, batch_size=batch_size, normalize=True)
        else:
            return self._st_model.encode(texts, normalize_embeddings=True, show_progress_bar=False).astype("float32")

    def is_subject_in_repository(self, subject: str) -> bool:
        """Checks if a question paper subject exists in the curriculum topic repository."""
        if not subject or str(subject).strip().lower() in ("unknown", "error", ""):
            return False
        s_norm = self._normalize_subject(subject).lower()
        return s_norm in self.known_subjects

    @staticmethod
    def _normalize_board(board_raw: Any) -> str:
        """Normalizes board into CBSE or State Board strictly."""
        if not board_raw:
            return "Unknown"
        b = str(board_raw).strip().lower()
        if "cbse" in b:
            return "CBSE"
        if any(k in b for k in ["state", "tn", "samacheer", "tamil nadu", "tamilnadu"]):
            return "State Board"
        return "Unknown"

    def _load_repository(self):
        """Load topic repository and build indices (BM25 + Dense embeddings)."""
        if not os.path.exists(self.repo_path):
            raise FileNotFoundError(f"Topic repository not found: {self.repo_path}")

        self.full_df = pd.read_excel(self.repo_path)
        for col in ['Class', 'Subject', 'Board', 'Chapter', 'Topic', 'Topic_ID']:
            self.full_df[col] = self.full_df[col].astype(str).str.strip()
        self.full_df['Class'] = self.full_df['Class'].str.upper()

        # Build metadata and corpus
        self.topics_metadata = []
        self.corpus_texts = []
        for _, row in self.full_df.iterrows():
            chapter = row['Chapter']
            topic = row['Topic']
            doc_text = f"{chapter} - {topic}. {topic} {topic}."
            self.topics_metadata.append({
                "board": row['Board'], "class": row['Class'], "subject": row['Subject'],
                "chapter": chapter, "topic": topic, "topic_id": row['Topic_ID'],
                "doc_text": doc_text
            })
            self.corpus_texts.append(doc_text)

        self.known_subjects = {c["subject"].lower() for c in self.topics_metadata}
        # Add standard aliases
        if "maths" in self.known_subjects:
            self.known_subjects.add("mathematics")

        # BM25 Lexical Index
        self.tokenized_corpus = [word_tokenize(t.lower()) for t in self.corpus_texts]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

        # Dense Embeddings — load from precomputed cache or compute fresh
        if os.path.exists(self.cache_path):
            self.dense_embs = np.load(self.cache_path).astype("float32")
            if self.dense_embs.shape[0] != len(self.corpus_texts):
                print(f"[QPMapperV3] Cache shape mismatch ({self.dense_embs.shape[0]} vs {len(self.corpus_texts)}). Recomputing...")
                self._compute_and_cache_embeddings()
            else:
                print(f"[QPMapperV3] Loaded precomputed embeddings from cache ({self.dense_embs.shape})")
        else:
            self._compute_and_cache_embeddings()

    def _compute_and_cache_embeddings(self):
        """Compute dense embeddings for all curriculum topics and save to .npy cache."""
        import time
        print(f"[QPMapperV3] Computing embeddings for {len(self.corpus_texts)} topics...")
        t0 = time.time()
        self.dense_embs = self._encode(self.corpus_texts, batch_size=128)
        duration = time.time() - t0
        print(f"[QPMapperV3] Computed in {duration:.1f}s ({len(self.corpus_texts)/duration:.0f} topics/sec)")
        np.save(self.cache_path, self.dense_embs)
        print(f"[QPMapperV3] Saved cache: {self.cache_path} ({os.path.getsize(self.cache_path)/(1024*1024):.1f} MB)")

    # =========================================================================
    # GRADE & SUBJECT NORMALIZATION
    # =========================================================================

    @staticmethod
    def _normalize_grade(grade_raw: Any) -> str:
        if not grade_raw:
            return "Unknown"
        g = str(grade_raw).strip().upper()
        if "LKG" in g or "L.K.G" in g: return "LKG"
        if "UKG" in g or "U.K.G" in g: return "UKG"
        if "PRE" in g or "KG" in g: return "LKG"
        roman_map = {
            "XII": "12", "XI": "11", "X": "10", "IX": "9", "VIII": "8",
            "VII": "7", "VI": "6", "V": "5", "IV": "4", "III": "3", "II": "2", "I": "1"
        }
        for r, d in roman_map.items():
            if re.search(r'\b' + r + r'\b', g):
                return d
        digits = re.findall(r'\b\d+\b', g)
        return digits[0] if digits else g

    @staticmethod
    def _normalize_subject(subject_raw: Any) -> str:
        if not subject_raw:
            return "Unknown"
        s = str(subject_raw).strip().lower()
        if "computer" in s or "prog" in s or "inform" in s or "ansi" in s: return "Computer Science"
        if "social" in s or "sst" in s or "history" in s or "geography" in s or "civics" in s: return "Social Science"
        if "business math" in s or "business stat" in s: return "Business Maths and Statistics"
        if "math" in s: return "Maths"
        if "sci" in s: return "Science"
        if "phy" in s: return "Physics"
        if "chem" in s: return "Chemistry"
        if "bio" in s: return "Biology"
        if "evs" in s or "environment" in s: return "EVS"
        if "eng" in s: return "English"
        if "eco" in s: return "Economics"
        if "acc" in s: return "Accountancy"
        if "bus" in s or "comm" in s or "வணிக" in s: return "Business Studies"
        if "tamil" in s or "தமிழ்" in s: return "Tamil"
        if "hindi" in s or "हिन्दी" in s: return "Hindi"
        return subject_raw

    # =========================================================================
    # CORE MAPPING — Single Question
    # =========================================================================

    def map_question(self, raw_question_text: str,
                     subject: str = "Unknown",
                     target_grade: str = "Unknown",
                     board: str = "Unknown",
                     diagram_labels: Optional[List[str]] = None) -> Dict[str, Any]:
      
        if not raw_question_text or not raw_question_text.strip():
            return self._empty_result(raw_question_text, "Empty question text",
                                      subject=subject, target_grade=target_grade, board=board, status="unmapped")

        # Step 0: Fast Guardrail for Out-of-Knowledge-Base Subjects
        norm_grade = self._normalize_grade(target_grade)
        norm_subj = self._normalize_subject(subject)
        norm_board = self._normalize_board(board)

        if norm_subj != "Unknown" and not self.is_subject_in_repository(norm_subj):
            return self._empty_result(
                question_text=raw_question_text,
                reason=f"Subject '{norm_subj}' is not present in curriculum knowledge base",
                subject=norm_subj,
                target_grade=norm_grade,
                board=norm_board,
                status="unmapped"
            )

        # Step 1: Clean Stem
        clean_res = QuestionStemCleaner.clean(raw_question_text)
        cleaned_stem = clean_res["cleaned_stem"]
        if diagram_labels:
            cleaned_stem += f" [Diagram Context: {' '.join(diagram_labels)}]"

        # Step 2: Regional Bilingual Enrichment (Tamil & Hindi)
        enriched_stem, _ = BilingualConceptBridge.enrich_regional_query(cleaned_stem)

        # Step 3: Sub-Domain Routing
        detected_subdomain = SubjectDomainRouter.detect_subdomain(subject, enriched_stem)

        # Step 4b: Academic Concept Enrichment (STEM curriculum terminology bridge)
        enriched_stem = AcademicConceptBridge.enrich_academic_query(enriched_stem, norm_subj)

        # Step 5: Dense + BM25 Scoring
        search_query = enriched_stem
        q_tokens = [w for w in word_tokenize(search_query.lower()) if len(w) > 1 or w in {'x', 'y', 'z'}]
        q_emb = self._encode([search_query])

        # Dense cosine similarity
        dense_sims = np.dot(self.dense_embs, q_emb.T).flatten()

        # BM25 lexical scores
        bm25_raw = self.bm25.get_scores(q_tokens) if q_tokens else np.zeros(len(self.corpus_texts))
        bm25_max = bm25_raw.max() if len(bm25_raw) > 0 and bm25_raw.max() > 0 else 1.0
        bm25_sims = bm25_raw / bm25_max

        # Step 6: Hard Masking for Board, Grade, and Subject
        # Strict Board Isolation: CBSE question papers MUST ONLY map to CBSE topics, State Board to State Board
        board_match_exists = False
        grade_match_exists = False

        if norm_board in ("CBSE", "State Board"):
            board_candidates = [cand for cand in self.topics_metadata if cand["board"] == norm_board]
            board_match_exists = len(board_candidates) > 0

            if board_match_exists and norm_grade != "Unknown" and norm_grade.isdigit():
                grade_candidates = [c for c in board_candidates if c["class"] == norm_grade]
                grade_match_exists = len(grade_candidates) > 0

        for idx, cand in enumerate(self.topics_metadata):
            c_subj = cand["subject"]
            c_board = cand["board"]
            c_class = cand["class"]

            # Subject Compatibility Check
            if norm_subj != "Unknown" and not SubjectCompatibilityEngine.is_compatible(norm_subj, c_subj, norm_grade):
                dense_sims[idx] = -100.0
                bm25_sims[idx] = 0.0
                continue

            # Strict Board Isolation
            if norm_board in ("CBSE", "State Board") and board_match_exists:
                if c_board != norm_board:
                    dense_sims[idx] = -100.0
                    bm25_sims[idx] = 0.0
                    continue

            # Strict Grade Isolation
            if grade_match_exists:
                if c_class != norm_grade:
                    dense_sims[idx] = -100.0
                    bm25_sims[idx] = 0.0
                    continue

        if dense_sims.max() <= -50.0:
            return self._empty_result(
                question_text=raw_question_text,
                reason=f"No matching curriculum topics found in knowledge base for Board='{norm_board}', Grade='{norm_grade}', Subject='{norm_subj}'",
                subject=norm_subj,
                target_grade=norm_grade,
                board=norm_board,
                status="unmapped"
            )

        # Step 7: Reciprocal Rank Fusion (RRF)
        dense_ranks = np.argsort(np.argsort(-dense_sims))
        bm25_ranks = np.argsort(np.argsort(-bm25_sims))
        rrf_scores = (1.0 / (60.0 + dense_ranks)) + (1.0 / (60.0 + bm25_ranks))
        rrf_max = rrf_scores.max() if rrf_scores.max() > 0 else 1.0
        norm_rrf = rrf_scores / rrf_max

        # Step 8: Grade + Domain + Keyword Scoring & Concept Disambiguation
        content_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', cleaned_stem.lower())) - self._stop
        final_candidates = []
        top_prelim_indices = np.argsort(-norm_rrf)[:100]

        for c_idx in top_prelim_indices:
            if dense_sims[c_idx] <= -50.0:
                continue

            cand = self.topics_metadata[c_idx]
            base_score = float(norm_rrf[c_idx])
            cosine_score = float(dense_sims[c_idx])
            bm25_score = float(bm25_sims[c_idx])

            c_class, c_subj = cand["class"], cand["subject"]
            c_topic, c_chap = cand["topic"], cand["chapter"]

            # Double-check subject and board compatibility
            if norm_subj != "Unknown" and not SubjectCompatibilityEngine.is_compatible(norm_subj, c_subj, norm_grade):
                continue
            if norm_board in ("CBSE", "State Board") and cand["board"] != norm_board:
                continue
            if grade_match_exists and c_class != norm_grade:
                continue

            bonus, penalty = 0.0, 0.0

            # Grade Alignment (for soft cases when grade_match_exists is False)
            if norm_grade != "Unknown":
                if c_class == norm_grade:
                    bonus += 0.40
                elif c_class.isdigit() and norm_grade.isdigit() and abs(int(c_class) - int(norm_grade)) == 1:
                    penalty += 0.20
                else:
                    penalty += 0.60

            # Subject Alignment
            if norm_subj != "Unknown" and norm_subj.lower() in c_subj.lower():
                bonus += 0.25

            # Domain Sub-Routing
            if detected_subdomain:
                bonus, penalty = self._apply_subdomain_scoring(
                    detected_subdomain, c_chap, c_topic, bonus, penalty
                )

            # Multi-token Keyword Overlap
            t_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', c_topic.lower())) - self._stop
            ch_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', c_chap.lower())) - self._stop
            matched_t = content_words & t_words
            matched_ch = content_words & ch_words

            if len(t_words) <= 1:
                keyword_bonus = 0.02 if (len(matched_t) == 1 and len(matched_ch) == 0 and len(content_words) > 3) else (0.10 if matched_t else 0.0)
            else:
                keyword_bonus = (len(matched_t) / len(t_words)) * 0.20
            if matched_ch:
                keyword_bonus += 0.10

            # Contextual Disambiguation: penalize weak single-word matches
            if matched_t and len(matched_t) == 1:
                weak_word = list(matched_t)[0]
                generic_connectors = {
                    'path', 'line', 'point', 'form', 'process', 'system', 'type', 'types',
                    'part', 'parts', 'unit', 'units', 'change', 'changes', 'effect', 'effects',
                    'method', 'structure', 'function', 'relation', 'properties', 'nature',
                    'moving', 'text', 'number', 'object', 'area', 'speed', 'body', 'time'
                }
                if weak_word.lower() in generic_connectors:
                    domain_cues = {
                        'measurement': {'radius', 'circumference', 'circular', 'diameter', 'perimeter', 'area', 'volume', 'length', 'breadth', 'height'},
                        'motion': {'velocity', 'acceleration', 'speed', 'moving', 'particle', 'displacement', 'distance', 'circular'},
                        'electricity': {'current', 'voltage', 'resistance', 'circuit', 'battery', 'charge', 'ohm', 'ampere'},
                        'optics': {'lens', 'mirror', 'refraction', 'reflection', 'focal', 'image', 'prism', 'spectrum'},
                    }
                    q_domain_hits = set()
                    for domain, cues in domain_cues.items():
                        if content_words & cues:
                            q_domain_hits.add(domain)

                    if q_domain_hits:
                        topic_chapter_text = f"{c_topic} {c_chap}".lower()
                        domain_aligned = any(cue_word in topic_chapter_text for d in q_domain_hits for cue_word in domain_cues[d])
                        if not domain_aligned:
                            penalty += 0.50

            # Polysemous & Concept Specific Disambiguation
            t_and_c = f"{c_topic} {c_chap}".lower()

            # 1. Quadratic Equations vs. Arithmetic Progressions
            is_quadratic_q = any(w in content_words for w in ['quadratic', 'discriminant']) or \
                             ('consecutive' in content_words and 'product' in content_words) or \
                             ('roots' in content_words and 'equation' in content_words)
            if is_quadratic_q:
                if 'arithmetic progression' in t_and_c or 'ap' in t_words:
                    penalty += 0.90
                if 'quadratic' in t_and_c:
                    bonus += 0.35

            is_ap_q = 'arithmetic' in content_words or ('progression' in content_words and 'terms' in content_words) or \
                      ('common' in content_words and 'difference' in content_words)
            if is_ap_q:
                if 'quadratic' in t_and_c:
                    penalty += 0.90
                if 'arithmetic progression' in t_and_c:
                    bonus += 0.35

            # 2. Control and Coordination (Human Brain / Nervous System vs other chapters)
            is_brain_q = any(w in content_words for w in ['brain', 'cerebrum', 'cerebellum', 'medulla', 'pons', 'neuron', 'synapse', 'cns']) or \
                         ('walking' in content_words and 'line' in content_words) or ('reflex' in content_words and 'action' in content_words)
            if is_brain_q:
                if not any(w in t_and_c for w in ['nervous', 'brain', 'control and coordination', 'reflex']):
                    penalty += 0.90
                else:
                    bonus += 0.40

            # 3. Electrostatics / Dipole vs Current Electricity
            is_dipole_q = 'dipole' in content_words or ('electrostatic' in content_words and 'potential' in content_words)
            if is_dipole_q:
                if 'dipole' in t_and_c or 'electrostat' in t_and_c:
                    bonus += 0.30

            # 4. Standard chemistry/physics polysemous filters
            if "equilibrium" in content_words:
                has_phy_cues = any(w in content_words for w in ['charge', 'charges', 'point', 'electric', 'collinear', 'coulomb', 'force'])
                if has_phy_cues and any(ck in t_and_c for ck in ['chemical', 'reaction', 'reactions']):
                    penalty += 0.90
            if "bacteria" in content_words:
                has_disease_cues = any(w in content_words for w in ['typhoid', 'hepatitis', 'tuberculosis', 'cholera', 'disease', 'infection', 'pathogen'])
                if has_disease_cues and any(pk in t_and_c for pk in ['polymer', 'plastic', 'eating']):
                    penalty += 0.90
            if any(rw in content_words for rw in ['roots', 'root']):
                has_botany_cues = any(w in content_words for w in ['betel', 'pepper', 'climbing', 'plant', 'plants', 'stem', 'leaf'])
                if has_botany_cues and any(mk in t_and_c for mk in ['metal', 'metals', 'non-metal', 'non-metals', 'algebra']):
                    penalty += 0.90

            # Final Combined Score
            combined = (0.50 * cosine_score) + (0.30 * base_score) + (0.20 * bm25_score) + bonus + keyword_bonus - penalty
            if norm_grade != "Unknown" and c_class == norm_grade:
                combined *= 1.15
            combined = max(0.0, min(1.0, combined))

            final_candidates.append({
                "cand": cand, "score": combined,
                "cosine": cosine_score, "bm25": bm25_score
            })

        # Step 9: Select Best
        final_candidates.sort(key=lambda x: x["score"], reverse=True)
        best = final_candidates[0] if final_candidates else None

        if not best or best["score"] < 0.35:
            return self._empty_result(
                question_text=raw_question_text,
                reason=f"Confidence below threshold (score={best['score']:.4f} < 0.35)" if best else "No candidates",
                subject=norm_subj,
                target_grade=norm_grade,
                board=norm_board,
                status="unmapped"
            )

        # Step 10: Confidence Calibration
        best_cand = best["cand"]
        score_val = round(float(best["score"]), 4)

        if score_val >= 0.65:
            conf_level, status, review = "high", "mapped", False
        elif score_val >= 0.40:
            conf_level, status, review = "medium", "mapped", False
        else:
            conf_level, status, review = "low", "manual_review", True

        return {
            "question_text": raw_question_text,
            "subject": best_cand["subject"],
            "class": best_cand["class"],
            "board": best_cand["board"],
            "chapter": best_cand["chapter"],
            "topic": best_cand["topic"],
            "topic_id": best_cand["topic_id"],
            "confidence_score": score_val,
            "confidence_level": conf_level,
            "mapping_status": status,
            "manual_review_required": review,
            "reason": f"Hybrid RRF Score: {score_val:.4f} (Cosine: {best['cosine']:.4f}, BM25: {best['bm25']:.4f})"
        }

    @staticmethod
    def _apply_subdomain_scoring(subdomain: str, chapter: str, topic: str,
                                  bonus: float, penalty: float) -> Tuple[float, float]:
        """Apply sub-domain specific scoring boosts and penalties."""
        cl = chapter.lower()
        tl = topic.lower()

        # Universal: penalize non-natural-science chapters regardless of subdomain
        NON_SCIENCE_CHAPTERS = ["visual communication", "digital painting", "computer", "word processor", "spreadsheet"]
        if any(ns in cl for ns in NON_SCIENCE_CHAPTERS):
            penalty += 0.80

        # Science Sub-Domains
        if subdomain == "Biology":
            if any(w in cl for w in [
                "pressure", "light", "electricity", "motion", "sound", "force", "acids",
                "metals", "non-metals", "polymer", "plastics", "changes around", "matter around",
                "atomic", "chemical", "reactions", "states of water", "heat"
            ]):
                penalty += 0.85
            elif any(w in cl for w in [
                "life", "control", "organism", "reproduction", "heredity", "cell", "living",
                "plant", "health", "hygiene", "microorganisms", "food"
            ]):
                bonus += 0.40
        elif subdomain == "Physics":
            if any(w in cl for w in ["cell", "reproduction", "heredity", "life", "nutrition", "acid", "carbon", "reaction", "equilibrium", "polymer", "periodic"]):
                penalty += 0.85
            if any(w in cl for w in ["measurement", "motion", "force", "pressure", "electric", "current", "charge", "magnetic", "light", "optics"]):
                bonus += 0.35
            if "light" in cl:
                has_optics_cues = any(w in tl.lower() for w in [
                    "reflection", "refraction", "lens", "mirror", "focal", "image",
                    "prism", "spectrum", "dispersion", "dioptre", "ray diagram"
                ])
                if not has_optics_cues:
                    penalty += 0.25
        elif subdomain == "Chemistry":
            if any(w in cl for w in ["cell", "reproduction", "heredity", "motion", "sound", "light", "electricity", "magnetism", "plant"]):
                penalty += 0.85
            elif any(w in cl for w in ["chemical", "acid", "base", "salt", "metal", "non-metal", "carbon", "periodic", "matter", "atomic", "solution"]):
                bonus += 0.35

        # Maths Sub-Domains
        elif subdomain == "Trigonometry":
            if any(w in cl or w in tl for w in ["trigonometr", "identit", "ratio"]):
                bonus += 0.45
            else:
                penalty += 0.35
        elif subdomain == "Algebra":
            if any(w in cl for w in ["algebra", "polynomial", "quadratic", "linear", "equation"]):
                bonus += 0.30
            elif any(w in cl for w in ["triangle", "circle", "coordinate", "statistics"]):
                penalty += 0.25
        elif subdomain == "Geometry":
            if any(w in cl for w in ["triangle", "circle", "geometry", "congruen", "similar"]):
                bonus += 0.30
        elif subdomain == "Coordinate Geometry":
            if any(w in cl for w in ["coordinate", "distance", "midpoint", "section"]):
                bonus += 0.35
            elif any(w in cl for w in ["trigonometr", "algebra"]):
                penalty += 0.20
        elif subdomain == "Mensuration":
            if any(w in cl for w in ["mensur", "surface", "volume", "area"]):
                bonus += 0.30
        elif subdomain == "Statistics & Probability":
            if any(w in cl for w in ["statistic", "probabilit", "data"]):
                bonus += 0.35
            else:
                penalty += 0.25

        return bonus, penalty

    # =========================================================================
    # BATCH MAPPING — Full Question Paper
    # =========================================================================

    def map_question_paper(self, qp_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Map all questions in a structured question paper object."""
        exam_info = qp_data.get("exam_info", {})
        target_grade = exam_info.get("grade", qp_data.get("class", "Unknown"))
        subject = exam_info.get("subject", qp_data.get("subject", "Unknown"))
        board = exam_info.get("board", qp_data.get("board", "Unknown"))

        all_qs = []
        if "sections" in qp_data:
            for sec in qp_data.get("sections", []):
                for q in sec.get("questions", []):
                    all_qs.append((sec, q))
        elif "questions" in qp_data:
            for q in qp_data.get("questions", []):
                all_qs.append(({}, q))

        results = []
        print(f"[QPMapperV3] Mapping {len(all_qs)} questions | Grade: {target_grade} | Subject: {subject} | Board: {board}")

        for idx, (sec, q) in enumerate(all_qs, 1):
            q_text = q.get("question_text") or q.get("question") or ""
            q_num = q.get("question_number") or q.get("question_no") or idx
            q_marks = q.get("marks") or sec.get("marks_per_question") or 1.0
            q_diag_labels = q.get("diagram_labels") or []
            q_has_diag = q.get("has_diagram", False)
            q_diag_img = q.get("diagram_image", "")

            mapped = self.map_question(
                raw_question_text=q_text,
                subject=subject,
                target_grade=target_grade,
                board=board,
                diagram_labels=q_diag_labels
            )
            mapped["question_no"] = q_num
            mapped["max_marks"] = float(q_marks)
            if q_has_diag:
                mapped["has_diagram"] = True
                mapped["diagram_image"] = q_diag_img
                mapped["diagram_labels"] = q_diag_labels
            results.append(mapped)

        return results

    def _empty_result(self, question_text: str, reason: str,
                      subject: str = "Unknown", target_grade: str = "Unknown",
                      board: str = "Unknown", status: str = "unmapped") -> Dict[str, Any]:
        return {
            "question_text": question_text,
            "subject": subject,
            "class": target_grade,
            "board": board,
            "chapter": "Unmapped (Subject Not In Knowledge Base)" if "not in" in reason.lower() else "Unmapped",
            "topic": "Unmapped Topic",
            "topic_id": "UNMAPPED",
            "confidence_score": 0.0,
            "confidence_level": "none",
            "mapping_status": status,
            "manual_review_required": True,
            "reason": reason
        }

    # =========================================================================
    # PRODUCTION INTERFACE COMPATIBILITY (Drop-in for QuestionTopicMappingEngine)
    # =========================================================================

    def process_file(self, file_path: str, force_ocr: bool = False) -> List[Dict[str, Any]]:
        
        print(f"\n[QPMapperV3] Processing File: {file_path}")
        
        filename = os.path.basename(file_path).lower()
        grade_match = re.search(r'(?:class(?:_|-|\s)*)?(\d+)(?:\s*(?:th|st|nd|rd))?', filename)
        grade = grade_match.group(1) if grade_match else "Unknown"
        
        board = "State Board" if any(x in filename for x in ["tn", "state", "samacheer"]) else ("CBSE" if "cbse" in filename else "Unknown")
        
        subject = "Unknown"
        if "english" in filename or "eng" in filename: subject = "English"
        elif "science" in filename or "sci" in filename or "evs" in filename: subject = "Science"
        elif "math" in filename: subject = "Mathematics"
        elif "chem" in filename: subject = "Chemistry"
        elif "phy" in filename: subject = "Physics"
        elif "bio" in filename: subject = "Biology"
        elif "account" in filename: subject = "Accountancy"
        elif "business" in filename or "bst" in filename: subject = "Business Studies"
        elif "eco" in filename: subject = "Economics"
        elif "comp" in filename or "cs" in filename: subject = "Computer Science"
        elif "tamil" in filename: subject = "Tamil"
        elif "hindi" in filename: subject = "Hindi"

        if file_path.lower().endswith(".json"):
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            if isinstance(raw_data, dict):
                if "board" in raw_data: board = raw_data["board"]
                if "class" in raw_data: grade = str(raw_data["class"])
                if "subject" in raw_data: subject = raw_data["subject"]
                
                if "question_topic_mapping" in raw_data:
                    extracted = [
                        {
                            "question_no": item.get("question_no", idx),
                            "question": item.get("question_text", ""),
                            "marks": item.get("max_marks", 1.0)
                        }
                        for idx, item in enumerate(raw_data["question_topic_mapping"], 1)
                    ]
                elif "questions" in raw_data:
                    extracted = raw_data["questions"]
                else:
                    extracted = [raw_data]
            elif isinstance(raw_data, list):
                extracted = raw_data
            else:
                extracted = []
        elif file_path.lower().endswith(".txt"):
            from src.studiqs.core.question_parser import TextQuestionParser
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_text = f.read()
            parser = TextQuestionParser()
            qp_structured = parser.parse(raw_text)
            return self.map_question_paper(qp_structured)
        else:
            print("[QPMapperV3] Parsing questions with DocIntelligencePipeline (qp_parser_v3)...")
            from src.studiqs.core.qp_parser_v3 import DocIntelligencePipeline
            parser = DocIntelligencePipeline()
            extracted = parser.parse(file_path)
            
        qp_structured = {
            "exam_info": {"subject": subject, "grade": grade, "board": board},
            "sections": [
                {
                    "section_name": "All",
                    "questions": [
                        {
                            "question_number": q.get("question_no") or q.get("question_number", idx),
                            "question_text": q.get("question") or q.get("question_text", ""),
                            "marks": q.get("marks", 1.0),
                            "question_type": q.get("question_type", "SA"),
                            "has_diagram": q.get("has_diagram", False),
                            "diagram_image": q.get("diagram_image", ""),
                            "diagram_labels": q.get("diagram_labels", [])
                        } for idx, q in enumerate(extracted, 1)
                    ]
                }
            ]
        }
        
        return self.map_question_paper(qp_structured)

    def process_json(self, raw_input_str: str) -> List[Dict[str, Any]]:
        
        try:
            data = json.loads(raw_input_str)
            if isinstance(data, dict):
                question_text = data.get("question") or data.get("question_text", "")
                subject = data.get("subject", "Unknown")
                grade = str(data.get("class", data.get("grade", "Unknown")))
                board = data.get("board", "Unknown")
            else:
                question_text = str(data)
                subject, grade, board = "Unknown", "Unknown", "Unknown"
        except json.JSONDecodeError:
            question_text = raw_input_str
            subject, grade, board = "Unknown", "Unknown", "Unknown"

        mapped = self.map_question(
            raw_question_text=question_text,
            subject=subject,
            target_grade=grade,
            board=board
        )
        mapped["question_no"] = 1
        mapped["max_marks"] = 1.0
        return [mapped]

    def format_production_payload(self, mapped_results: List[Dict[str, Any]],
                                  source_file: str = "",
                                  board: str = "Unknown",
                                  grade: str = "Unknown",
                                  subject: str = "Unknown",
                                  exam_name: str = "Assessment") -> Dict[str, Any]:
        """
        Format output strictly matching 'outputs/week 3 fixes task 2/*.json' production schema.
        """
        total_q = len(mapped_results)
        total_marks = sum(float(m.get("max_marks", 1.0)) for m in mapped_results)
        mapped_count = sum(1 for m in mapped_results if m.get("mapping_status") == "mapped")
        review_count = total_q - mapped_count

        clean_mapping_list = []
        for m in mapped_results:
            clean_mapping_list.append({
                "question_no": m.get("question_no", "?"),
                "question_text": m.get("question_text", ""),
                "max_marks": float(m.get("max_marks", 1.0)),
                "subject": m.get("subject", subject),
                "chapter": m.get("chapter", "Unknown"),
                "topic": m.get("topic", "Unknown Topic"),
                "topic_id": m.get("topic_id", "Unknown"),
                "confidence_score": float(m.get("confidence_score", 0.0)),
                "confidence_level": m.get("confidence_level", "low"),
                "mapping_status": m.get("mapping_status", "manual_review"),
                "manual_review_required": bool(m.get("manual_review_required", True))
            })

        return {
            "exam_id": f"EXAM-{grade}-{subject[:3].upper()}-001",
            "student_id": "STU001",
            "board": board,
            "class": str(grade),
            "section": "A",
            "subject": subject,
            "exam_name": exam_name,
            "processing_status": "completed",
            "question_paper_summary": {
                "source_file": os.path.basename(source_file) if source_file else "unknown",
                "total_questions_extracted": total_q,
                "total_marks": round(total_marks, 2),
                "mapped_questions": mapped_count,
                "manual_review_questions": review_count
            },
            "question_topic_mapping": clean_mapping_list
        }

    def save_outputs(self, results: List[Dict[str, Any]],
                     output_dir: Optional[str] = None,
                     filename_base: str = "question_topic_mapping",
                     source_file: str = "") -> Tuple[Path, Path]:
        """
        Save results to JSON and CSV formats.
        """
        if output_dir is None:
            project_root = _find_workspace_root()
            output_dir = project_root / "outputs" / "Task_8_Topic_Mapping"
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        formatted_csv_rows = []
        for r in results:
            formatted_csv_rows.append({
                "question_no": r.get("question_no", "?"),
                "question": r.get("question_text", ""),
                "subject": r.get("subject", "Unknown"),
                "chapter": r.get("chapter", "Unknown"),
                "topic": r.get("topic", "Unknown")
            })

        out_json = output_dir / f"{filename_base}.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        out_csv = output_dir / f"{filename_base}.csv"
        pd.DataFrame(formatted_csv_rows).to_csv(out_csv, index=False, encoding="utf-8")

        print(f"\n✅ Saved JSON → {out_json}")
        print(f"✅ Saved CSV  → {out_csv}")
        return out_json, out_csv

    def validate_input(self, input_data: Any) -> Any:
        """Validates input question paper structured dictionary or question list."""
        if input_data is None:
            raise ValueError("Input data to QPTopicMapperV3 cannot be None.")
        if isinstance(input_data, dict):
            if not input_data.get("sections") and not input_data.get("questions"):
                pass
        elif isinstance(input_data, list):
            if len(input_data) == 0:
                raise ValueError("Input question list cannot be empty.")
        elif isinstance(input_data, str):
            if len(input_data.strip()) == 0:
                raise ValueError("Input question text cannot be empty.")
        return input_data

    def fallback(self, error: Exception, input_data: Any) -> Any:
        """Safe degraded fallback when semantic topic mapping encounters an unexpected error."""
        print(f"[QPTopicMapperV3] Resilient Fallback triggered: {error}")
        if isinstance(input_data, dict):
            raw_sections = input_data.get("sections")
            if not isinstance(raw_sections, list):
                raw_sections = []

            all_qs = []
            for sec in raw_sections:
                if isinstance(sec, dict):
                    all_qs.extend(sec.get("questions") or [])

            if not all_qs:
                raw_qs = input_data.get("questions")
                if isinstance(raw_qs, list):
                    all_qs = raw_qs

            if not all_qs:
                all_qs = [{
                    "question_no": 1,
                    "question_text": f"[DEGRADED_MAPPING_FALLBACK] Unhandled mapping exception: {error}",
                    "marks": 1.0
                }]

            exam_info = input_data.get("exam_info") or {}
            subject = exam_info.get("subject", "General")
            
            return [
                {
                    "question_no": q.get("question_number") or q.get("question_no") or idx,
                    "question_number": q.get("question_number") or q.get("question_no") or idx,
                    "question_text": q.get("question_text") or q.get("question") or "",
                    "max_marks": float(q.get("marks") or q.get("max_marks") or 1.0),
                    "marks": float(q.get("marks") or q.get("max_marks") or 1.0),
                    "question_type": q.get("question_type", "SA"),
                    "subject": subject,
                    "chapter": "Unknown",
                    "topic": "Unknown Topic",
                    "topic_id": "Unknown",
                    "confidence_score": 0.0,
                    "confidence_level": "none",
                    "mapping_status": "manual_review",
                    "manual_review_required": True,
                    "fallback_reason": str(error)
                }
                for idx, q in enumerate(all_qs, 1)
            ]
        elif isinstance(input_data, str):
            return {
                "topic": "Unknown Topic",
                "topic_id": "Unknown",
                "chapter": "Unknown",
                "confidence_score": 0.0,
                "confidence_level": "none",
                "mapping_status": "manual_review",
                "manual_review_required": True,
                "fallback_reason": str(error)
            }
        return []

    @resilient_engine_step("QPTopicMapperV3")
    def execute_core(self, validated_data: Any) -> Any:
        """Executes core mapping with latency tracking, Pydantic validation & MLOps logging."""
        start_t = time.perf_counter()
        if isinstance(validated_data, dict):
            mapped = self._map_questions_internal(validated_data)
            latency_ms = (time.perf_counter() - start_t) * 1000.0

            # Pydantic schema validation & sanitization
            validated_mapped = []
            for m in mapped:
                try:
                    schema_item = TopicMappingSchema(
                        question_no=m.get("question_no", 1),
                        question_text=m.get("question_text", ""),
                        max_marks=float(m.get("max_marks", 1.0)),
                        subject=m.get("subject", "General"),
                        chapter=m.get("chapter", "Unknown"),
                        topic=m.get("topic", "Unknown Topic"),
                        topic_id=m.get("topic_id", "Unknown"),
                        confidence_score=float(m.get("confidence_score", 0.0)),
                        confidence_level=m.get("confidence_level", "none"),
                        mapping_status=m.get("mapping_status", "manual_review"),
                        manual_review_required=bool(m.get("manual_review_required", True)),
                        sub_domain=m.get("sub_domain")
                    )
                    clean_item = dict(m)
                    clean_item.update(schema_item.model_dump())
                    validated_mapped.append(clean_item)
                except Exception as v_err:
                    validated_mapped.append(m)

            # MLOps Telemetry & Drift Monitoring
            exam_info = validated_data.get("exam_info", {})
            paper_name = exam_info.get("source_file") or exam_info.get("exam_name") or "question_paper"
            tot_q = len(validated_mapped)
            mapped_count = sum(1 for q in validated_mapped if q.get("mapping_status") == "mapped" or (q.get("topic") and q.get("topic") != "Unknown Topic"))
            accuracy = mapped_count / max(tot_q, 1)
            conf_list = [q.get("confidence_score", 0.0) for q in validated_mapped]
            mean_conf = float(np.mean(conf_list)) if conf_list else 0.0
            low_conf_cnt = sum(1 for q in validated_mapped if q.get("manual_review_required") or q.get("confidence_score", 0.0) < 0.50)

            try:
                tracker = get_mlops_tracker()
                tracker.log_mapping_metrics(
                    paper_name=paper_name,
                    total_questions=tot_q,
                    mapped_questions=mapped_count,
                    mapping_accuracy=accuracy,
                    mean_confidence=mean_conf,
                    low_confidence_count=low_conf_cnt,
                    latency_ms=latency_ms
                )
            except Exception as ml_err:
                print(f"[QPTopicMapperV3] MLOps logging notice: {ml_err}")

            return validated_mapped
        elif isinstance(validated_data, str):
            return self.map_question(validated_data)
        return []

    def _map_questions(self, qp_structured: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Runs batch question mapping through the resilient BaseEngine lifecycle."""
        return self.run(qp_structured)

    def map_all_questions(self, qp_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Runs batch question mapping through the resilient BaseEngine lifecycle."""
        return self.run(qp_data)

    def _map_questions_internal(self, qp_structured: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Internal backward-compatible batch question mapper for qp_structured format.
        Extracts questions from all sections, routes subject/grade/board, and returns standard mapped question dicts.
        """
        exam_info = qp_structured.get("exam_info", {})
        subject = exam_info.get("subject") or "Unknown"
        grade = str(exam_info.get("grade") or "Unknown")
        board = exam_info.get("board") or "Unknown" 

        raw_sections = qp_structured.get("sections")
        if not isinstance(raw_sections, list):
            raw_sections = []

        all_qs = []
        for sec in raw_sections:
            if isinstance(sec, dict):
                all_qs.extend(sec.get("questions") or [])

        if not all_qs:
            raw_qs = qp_structured.get("questions")
            if isinstance(raw_qs, list):
                all_qs = raw_qs

        mapped_questions = []
        for idx, q in enumerate(all_qs, 1):
            q_num = q.get("question_number") or q.get("question_no") or idx
            q_text = q.get("question_text") or q.get("question") or ""
            q_marks = float(q.get("marks") or 1.0)
            q_type = q.get("question_type") or "SA"

            m_res = self.map_question(
                raw_question_text=q_text,
                subject=subject,
                target_grade=grade,
                board=board
            )

            mapped_questions.append({
                "question_no": q_num,
                "question_number": q_num,
                "question_text": q_text,
                "max_marks": q_marks,
                "marks": q_marks,
                "question_type": q_type,
                "subject": subject,
                "chapter": m_res.get("chapter", "Unknown"),
                "topic": m_res.get("topic", "Unknown"),
                "topic_id": m_res.get("topic_id", "Unknown"),
                "confidence_score": m_res.get("confidence_score", 0.0),
                "confidence_level": m_res.get("confidence_level", "none"),
                "mapping_status": m_res.get("mapping_status", "mapped"),
                "manual_review_required": m_res.get("manual_review_required", False)
            })

        return mapped_questions


# =============================================================================
# BACKWARD COMPATIBILITY ALIASES
# =============================================================================
QuestionTopicMappingEngine = QPTopicMapperV3
QuestionTopicMappingEngineV3 = QPTopicMapperV3
HybridTopicRepositoryMapper = QPTopicMapperV3
RuleBasedTopicMapper = QPTopicMapperV3


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="QPTopicMapperV3 — Production Lightweight Topic Mapping Engine")
    parser.add_argument("input_path", nargs="?", default="", help="Path to question paper file (.pdf, .json, .txt)")
    parser.add_argument("--input", "-i", dest="input_opt", default="", help="Optional input path")
    parser.add_argument("--output", "-o", dest="output_dir", default="", help="Output directory")
    parser.add_argument("--repo", default=None, help="Path to topic_repository_complete.xlsx")
    parser.add_argument("--self-test", action="store_true", help="Run quick self test")
    args = parser.parse_args()

    target_input = args.input_opt or args.input_path

    print("=" * 80)
    print("QPTopicMapperV3 — Production Lightweight Topic Mapping Engine")
    print("=" * 80)

    engine = QPTopicMapperV3(repo_path=args.repo)

    if target_input:
        if os.path.exists(target_input):
            print(f"[CLI] Processing input file: {target_input}")
            output = engine.process_file(target_input)
        else:
            print(f"[CLI] Processing input JSON string")
            output = engine.process_json(target_input)

        out_dir = args.output_dir or None
        file_base = os.path.splitext(os.path.basename(target_input))[0] if os.path.exists(target_input) else "question_topic_mapping"
        engine.save_outputs(output, output_dir=out_dir, filename_base=file_base, source_file=target_input)
    else:
        # Quick self-test
        print("[CLI] Running quick self-test with sample questions:")
        test_cases = [
            ("Conversion of 7m into cm gives", "Science", "6", "TN State Board"),
            ("Find the roots of x² - 5x + 6 = 0", "Mathematics", "10", "CBSE"),
            ("Which organ produces bile juice?", "Science", "4", "CBSE"),
        ]

        for q, subj, grade, board in test_cases:
            res = engine.map_question(q, subject=subj, target_grade=grade, board=board)
            print(f"\n  Q: {q[:50]}")
            print(f"  -> [{res['topic_id']}] {res['chapter']} | {res['topic']} (Score: {res['confidence_score']}, {res['confidence_level']})")

    