import csv
import io
import tempfile
from pathlib import Path

import streamlit as st

from main import ExtractionError, extract_receipt_data

st.set_page_config(page_title="Receipt OCR", page_icon="🧾", layout="wide")

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
/* ── Palette ─────────────────────────────────────────────── */
:root {
    --accent:        #4F8A8B;
    --accent-dim:    rgba(79,138,139,0.10);
    --accent-mid:    rgba(79,138,139,0.32);
    --accent-solid:  rgba(79,138,139,0.60);
    --text-bright:   #F1F5F9;
    --text-muted:    #94A3B8;
}

/* ── Header ──────────────────────────────────────────────── */
.app-header {
    display: flex;
    align-items: flex-start;
    gap: 14px;
    margin-bottom: 28px;
    padding-bottom: 18px;
    border-bottom: 1px solid rgba(79,138,139,0.18);
}
.app-header-bar {
    width: 4px;
    min-height: 54px;
    background: var(--accent);
    border-radius: 3px;
    flex-shrink: 0;
}
.app-header-title {
    font-size: 1.85rem;
    font-weight: 700;
    color: var(--text-bright);
    line-height: 1.15;
    margin: 0 0 5px 0;
}
.app-header-sub {
    font-size: 0.83rem;
    color: var(--text-muted);
    margin: 0;
    letter-spacing: 0.01em;
}

/* ── File uploader ───────────────────────────────────────── */
[data-testid="stFileUploadDropzone"] {
    border: 2px dashed var(--accent-solid) !important;
    border-radius: 10px !important;
    background: var(--accent-dim) !important;
    transition: border-color 0.2s ease, background 0.2s ease !important;
}
[data-testid="stFileUploadDropzone"]:hover {
    border-color: var(--accent) !important;
    background: rgba(79,138,139,0.18) !important;
}

/* ── Receipt section header ──────────────────────────────── */
.receipt-title {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 8px 0 18px 0;
}
.receipt-title-bar {
    width: 3px;
    height: 20px;
    background: var(--accent);
    border-radius: 2px;
    flex-shrink: 0;
}
.receipt-title-text {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-bright);
    font-family: ui-monospace, monospace;
    letter-spacing: 0.02em;
}

/* ── Field labels ────────────────────────────────────────── */
.field-label {
    font-size: 0.67rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.10em !important;
    text-transform: uppercase !important;
    color: var(--accent) !important;
    margin: 10px 0 0 0 !important;
    padding: 0 !important;
    line-height: 1.2 !important;
}

/* ── Vendor: larger font via :has() adjacent selector ────── */
.element-container:has(.vendor-marker) + .element-container input {
    font-size: 1.12rem !important;
    font-weight: 600 !important;
    color: var(--text-bright) !important;
}

/* ── Numbers: right-align + brighter ─────────────────────── */
[data-testid="stNumberInput"] input {
    text-align: right !important;
    color: var(--text-bright) !important;
    font-weight: 500 !important;
    font-variant-numeric: tabular-nums !important;
    letter-spacing: 0.01em !important;
}

/* ── Fade divider ────────────────────────────────────────── */
.fade-divider {
    height: 1px;
    border: none;
    background: linear-gradient(
        to right,
        transparent 0%,
        var(--accent-mid) 25%,
        var(--accent-mid) 75%,
        transparent 100%
    );
    margin: 36px 0 28px 0;
}

