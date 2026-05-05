# 🧾 Receipt OCR

A Streamlit app that extracts structured data from receipt images using a vision LLM, designed for Japanese receipts (also works on English and Vietnamese).

Built as a learning side project to help a friend extract receipt data at work and input it into an accounting system.

## Motivation

This started as a practical favour — a friend was manually transcribing Japanese receipts into a spreadsheet at work, which felt like exactly the kind of task a vision model should be able to handle.

The interesting part wasn't any single piece of it. Vision LLMs, structured JSON output, and Streamlit have all matured to the point where each one is straightforward on its own. What was genuinely surprising was how quickly they composed together into something useful. A working prototype — with Japanese OCR, editable review UI, and CSV export — came together in a single two-hour session.

It's a good reminder that the gap between "I know these tools exist" and "I can combine them to solve a real problem" is much smaller now than it used to be.

---

## What it does

1. Upload one or more receipt images (PNG, JPG, WEBP)
2. A vision model extracts structured fields automatically
3. Review and correct the extracted data in the UI
4. Export everything to CSV

**Extracted fields:** vendor, date, currency, subtotal (excl. tax), tax, total (incl. tax), gift card amount, points redeemed, line items

---

## Tech stack

| Layer | Choice |
|---|---|
| UI | Streamlit |
| Language | Python 3.10+ |
| Cloud backend | Qwen2.5-VL-72B-Instruct via [OpenRouter](https://openrouter.ai) — best accuracy, ~8s/receipt |
| Local backend | Qwen2.5-VL-7B or Gemma3-12B via [Ollama](https://ollama.com) — private, no API key needed |

The app supports switching between backends at runtime. See [Model selection learnings](#model-selection-learnings) for a comparison of accuracy and tradeoffs across all tested models, including Claude.

---

## Setup

**1. Clone and create a virtual environment**
```bash
git clone https://github.com/khoacs/receipt-ai.git
cd receipt-ai
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure your backend**

*Option A — OpenRouter (cloud, best accuracy):*
Create a free account at [openrouter.ai](https://openrouter.ai), generate an API key, then:
```bash
cp .env.example .env
# edit .env and paste your OPENROUTER_API_KEY
```

*Option B — Ollama (local, private, no API key needed):*
Install [Ollama](https://ollama.com), then pull a vision model:
```bash
ollama pull qwen2.5vl:7b   # recommended local model
ollama serve
```
No `.env` file needed for local inference.

**4. Run**
```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. Select your backend from the radio buttons at the top.

---

## CLI usage

You can also run extraction directly without the UI:
```bash
python main.py data/input/your-receipt.jpg                   # OpenRouter (default)
python main.py data/input/your-receipt.jpg --backend ollama-qwen   # local Qwen 7B
python main.py data/input/your-receipt.jpg --backend ollama-gemma  # local Gemma 12B
```

Prints extracted JSON to stdout.

---

## Accuracy notes

OCR accuracy on Japanese thermal paper receipts is good but not perfect:

- Vendor names and totals are usually correct
- Line item descriptions on receipts with stylized or compressed fonts can be slightly off
- Tax/subtotal split is calculated in code when the receipt only prints the tax-inclusive total

**The UI is intentionally designed for human review and correction before export.** Treat the extracted data as a first draft.

---

## Model selection learnings

Tested four models against real Japanese receipts during development. The key takeaway: **architecture and training purpose matter more than parameter count.**

### Models tested

| Model | Params | Type | Accuracy | Speed |
|---|---|---|---|---|
| Claude (Anthropic) | — | Vision-native, proprietary | Best | — |
| Qwen2.5-VL 72B (OpenRouter) | 72B | Vision-native | Very good | ~8s |
| Qwen2.5-VL 7B (Ollama) | 7B | Vision-native | Mediocre | ~6s |
| Gemma3 12B (Ollama) | 12B | Text-first + vision | Poor | — |

### Bigger does not always mean better

Gemma3 12B has nearly twice the parameters of Qwen2.5-VL 7B, yet performed far worse. On `fish.png` (a Japanese restaurant receipt):

- **Gemma3 12B** hallucinated entirely — vendor became `珈琲店` (coffee shop), date became `2024-03-13`, total became `¥1,560`, and line items came back empty. None of these appear on the receipt.
- **Qwen2.5-VL 7B** got the date and total right (`2026-01-23`, `¥1,628`) and extracted the dish name, though the vendor logo was misread.

Gemma3 is a text-first model with vision bolted on. Qwen2.5-VL was purpose-built as a Vision-Language model — the VL is load-bearing. A smaller purpose-built model beats a larger general-purpose one on visual tasks.

### Within the same architecture family, bigger does help

On `jins.png` (a JINS eyewear receipt with tax-inclusive pricing):

- **Qwen2.5-VL 7B** read `小計 ¥20,400` as a pre-tax subtotal, then added ¥1,855 tax on top, producing a ¥22,255 total that doesn't exist on the receipt.
- **Qwen2.5-VL 72B** correctly understood that Japanese receipt prices are tax-inclusive, derived the pre-tax subtotal as `¥20,400 − ¥1,855 = ¥18,545`, and returned the correct total of `¥20,400`.

The 7B model reads numbers correctly but misunderstands their meaning. The 72B model has enough capacity to reason about Japanese receipt conventions.

### Other observed behaviours in smaller models

- **Inconsistency at temperature=0** — the 7B model returned different vendor names across two runs of the same image. Ollama applies a small internal noise floor, so determinism isn't guaranteed.
- **Skipping fields** — the 7B model omitted `gift_card` and `points` from its JSON entirely. Larger models follow the schema as instructed, even returning null for absent fields.
- **Domain formatting is hard** — Japanese thermal paper combines stylised logos, tax-inclusive pricing, compressed kanji in tight tables, and low contrast. Smaller models handle numbers and dates but struggle with the semantic layer.

### Adding Claude to the comparison

After testing three open models, the same receipt (`fish.png`) was run through Claude's vision API directly as a final benchmark. Full results across all four:

| Field | Claude | Qwen2.5-VL 72B | Qwen2.5-VL 7B | Gemma3 12B |
|---|---|---|---|---|
| Vendor | **できたてん** ✓ | てつ丸 ✗ | てきだて処 / (empty) ✗ | 珈琲店 ✗ |
| Date | **2026-01-23** ✓ | 2026-01-23 ✓ | 2026-01-23 ✓ | 2024-03-13 ✗ |
| Total | **¥1,628** ✓ | ¥1,628 ✓ | ¥1,628 ✓ | ¥1,560 ✗ |
| Tax | **null** ✓ | null ✓ | null ✓ | ¥260 (hallucinated) ✗ |
| Line item | **とろ鰆と銀鮭しらす丼** ✓ | 七三鰆七銀鮭しらす丼 (garbled) | とろ鯖と銀鮭ちらす丼 (鰆→鯖) | empty ✗ |

Claude was the only model to correctly read the stylised handwritten vendor logo (`できたてん`), get the exact dish name right (`とろ鰆` sawara vs `とろ鯖` mackerel in the 7B), and correctly return null for tax rather than inventing a figure.

The honest tradeoff: Claude is a proprietary API with per-token pricing. The open models are free or self-hosted. For a personal accounting tool processing a handful of receipts a week, the cost difference is negligible — but for high-volume use, it becomes a real consideration.

### How to choose

Use a **large cloud vision model** when accuracy matters and receipts have complex layouts, stylised fonts, or non-Latin character sets.

Use a **local vision model** when privacy is the primary constraint and human review will catch errors — but prefer a vision-native model (Qwen2.5-VL) over a general-purpose one (Gemma3) regardless of parameter count.

---

## Privacy

The app offers two modes with different privacy profiles:

- **Cloud (OpenRouter)** — receipt images are sent as base64 to OpenRouter's API and processed by Qwen model servers outside Japan. Receipt data leaves your device. Acceptable for personal use but may not be suitable for sensitive business receipts.
- **Local (Ollama)** — all processing happens on your machine. Images never leave your device.

Switch between modes using the backend selector in the UI.

---

## Roadmap

- [x] Phase 1 — Core extraction (`main.py`) + Streamlit UI + CSV export
- [x] Phase 2 — Local Ollama backend (Qwen2.5-VL 7B, Gemma3 12B) for on-device privacy
- [x] Phase 2b — Multi-backend selector in UI with runtime switching
- [x] Phase 2c — Model benchmarking across cloud and local backends (see [Model selection learnings](#model-selection-learnings))
- [ ] Phase 3 — Direct integration with accounting system (TBD)

---

## Project structure

```
receipt-ai/
├── app.py              # Streamlit UI
├── main.py             # Extraction logic (vision API + validation)
├── requirements.txt
├── .env.example
├── .streamlit/
│   └── config.toml     # Dark theme + disables usage stats prompt
└── data/
    ├── input/          # Drop receipt images here (git-ignored)
    └── output/         # Exported CSVs land here (git-ignored)
```

---

## License

MIT
