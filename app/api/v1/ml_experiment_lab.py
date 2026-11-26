from typing import Any, List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.dependencies import MongoUser, require_roles
from app.db.mongo import clean_doc, clean_docs, get_mongo_db
from app.schemas.ml_experiment import (
    AudioAnnotationsBatchRequest,
    ModelEvaluationRequest,
    TrainingConfigRequest,
)
from app.services.audio_dataset_service import AudioDatasetService
from app.services.evaluation_report_service import EvaluationReportService
from app.services.model_evaluation_service import ModelEvaluationService
from app.services.model_registry_service import ModelRegistryService

router = APIRouter(tags=["ML Audio Experimentation, Evaluation & Visualization"])


@router.post("/audio-datasets/upload", summary="Upload Multiple Audio Files (WAV, MP3, M4A, FLAC)")
async def upload_audio_dataset(
    dataset_name: str = Form("AuraDoc Audio Dataset"),
    language: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    return await AudioDatasetService.create_dataset_from_uploads(
        db=db,
        dataset_name=dataset_name,
        files=files,
        language=language,
        user_id=getattr(current_user, "user_id", None),
    )


@router.post("/audio-datasets/import-local", summary="Import Built-in submission_kannada_audios or sample_audios")
def import_local_audio_dataset(
    source_folder: str = Query("submission_kannada_audios", description="submission_kannada_audios or sample_audios"),
    dataset_name: Optional[str] = Query(None),
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    return AudioDatasetService.import_local_folder(
        db=db,
        source_folder=source_folder,
        dataset_name=dataset_name,
        user_id=getattr(current_user, "user_id", None),
    )


@router.get("/audio-datasets", summary="List All Audio Datasets")
def list_audio_datasets(
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    docs = list(db.audio_datasets.find().sort("created_at", -1).limit(50))
    return {"items": clean_docs(docs), "total": len(docs)}


@router.get("/audio-datasets/{dataset_id}", summary="Get Audio Dataset Details & File Metadata")
def get_audio_dataset(
    dataset_id: str,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    doc = db.audio_datasets.find_one({"dataset_id": dataset_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    return clean_doc(doc)


@router.post("/audio-datasets/{dataset_id}/annotations", summary="Save Reference Ground-Truth Transcriptions")
def save_dataset_annotations(
    dataset_id: str,
    payload: AudioAnnotationsBatchRequest,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    return AudioDatasetService.save_annotations(
        db=db,
        dataset_id=dataset_id,
        annotations=payload.annotations,
    )


@router.get("/models/registry", summary="Get Dynamic AI/ML Model Registry")
def get_model_registry(
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    models = ModelRegistryService.list_models(db)
    return {"models": models, "total": len(models)}


@router.post("/models/evaluate", summary="Run Multi-Model Evaluation & Automatic Graph Generation")
def evaluate_models(
    payload: ModelEvaluationRequest,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    return ModelEvaluationService.run_evaluation(
        db=db,
        req=payload,
        user_id=getattr(current_user, "user_id", None),
    )


@router.get("/models/evaluations", summary="List Previous Evaluation Experiments")
def list_evaluations(
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    docs = list(db.model_evaluations.find().sort("created_at", -1).limit(30))
    return {"items": clean_docs(docs), "total": len(docs)}


@router.post("/models/train", summary="Start Local Model Training / Lexicon Calibration Job")
def train_model(
    payload: TrainingConfigRequest,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin"])),
):
    return ModelEvaluationService.start_training_job(
        db=db,
        req=payload,
        user_id=getattr(current_user, "user_id", None),
    )


@router.get("/models/training/{job_id}", summary="Get Training Job Status & Epoch History")
def get_training_job(
    job_id: str,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    doc = db.training_jobs.find_one({"job_id": job_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} not found")
    return clean_doc(doc)


@router.get("/models/evaluation/{evaluation_id}", summary="Get Full Evaluation Results")
def get_evaluation(
    evaluation_id: str,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    doc = db.model_evaluations.find_one({"evaluation_id": evaluation_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Evaluation {evaluation_id} not found")
    return clean_doc(doc)


@router.get("/models/evaluation/{evaluation_id}/graphs", summary="Get Structured Graph Data for Evaluation")
def get_evaluation_graphs(
    evaluation_id: str,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    doc = db.model_evaluations.find_one({"evaluation_id": evaluation_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Evaluation {evaluation_id} not found")
    return {"evaluation_id": evaluation_id, "graphs": doc.get("graphs", {})}


@router.get("/models/evaluation/{evaluation_id}/report", summary="Generate & Download PDF Evaluation Report")
def download_evaluation_report(
    evaluation_id: str,
    db=Depends(get_mongo_db),
    current_user: MongoUser = Depends(require_roles(["Doctor", "Admin", "Staff"])),
):
    eval_doc = db.model_evaluations.find_one({"evaluation_id": evaluation_id})
    if not eval_doc:
        raise HTTPException(status_code=404, detail=f"Evaluation {evaluation_id} not found")
    ds_doc = db.audio_datasets.find_one({"dataset_id": eval_doc.get("dataset_id")}) or {}
    pdf_path = EvaluationReportService.generate_pdf_report(eval_doc, ds_doc)
    return FileResponse(
        path=pdf_path,
        filename=f"AuraDoc_ML_Evaluation_{evaluation_id}.pdf",
        media_type="application/pdf",
    )
