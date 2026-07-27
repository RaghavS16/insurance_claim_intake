from fastapi import FastAPI

app = FastAPI(title="Insurance Claim Intake API")

@app.get("/health")
def health_check():
    return {"status": "ok"}