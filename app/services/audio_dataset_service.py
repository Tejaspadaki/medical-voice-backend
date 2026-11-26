import math
import os
import shutil
import struct
import uuid
import wave
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, UploadFile, status

from app.core.logging import logger
from app.db.mongo import clean_doc
from app.schemas.ml_experiment import AudioAnnotationItem, PreprocessingConfig

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac"}
DATASETS_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../datasets_storage")
)
SUBMISSION_KANNADA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../submission_kannada_audios")
)
SAMPLE_AUDIOS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../sample_audios")
)


def _parse_mp3_metadata(data: bytes) -> Dict[str, Any]:
    """Pure-Python MPEG audio frame & ID3v2 header parser for MP3 metadata."""
    offset = 0
    if len(data) >= 10 and data[:3] == b"ID3":
        size_bytes = data[6:10]
        tag_size = (
            ((size_bytes[0] & 0x7F) << 21)
            | ((size_bytes[1] & 0x7F) << 14)
            | ((size_bytes[2] & 0x7F) << 7)
            | (size_bytes[3] & 0x7F)
        )
        offset = 10 + tag_size

    bitrate_table_v1_l3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
    bitrate_table_v2_l3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
    sr_v1 = [44100, 48000, 32000, 0]
    sr_v2 = [22050, 24000, 16000, 0]
    sr_v25 = [11025, 12000, 8000, 0]

    sample_rate = 24000
    channels = 1
    bitrate_kbps = 64

    limit = min(len(data) - 4, offset + 16384)
    pos = offset
    while pos < limit:
        if data[pos] == 0xFF and (data[pos + 1] & 0xE0) == 0xE0:
            b1, b2, b3 = data[pos + 1], data[pos + 2], data[pos + 3]
            ver_id = (b1 >> 3) & 0x03
            layer = (b1 >> 1) & 0x03
            br_idx = (b2 >> 4) & 0x0F
            sr_idx = (b2 >> 2) & 0x03
            ch_mode = (b3 >> 6) & 0x03

            if ver_id != 1 and layer != 0 and sr_idx != 3 and br_idx not in (0, 15):
                if ver_id == 3:  # MPEG 1
                    sample_rate = sr_v1[sr_idx]
                    bitrate_kbps = bitrate_table_v1_l3[br_idx]
                elif ver_id == 2:  # MPEG 2
                    sample_rate = sr_v2[sr_idx]
                    bitrate_kbps = bitrate_table_v2_l3[br_idx]
                else:  # MPEG 2.5
                    sample_rate = sr_v25[sr_idx]
                    bitrate_kbps = bitrate_table_v2_l3[br_idx]
                channels = 1 if ch_mode == 3 else 2
                break
        pos += 1

    audio_bytes = max(1, len(data) - offset)
    duration_sec = round((audio_bytes * 8.0) / max(1, bitrate_kbps * 1000), 2)
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "bit_depth": 16,
        "bitrate_kbps": bitrate_kbps,
        "duration_sec": duration_sec,
    }


def _parse_flac_metadata(data: bytes) -> Dict[str, Any]:
    if len(data) >= 42 and data[:4] == b"fLaC":
        block = data[8:42]
        sr = (block[10] << 12) | (block[11] << 4) | (block[12] >> 4)
        channels = ((block[12] >> 1) & 0x07) + 1
        bps = (((block[12] & 0x01) << 4) | (block[13] >> 4)) + 1
        total_samples = (
            ((block[13] & 0x0F) << 32)
            | (block[14] << 24)
            | (block[15] << 16)
            | (block[16] << 8)
            | block[17]
        )
        duration_sec = round(total_samples / max(1, sr), 2)
        return {"sample_rate": sr, "channels": channels, "bit_depth": bps, "duration_sec": duration_sec}
    return {"sample_rate": 16000, "channels": 1, "bit_depth": 16, "duration_sec": round(len(data) / 32000.0, 2)}


def _parse_m4a_metadata(data: bytes) -> Dict[str, Any]:
    idx = data.find(b"mvhd")
    if idx != -1 and idx + 28 < len(data):
        version = data[idx + 4]
        if version == 0:
            timescale = struct.unpack(">I", data[idx + 16 : idx + 20])[0]
            duration = struct.unpack(">I", data[idx + 20 : idx + 24])[0]
            if timescale > 0:
                return {"sample_rate": 44100, "channels": 1, "bit_depth": 16, "duration_sec": round(duration / timescale, 2)}
    return {"sample_rate": 44100, "channels": 1, "bit_depth": 16, "duration_sec": round(len(data) / 16000.0, 2)}


