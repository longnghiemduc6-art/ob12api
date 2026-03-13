"""OB1 2API launcher."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8081, reload=True)
