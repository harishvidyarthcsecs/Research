#!/usr/bin/env python3
"""
Setup script for the Autonomous Research Agent System.
"""
import os
import sys
from pathlib import Path


def create_directories():
    """Create necessary directories."""
    directories = [
        "data/memory",
        "output",
        "logs"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created directory: {directory}")


def check_python_version():
    """Check if Python version is compatible."""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        sys.exit(1)
    else:
        print(f"✅ Python version: {sys.version}")


def install_dependencies():
    """Install required dependencies."""
    try:
        import subprocess
        print("📦 Installing dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        sys.exit(1)


def verify_installation():
    """Verify that the system can be imported."""
    try:
        sys.path.insert(0, "src")
        from research_system import AutonomousResearchSystem
        print("✅ System can be imported successfully")
        
        # Test initialization
        system = AutonomousResearchSystem()
        print("✅ System initialization successful")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Initialization error: {e}")
        sys.exit(1)


def main():
    """Main setup function."""
    print("🔬 Setting up Autonomous Research Agent System")
    print("=" * 50)
    
    # Check Python version
    check_python_version()
    
    # Create directories
    create_directories()
    
    # Install dependencies
    install_dependencies()
    
    # Verify installation
    verify_installation()
    
    print("\n🎉 Setup completed successfully!")
    print("\nNext steps:")
    print("1. Run: python main.py")
    print("2. Or import in your code: from src.research_system import AutonomousResearchSystem")
    print("3. Check the output/ directory for results")


if __name__ == "__main__":
    main()