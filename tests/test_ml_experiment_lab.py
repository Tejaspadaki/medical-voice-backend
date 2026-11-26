"""
End-to-end tests for AuraDoc Clinical AI Multi-Model Audio Experimentation,
Evaluation, Training/Calibration, Graph Generation, and PDF Reporting
using the 10 Kannada submission audio files in submission_kannada_audios/.
"""
import os
from datetime import datetime, timezone

from app.core.dependencies import MongoUser
from app.schemas.ml_experiment import (
    AudioAnnotationItem,
    ModelEvaluationRequest,
    TrainingConfigRequest,
)
from app.services.audio_dataset_service import AudioDatasetService
from app.services.evaluation_report_service import EvaluationReportService
from app.services.model_evaluation_service import ModelEvaluationService, compute_wer_cer
from app.services.model_registry_service import ModelRegistryService
from app.services.sarvam_service import SarvamService


class FakeCollection:
    def __init__(self):
        self.docs = []

    def find_one(self, query=None, sort=None):
        query = query or {}
        matches = []
        for d in self.docs:
            ok = True
            for k, v in query.items():
                if k == "model_summaries.model_id":
                    if not any(ms.get("model_id") == v for ms in d.get("model_summaries", [])):
                        ok = False
                        break
                elif d.get(k) != v:
                    ok = False
                    break
            if ok:
                matches.append(dict(d))
        if not matches:
            return None
        if sort:
            key = sort[0][0]
            rev = sort[0][1] == -1
            matches.sort(key=lambda x: x.get(key) or datetime.min.replace(tzinfo=timezone.utc), reverse=rev)
        return matches[0]

    def find(self, query=None):
        return [dict(d) for d in self.docs]

    def insert_one(self, doc):
        self.docs.append(dict(doc))
        return True

    def update_one(self, query, update, upsert=False):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in query.items()):
                if "$set" in update:
                    self.docs[i].update(update["$set"])
                return True
        if upsert:
            new_doc = dict(query)
            if "$set" in update:
                new_doc.update(update["$set"])
            self.docs.append(new_doc)
        return True


class FakeDB:
    def __init__(self):
        self.audio_datasets = FakeCollection()
        self.audio_annotations = FakeCollection()
        self.model_evaluations = FakeCollection()
        self.training_jobs = FakeCollection()


def test_wer_cer_exact_math_and_missing_gt():
    # Missing GT must never fabricate WER/CER
    missing = compute_wer_cer(None, "hello world", "unicode_nfkc_lowercase_punct_strip")
    assert missing["wer"] is None
    assert missing["cer"] is None
    assert missing["status"] == "ANNOTATION_REQUIRED"

    # Exact match -> 0.0
    exact = compute_wer_cer("ನಮಸ್ಕಾರ ಬಸವರಾಜ್", "ನಮಸ್ಕಾರ ಬಸವರಾಜ್!", "unicode_nfkc_lowercase_punct_strip")
    assert exact["wer"] == 0.0
    assert exact["cer"] == 0.0

    # 1 substitution out of 2 words -> WER = 0.5
    one_sub = compute_wer_cer("high fever", "mild fever", "unicode_nfkc_lowercase_punct_strip")
    assert one_sub["wer"] == 0.5


def test_full_10_kannada_audio_pipeline_end_to_end(monkeypatch):
    db = FakeDB()

    # 1. Registry
    models = ModelRegistryService.list_models(db)
    model_ids = {m["model_id"] for m in models}
    assert {"sarvam_saaras_v3", "indicwhisper_local", "gemini_clinical_ner", "auradoc_bilingual_nlp"}.issubset(model_ids)

    # 2. Import 10 Kannada submission audio files
    ds = AudioDatasetService.import_local_folder(db, "submission_kannada_audios", "10 Kannada Submission Set", user_id=1)
    assert ds["total_files"] == 10
    assert ds["is_pilot_dataset"] is True
    for af in ds["audio_files"]:
        assert af["duration_sec"] > 0
        assert af["sample_rate"] > 0
        assert os.path.exists(af["original_path"])
        assert os.path.exists(af["preprocessed_path"])
        assert af["annotation_status"] == "ANNOTATION_REQUIRED"

    # 3. Evaluation BEFORE annotations -> WER/CER must remain None
    monkeypatch.setattr(SarvamService, "is_configured", classmethod(lambda cls: False))
    pre_eval = ModelEvaluationService.run_evaluation(
        db,
        ModelEvaluationRequest(dataset_id=ds["dataset_id"], model_ids=["indicwhisper_local"]),
    )
    assert pre_eval["model_summaries"][0]["avg_wer"] is None
    assert pre_eval["is_pilot_evaluation"] is True

    # 4. Annotate all 10 files with ground-truth transcripts
    gt_items = [
        AudioAnnotationItem(
            audio_id=af["audio_id"],
            reference_text="ರೋಗಿಗೆ ಕಳೆದ ಮೂರು ದಿನಗಳಿಂದ ತೀವ್ರ ಜ್ವರ ಮತ್ತು ಕೆಮ್ಮು ಇದೆ.",
            language="kn",
            annotator="Dr. Test",
            clinical_entities_gt={"symptoms": ["High Fever", "Cough"], "diagnosis": [], "medications": [], "dosages": [], "frequencies": [], "durations": []},
        )
        for af in ds["audio_files"]
    ]
    ds_ann = AudioDatasetService.save_annotations(db, ds["dataset_id"], gt_items)
    assert ds_ann["annotated_count"] == 10

    # 5. Local Calibration Training (auradoc_bilingual_nlp) + Cloud API guard (sarvam_saaras_v3)
    trn_ok = ModelEvaluationService.start_training_job(
        db,
        TrainingConfigRequest(dataset_id=ds["dataset_id"], model_id="auradoc_bilingual_nlp", epochs=2, train_split=0.8),
    )
    assert trn_ok["status"] == "COMPLETED"
    assert len(trn_ok["history"]) >= 1
    assert os.path.exists(trn_ok["checkpoint_path"])

    trn_cloud = ModelEvaluationService.start_training_job(
        db,
        TrainingConfigRequest(dataset_id=ds["dataset_id"], model_id="sarvam_saaras_v3", epochs=2),
    )
    assert trn_cloud["status"] == "INFERENCE_EVALUATION_ONLY"
    assert trn_cloud["history"] == []  # Never fabricates cloud training history

    # 6. Full Multi-Model Evaluation + Automatic Graphs + PDF Report
    eval_res = ModelEvaluationService.run_evaluation(
        db,
        ModelEvaluationRequest(
            dataset_id=ds["dataset_id"],
            model_ids=["indicwhisper_local", "auradoc_bilingual_nlp"],
        ),
    )
    assert eval_res["model_summaries"][0]["avg_wer"] is not None
    assert eval_res["graphs"]["dataset_graphs"]["dataset_size_analysis"]["total_files"] == 10
    assert eval_res["graphs"]["training_performance_graphs"]["available"] is True
    assert len(eval_res["graphs"]["comparison_radar"]) == 2
    assert len(eval_res["nlp_evaluations"]) == 10

    pdf_path = EvaluationReportService.generate_pdf_report(eval_res, ds_ann)
    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 2000
