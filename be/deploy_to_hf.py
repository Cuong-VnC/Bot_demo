import os
import sys
from huggingface_hub import HfApi

def deploy():
    print("[HF] Hugging Face Auto-Deployment Tool")
    print("===================================")
    
    # Try to get credentials
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        # Prompt user if running interactively
        hf_token = input("Enter Hugging Face WRITE Token: ").strip()
        if not hf_token:
            print("Error: Hugging Face Token is required.")
            sys.exit(1)
            
    hf_space_id = os.getenv("HF_SPACE_ID")
    if not hf_space_id:
        hf_space_id = input("Enter Hugging Face Space ID (e.g. username/space-name): ").strip()
        if not hf_space_id:
            print("Error: Space ID is required.")
            sys.exit(1)
            
    print(f"\nPreparing to upload folder to Hugging Face Space: '{hf_space_id}'...")
    
    api = HfApi()
    
    # Files/folders to ignore during upload
    ignore_patterns = [
        "__pycache__/",
        "*.log",
        "*.pyc",
        ".git/",
        ".gitignore",
        "data/database.db",
        "data/*.db",
        "data/app.log",
        "temp/*",
        "youtube_credentials.json",
        "client_secret.json",
        "youtube_oauth_helper.py"
    ]
    
    try:
        print("Uploading files... (this may take a few moments)")
        api.upload_folder(
            folder_path=".",
            repo_id=hf_space_id,
            repo_type="space",
            token=hf_token,
            ignore_patterns=ignore_patterns
        )
        print("\nDeployment completed successfully!")
        print(f"Public URL: https://huggingface.co/spaces/{hf_space_id}")
    except Exception as e:
        print(f"\nDeployment failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    deploy()
