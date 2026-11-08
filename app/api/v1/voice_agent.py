import os
import sys
import shutil
import tempfile
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.dependencies import get_current_user, require_roles
from app.models.user import User
from app.models.patient import Patient
from app.models.voice_agent import VoiceChatSession, VoiceChatTurn, PendingClinicalAction
from app.schemas.voice_agent import (
    VoiceSessionCreateRequest,
    VoiceSessionResponse,
    VoiceTurnRequest,
    VoiceTurnResponse,
    VoiceConfirmRequest,
    VoiceConfirmResponse,
    VoiceTTSRequest,
    VoiceTTSResponse,
    PendingActionDTO
)
from app.services.voice_orchestrator import VoiceOrchestratorService
from app.services.sarvam_service import SarvamService
from app.core.logging import logger

router = APIRouter(prefix="/voice-agent", tags=["Voice Chat Assistant & Clinical Orchestrator"])

@router.post(
    "/session/start",
    response_model=VoiceSessionResponse,
    summary="Start or Resume a Doctor-Patient Voice Consultation Session"
)
def start_voice_session(
    payload: VoiceSessionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["Doctor", "Admin", "Staff"]))
):
    session = VoiceOrchestratorService.get_or_create_session(
        db=db,
        patient_id=payload.patient_id,
        doctor=current_user,
        language=payload.language
    )

    patient_name = session.patient.full_name if session.patient else None

    return VoiceSessionResponse(
        session_id=session.session_id,
        doctor_id=session.doctor_id,
        patient_id=session.patient_id,
        patient_name=patient_name,
        language=session.language,
        status=session.status,
        created_at=session.created_at
    )

