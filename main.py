import json
import re
from collections import defaultdict

import google.generativeai as genai
import pandas as pd
import streamlit as st
from PIL import Image


# ── Styling ───────────────────────────────────────────────────────────────────

CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

    html, body, .stApp {
        background-color: #fdf6f0;
        font-family: 'Poppins', sans-serif;
        color: #3a3a5a;
    }

    /* Hide default Streamlit header padding */
    .block-container { padding-top: 2rem; }

    /* Title */
    h1 {
        color: #b5838d !important;
        font-weight: 700 !important;
        letter-spacing: -0.5px;
    }

    /* Cards */
    .card {
        background: white;
        border-radius: 20px;
        padding: 24px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.06);
        margin-bottom: 16px;
    }

    .card-title {
        font-size: 13px;
        font-weight: 600;
        color: #9b89b4;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 4px;
    }

    .card-value {
        font-size: 28px;
        font-weight: 700;
        color: #3a3a5a;
    }

    /* Person pay card */
    .person-card {
        background: white;
        border-radius: 16px;
        padding: 18px 22px;
        margin-bottom: 12px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .person-name {
        font-size: 16px;
        font-weight: 600;
        color: #3a3a5a;
    }

    .person-amount {
        font-size: 20px;
        font-weight: 700;
        color: #b5838d;
        background: #fdf0f0;
        padding: 6px 16px;
        border-radius: 30px;
    }

    /* Total banner */
    .total-banner {
        background: linear-gradient(135deg, #c8b6e2, #b5838d);
        border-radius: 20px;
        padding: 24px;
        color: white;
        text-align: center;
        margin-bottom: 20px;
    }

    .total-banner .label {
        font-size: 13px;
        opacity: 0.85;
        letter-spacing: 1px;
        text-transform: uppercase;
    }

    .total-banner .amount {
        font-size: 42px;
        font-weight: 700;
        margin: 4px 0;
    }

    /* Breakdown row */
    .breakdown-row {
        display: flex;
        justify-content: space-between;
        padding: 8px 0;
        border-bottom: 1px dashed #f0e8f5;
        font-size: 14px;
        color: #6a6a8a;
    }

    .breakdown-row:last-child { border-bottom: none; }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #c8b6e2, #b5838d);
        color: white !important;
        border: none;
        border-radius: 30px;
        font-weight: 600;
        padding: 0.55rem 1.8rem;
        font-size: 15px;
        transition: opacity 0.2s;
        width: 100%;
    }

    .stButton > button:hover { opacity: 0.88; }

    /* Back button override */
    div[data-testid="column"]:first-child .stButton > button {
        background: #f0eaf8;
        color: #9b89b4 !important;
    }

    /* Inputs */
    .stTextArea textarea, .stTextInput input {
        border-radius: 12px !important;
        border: 1.5px solid #e8e0f5 !important;
        background: white !important;
        color: #3a3a5a !important;
    }

    .stNumberInput input {
        border-radius: 12px !important;
        border: 1.5px solid #e8e0f5 !important;
        color: #3a3a5a !important;
    }

    /* Multiselect */
    .stMultiSelect > div {
        border-radius: 12px !important;
        border: 1.5px solid #e8e0f5 !important;
    }

    /* Data editor */
    .stDataEditor { border-radius: 12px; overflow: hidden; }

    /* File uploader */
    .stFileUploader {
        border-radius: 16px;
        border: 2px dashed #d4c5ee !important;
        background: white;
    }

    /* Radio */
    .stRadio > div { gap: 12px; }
    .stRadio label, .stRadio span { color: #9b89b4 !important; font-weight: 500; }

    /* Metric override */
    [data-testid="stMetricValue"] { color: #b5838d !important; font-weight: 700 !important; }
    [data-testid="stMetricLabel"] { color: #9b89b4 !important; }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: white;
        border-right: 1px solid #f0eaf8;
    }

    /* Caption */
    .stCaption { color: #a0a0c0 !important; }

    /* Warning / error */
    .stAlert { border-radius: 12px !important; }
</style>
"""


# ── Step Progress Indicator ───────────────────────────────────────────────────

STEP_LABELS = ["Upload", "Items", "People", "Assign", "Results"]

def render_step_bar(current: int):
    html = '<div style="display:flex;align-items:center;gap:0;margin-bottom:28px;">'
    for i, label in enumerate(STEP_LABELS, 1):
        done = i < current
        active = i == current

        if active:
            circle_bg = "#b5838d"
            circle_color = "white"
            text_color = "#b5838d"
            font_weight = "700"
        elif done:
            circle_bg = "#c8b6e2"
            circle_color = "white"
            text_color = "#c8b6e2"
            font_weight = "500"
        else:
            circle_bg = "#f0eaf8"
            circle_color = "#ccc"
            text_color = "#ccc"
            font_weight = "400"

        icon = "✓" if done else str(i)

        html += f"""
        <div style="display:flex;flex-direction:column;align-items:center;gap:5px;flex:1;">
            <div style="width:34px;height:34px;border-radius:50%;background:{circle_bg};
                        color:{circle_color};display:flex;align-items:center;justify-content:center;
                        font-weight:700;font-size:13px;">{icon}</div>
            <span style="font-size:10px;color:{text_color};font-weight:{font_weight};
                         text-transform:uppercase;letter-spacing:0.5px;">{label}</span>
        </div>
        """
        if i < len(STEP_LABELS):
            line_color = "#c8b6e2" if done else "#f0eaf8"
            html += f'<div style="flex:1;height:2px;background:{line_color};margin-bottom:20px;"></div>'

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


# ── Gemini Extraction ─────────────────────────────────────────────────────────

GEMINI_PROMPT = """
Look at this receipt image and extract all food and drink items.

Rules:
- If an item has quantity 1, return it as one entry with its price.
- If an item has quantity greater than 1, return it as SEPARATE entries — one per unit, each with the unit price (not the total). For example, 2x Latte at RM13.00 each becomes two entries both named "Latte" with price 13.00.
- Do not include tax, service charge, rounding, subtotal, or total rows.
- Return ONLY a valid JSON array, no explanation, no markdown.

Format:
[{"name": "Item Name", "price": 12.50}, ...]
"""


def extract_items_with_gemini(image: Image.Image, api_key: str) -> list[dict]:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content([GEMINI_PROMPT, image])
    text = response.text.strip()
    text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.MULTILINE).strip()
    raw = json.loads(text)
    return [
        {"name": str(item["name"]), "price": float(item["price"])}
        for item in raw
        if item.get("name") and float(item.get("price", 0)) > 0
    ]


# ── Bill Calculation ──────────────────────────────────────────────────────────

def calculate_bill(items: list[dict], service_charge_rate: float, tax_fixed: float) -> dict[str, float]:
    """
    - Service charge: % of each person's subtotal (proportional to what they ate).
    - Tax: fixed RM split equally among all people.
    """
    person_subtotals: dict[str, float] = defaultdict(float)
    for item in items:
        persons = item.get("persons") or []
        if not persons:
            continue
        share = item["price"] / len(persons)
        for person in persons:
            person_subtotals[person] += share

    all_people = list(person_subtotals.keys())
    tax_per_person = round(tax_fixed / len(all_people), 2) if all_people else 0

    return {
        person: round(subtotal * (1 + service_charge_rate / 100) + tax_per_person, 2)
        for person, subtotal in person_subtotals.items()
    }


# ── Step 1: Upload ────────────────────────────────────────────────────────────

def step_upload():
    render_step_bar(1)

    if "api_key" not in st.session_state:
        st.session_state.api_key = st.secrets.get("GEMINI_API_KEY", "")

    if not st.session_state.api_key:
        with st.sidebar:
            st.markdown("### Gemini API Key")
            st.caption("Required for auto-extraction. [Get a free key](https://aistudio.google.com/app/apikey)")
            api_key = st.text_input("API Key", type="password", key="api_key_input")
            if api_key:
                st.session_state.api_key = api_key

    st.markdown('<div class="card-title">Receipt Source</div>', unsafe_allow_html=True)
    source = st.radio("", ["Upload image", "Take photo"], horizontal=True, label_visibility="collapsed")

    image = None
    if source == "Upload image":
        file = st.file_uploader("Drop your receipt here", type=["png", "jpg", "jpeg"], label_visibility="visible")
        if file:
            image = Image.open(file)
    else:
        captured = st.camera_input("Point camera at receipt")
        if captured:
            image = Image.open(captured)

    if image:
        st.image(image, use_container_width=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Read Receipt"):
            key = st.session_state.get("api_key", "")
            if not key:
                st.error("Enter your Gemini API key in the sidebar first.")
            else:
                with st.spinner("Reading receipt..."):
                    try:
                        st.session_state.bill_items = extract_items_with_gemini(image, key)
                        if not st.session_state.bill_items:
                            st.warning("No items found. Add them manually on the next screen.")
                        st.session_state.step = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not read receipt: {e}")
    else:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Enter Items Manually"):
            st.session_state.bill_items = []
            st.session_state.step = 2
            st.rerun()


# ── Step 2: Review Items ──────────────────────────────────────────────────────

def step_items():
    render_step_bar(2)

    st.markdown('<div class="card-title">Review & Edit Items</div>', unsafe_allow_html=True)
    st.caption("Edit, add, or remove items before continuing.")

    initial_data = pd.DataFrame(
        [{"name": i["name"], "price": i["price"]} for i in st.session_state.bill_items]
        or [{"name": "", "price": 0.0}]
    )

    edited = st.data_editor(
        initial_data,
        num_rows="dynamic",
        column_config={
            "name": st.column_config.TextColumn("Item Name"),
            "price": st.column_config.NumberColumn("Price (RM)", min_value=0.0, format="%.2f"),
        },
        use_container_width=True,
        key="items_editor",
    )

    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    if col1.button("Back"):
        st.session_state.step = 1
        st.rerun()

    if col2.button("Next"):
        valid = edited.dropna(subset=["name"])
        valid = valid[valid["name"].str.strip() != ""]
        valid = valid[valid["price"] > 0]
        if valid.empty:
            st.warning("Add at least one item with a name and price.")
        else:
            st.session_state.bill_items = valid[["name", "price"]].to_dict("records")
            st.session_state.step = 3
            st.rerun()


# ── Step 3: People ────────────────────────────────────────────────────────────

def step_people():
    render_step_bar(3)

    st.markdown('<div class="card-title">Who is splitting?</div>', unsafe_allow_html=True)
    st.caption("Enter one name per line.")

    people_text = st.text_area(
        "",
        value="\n".join(st.session_state.get("people", [])),
        height=160,
        placeholder="Alice\nBob\nCharlie",
        label_visibility="collapsed",
    )

    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    if col1.button("Back"):
        st.session_state.step = 2
        st.rerun()

    if col2.button("Next"):
        people = [n.strip() for n in people_text.splitlines() if n.strip()]
        if not people:
            st.warning("Enter at least one name.")
        else:
            st.session_state.people = people
            st.session_state.step = 4
            st.rerun()


# ── Step 4: Assign ────────────────────────────────────────────────────────────

def step_assign():
    render_step_bar(4)

    people = st.session_state.people
    items = st.session_state.bill_items

    col_sc, col_tax = st.columns(2)
    service_charge_rate = col_sc.number_input(
        "Service Charge (%)", min_value=0.0, max_value=50.0, value=5.0, step=0.5
    )
    tax_fixed = col_tax.number_input(
        "Tax (RM)", min_value=0.0, value=0.0, step=0.01
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="card-title">Who ate what?</div>', unsafe_allow_html=True)
    st.caption("Select everyone who shares each item.")

    for i, item in enumerate(items):
        default_persons = [p for p in item.get("persons", []) if p in people] or people
        assigned = st.multiselect(
            f"{item['name']}  —  RM {item['price']:.2f}",
            options=people,
            default=default_persons,
            key=f"assign_{i}",
        )
        items[i]["persons"] = assigned

    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    if col1.button("Back"):
        st.session_state.step = 3
        st.rerun()

    if col2.button("Calculate"):
        st.session_state.bill_items = items
        st.session_state.service_charge_rate = service_charge_rate
        st.session_state.tax_fixed = tax_fixed
        st.session_state.step = 5
        st.rerun()


# ── Step 5: Results ───────────────────────────────────────────────────────────

def step_results():
    render_step_bar(5)

    items = st.session_state.bill_items
    service_charge_rate = st.session_state.get("service_charge_rate", 5.0)
    tax_fixed = st.session_state.get("tax_fixed", 0.0)
    totals = calculate_bill(items, service_charge_rate, tax_fixed)

    grand_subtotal = sum(item["price"] for item in items)
    grand_service_charge = round(grand_subtotal * service_charge_rate / 100, 2)
    grand_total = round(grand_subtotal + grand_service_charge + tax_fixed, 2)

    # Grand total banner
    st.markdown(f"""
    <div class="total-banner">
        <div class="label">Grand Total</div>
        <div class="amount">RM {grand_total:.2f}</div>
        <div style="opacity:0.8;font-size:13px;">for {len(totals)} people</div>
    </div>
    """, unsafe_allow_html=True)

    # Breakdown
    st.markdown(f"""
    <div class="card">
        <div class="card-title">Breakdown</div>
        <div class="breakdown-row"><span>Subtotal</span><span>RM {grand_subtotal:.2f}</span></div>
        <div class="breakdown-row"><span>Service Charge ({service_charge_rate:.0f}%)</span><span>RM {grand_service_charge:.2f}</span></div>
        <div class="breakdown-row"><span>Tax</span><span>RM {tax_fixed:.2f}</span></div>
    </div>
    """, unsafe_allow_html=True)

    # Per person cards
    st.markdown('<div class="card-title" style="margin-top:8px;">Each Person Pays</div>', unsafe_allow_html=True)

    for person, amount in sorted(totals.items()):
        st.markdown(f"""
        <div class="person-card">
            <span class="person-name">{person}</span>
            <span class="person-amount">RM {amount:.2f}</span>
        </div>
        """, unsafe_allow_html=True)

    unassigned = [item["name"] for item in items if not item.get("persons")]
    if unassigned:
        st.warning(f"Not assigned to anyone: {', '.join(unassigned)}")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Start Over"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ── Session Init ──────────────────────────────────────────────────────────────

def init_session():
    defaults = {"step": 1, "bill_items": [], "people": [], "service_charge_rate": 5.0, "tax_fixed": 0.0}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Bill Splitter", page_icon="🧾", layout="centered")
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("Bill Splitter")

    init_session()

    step_handlers = {
        1: step_upload,
        2: step_items,
        3: step_people,
        4: step_assign,
        5: step_results,
    }
    step_handlers[st.session_state.step]()


if __name__ == "__main__":
    main()
