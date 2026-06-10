#!/usr/bin/env python3
"""
ZTP Hugging Face Uploader: Uploads the generated 1000Hz haptic dataset
and its README.md dataset card directly to the Hugging Face Hub.
"""

import os
import sys
from huggingface_hub import HfApi

def upload_dataset(repo_name, token=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parquet_path = os.path.join(script_dir, "haptic_trajectories.parquet")
    readme_path = os.path.join(script_dir, "README.md")

    if not os.path.exists(parquet_path):
        print(f"❌ Parquet file not found at {parquet_path}. Run generate_large_dataset.py first.")
        return

    if not os.path.exists(readme_path):
        print(f"❌ README.md dataset card not found at {readme_path}.")
        return

    # Use environment token if not passed
    token = token or os.environ.get("HF_TOKEN")
    if not token:
        print("\n🔑 Hugging Face Write Token is required to create and upload datasets.")
        print("You can get a token from: https://huggingface.co/settings/tokens")
        token = input("Please enter your HF Write Token: ").strip()
        if not token:
            print("❌ Upload cancelled: No token provided.")
            return

    api = HfApi()

    print(f"\n🚀 Creating/Verifying Hugging Face repository: {repo_name}...")
    try:
        api.create_repo(
            repo_id=repo_name,
            repo_type="dataset",
            private=False,
            exist_ok=True,
            token=token
        )
        print(f"✅ Repository ready: https://huggingface.co/datasets/{repo_name}")
    except Exception as e:
        print(f"❌ Failed to create/verify repository: {e}")
        return

    print("\n💾 Uploading haptic_trajectories.parquet (12.27 MB)...")
    try:
        api.upload_file(
            path_or_fileobj=parquet_path,
            path_in_repo="haptic_trajectories.parquet",
            repo_id=repo_name,
            repo_type="dataset",
            token=token
        )
        print("✅ Parquet uploaded successfully!")
    except Exception as e:
        print(f"❌ Parquet upload failed: {e}")
        return

    print("\n📝 Uploading README.md Dataset Card...")
    try:
        api.upload_file(
            path_or_fileobj=readme_path,
            path_in_repo="README.md",
            repo_id=repo_name,
            repo_type="dataset",
            token=token
        )
        print("✅ README.md uploaded successfully!")
        print(f"\n🎉 DATASET SHIPPED SUCCESSFULLY! View it live at:")
        print(f"👉 https://huggingface.co/datasets/{repo_name}")
    except Exception as e:
        print(f"❌ README upload failed: {e}")

if __name__ == "__main__":
    # Naming convention tailored for the HF Leaderboard search optimizations:
    # {Username}/humanoid-tactile-slip-reflex-1000hz
    
    # We default to a zero-trust-physics placeholder, but let the user override or supply their HF username
    default_org = "ZeroTrustPhysics"
    default_name = "humanoid-tactile-slip-reflex-1000hz"
    
    print("🤖 ZTP Haptic Dataset Uploader")
    print(f"Recommended Leaderboard Naming Convention: <username>/{default_name}")
    
    username = input(f"Enter your Hugging Face username or organization (default: {default_org}): ").strip()
    if not username:
        username = default_org
        
    repo_name = f"{username}/{default_name}"
    
    upload_dataset(repo_name)