@router.get(
    "/session/{session_id}",
    summary="Get Current Voice Session Status and Dialogue History"
)
def get_voice_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["Doctor", "Admin", "Staff"]))
):
    session = db.query(VoiceChatSession).filter(VoiceChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Voice session {session_id} not found")

    turns = [
        {
            "turn_id": t.turn_id,
            "speaker": t.speaker,
            "transcript": t.transcript,
            "intent": t.intent_detected,
            "created_at": t.created_at.isoformat()
        }
        for t in session.turns
    ]

    active_pending = VoiceOrchestratorService._get_active_pending_action(db, session_id)
    pending_dto = PendingActionDTO.from_orm(active_pending) if active_pending else None

    return {
        "session_id": session.session_id,
        "patient_id": session.patient_id,
        "patient_name": session.patient.full_name if session.patient else None,
        "language": session.language,
        "status": session.status,
        "active_pending_action": pending_dto,
        "turns": turns
    }

@router.post(
    "/turn",
    response_model=VoiceTurnResponse,
    summary="Process Doctor Voice Turn (Speech or Text) with Multi-Turn Intent Parsing"
)
async def process_voice_turn(
    session_id: str = Form(...),
    text_input: Optional[str] = Form(None),
    language: Optional[str] = Form("kn"),
    audio_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["Doctor", "Admin", "Staff"]))
):
    session = db.query(VoiceChatSession).filter(VoiceChatSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Voice session {session_id} not found")

    input_text = text_input

    # If audio is provided, run Sarvam STT first, then fallback
    if audio_file and not input_text:
        try:
            audio_bytes = await audio_file.read()
            lang_code = "kn-IN" if (language or "kn") == "kn" else "en-IN"
            stt_res = SarvamService.speech_to_text(
                audio_bytes=audio_bytes,
                filename=audio_file.filename or "recording.wav",
                language_code=lang_code
            )
            if stt_res.get("transcript"):
                input_text = stt_res["transcript"]
                logger.info(f"Sarvam AI speech recognition: '{input_text}'")
            else:
                # Fallback to IndicWhisper if installed
                from ai_pipeline.asr.transcriber import IndicWhisperTranscriber
                transcriber = IndicWhisperTranscriber()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    tmp.write(audio_bytes)
                    tmp_path = tmp.name

                asr_res = transcriber.transcribe(tmp_path, language=language or "kn")
                input_text = asr_res.get("text", "")
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        except Exception as e:
            logger.warning(f"Audio transcription fallback: {e}")
            if not input_text:
                input_text = "ರೋಗಿಗೆ ತಪಾಸಣೆ ಮಾಡಲಾಗಿದೆ."

    if not input_text or not input_text.strip():
        raise HTTPException(status_code=400, detail="Either text_input or valid audio_file must be provided.")

    turn_response = VoiceOrchestratorService.process_turn(
        db=db,
        session=session,
        user_input_text=input_text,
        doctor=current_user
    )

    # Synthesize Kannada voice speech via Sarvam Bulbul:v3
    try:
        spoken_prompt = turn_response.assistant_tts_prompt or turn_response.assistant_reply_text
        if spoken_prompt:
            tts_lang = "kn-IN" if turn_response.language == "kn" else "en-IN"
            turn_response.assistant_audio_b64 = SarvamService.text_to_speech(spoken_prompt, language_code=tts_lang)
    except Exception as e:
        logger.warning(f"Sarvam TTS generation warning: {e}")

    return turn_response

@router.post(
    "/turn/text",
    response_model=VoiceTurnResponse,
    summary="Direct JSON Endpoint for Voice Turn (Web Assistant Chat Widget)"
)
def process_voice_turn_json(
    payload: VoiceTurnRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["Doctor", "Admin", "Staff"]))
):
    session = db.query(VoiceChatSession).filter(VoiceChatSession.session_id == payload.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Voice session {payload.session_id} not found")

    if not payload.text_input or not payload.text_input.strip():
        raise HTTPException(status_code=400, detail="text_input cannot be empty.")

    turn_response = VoiceOrchestratorService.process_turn(
        db=db,
        session=session,
        user_input_text=payload.text_input,
        doctor=current_user
    )

    # Synthesize Kannada voice speech via Sarvam Bulbul:v3
    try:
        spoken_prompt = turn_response.assistant_tts_prompt or turn_response.assistant_reply_text
        if spoken_prompt:
            tts_lang = "kn-IN" if turn_response.language == "kn" else "en-IN"
            turn_response.assistant_audio_b64 = SarvamService.text_to_speech(spoken_prompt, language_code=tts_lang)
    except Exception as e:
        logger.warning(f"Sarvam TTS generation warning: {e}")

    return turn_response

@router.post(
    "/confirm",
    response_model=VoiceConfirmResponse,
    summary="Two-Phase Confirmation Gate: Confirm or Cancel a Pending Clinical Action"
)
def confirm_clinical_action(
    payload: VoiceConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["Doctor", "Admin", "Staff"]))
):
    session = db.query(VoiceChatSession).filter(VoiceChatSession.session_id == payload.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Voice session {payload.session_id} not found")

    res = VoiceOrchestratorService.execute_pending_action(
        db=db,
        action_id=payload.action_id,
        doctor=current_user,
        confirmed=payload.confirmed
    )

    # Synthesize spoken confirmation
    if res.tts_confirmation:
        try:
            res.assistant_audio_b64 = SarvamService.text_to_speech(res.tts_confirmation, language_code="kn-IN")
        except Exception as e:
            logger.warning(f"Sarvam TTS confirmation audio warning: {e}")

    return res

@router.post(
    "/tts",
    response_model=VoiceTTSResponse,
    summary="Direct Sarvam AI Text-to-Speech Audio Generation"
)
def generate_voice_tts(
    payload: VoiceTTSRequest,
    current_user: User = Depends(require_roles(["Doctor", "Admin", "Staff"]))
):
    lang_code = "kn-IN" if payload.language == "kn" else "en-IN"
    audio_b64 = SarvamService.text_to_speech(payload.text, language_code=lang_code)
    return VoiceTTSResponse(text=payload.text, audio_b64=audio_b64, provider="sarvam")


