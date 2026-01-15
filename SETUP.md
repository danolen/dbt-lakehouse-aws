# Setup Instructions

## 1. Create Virtual Environment

```bash
python3 -m venv venv
```

## 2. Activate Virtual Environment

**On macOS/Linux:**
```bash
source venv/bin/activate
```

**On Windows:**
```bash
venv\Scripts\activate
```

You'll know it's activated when you see `(venv)` at the start of your terminal prompt.

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## 4. Run the App

```bash
streamlit run app/app.py
```

## Deactivate Virtual Environment

When you're done, you can deactivate:
```bash
deactivate
```
