import re
import uuid
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone, timedelta
import json
import httpx

from app.schemas.consultation import ConsultationCreateRequest
from app.schemas.voice_agent import PendingActionDTO, VoiceTurnResponse, VoiceConfirmResponse
from app.services.medical_translator import EnglishToKannadaMedicalTranslator
from app.services.consultation_service import ConsultationService
from app.db.mongo import get_mongo_db, get_next_sequence, clean_doc, DictObj
from app.core.config import settings
from app.core.logging import logger

class SessionWrapper:
    """
    MongoDB Voice Chat Session wrapper with backwards-compatible attribute access.
    """
    def __init__(self, data: Dict[str, Any], db=None):
        self._data = clean_doc(data) or {}
        self.session_id = self._data.get("session_id")
        self.doctor_id = self._data.get("doctor_id")
        self.patient_id = self._data.get("patient_id")
        self.language = self._data.get("language", "kn")
        self.status = self._data.get("status", "active")
        self.created_at = self._data.get("created_at") or datetime.now(timezone.utc)
        self.updated_at = self._data.get("updated_at") or datetime.now(timezone.utc)
        self._db = db

    @property
    def patient(self):
        if not self.patient_id or self._db is None:
            return None
        p = self._db.patients.find_one({"patient_id": self.patient_id})
        return DictObj(p) if p else None

    @property
    def turns(self):
        if not self.session_id or self._db is None:
            return []
        raw_turns = list(self._db.voice_chat_turns.find({"session_id": self.session_id}).sort("created_at", 1))
        return [DictObj(t) for t in raw_turns]

    def get(self, key, default=None):
        return self._data.get(key, default)


class ActionWrapper:
    """
    MongoDB Pending Clinical Action wrapper.
    """
    def __init__(self, data: Dict[str, Any]):
        self._data = clean_doc(data) or {}
        self.action_id = self._data.get("action_id")
        self.session_id = self._data.get("session_id")
        self.action_type = self._data.get("action_type")
        self.patient_id = self._data.get("patient_id")
        self.payload = self._data.get("payload", {})
        self.tts_prompt_kannada = self._data.get("tts_prompt_kannada", "")
        self.tts_prompt_english = self._data.get("tts_prompt_english", "")
        self.status = self._data.get("status", "pending")
        self.created_at = self._data.get("created_at") or datetime.now(timezone.utc)
        self.expires_at = self._data.get("expires_at") or (datetime.now(timezone.utc) + timedelta(minutes=5))

    def to_dto(self) -> PendingActionDTO:
        return PendingActionDTO(
            action_id=self.action_id,
            session_id=self.session_id,
            action_type=self.action_type,
            patient_id=self.patient_id,
            payload=self.payload,
            tts_prompt_kannada=self.tts_prompt_kannada,
            tts_prompt_english=self.tts_prompt_english,
            status=self.status,
            created_at=self.created_at,
            expires_at=self.expires_at
        )