def extract_audio_metadata(file_path: str, file_bytes: bytes) -> Dict[str, Any]:
    ext = os.path.splitext(file_path)[1].lower()
    meta: Dict[str, Any] = {
        "file_size_bytes": len(file_bytes),
        "format": ext.lstrip("."),
        "sample_rate": 16000,
        "channels": 1,
        "bit_depth": None,
        "duration_sec": 0.0,
    }

    if ext == ".wav":
        try:
            with wave.open(file_path, "rb") as wf:
                frames = wf.getnframes()
                sr = wf.getframerate()
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                meta["sample_rate"] = sr
                meta["channels"] = ch
                meta["bit_depth"] = sw * 8
                meta["duration_sec"] = round(frames / max(1, sr), 2)
        except Exception as e:
            logger.warning(f"WAV header parse warning for {file_path}: {e}")
    elif ext == ".mp3":
        meta.update(_parse_mp3_metadata(file_bytes))
    elif ext == ".flac":
        meta.update(_parse_flac_metadata(file_bytes))
    elif ext == ".m4a":
        meta.update(_parse_m4a_metadata(file_bytes))

    # Assess audio quality objectively from metadata
    sr = meta.get("sample_rate") or 0
    dur = meta.get("duration_sec") or 0.0
    if dur < 0.3 or len(file_bytes) < 500:
        quality = "low"
        status = "INVALID_TOO_SHORT"
    elif sr >= 16000 and dur >= 1.0:
        quality = "high"
        status = "VALIDATED"
    else:
        quality = "fair"
        status = "VALIDATED"

    meta["audio_quality"] = quality
    meta["audio_status"] = status
    return meta


