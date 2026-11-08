import os
import json
import base64
from typing import Optional, Dict, Any
import httpx

from app.core.config import settings
from app.core.logging import logger

class SarvamService:
    """
    Production Integration for Sarvam AI (Indian Multilingual Voice AI):
    - Speech-To-Text (STT): saaras:v3 (Kannada kn-IN, Hindi hi-IN, Indian English en-IN)
    - Text-To-Speech (TTS): bulbul:v3 (Natural spoken Kannada with speaker 'kavya')
    """

    STT_URL = "https://api.sarvam.ai/speech-to-text"
    TTS_URL = "https://api.sarvam.ai/text-to-speech"

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.SARVAM_API_KEY and settings.SARVAM_API_KEY.strip())

    @classmethod
    def speech_to_text(
        cls,
        audio_bytes: bytes,
        filename: str = "recording.wav",
        language_code: str = "kn-IN",
        model: str = "saaras:v3"
    ) -> Dict[str, Any]:
        """
        Transcribes speech audio using Sarvam AI Saaras:v3 model.
        Returns a dict with 'transcript', 'language_code', etc.
        """
        if not cls.is_configured():
            logger.warning("SARVAM_API_KEY is not configured. Falling back.")
            return {"transcript": "", "error": "SARVAM_API_KEY not configured"}

        try:
            headers = {
                "api-subscription-key": settings.SARVAM_API_KEY.strip()
            }
            files = {
                "file": (filename, audio_bytes, "audio/wav")
            }
            data = {
                "model": model,
                "language_code": language_code
            }

            with httpx.Client(timeout=15.0) as client:
                resp = client.post(cls.STT_URL, headers=headers, files=files, data=data)
                if resp.status_code == 200:
                    result = resp.json()
                    transcript = result.get("transcript", "").strip()
                    logger.info(f"Sarvam STT success ({language_code}): '{transcript}'")
                    return {
                        "transcript": transcript,
                        "language_code": result.get("language_code", language_code),
                        "request_id": result.get("request_id")
                    }
                else:
                    logger.error(f"Sarvam STT failed HTTP {resp.status_code}: {resp.text}")
                    return {"transcript": "", "error": resp.text}

        except Exception as e:
            logger.error(f"Sarvam STT exception: {e}")
            return {"transcript": "", "error": str(e)}

    @classmethod
    def text_to_speech(
        cls,
        text: str,
        language_code: str = "kn-IN",
        speaker: str = "kavya",
        model: str = "bulbul:v3"
    ) -> Optional[str]:
        """
        Synthesizes text into high-fidelity Indian speech audio using Sarvam AI Bulbul:v3.
        Returns base64-encoded WAV audio string, or None if unavailable.
        """
        if not cls.is_configured():
            logger.warning("SARVAM_API_KEY is not configured for TTS.")
            return None

        clean_text = text.strip()
        if not clean_text:
            return None

        # Truncate to reasonable length if needed
        if len(clean_text) > 500:
            clean_text = clean_text[:500]

        try:
            headers = {
                "api-subscription-key": settings.SARVAM_API_KEY.strip(),
                "Content-Type": "application/json"
            }
            payload = {
                "inputs": [clean_text],
                "target_language_code": language_code,
                "speaker": speaker,
                "model": model
            }

            with httpx.Client(timeout=15.0) as client:
                resp = client.post(cls.TTS_URL, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    audios = data.get("audios", [])
                    if audios and len(audios) > 0:
                        logger.info(f"Sarvam TTS generated {len(audios[0])} base64 chars for text: '{clean_text[:40]}...'")
                        return audios[0]
                else:
                    logger.error(f"Sarvam TTS failed HTTP {resp.status_code}: {resp.text}")

        except Exception as e:
            logger.error(f"Sarvam TTS exception: {e}")

        return None

