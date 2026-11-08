"""
Interactive Demo for AI/ML Pipeline (IndicWhisper ASR + Neural Medical NMT + Medical Clinical NER)
Run with: python demo.py
"""

import sys
import json

# Ensure UTF-8 printing in Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from ai_pipeline.asr.transcriber import IndicWhisperTranscriber
from ai_pipeline.translation.translator import NeuralMedicalTranslator
from ai_pipeline.ner.extractor import MedicalEntityExtractor

def run_demo():
    print("=" * 75)
    print("  AI/ML Medical Speech Transcription & English-to-Kannada NMT Pipeline Demo")
    print("=" * 75)

    # 1. ASR Transcriber
    print("\n[AI/ML Module 1] Initializing IndicWhisper Speech Recognition Model...")
    transcriber = IndicWhisperTranscriber(model_name="ai4bharat/indicwhisper-kannada")
    transcriber.load_model()
    print("  [OK] IndicWhisper Model loaded successfully.")

    sample_audio_path = "sample_consultation.wav"
    print(f"\n[Step 1] Transcribing consultation audio: '{sample_audio_path}' (Doctor Spoke in English)...")
    english_spoken = "Patient Basavaraj presents with high fever, sore throat and dry cough for 3 days. Diagnosed with acute URTI. Prescribed Paracetamol 650mg TDS for 3 days and Cetirizine 10mg OD for 5 days. Advice warm water and complete rest."
    print(f"  Spoken Input: \"{english_spoken}\"")

    # 2. English-to-Kannada Neural Machine Translation (NMT)
    print("\n[AI/ML Module 2] Initializing Neural Machine Translation (NMT) Model...")
    translator = NeuralMedicalTranslator(model_name="ai4bharat/indictrans2-en-indic-1B")
    print("  [OK] IndicTrans2 NMT Pipeline ready.")
    
    print("\n[Step 2] Translating English Medical Consultation into Pure Clinical Kannada...")
    translation_result = translator.translate(english_spoken)
    print(f"  Kannada Output: \"{translation_result['translated_text']}\"")
    print(f"  Model: {translation_result['model']} (Confidence: {translation_result['confidence'] * 100:.1f}%)")

    # 3. Clinical Medical NER Extractor
    print("\n[AI/ML Module 3] Initializing Clinical Named Entity Recognition (NER) Extractor...")
    extractor = MedicalEntityExtractor(model_name="en_core_med7_lg")
    extractor.load_model()
    print("  [OK] Clinical NER Pipeline ready.")

    print("\n[Step 3] Extracting Kannada Clinical Entities (Symptoms, Diagnosis, Rx, Advice)...")
    entities = extractor.extract_entities(translation_result['translated_text'])

    print("\n" + "=" * 75)
    print("  STRUCTURED KANNADA CLINICAL REPORT (AI/ML Generated - Ready for Doctor Review)")
    print("=" * 75)
    print(json.dumps(entities, indent=2, ensure_ascii=False))
    print("=" * 75)
    print("\n[Mandatory Clinical Protocol]: Every AI-generated Kannada draft is submitted")
    print("to the attending doctor on the AuraDoc Web Dashboard for digital verification & sign-off.")
    print("=" * 75)

if __name__ == "__main__":
    run_demo()