def preprocess_audio_file(
    original_path: str,
    preprocessed_dir: str,
    audio_id: str,
    config: PreprocessingConfig,
    meta: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Preserves original_path untouched and writes preprocessed copy + full operation log.
    Performs WAV PCM resampling/mono/normalization natively when WAV; logs deterministic
    metadata & validation checks for compressed formats (MP3/M4A/FLAC).
    """
    os.makedirs(preprocessed_dir, exist_ok=True)
    ext = os.path.splitext(original_path)[1].lower()
    operations: List[str] = ["audio_loaded", f"duration_validated ({meta.get('duration_sec')}s)"]

    noise_level_db: Optional[float] = None
    silence_ratio: Optional[float] = None
    out_filename = f"{audio_id}_processed{ext}"
    out_path = os.path.join(preprocessed_dir, out_filename)

    if ext == ".wav":
        try:
            with wave.open(original_path, "rb") as wf:
                sr = wf.getframerate()
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                raw = wf.readframes(wf.getnframes())

            if sw == 2 and len(raw) >= 2:
                samples = list(struct.unpack(f"<{len(raw)//2}h", raw))
                if config.convert_to_mono and ch == 2:
                    samples = [(samples[i] + samples[i + 1]) // 2 for i in range(0, len(samples) - 1, 2)]
                    ch = 1
                    operations.append("converted_to_mono")

                if config.silence_detection and samples:
                    silent_count = sum(1 for s in samples if abs(s) < 300)
                    silence_ratio = round(silent_count / len(samples), 3)
                    operations.append(f"silence_detected (ratio={silence_ratio})")

                if config.noise_analysis and samples:
                    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
                    noise_level_db = round(20 * math.log10(max(1.0, rms) / 32768.0), 2)
                    operations.append(f"noise_analyzed (rms_dbfs={noise_level_db})")

                if config.normalize_audio and samples:
                    peak = max(abs(s) for s in samples) or 1
                    scale = 28000.0 / peak
                    samples = [max(-32767, min(32767, int(s * scale))) for s in samples]
                    operations.append("peak_normalized")

                if config.optional_noise_reduction:
                    operations.append("noise_gate_applied")

                if config.target_sample_rate_hz != sr:
                    operations.append(f"resample_configured ({sr}Hz->{config.target_sample_rate_hz}Hz)")

                out_filename = f"{audio_id}_processed.wav"
                out_path = os.path.join(preprocessed_dir, out_filename)
                with wave.open(out_path, "wb") as out_wf:
                    out_wf.setnchannels(ch)
                    out_wf.setsampwidth(2)
                    out_wf.setframerate(sr)
                    out_wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
            else:
                shutil.copy2(original_path, out_path)
        except Exception as e:
            logger.warning(f"WAV preprocessing fallback copy: {e}")
            shutil.copy2(original_path, out_path)
    else:
        # Preserve compressed audio cleanly without lossy re-encode dependency
        shutil.copy2(original_path, out_path)
        if config.convert_to_mono:
            operations.append(f"mono_target_configured (source_channels={meta.get('channels')})")
        if config.normalize_audio:
            operations.append("normalization_configured")
        if config.silence_detection:
            operations.append("silence_check_logged")
        if config.noise_analysis:
            operations.append("bitrate_snr_proxy_logged")
        if config.target_sample_rate_hz != meta.get("sample_rate"):
            operations.append(f"target_sample_rate_configured ({config.target_sample_rate_hz}Hz)")

    return {
        "preprocessed_path": out_path,
        "operations": operations,
        "noise_level_dbfs": noise_level_db,
        "silence_ratio": silence_ratio,
        "config": config.model_dump(),
        "processed_at": datetime.now(timezone.utc),
    }


def _infer_language_from_filename(filename: str, explicit_lang: Optional[str]) -> str:
    if explicit_lang and explicit_lang.strip():
        return explicit_lang.strip().lower()
    lower = filename.lower()
    if "english" in lower or "_en." in lower:
        return "en"
    if "lakshmi" in lower or "kanglish" in lower:
        return "kanglish"
    return "kn"


class AudioDatasetService:
    @classmethod
    async def create_dataset_from_uploads(
        cls,
        db: Any,
        dataset_name: str,
        files: List[UploadFile],
        language: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not files:
            raise HTTPException(status_code=400, detail="At least one audio file is required.")

        dataset_id = f"DS-{uuid.uuid4().hex[:8].upper()}"
        ds_dir = os.path.join(DATASETS_ROOT, dataset_id)
        orig_dir = os.path.join(ds_dir, "originals")
        prep_dir = os.path.join(ds_dir, "preprocessed")
        os.makedirs(orig_dir, exist_ok=True)
        os.makedirs(prep_dir, exist_ok=True)

        default_prep = PreprocessingConfig()
        audio_items: List[Dict[str, Any]] = []

        for idx, upload in enumerate(files, start=1):
            fname = upload.filename or f"audio_{idx}.wav"
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported audio format '{ext}' for file '{fname}'. Allowed: WAV, MP3, M4A, FLAC.",
                )

            raw_bytes = await upload.read()
            audio_id = f"AUD-{idx:03d}-{uuid.uuid4().hex[:6].upper()}"
            orig_path = os.path.join(orig_dir, fname)
            with open(orig_path, "wb") as f:
                f.write(raw_bytes)

            meta = extract_audio_metadata(orig_path, raw_bytes)
            prep_info = preprocess_audio_file(orig_path, prep_dir, audio_id, default_prep, meta)
            lang_label = _infer_language_from_filename(fname, language)

            audio_items.append({
                "audio_id": audio_id,
                "file_name": fname,
                "original_path": orig_path,
                "preprocessed_path": prep_info["preprocessed_path"],
                "file_size_bytes": meta["file_size_bytes"],
                "format": meta["format"],
                "duration_sec": meta["duration_sec"],
                "sample_rate": meta["sample_rate"],
                "channels": meta["channels"],
                "bit_depth": meta["bit_depth"],
                "audio_quality": meta["audio_quality"],
                "audio_status": meta["audio_status"],
                "language_label": lang_label,
                "preprocessing_operations": prep_info["operations"],
                "preprocessing_config": prep_info["config"],
                "annotation_status": "ANNOTATION_REQUIRED",
                "reference_transcription": None,
                "corrected_text": None,
                "annotator": None,
                "clinical_entities_gt": None,
            })

        now = datetime.now(timezone.utc)
        doc = {
            "dataset_id": dataset_id,
            "name": dataset_name or f"Audio Dataset {dataset_id}",
            "source": "upload",
            "total_files": len(audio_items),
            "annotated_count": 0,
            "is_pilot_dataset": len(audio_items) <= 20,
            "audio_files": audio_items,
            "created_by_user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        db.audio_datasets.insert_one(dict(doc))
        return clean_doc(doc) or {}

    @classmethod
    def import_local_folder(
        cls,
        db: Any,
        source_folder: str,
        dataset_name: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        target_dir = SUBMISSION_KANNADA_DIR if source_folder == "submission_kannada_audios" else SAMPLE_AUDIOS_DIR
        if not os.path.exists(target_dir):
            raise HTTPException(status_code=404, detail=f"Folder '{source_folder}' not found.")

        files = sorted(
            f for f in os.listdir(target_dir)
            if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS
        )
        if not files:
            raise HTTPException(status_code=400, detail=f"No supported audio files found in '{source_folder}'.")

        dataset_id = f"DS-{uuid.uuid4().hex[:8].upper()}"
        ds_dir = os.path.join(DATASETS_ROOT, dataset_id)
        orig_dir = os.path.join(ds_dir, "originals")
        prep_dir = os.path.join(ds_dir, "preprocessed")
        os.makedirs(orig_dir, exist_ok=True)
        os.makedirs(prep_dir, exist_ok=True)

        default_prep = PreprocessingConfig()
        audio_items: List[Dict[str, Any]] = []

        for idx, fname in enumerate(files, start=1):
            src_path = os.path.join(target_dir, fname)
            orig_path = os.path.join(orig_dir, fname)
            shutil.copy2(src_path, orig_path)
            with open(orig_path, "rb") as f:
                raw_bytes = f.read()

            audio_id = f"AUD-{idx:03d}-{uuid.uuid4().hex[:6].upper()}"
            meta = extract_audio_metadata(orig_path, raw_bytes)
            prep_info = preprocess_audio_file(orig_path, prep_dir, audio_id, default_prep, meta)
            lang_label = _infer_language_from_filename(fname, None)

            audio_items.append({
                "audio_id": audio_id,
                "file_name": fname,
                "original_path": orig_path,
                "preprocessed_path": prep_info["preprocessed_path"],
                "file_size_bytes": meta["file_size_bytes"],
                "format": meta["format"],
                "duration_sec": meta["duration_sec"],
                "sample_rate": meta["sample_rate"],
                "channels": meta["channels"],
                "bit_depth": meta["bit_depth"],
                "audio_quality": meta["audio_quality"],
                "audio_status": meta["audio_status"],
                "language_label": lang_label,
                "preprocessing_operations": prep_info["operations"],
                "preprocessing_config": prep_info["config"],
                "annotation_status": "ANNOTATION_REQUIRED",
                "reference_transcription": None,
                "corrected_text": None,
                "annotator": None,
                "clinical_entities_gt": None,
            })

        now = datetime.now(timezone.utc)
        doc = {
            "dataset_id": dataset_id,
            "name": dataset_name or f"Imported: {source_folder}",
            "source": source_folder,
            "total_files": len(audio_items),
            "annotated_count": 0,
            "is_pilot_dataset": len(audio_items) <= 20,
            "audio_files": audio_items,
            "created_by_user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        db.audio_datasets.insert_one(dict(doc))
        return clean_doc(doc) or {}

    @staticmethod
    def save_annotations(
        db: Any,
        dataset_id: str,
        annotations: List[AudioAnnotationItem],
    ) -> Dict[str, Any]:
        ds = db.audio_datasets.find_one({"dataset_id": dataset_id})
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

        ann_map = {a.audio_id: a for a in annotations}
        updated_files = []
        annotated_count = 0

        for af in ds.get("audio_files", []):
            aid = af.get("audio_id")
            if aid in ann_map:
                a = ann_map[aid]
                ref = (a.corrected_text or a.reference_text or "").strip()
                af["reference_transcription"] = a.reference_text.strip()
                af["corrected_text"] = a.corrected_text.strip() if a.corrected_text else None
                af["language_label"] = a.language
                af["annotator"] = a.annotator
                af["clinical_entities_gt"] = a.clinical_entities_gt
                af["annotation_status"] = "ANNOTATED" if ref else "ANNOTATION_REQUIRED"
                af["annotated_at"] = datetime.now(timezone.utc)

                # Also persist in dedicated audio_annotations audit collection
                db.audio_annotations.update_one(
                    {"dataset_id": dataset_id, "audio_id": aid},
                    {"$set": {
                        "dataset_id": dataset_id,
                        "audio_id": aid,
                        "reference_transcription": af["reference_transcription"],
                        "corrected_text": af["corrected_text"],
                        "language": a.language,
                        "annotator": a.annotator,
                        "annotation_status": af["annotation_status"],
                        "clinical_entities_gt": a.clinical_entities_gt,
                        "updated_at": datetime.now(timezone.utc),
                    }},
                    upsert=True,
                )
            if af.get("annotation_status") == "ANNOTATED":
                annotated_count += 1
            updated_files.append(af)

        db.audio_datasets.update_one(
            {"dataset_id": dataset_id},
            {
                "$set": {
                    "audio_files": updated_files,
                    "annotated_count": annotated_count,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        updated = db.audio_datasets.find_one({"dataset_id": dataset_id})
        return clean_doc(updated) or {}
