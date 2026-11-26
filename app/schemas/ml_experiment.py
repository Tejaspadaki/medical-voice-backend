from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PreprocessingConfig(BaseModel):
    target_sample_rate_hz: int = Field(16000, ge=8000, le=48000)
    convert_to_mono: bool = True
    normalize_audio: bool = True
    silence_detection: bool = True
    noise_analysis: bool = True
    optional_noise_reduction: bool = False
    min_duration_sec: float = 0.2
    max_duration_sec: float = 600.0


class AudioAnnotationItem(BaseModel):
    audio_id: str
    reference_text: str
    language: str = "kn"
    corrected_text: Optional[str] = None
    annotator: str = "Doctor/Annotator"
    clinical_entities_gt: Optional[Dict[str, Any]] = None


class AudioAnnotationsBatchRequest(BaseModel):
    annotations: List[AudioAnnotationItem] = Field(..., min_length=1)


class ModelEvaluationRequest(BaseModel):
    dataset_id: str
    model_ids: List[str] = Field(..., min_length=1)
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)
    normalization_method: str = "unicode_nfkc_lowercase_punct_strip"
    evaluate_clinical_nlp: bool = True


class TrainingConfigRequest(BaseModel):
    dataset_id: str
    model_id: str
    batch_size: int = Field(4, ge=1, le=128)
    learning_rate: float = Field(1e-4, gt=0, le=1.0)
    epochs: int = Field(3, ge=1, le=100)
    train_split: float = Field(0.8, ge=0.5, le=0.95)
    early_stopping_patience: int = Field(2, ge=1, le=20)
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)