/* ── Download button ─────────────────────────────────────── */
[data-testid="stDownloadButton"] > button {
    background: var(--accent-dim) !important;
    border: 1px solid var(--accent-solid) !important;
    color: var(--text-bright) !important;
    border-radius: 7px !important;
    font-weight: 500 !important;
    transition: background 0.2s ease, border-color 0.2s ease !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background: rgba(79,138,139,0.22) !important;
    border-color: var(--accent) !important;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown("""
<div class="app-header">
  <div class="app-header-bar"></div>
  <div>
    <div class="app-header-title">🧾 Receipt OCR</div>
    <div class="app-header-sub">Upload receipt images &nbsp;·&nbsp; review &amp; correct extracted data &nbsp;·&nbsp; export to CSV</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "receipts" not in st.session_state:
    st.session_state.receipts = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def field_label(text: str, vendor: bool = False) -> None:
    """Render a styled uppercase label. Set vendor=True to inject the CSS marker."""
    marker = ' <span class="vendor-marker"></span>' if vendor else ""
    st.markdown(f'<p class="field-label">{text}{marker}</p>', unsafe_allow_html=True)


def text_field(label: str, vendor: bool = False, **kwargs) -> str:
    field_label(label, vendor=vendor)
    return st.text_input("", label_visibility="collapsed", **kwargs)


def number_field(label: str, **kwargs) -> float:
    field_label(label)
    return st.number_input("", label_visibility="collapsed", **kwargs)


# ---------------------------------------------------------------------------
# File uploader
# ---------------------------------------------------------------------------

uploaded_files = st.file_uploader(
    "Drop receipt images here — PNG, JPG, WEBP",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)

if uploaded_files:
    for uploaded_file in uploaded_files:
        name = uploaded_file.name
        if name not in st.session_state.receipts:
            with st.spinner(f"Extracting {name}…"):
                try:
                    suffix = Path(name).suffix
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        tmp.write(uploaded_file.read())
                        tmp_path = tmp.name
                    data = extract_receipt_data(tmp_path)
                    Path(tmp_path).unlink(missing_ok=True)
                    st.session_state.receipts[name] = data
                except ExtractionError as e:
                    st.error(f"**{name}**: {e}")
                    continue
                except Exception as e:
                    st.error(f"**{name}**: unexpected error — {e}")
                    continue

# ---------------------------------------------------------------------------
# Receipt cards
# ---------------------------------------------------------------------------

for i, (name, data) in enumerate(st.session_state.receipts.items()):
    if i > 0:
        st.markdown('<hr class="fade-divider">', unsafe_allow_html=True)

    st.markdown(f"""
    <div class="receipt-title">
      <div class="receipt-title-bar"></div>
      <span class="receipt-title-text">{name}</span>
    </div>
    """, unsafe_allow_html=True)

    img_file = next((f for f in (uploaded_files or []) if f.name == name), None)
    left, right = st.columns([1, 2])

    with left:
        if img_file:
            img_file.seek(0)
            st.image(img_file, use_container_width=True)

    with right:
        col1, col2 = st.columns(2)

        with col1:
            data["vendor"] = text_field("Vendor", vendor=True,
                                        value=data.get("vendor") or "",
                                        key=f"{name}_vendor")
            data["date"] = text_field("Date",
                                      value=data.get("date") or "",
                                      key=f"{name}_date")
            data["currency"] = text_field("Currency",
                                          value=data.get("currency") or "",
                                          key=f"{name}_currency")

        with col2:
            data["subtotal"]  = number_field("Subtotal (excl. tax)",
                                             value=float(data.get("subtotal") or 0),
                                             step=1.0, key=f"{name}_subtotal")
            data["tax"]       = number_field("Tax",
                                             value=float(data.get("tax") or 0),
                                             step=1.0, key=f"{name}_tax")
            data["total"]     = number_field("Total (incl. tax)",
                                             value=float(data.get("total") or 0),
                                             step=1.0, key=f"{name}_total")
            data["gift_card"] = number_field("Gift card",
                                             value=float(data.get("gift_card") or 0),
                                             step=1.0, key=f"{name}_gift_card")
            data["points"]    = number_field("Points redeemed",
                                             value=float(data.get("points") or 0),
                                             step=1.0, key=f"{name}_points")

        st.markdown('<p class="field-label" style="margin-top:16px">Line items</p>',
                    unsafe_allow_html=True)
        edited_items = st.data_editor(
            data.get("line_items") or [],
            key=f"{name}_items",
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "description": st.column_config.TextColumn("Description", width="large"),
                "amount":      st.column_config.NumberColumn("Amount", format="%.0f"),
            },
        )
        data["line_items"] = edited_items

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

if st.session_state.receipts:
    st.markdown('<hr class="fade-divider">', unsafe_allow_html=True)

    def build_csv(receipts: dict) -> str:
        buf = io.StringIO()
        fields = ["file", "vendor", "date", "currency", "subtotal", "tax",
                  "total", "gift_card", "points", "item_description", "item_amount"]
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        for filename, d in receipts.items():
            base = {
                "file":      filename,
                "vendor":    d.get("vendor"),
                "date":      d.get("date"),
                "currency":  d.get("currency"),
                "subtotal":  d.get("subtotal"),
                "tax":       d.get("tax"),
                "total":     d.get("total"),
                "gift_card": d.get("gift_card"),
                "points":    d.get("points"),
            }
            items = d.get("line_items") or []
            if items:
                for item in items:
                    writer.writerow({**base,
                                     "item_description": item.get("description"),
                                     "item_amount":      item.get("amount")})
            else:
                writer.writerow({**base, "item_description": None, "item_amount": None})
        return buf.getvalue()

    csv_data = build_csv(st.session_state.receipts)

    dl_col, clear_col, _ = st.columns([2, 1, 4])
    with dl_col:
        st.download_button(
            label=f"⬇️  Export {len(st.session_state.receipts)} receipt(s) to CSV",
            data=csv_data,
            file_name="receipts.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with clear_col:
        if st.button("Clear all", type="secondary", use_container_width=True):
            st.session_state.receipts = {}
            st.rerun()
