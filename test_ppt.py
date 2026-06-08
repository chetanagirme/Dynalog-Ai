import sys
sys.path.insert(0, '.')

print("Testing imports...")
try:
    from ppt_generator import generate_ppt
    print("ppt_generator OK")
except Exception as e:
    print(f"ppt_generator FAILED: {e}")

try:
    import ollama
    models = ollama.list()
    names = [m['name'] for m in models.get('models', [])]
    print(f"Ollama OK — models: {names}")
except Exception as e:
    print(f"Ollama FAILED: {e}")

try:
    from pptx import Presentation
    print("python-pptx OK")
except Exception as e:
    print(f"python-pptx FAILED — run: pip install python-pptx")

try:
    from rag_engine import search_project
    print("rag_engine OK")
except Exception as e:
    print(f"rag_engine FAILED: {e}")

print("Done.")