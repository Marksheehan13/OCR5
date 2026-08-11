"""Start the standalone OCR5 website locally or on a managed web host."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