class VoiceOrchestratorService:
    """
    Intelligent Multi-Turn Clinical Voice Agent Orchestrator powered by MongoDB.
    Handles Kannada, English, and Code-Mixed voice dialogues,
    clinical entity extraction, patient search, and two-phase confirmation gating.
    """

    CONFIRMATION_KEYWORDS = {
        "kn": ["ಹೌದು", "ಸರಿ", "ಖಚಿತಪಡಿಸಿ", "ಮಾಡಬಹುದು", "ಸರಿ ಇದೆ", "ಸೇವ್ ಮಾಡಿ", "ಖಂಡಿತ", "ಒಪ್ಪಿಗೆ", "ಸೇವ್"],
        "en": ["yes", "confirm", "save", "proceed", "okay", "ok", "correct", "sure", "approve", "done"]
    }

    REJECTION_KEYWORDS = {
        "kn": ["ಬೇಡ", "ರದ್ದು", "ತಪ್ಪು", "ಬೇಡವೇ ಬೇಡ", "ಕ್ಯಾನ್ಸಲ್", "ಬೇರೆ ಬರೆಯಿರಿ"],
        "en": ["no", "cancel", "reject", "stop", "wrong", "do not save", "discard", "abort"]
    }

    @classmethod
    def get_or_create_session(
        cls,
        db=None,
        session_id: Optional[str] = None,
        patient_id: Optional[int] = None,
        doctor: Optional[Any] = None,
        language: str = "kn"
    ) -> SessionWrapper:
        if db is None:
            db = get_mongo_db()

        if session_id:
            sess = db.voice_chat_sessions.find_one({"session_id": session_id})
            if sess:
                if patient_id and sess.get("patient_id") != patient_id:
                    db.voice_chat_sessions.update_one(
                        {"session_id": session_id},
                        {"$set": {"patient_id": patient_id, "updated_at": datetime.now(timezone.utc)}}
                    )
                    sess["patient_id"] = patient_id
                return SessionWrapper(sess, db)

        new_id = str(uuid.uuid4())
        doctor_id = getattr(doctor, "user_id", None) if doctor else None
        doc = {
            "session_id": new_id,
            "doctor_id": doctor_id,
            "patient_id": patient_id,
            "language": language,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        db.voice_chat_sessions.insert_one(doc)
        return SessionWrapper(doc, db)

    @classmethod
    def process_turn(
        cls,
        db=None,
        session: Any = None,
        user_input_text: str = "",
        doctor: Optional[Any] = None,
        audio_url: Optional[str] = None
    ) -> VoiceTurnResponse:
        if db is None:
            db = get_mongo_db()

        cleaned_input = user_input_text.strip()
        logger.info(f"Voice Turn [{session.session_id}]: '{cleaned_input}'")

        # 1. Log Doctor's speech turn
        turn_id = str(uuid.uuid4())
        doctor_turn = {
            "turn_id": turn_id,
            "session_id": session.session_id,
            "speaker": "doctor",
            "transcript": cleaned_input,
            "audio_url": audio_url,
            "intent_detected": None,
            "created_at": datetime.now(timezone.utc)
        }
        db.voice_chat_turns.insert_one(doctor_turn)

        # 2. Check for active pending actions first (Two-Phase Gate)
        active_pending = cls._get_active_pending_action(db, session.session_id)
        if active_pending:
            if cls._is_confirmation(cleaned_input):
                confirm_res = cls.execute_pending_action(
                    db=db,
                    action_id=active_pending.action_id,
                    doctor=doctor,
                    confirmed=True
                )
                db.voice_chat_turns.update_one({"turn_id": turn_id}, {"$set": {"intent_detected": "CONFIRM_ACTION"}})

                # Refresh session to pick up updated patient_id (e.g. after CREATE_PATIENT)
                sess_doc = db.voice_chat_sessions.find_one({"session_id": session.session_id})
                if sess_doc:
                    session.patient_id = sess_doc.get("patient_id")

                patient_info = None
                if session.patient_id:
                    p = db.patients.find_one({"patient_id": session.patient_id})
                    if p:
                        patient_info = {
                            "patient_id": p.get("patient_id"),
                            "name": p.get("full_name"),
                            "age": p.get("age"),
                            "gender": p.get("gender")
                        }

                assistant_text = confirm_res.tts_confirmation or confirm_res.message or "ಖಚಿತಗೊಂಡಿದೆ!"
                assistant_tts = assistant_text

                cls._log_assistant_turn(db, session.session_id, assistant_text, "CONFIRM_ACTION")
                return VoiceTurnResponse(
                    session_id=session.session_id,
                    turn_id=str(uuid.uuid4()),
                    user_transcript=cleaned_input,
                    assistant_reply_text=assistant_text,
                    assistant_tts_prompt=assistant_tts,
                    language=session.language,
                    intent_detected="CONFIRM_ACTION",
                    patient=patient_info,
                    pending_action=None,
                    requires_confirmation=False
                )
            elif cls._is_rejection(cleaned_input):
                cls.execute_pending_action(
                    db=db,
                    action_id=active_pending.action_id,
                    doctor=doctor,
                    confirmed=False
                )
                db.voice_chat_turns.update_one({"turn_id": turn_id}, {"$set": {"intent_detected": "REJECT_ACTION"}})

                assistant_text = "ಸರಿ, ಈ ಶಿಫಾರಸನ್ನು ರದ್ದುಗೊಳಿಸಲಾಗಿದೆ (Action cancelled). ಬೇರೆ ಏನು ದಾಖಲಿಸಬೇಕು?"
                assistant_tts = assistant_text
                cls._log_assistant_turn(db, session.session_id, assistant_text, "REJECT_ACTION")
                return VoiceTurnResponse(
                    session_id=session.session_id,
                    turn_id=str(uuid.uuid4()),
                    user_transcript=cleaned_input,
                    assistant_reply_text=assistant_text,
                    assistant_tts_prompt=assistant_tts,
                    language=session.language,
                    intent_detected="REJECT_ACTION",
                    pending_action=None,
                    requires_confirmation=False
                )

        # 3. Detect New Patient Creation / Registration Request (e.g. "Create patient Tejas Padaki")
        patient_create_data = cls._detect_patient_creation(cleaned_input)
        if patient_create_data:
            db.voice_chat_turns.update_one({"turn_id": turn_id}, {"$set": {"intent_detected": "STAGE_PATIENT_CREATION"}})

            p_name = patient_create_data["full_name"]
            p_gender_kn = "ಪುರುಷ" if patient_create_data["gender"] == "Male" else "ಮಹಿಳೆ"
            p_age = patient_create_data["age"]

            spoken_kn = f"ಹೊಸ ರೋಗಿ {p_name} ({p_age} ವರ್ಷ, {p_gender_kn}) ಅವರ ಪ್ರೊಫೈಲ್ ರಚಿಸಬೇಕೇ? ದೃಢೀಕರಿಸಿ ಸೇವ್ ಮಾಡಲೇ?"
            spoken_en = f"Shall I register new patient {p_name} ({p_age} years, {patient_create_data['gender']})? Confirm to create profile."

            pending_action_doc = {
                "action_id": str(uuid.uuid4()),
                "session_id": session.session_id,
                "action_type": "CREATE_PATIENT",
                "patient_id": None,
                "payload": patient_create_data,
                "tts_prompt_kannada": spoken_kn,
                "tts_prompt_english": spoken_en,
                "status": "pending",
                "created_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)
            }
            db.pending_clinical_actions.insert_one(pending_action_doc)
            action_wrapper = ActionWrapper(pending_action_doc)

            cls._log_assistant_turn(db, session.session_id, spoken_kn, "STAGE_PATIENT_CREATION")
            return VoiceTurnResponse(
                session_id=session.session_id,
                turn_id=str(uuid.uuid4()),
                user_transcript=cleaned_input,
                assistant_reply_text=spoken_kn,
                assistant_tts_prompt=spoken_kn,
                language=session.language,
                intent_detected="STAGE_PATIENT_CREATION",
                pending_action=action_wrapper.to_dto(),
                patient={"patient_id": None, "name": p_name},
                requires_confirmation=True
            )

        # 4. Patient Switch / Search Intent
        patient_matched = cls._detect_patient_search(db, cleaned_input)
        if patient_matched:
            matched_id = patient_matched.get("patient_id")
            session.patient_id = matched_id
            db.voice_chat_sessions.update_one(
                {"session_id": session.session_id},
                {"$set": {"patient_id": matched_id, "updated_at": datetime.now(timezone.utc)}}
            )
            db.voice_chat_turns.update_one({"turn_id": turn_id}, {"$set": {"intent_detected": "SWITCH_PATIENT"}})

            p_name = patient_matched.get("full_name")
            p_age = patient_matched.get("age", 30)
            p_gender = patient_matched.get("gender", "Unknown")

            kannada_reply = (
                f"ರೋಗಿ {p_name} ({p_age} ವರ್ಷ, {p_gender}) ಅವರ ಪ್ರೊಫೈಲ್ ತೆರೆಯಲಾಗಿದೆ. "
                f"ಅವರ ಇತ್ತೀಚಿನ ತೊಂದರೆ ಅಥವಾ ಔಷಧಿಗಳನ್ನು ತಿಳಿಸಿ."
            )
            cls._log_assistant_turn(db, session.session_id, kannada_reply, "SWITCH_PATIENT")
            return VoiceTurnResponse(
                session_id=session.session_id,
                turn_id=str(uuid.uuid4()),
                user_transcript=cleaned_input,
                assistant_reply_text=kannada_reply,
                assistant_tts_prompt=kannada_reply,
                language=session.language,
                intent_detected="SWITCH_PATIENT",
                patient={
                    "patient_id": matched_id,
                    "name": p_name,
                    "age": p_age,
                    "gender": p_gender
                },
                pending_action=None,
                requires_confirmation=False
            )

        # 5. Clinical Query / History Request
        if cls._is_history_query(cleaned_input):
            db.voice_chat_turns.update_one({"turn_id": turn_id}, {"$set": {"intent_detected": "PATIENT_HISTORY"}})
            history_reply = cls._build_patient_history_reply(db, session.patient_id)
            cls._log_assistant_turn(db, session.session_id, history_reply, "PATIENT_HISTORY")
            return VoiceTurnResponse(
                session_id=session.session_id,
                turn_id=str(uuid.uuid4()),
                user_transcript=cleaned_input,
                assistant_reply_text=history_reply,
                assistant_tts_prompt=history_reply,
                language=session.language,
                intent_detected="PATIENT_HISTORY",
                requires_confirmation=False
            )

        # 6. Clinical Dictation & Prescription Staging (Primary Feature)
        extracted_data = cls._extract_clinical_information(cleaned_input)
        if extracted_data["has_clinical_content"]:
            db.voice_chat_turns.update_one({"turn_id": turn_id}, {"$set": {"intent_detected": "STAGE_PRESCRIPTION"}})

            current_patient = db.patients.find_one({"patient_id": session.patient_id}) if session.patient_id else None
            patient_name = current_patient.get("full_name") if current_patient else "ಆಯ್ಕೆಯಾದ ರೋಗಿ"

            # Formulate Kannada & English Readbacks
            spoken_kn, spoken_en = cls._formulate_confirmation_readback(patient_name, extracted_data)

            # Create Pending Action with 5-minute TTL
            pending_action_doc = {
                "action_id": str(uuid.uuid4()),
                "session_id": session.session_id,
                "action_type": "CREATE_PRESCRIPTION",
                "patient_id": session.patient_id,
                "payload": extracted_data,
                "tts_prompt_kannada": spoken_kn,
                "tts_prompt_english": spoken_en,
                "status": "pending",
                "created_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)
            }
            db.pending_clinical_actions.insert_one(pending_action_doc)
            action_wrapper = ActionWrapper(pending_action_doc)

            cls._log_assistant_turn(db, session.session_id, spoken_kn, "STAGE_PRESCRIPTION")

            return VoiceTurnResponse(
                session_id=session.session_id,
                turn_id=str(uuid.uuid4()),
                user_transcript=cleaned_input,
                assistant_reply_text=spoken_kn,
                assistant_tts_prompt=spoken_kn,
                language=session.language,
                intent_detected="STAGE_PRESCRIPTION",
                pending_action=action_wrapper.to_dto(),
                patient={"patient_id": current_patient.get("patient_id"), "name": current_patient.get("full_name")} if current_patient else None,
                requires_confirmation=True
            )

        # 7. Fallback General Assistance
        db.voice_chat_turns.update_one({"turn_id": turn_id}, {"$set": {"intent_detected": "GENERAL_CONVERSATION"}})
        default_reply = (
            "ನಮಸ್ಕಾರ ಡಾಕ್ಟರ್. ನೀವು ರೋಗಿಯ ಲಕ್ಷಣಗಳು (ಸಂಪರ್ಕಿಸಿ), ರಕ್ತದೊತ್ತಡ, ರೋಗನಿರ್ಣಯ ಅಥವಾ ಮಾತ್ರೆಗಳ ಹೆಸರನ್ನು ಧ್ವನಿಯ ಮೂಲಕ ಹೇಳಬಹುದು. "
            "ಉದಾಹರಣೆಗೆ: 'BP 150/95, Telmisartan 40mg ದಿನಕ್ಕೆ ಒಮ್ಮೆ ಬೆಳಗ್ಗೆ'."
        )
        cls._log_assistant_turn(db, session.session_id, default_reply, "GENERAL_CONVERSATION")
        return VoiceTurnResponse(
            session_id=session.session_id,
            turn_id=str(uuid.uuid4()),
            user_transcript=cleaned_input,
            assistant_reply_text=default_reply,
            assistant_tts_prompt=default_reply,
            language=session.language,
            intent_detected="GENERAL_CONVERSATION",
            requires_confirmation=False
        )

    @classmethod
    def execute_pending_action(
        cls,
        db=None,
        action_id: str = "",
        doctor: Optional[Any] = None,
        confirmed: bool = True
    ) -> VoiceConfirmResponse:
        if db is None:
            db = get_mongo_db()

        action = db.pending_clinical_actions.find_one({"action_id": action_id})
        if not action:
            return VoiceConfirmResponse(
                success=False,
                action_id=action_id,
                status="not_found",
                message="Pending action not found or expired."
            )

        if not confirmed:
            db.pending_clinical_actions.update_one({"action_id": action_id}, {"$set": {"status": "rejected"}})
            return VoiceConfirmResponse(
                success=True,
                action_id=action_id,
                status="rejected",
                message="Clinical action was cancelled.",
                tts_confirmation="ಕ್ರಿಯೆಯನ್ನು ರದ್ದುಗೊಳಿಸಲಾಗಿದೆ."
            )

        # Confirm action
        db.pending_clinical_actions.update_one({"action_id": action_id}, {"$set": {"status": "confirmed"}})

        payload = action.get("payload") or {}

        # Branch A: Create Patient Action
        if action.get("action_type") == "CREATE_PATIENT":
            full_name = payload.get("full_name") or "Tejas Padaki"
            gender = payload.get("gender") or "Male"
            age = int(payload.get("age") or 30)
            phone = payload.get("phone")
            if not phone:
                import random
                phone = f"+91 9845{random.randint(100000, 999999)}"

            from datetime import date
            today = date.today()
            dob_val = date(today.year - age, 1, 1).isoformat()

            new_patient_id = get_next_sequence("patient_id", db)
            patient_doc = {
                "patient_id": new_patient_id,
                "full_name": full_name,
                "gender": gender,
                "dob": dob_val,
                "age": age,
                "phone": phone,
                "preferred_language": payload.get("preferred_language", "Kannada"),
                "blood_group": payload.get("blood_group", "O+"),
                "medical_history": [],
                "allergies": [],
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            db.patients.insert_one(patient_doc)

            # Associate active session with new patient immediately
            sess_id = action.get("session_id")
            if sess_id:
                db.voice_chat_sessions.update_one(
                    {"session_id": sess_id},
                    {"$set": {"patient_id": new_patient_id, "updated_at": datetime.now(timezone.utc)}}
                )

            msg_kn = (
                f"ಖಚಿತಗೊಂಡಿದೆ! ರೋಗಿ {full_name} (#PT-{new_patient_id:04d}) ಯಶಸ್ವಿಯಾಗಿ ನೋಂದಾಯಿಸಲಾಗಿದೆ. "
                f"ಈಗ ಅವರ ರೋಗಲಕ್ಷಣಗಳು (symptoms), ಬಿಪಿ ಮತ್ತು ಔಷಧಿಗಳನ್ನು ತಿಳಿಸಿ."
            )
            return VoiceConfirmResponse(
                success=True,
                action_id=action_id,
                status="confirmed",
                message=f"Patient {full_name} registered successfully (#PT-{new_patient_id:04d}).",
                consultation_id=None,
                report_id=None,
                tts_confirmation=msg_kn
            )

        # Branch B: Create Prescription / Finalize Consultation
        patient_id = action.get("patient_id") or payload.get("patient_id") or 1

        acting_doctor = doctor
        if not acting_doctor:
            from app.core.dependencies import MongoUser
            user_doc = db.users.find_one({"is_active": True})
            acting_doctor = MongoUser(user_doc) if user_doc else None
        elif isinstance(acting_doctor, dict):
            from app.core.dependencies import MongoUser
            acting_doctor = MongoUser(acting_doctor)

        consultation_req = ConsultationCreateRequest(
            patient_id=patient_id,
            transcript_text=payload.get("kannada_transcript") or "ಧ್ವನಿ ಸಂವಾದದ ಮೂಲಕ ನಮೂದಾದ ಸಮಾಲೋಚನೆ.",
            language="kn",
            original_english_speech=payload.get("original_text") or "",
            symptoms=payload.get("symptoms", []),
            diagnosis=payload.get("diagnosis", []),
            medications=payload.get("medications", []),
            advice=payload.get("advice", []),
            doctor_signature_confirmed=True
        )

        try:
            consultation = ConsultationService.create_and_approve_consultation(
                db=db,
                payload=consultation_req,
                current_user=acting_doctor
            )
            return VoiceConfirmResponse(
                success=True,
                action_id=action_id,
                status="confirmed",
                message="Consultation verified, signed and saved to EHR.",
                consultation_id=consultation.consultation_id,
                report_id=consultation.report_id,
                tts_confirmation=f"ಸಮಾಲೋಚನೆ ವರದಿ #{consultation.report_id} ಯಶಸ್ವಿಯಾಗಿ ಮುಕ್ತಾಯಗೊಂಡಿದೆ."
            )
        except Exception as e:
            logger.error(f"Error executing pending clinical action: {e}", exc_info=True)
            return VoiceConfirmResponse(
                success=False,
                action_id=action_id,
                status="error",
                message=f"Failed to commit consultation: {str(e)}"
            )

    # ------------------ Helper Parsing & NLP Logic ------------------

    @classmethod
    def _is_confirmation(cls, text: str) -> bool:
        lower = text.lower()
        for kw in cls.CONFIRMATION_KEYWORDS["en"] + cls.CONFIRMATION_KEYWORDS["kn"]:
            if kw in lower or kw in text:
                return True
        return False

    @classmethod
    def _is_rejection(cls, text: str) -> bool:
        lower = text.lower()
        for kw in cls.REJECTION_KEYWORDS["en"] + cls.REJECTION_KEYWORDS["kn"]:
            if kw in lower or kw in text:
                return True
        return False

    @classmethod
    def _detect_patient_creation(cls, text: str) -> Optional[Dict[str, Any]]:
        """
        Detects doctor requests to register/create a new patient.
        Supports phrases like:
        - "Create patient Tejas Padaki"
        - "Create the patient name Tejas Padaki"
        - "Add patient Tejas Padaki, 28 years male"
        - "New patient Tejas Padaki"
        - "ಹೊಸ ರೋಗಿ ತೇಜಸ್ ಪಾಡಕಿ"
        """
        lower = text.lower()
        create_triggers = [
            "create patient", "create the patient", "add patient", "add a patient",
            "new patient", "register patient", "register a new patient", "create new patient",
            "ಹೊಸ ರೋಗಿ", "ರೋಗಿ ಸೇರಿಸಿ", "ಹೊಸ ಪೇಷೆಂಟ್", "ರೋಗಿ ರಚಿಸಿ", "ಹೊಸ ರೋಗಿಯನ್ನು"
        ]

        is_creation = any(trigger in lower for trigger in create_triggers) or any(trigger in text for trigger in create_triggers)
        if not is_creation:
            return None

        # Clean trigger words out to isolate the patient's name
        cleaned = text
        for trigger in create_triggers:
            cleaned = re.sub(re.escape(trigger), " ", cleaned, flags=re.IGNORECASE)

        # Remove filler words: "name", "named", "called", "is", "for", "ಹೆಸರು", "ಹೆಸರಿನ"
        cleaned = re.sub(r'\b(name|named|called|is|for|with|who|has|ಹೆಸರು|ಹೆಸರಿನ|ಎಂಬ)\b', ' ', cleaned, flags=re.IGNORECASE)

        # Detect Age if present e.g. "28 years", "28 yrs", "28 ವಯಸ್ಸು"
        age_match = re.search(r'\b(\d{1,3})\s*(years?|yrs?|ವಯಸ್ಸು|ವರ್ಷ)\b', cleaned, re.IGNORECASE)
        age = int(age_match.group(1)) if age_match else 30
        if age_match:
            cleaned = cleaned.replace(age_match.group(0), " ")

        # Detect Gender if present
        gender = "Male"
        if re.search(r'\b(female|woman|girl|lady|ಮಹಿಳೆ|ಹೆಣ್ಣು)\b', cleaned, re.IGNORECASE):
            gender = "Female"
        elif re.search(r'\b(male|man|boy|gentleman|ಪುರುಷ|ಗಂಡು)\b', cleaned, re.IGNORECASE):
            gender = "Male"
        cleaned = re.sub(r'\b(female|male|man|woman|boy|girl|lady|gentleman|ಮಹಿಳೆ|ಪುರುಷ|ಗಂಡು|ಹೆಣ್ಣು)\b', ' ', cleaned, flags=re.IGNORECASE)

        # Detect Phone if present (10 digits)
        phone_match = re.search(r'\b(\+?91[\-\s]?)?[6-9]\d{9}\b', cleaned)
        phone = phone_match.group(0) if phone_match else None
        if phone_match:
            cleaned = cleaned.replace(phone_match.group(0), " ")

        # Clean punctuation and extra whitespace
        name_clean = re.sub(r'[,.\-_/]', ' ', cleaned).strip()
        tokens = [w for w in name_clean.split() if w.lower() not in ["the", "a", "an", "and", "please", "kindly", "ಅವರ", "ಅವರನ್ನು"]]
        name = " ".join(tokens).strip()

        if not name or len(name) < 2:
            name = "Tejas Padaki"  # Default sample requested by user

        name = name.title() if name.isascii() else name

        if not phone:
            import random
            phone = f"+91 9845{random.randint(100000, 999999)}"

        return {
            "full_name": name,
            "gender": gender,
            "age": age,
            "phone": phone,
            "preferred_language": "Kannada",
            "blood_group": "O+"
        }

    @classmethod
    def _detect_patient_search(cls, db, text: str) -> Optional[Dict[str, Any]]:
        patients = list(db.patients.find({"is_active": True}))
        lower = text.lower()
        for p in patients:
            p_name = p.get("full_name", "")
            first_name = p_name.split()[0].lower() if p_name else ""
            if (first_name and first_name in lower) or (p_name and p_name.lower() in lower):
                return p
            # Match Kannada patient names if present
            if p_name and p_name in text:
                return p
        return None

    @classmethod
    def _is_history_query(cls, text: str) -> bool:
        lower = text.lower()
        keywords = ["history", "previous", "past", "ಹಿಂದಿನ", "ಹಿಸ್ಟರಿ", "ತಪಾಸಣೆ", "records", "ವಿಸಿಟ್", "last visit"]
        return any(k in lower or k in text for k in keywords)

    @classmethod
    def _build_patient_history_reply(cls, db, patient_id: Optional[int]) -> str:
        if not patient_id:
            return "ಯಾವ ರೋಗಿಯ ಇತಿಹಾಸ ತಿಳಿಯಬೇಕೆಂದು ದಯವಿಟ್ಟು ಅವರ ಹೆಸರನ್ನು ಹೇಳಿ (ಉದಾ: 'ರೋಗಿ ಬಸವರಾಜ್')."

        patient = db.patients.find_one({"patient_id": patient_id})
        if not patient:
            return "ರೋಗಿಯ ವಿವರ ಕಂಡುಬಂದಿಲ್ಲ."

        consultations = list(db.consultations.find({"patient_id": patient_id}).sort("created_at", -1).limit(2))
        if not consultations:
            return f"ರೋಗಿ {patient.get('full_name')} ಅವರಿಗೆ ಈ ಮೊದಲು ಯಾವುದೇ ಸಮಾಲೋಚನೆಗಳು ದಾಖಲಾಗಿಲ್ಲ."

        latest = consultations[0]
        diagnosis = latest.get("diagnosis", [])
        diag_str = ", ".join([d.get("entity", "") if isinstance(d, dict) else str(d) for d in diagnosis]) if diagnosis else "ಸಾಮಾನ್ಯ ತಪಾಸಣೆ"
        rep_id = latest.get("report_id", latest.get("consultation_id"))
        return f"ರೋಗಿ {patient.get('full_name')} ಅವರ ಕೊನೆಯ ಭೇಟಿಯಲ್ಲಿ ರೋಗನಿರ್ಣಯ: {diag_str}. ಇತ್ತೀಚಿನ ವರದಿ ಸಂಖ್ಯೆ #{rep_id}."

    @classmethod
    def _call_gemini_extraction(cls, text: str) -> Optional[Dict[str, Any]]:
        """
        Uses Gemini to parse complex multilingual clinical dictation
        when GEMINI_API_KEY is configured.
        """
        if not settings.GEMINI_API_KEY:
            return None

        prompt = f"""
        You are a clinical AI medical assistant in an Indian hospital OPD.
        Analyze this doctor's voice dictation (in English, Kannada, or code-mixed speech):
        "{text}"

        Extract structured medical information in JSON format with keys:
        - "symptoms": list of objects {{"entity": str, "english": str, "duration": str}}
        - "diagnosis": list of objects {{"entity": str, "english": str}}
        - "medications": list of objects {{"drug_name": str, "dosage": str, "frequency": str, "duration": str}}
        - "advice": list of objects {{"instruction": str}}
        - "vitals": object {{"bp": str, "pulse": str, "temperature": str}}
        - "kannada_summary": str (spoken Kannada clinical sentence)

        Return ONLY raw valid JSON without markdown code fences.
        """
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
            }
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidate = data["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(candidate)
        except Exception as e:
            logger.warning(f"Gemini API call fallback to rule-based parser: {e}")
        return None

    @classmethod
    def _extract_clinical_information(cls, text: str) -> Dict[str, Any]:
        """
        Extracts medical entities (symptoms, diagnosis, medications, advice, vitals)
        using Gemini (if API key present) or EnglishToKannadaMedicalTranslator.
        """
        if settings.GEMINI_API_KEY:
            gemini_res = cls._call_gemini_extraction(text)
            if gemini_res and (gemini_res.get("medications") or gemini_res.get("diagnosis") or gemini_res.get("symptoms") or gemini_res.get("vitals")):
                kannada_trans = gemini_res.get("kannada_summary") or EnglishToKannadaMedicalTranslator.translate_text_to_kannada(text)
                return {
                    "has_clinical_content": True,
                    "original_text": text,
                    "kannada_transcript": kannada_trans,
                    "vitals": gemini_res.get("vitals", {}),
                    "symptoms": gemini_res.get("symptoms", []),
                    "diagnosis": gemini_res.get("diagnosis", []),
                    "medications": gemini_res.get("medications", []),
                    "advice": gemini_res.get("advice", [])
                }

        # Local Deterministic Parser Fallback
        entities = EnglishToKannadaMedicalTranslator.extract_from_english_text(text)
        kannada_trans = EnglishToKannadaMedicalTranslator.translate_text_to_kannada(text)

        # Check for vitals (BP, Pulse, Temp)
        bp_match = re.search(r'\b(bp|blood pressure|ರಕ್ತದೊತ್ತಡ)?\s*([0-9]{2,3}\s*/\s*[0-9]{2,3})\b', text, re.IGNORECASE)
        vitals = {}
        if bp_match:
            vitals["bp"] = bp_match.group(2).replace(" ", "")

        has_content = bool(
            entities.get("symptoms") or
            entities.get("diagnosis") or
            entities.get("medications") or
            vitals
        )

        return {
            "has_clinical_content": has_content,
            "original_text": text,
            "kannada_transcript": kannada_trans,
            "vitals": vitals,
            "symptoms": entities.get("symptoms", []),
            "diagnosis": entities.get("diagnosis", []),
            "medications": entities.get("medications", []),
            "advice": entities.get("advice", [])
        }

    @classmethod
    def _formulate_confirmation_readback(cls, patient_name: str, data: Dict[str, Any]) -> Tuple[str, str]:
        """
        Builds natural spoken confirmation readbacks for the Two-Phase Gate.
        """
        kn_parts = [f"ರೋಗಿ {patient_name} ಅವರಿಗೆ"]
        en_parts = [f"For patient {patient_name}:"]

        if data.get("vitals", {}).get("bp"):
            bp = data["vitals"]["bp"]
            kn_parts.append(f"ಬಿಪಿ {bp}")
            en_parts.append(f"BP {bp}")

        if data.get("diagnosis"):
            diag = data["diagnosis"][0].get("entity", "")
            kn_parts.append(f"ರೋಗನಿರ್ಣಯ: {diag}")
            en_parts.append(f"Diagnosis: {diag}")

        if data.get("medications"):
            med_kn_list = []
            med_en_list = []
            for m in data["medications"]:
                med_kn_list.append(f"{m.get('drug_name', '')} {m.get('dosage', '')} ({m.get('frequency', '')})")
                med_en_list.append(f"{m.get('drug_name', '')} {m.get('dosage', '')}")
            kn_parts.append(f"ಶಿಫಾರಸು ಮಾಡಿದ ಮಾತ್ರೆಗಳು: {', '.join(med_kn_list)}")
            en_parts.append(f"Prescribed: {', '.join(med_en_list)}")

        kn_parts.append("ದಾಖಲಿಸಿದ್ದೇನೆ. ಇದನ್ನು Save ಮಾಡಿ ವರದಿ ರಚಿಸಲೇ?")
        en_parts.append("staged. Should I confirm and save to the EHR?")

        return " ".join(kn_parts), " ".join(en_parts)

    @classmethod
    def _get_active_pending_action(cls, db, session_id: str) -> Optional[ActionWrapper]:
        now = datetime.now(timezone.utc)
        doc = db.pending_clinical_actions.find_one({
            "session_id": session_id,
            "status": "pending",
            "expires_at": {"$gt": now}
        })
        return ActionWrapper(doc) if doc else None

    @classmethod
    def _log_assistant_turn(cls, db, session_id: str, text: str, intent: str):
        turn = {
            "turn_id": str(uuid.uuid4()),
            "session_id": session_id,
            "speaker": "assistant",
            "transcript": text,
            "intent_detected": intent,
            "created_at": datetime.now(timezone.utc)
        }
        db.voice_chat_turns.insert_one(turn)
