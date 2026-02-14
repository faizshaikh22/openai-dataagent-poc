import uvicorn
import os

if __name__ == "__main__":
    # Ensure data directory exists
    if not os.path.exists("data"):
        os.makedirs("data")
        
    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=True)
