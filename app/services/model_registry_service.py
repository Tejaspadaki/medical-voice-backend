import importlib.util
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings


def _has_package(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


class ModelRegistryService:
    """
    Centralized, dynamic AI Model Registry.
    Inspects runtime configuration, API keys, installed ML libraries,
    and saved local checkpoints without fabricating fake model entries.
    """

    CHECKPOINTS_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../../model_checkpoints")
    )

    @classmethod
    def list_models(cls, db: Any = None) -> List[Dict[str, Any]]:
        os.makedirs(cls.CHECKPOINTS_DIR, exist_ok=True)
        sarvam_ready = bool(settings.SARVAM_API_KEY and settings.SARVAM_API_KEY.strip())
        gemini_ready = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip())
        torch_ready = _has_package("torch") and _has_package("transformers")

        # Discover any real saved local checkpoints/adapters
        saved_checkpoints = [
            f for f in os.listdir(cls.CHECKPOINTS_DIR)
            if f.endswith((".pt", ".bin", ".safetensors", ".json"))
        ]

        models: List[Dict[str, Any]] = [
            {
                "model_id": "sarvam_saaras_v3",
                "model_name": "Sarvam AI Saaras v3",
                "architecture": "Cloud Multilingual Conformer/Foundation ASR",
                "version": "saaras:v3",
                "purpose": "Kannada, English, Hindi & Code-Mixed Speech-to-Text (ASR)",
                "supported_languages": ["kn", "en", "hi", "kanglish"],
                "training_status": "pretrained_cloud_api",
                "pretrained_or_finetuned": "Pretrained (Vendor Cloud API)",
                "trainable_locally": False,
                "evaluation_mode": "inference_evaluation_only",
                "available": sarvam_ready,
                "availability_note": "Ready (SARVAM_API_KEY configured)" if sarvam_ready else "Unavailable (SARVAM_API_KEY not set)",
                "input_requirements": "Audio file (WAV/MP3, 16kHz recommended) + language_code (kn-IN / en-IN)",
                "output_format": "JSON {transcript, language_code, request_id}",
                "existing_metrics": cls._latest_metrics_for_model(db, "sarvam_saaras_v3"),
            },
            {
                "model_id": "indicwhisper_local",
                "model_name": "AI4Bharat IndicWhisper (Kannada)",
                "architecture": "Whisper Seq2Seq Transformer (ai4bharat/indicwhisper-kannada)",
                "version": "0.1.0",
                "purpose": "Local/Offline Kannada & English ASR Fallback",
                "supported_languages": ["kn", "en", "kanglish"],
                "training_status": "local_finetunable" if torch_ready else "scaffolding_stub_no_weights",
                "pretrained_or_finetuned": "Scaffolding Stub (requires torch + transformers + local weights for real inference)",
                "trainable_locally": True,
                "evaluation_mode": "local_finetune_or_inference" if torch_ready else "stub_scaffolding_warning",
                "available": True,
                "availability_note": (
                    "PyTorch + Transformers detected"
                    if torch_ready
                    else "Running in lightweight scaffolding mode (torch/transformers not installed; results marked as scaffolding)"
                ),
                "input_requirements": "16kHz Mono WAV/MP3 audio path + language code",
                "output_format": "Dict {text, language, segments}",
                "saved_checkpoints": saved_checkpoints,
                "existing_metrics": cls._latest_metrics_for_model(db, "indicwhisper_local"),
            },
            {
                "model_id": "gemini_clinical_ner",
                "model_name": f"Google Gemini ({settings.GEMINI_MODEL})",
                "architecture": "Multimodal Transformer LLM",
                "version": settings.GEMINI_MODEL,
                "purpose": "Clinical Entity Extraction (NER), Multilingual Structuring & Assessment",
                "supported_languages": ["kn", "en", "kanglish"],
                "training_status": "pretrained_cloud_api",
                "pretrained_or_finetuned": "Pretrained (Vendor Cloud API)",
                "trainable_locally": False,
                "evaluation_mode": "inference_evaluation_only",
                "available": gemini_ready,
                "availability_note": "Ready (GEMINI_API_KEY configured)" if gemini_ready else "Unavailable (GEMINI_API_KEY not set)",
                "input_requirements": "Clinical transcript text + patient context JSON",
                "output_format": "Structured JSON (symptoms, diagnosis, medications, advice, vitals)",
                "existing_metrics": cls._latest_metrics_for_model(db, "gemini_clinical_ner"),
            },
            {
                "model_id": "auradoc_bilingual_nlp",
                "model_name": "AuraDoc Bilingual Medical Lexicon & NER",
                "architecture": "Deterministic Clinical Rule + Bilingual Lexicon Engine",
                "version": "2.0.0",
                "purpose": "Offline English/Kannada Clinical Entity Extraction & Lexicon Calibration",
                "supported_languages": ["en", "kn"],
                "training_status": "lexicon_calibratable_locally",
                "pretrained_or_finetuned": "Curated Rule-Based Clinical Lexicon (Calibratable on annotated dataset)",
                "trainable_locally": True,
                "evaluation_mode": "local_lexicon_calibration_and_inference",
                "available": True,
                "availability_note": "Ready (Zero external API dependency)",
                "input_requirements": "Transcribed clinical text (English / Kannada)",
                "output_format": "Dict {symptoms, diagnosis, medications, advice}",
                "existing_metrics": cls._latest_metrics_for_model(db, "auradoc_bilingual_nlp"),
            },
            {
                "model_id": "sarvam_bulbul_v3_tts",
                "model_name": "Sarvam AI Bulbul v3 (TTS)",
                "architecture": "Neural Indian-Language TTS (speaker: kavya)",
                "version": "bulbul:v3",
                "purpose": "Natural Spoken Kannada Doctor Readback & Confirmation",
                "supported_languages": ["kn", "en"],
                "training_status": "pretrained_cloud_api",
                "pretrained_or_finetuned": "Pretrained (Vendor Cloud API)",
                "trainable_locally": False,
                "evaluation_mode": "tts_synthesis_only",
                "available": sarvam_ready,
                "availability_note": "Ready (SARVAM_API_KEY configured)" if sarvam_ready else "Unavailable (SARVAM_API_KEY not set)",
                "input_requirements": "Kannada/English text (<=500 chars)",
                "output_format": "Base64 WAV audio",
                "existing_metrics": None,
            },
        ]
        return models

    @classmethod
    def get_model(cls, model_id: str, db: Any = None) -> Optional[Dict[str, Any]]:
        for m in cls.list_models(db):
            if m["model_id"] == model_id:
                return m
        return None

    @staticmethod
    def _latest_metrics_for_model(db: Any, model_id: str) -> Optional[Dict[str, Any]]:
        if db is None:
            return None
        try:
            doc = db.model_evaluations.find_one(
                {"model_summaries.model_id": model_id},
                sort=[("created_at", -1)],
            )
            if not doc:
                return None
            for ms in doc.get("model_summaries", []):
                if ms.get("model_id") == model_id:
                    return {
                        "evaluation_id": doc.get("evaluation_id"),
                        "avg_wer": ms.get("avg_wer"),
                        "avg_cer": ms.get("avg_cer"),
                        "avg_latency_ms": ms.get("avg_latency_ms"),
                        "evaluated_at": doc.get("created_at").isoformat() if hasattr(doc.get("created_at"), "isoformat") else str(doc.get("created_at")),
                    }
        except Exception:
            return None
        return None
