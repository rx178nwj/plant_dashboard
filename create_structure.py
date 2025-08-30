# create_structure.py
import os

# 作成するディレクトリのリスト
# 'blueprints'内のサブディレクトリも定義
DIRECTORIES = [
    "blueprints/dashboard",
    "blueprints/devices",
    "blueprints/management",
    "blueprints/plants",
    "data",
    "logs",
    "scripts",
    "static/css",
    "static/js",
    "templates"
]

# blueprints内の各サブディレクトリに作成する__init__.pyファイル
INIT_FILES = [
    "blueprints/__init__.py",
    "blueprints/dashboard/__init__.py",
    "blueprints/devices/__init__.py",
    "blueprints/management/__init__.py",
    "blueprints/plants/__init__.py"
]

def create_project_structure():
    """
    プロジェクトのディレクトリ構造を作成します。
    """
    print("Creating project directory structure...")

    for directory in DIRECTORIES:
        try:
            os.makedirs(directory, exist_ok=True)
            print(f"  Created directory: {directory}")
        except OSError as e:
            print(f"Error creating directory {directory}: {e}")

    print("\nCreating __init__.py files to make blueprint directories packages...")
    for file_path in INIT_FILES:
        try:
            # 空の__init__.pyファイルを作成
            with open(file_path, 'w') as f:
                pass
            print(f"  Created file: {file_path}")
        except IOError as e:
            print(f"Error creating file {file_path}: {e}")

    print("\nProject structure created successfully!")

if __name__ == "__main__":
    create_project_structure()
