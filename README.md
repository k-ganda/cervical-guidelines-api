# Kenya Cervical and Breast Cancer Guidelines API

A standalone, deterministic clinical decision support API built with **FastAPI**, implementing the **Kenya National Cancer Screening and Early Diagnosis Guidelines (2024)** for **Cervical Cancer** and **Breast Cancer**. 

This API provides dedicated endpoints for evaluating clinical decision rules, returning structured action contracts (severity badges, clinical recommendations, reasons, action codes, and guideline page references) powered directly by the underlying `curated_cds` engine.

---

## 🚀 Features

* **15 Cervical Cancer Guideline Rules:** Covers HPV interpretation, VIA pre-check & interpretation, Cytology, Colposcopy, Histology, Ablation Eligibility (10-criterion checklist), and Special Populations (Pregnancy, Postpartum, Total Hysterectomy, HPV Vaccinated, Postmenopausal, Age 65+).
* **2 Breast Cancer Guideline Rules:** Covers 5-characteristic High-Risk Classification and Age-Banded Average-Risk Screening Schedules.
* **Dedicated Endpoints:** Every rule has its own distinct POST endpoint with specific primary and dependent inputs matching clinical workflow requirements.
* **Interactive OpenAPI Documentation:** Built-in Swagger UI with pre-populated dropdown choice sets for clear, interactive manual testing.

---

## 📦 Project Setup

### 1. Clone the Repository

```
git clone https://github.com/k-ganda/cervical-guidelines-api.git
cd cervical-guidelines-api
```

### 2. Create and Activate a Virtual Environment

On macOS / Linux:

```
python3 -m venv venv
source venv/bin/activate
```

On Windows (PowerShell):

```
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

Install FastAPI, Uvicorn, Pydantic, and supporting libraries:

```
pip install -r requirements.txt
```

### Running the Application

Start the local development server using Uvicorn:

```
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Once started, the server will run at http://localhost:8000.

### Testing the API via Swagger UI

Open your browser and navigate to:

```http://localhost:8000/docs```

You will see two endpoint tags:

15 Cervical Cancer Rules

2 Breast Cancer Rules

Select any rule (e.g., POST /api/v1/rules/cc.hpv.interpretation), click Try it out, select your test inputs from the dropdowns, and click Execute.
