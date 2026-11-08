# AI Pipeline Package (`ai_pipeline`)

Stub package for the ASR (Automatic Speech Recognition) and Medical Named Entity Recognition (NER) components of the **AI-Based Multilingual Medical Speech Transcription & Documentation System**.

## Modules
- `ai_pipeline.asr.IndicWhisperTranscriber`: Speech recognition module for Kannada, English, and Kannada-English code-mixed medical audio.
- `ai_pipeline.ner.MedicalEntityExtractor`: NLP extraction pipeline for clinical entities:
  - Symptoms (with duration & Kannada/English text)
  - Diagnosis
  - Medications (Drug, dosage, frequency, duration)
  - Clinical Advice & Patient Instructions

## Installation
```bash
pip install -e .
```
