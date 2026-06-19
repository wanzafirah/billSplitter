import json
import re
from collections import defaultdict

import google.generativeai as genai
import pandas as pd
import streamlit as st
from PIL import Image

#theme

PASTEL_CSS = """
<style>
    .stApp {
        background-color: #fdf6f0;
        color: #3a3a5a;
    }
    .stApp p, .stApp span, .stApp label, .stApp div {
        color: #3a3a5a;
    }
    h1 {
        color: #b5838d !important;
    }
    h2, h3 {
        color: #9b89b4 !important;
    }
    .stButton > button {
        background-color: #c8b6e2;
        color: #3a3a5a;
        border: none;
        border-radius: 10px;
        font-weight: 600;
        padding: 0.4rem 1.2rem;
    }
    .stButton > button:hover {
        background-color: #b8a2d8;
    }
    [data-testid="stMetricValue"] {
        color: #b5838d !important;
    }
    [data-testid="stMetricLabel"] {
        color: #9b89b4 !important;
    }
</style>
"""


#gemini extract

GEMINI_PROMPT = """
Look at this receipt image and extract all food and drink items with their total amounts.

Rules:
- Use the Amount column (rightmost price), not the unit price, so quantity is already included.
- Do not include tax, service charge, rounding, subtotal, or total rows.
- Return ONLY a valid JSON array, no explanation, no markdown.

Format:
[{"name": "Item Name", "price": 12.50}, ...]
"""


def extract_items_with_gemini(image: Image.Image, api_key: str) -> list[dict]:
    """Send receipt image to Gemini Vision and return parsed items."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content([GEMINI_PROMPT, image])

    # Strip markdown code fences if Gemini wraps the JSON
    text = response.text.strip()
    text = re.sub(r'^```json\s*|\s*```$', '', text, flags=re.MULTILINE).strip()

    raw = json.loads(text)
    return [
        {"name": str(item["name"]), "price": float(item["price"])}
        for item in raw
        if item.get("name") and float(item.get("price", 0)) > 0
    ]


# bill calculate

def calculate_bill(items: list[dict], tax_rate: float) -> dict[str, float]:
    """
    Calculate each person's share.
    Shared items are divided equally among assigned people.
    Tax is a percentage on top of each person's subtotal.
    """
    person_subtotals: dict[str, float] = defaultdict(float)

    for item in items:
        persons = item.get("persons") or []
        if not persons:
            continue
        share = item["price"] / len(persons)
        for person in persons:
            person_subtotals[person] += share

    return {
        person: round(subtotal * (1 + tax_rate / 100), 2)
        for person, subtotal in person_subtotals.items()
    }

#upload receipt

def step_upload():
    st.subheader("Upload Receipt")

    # Load API key: from Streamlit secrets (deployed) or sidebar input (local)
    if "api_key" not in st.session_state:
        st.session_state.api_key = st.secrets.get("GEMINI_API_KEY", "")

    if not st.session_state.api_key:
        with st.sidebar:
            st.markdown("### Gemini API Key")
            st.caption("Required for automatic extraction. [Get a free key](https://aistudio.google.com/app/apikey)")
            api_key = st.text_input("API Key", type="password", key="api_key_input")
            if api_key:
                st.session_state.api_key = api_key

    source = st.radio("Receipt source", ["Upload image", "Take photo"], horizontal=True)

    image = None
    if source == "Upload image":
        file = st.file_uploader("Choose a receipt image", type=["png", "jpg", "jpeg"])
        if file:
            image = Image.open(file)
    else:
        captured = st.camera_input("Take a photo of your receipt")
        if captured:
            image = Image.open(captured)

    if image:
        st.image(image, use_container_width=True)

        if st.button("Extract Items from Receipt"):
            key = st.session_state.get("api_key", "")
            if not key:
                st.error("Enter your Gemini API key in the sidebar first.")
            else:
                with st.spinner("Reading receipt..."):
                    try:
                        st.session_state.bill_items = extract_items_with_gemini(image, key)
                        if not st.session_state.bill_items:
                            st.warning("No items found. You can add them manually on the next screen.")
                        st.session_state.step = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not read receipt: {e}")

    st.markdown("---")
    if st.button("Skip — Enter Items Manually"):
        st.session_state.bill_items = []
        st.session_state.step = 2
        st.rerun()


# review item

def step_items():
    st.subheader("Review Items")
    st.caption("Edit names and prices. Use the trash icon to remove a row. Click below the table to add a row.")

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

    col1, col2 = st.columns(2)

    if col1.button("Back"):
        st.session_state.step = 1
        st.rerun()

    if col2.button("Next: Add People"):
        valid = edited.dropna(subset=["name"])
        valid = valid[valid["name"].str.strip() != ""]
        valid = valid[valid["price"] > 0]
        if valid.empty:
            st.warning("Add at least one item with a name and price before continuing.")
        else:
            st.session_state.bill_items = valid[["name", "price"]].to_dict("records")
            st.session_state.step = 3
            st.rerun()


# enter name

def step_people():
    st.subheader("Who is splitting the bill?")
    st.caption("Enter one name per line.")

    people_text = st.text_area(
        "Names",
        value="\n".join(st.session_state.get("people", [])),
        height=150,
        placeholder="Alice\nBob\nCharlie",
    )

    col1, col2 = st.columns(2)

    if col1.button("Back"):
        st.session_state.step = 2
        st.rerun()

    if col2.button("Next: Assign Items"):
        people = [n.strip() for n in people_text.splitlines() if n.strip()]
        if not people:
            st.warning("Enter at least one name before continuing.")
        else:
            st.session_state.people = people
            st.session_state.step = 4
            st.rerun()


# assign item to people

def step_assign():
    st.subheader("Assign Items")
    st.caption("Select everyone who shares each item. Items are split equally among selected people.")

    people = st.session_state.people
    items = st.session_state.bill_items

    tax_rate = st.number_input(
        "Tax / Service Charge (%)",
        min_value=0.0,
        max_value=50.0,
        value=6.0,
        step=0.5,
    )

    st.markdown("---")

    for i, item in enumerate(items):
        default_persons = [p for p in item.get("persons", people) if p in people] or people
        assigned = st.multiselect(
            f"{item['name']}  —  RM {item['price']:.2f}",
            options=people,
            default=default_persons,
            key=f"assign_{i}",
        )
        items[i]["persons"] = assigned

    st.markdown("---")
    col1, col2 = st.columns(2)

    if col1.button("Back"):
        st.session_state.step = 3
        st.rerun()

    if col2.button("Calculate"):
        st.session_state.bill_items = items
        st.session_state.tax_rate = tax_rate
        st.session_state.step = 5
        st.rerun()


#result

def step_results():
    st.subheader("Results")

    items = st.session_state.bill_items
    tax_rate = st.session_state.get("tax_rate", 6.0)
    totals = calculate_bill(items, tax_rate)

    grand_subtotal = sum(item["price"] for item in items)
    grand_tax = round(grand_subtotal * tax_rate / 100, 2)
    grand_total = round(grand_subtotal + grand_tax, 2)

    col1, col2, col3 = st.columns(3)
    col1.metric("Subtotal", f"RM {grand_subtotal:.2f}")
    col2.metric(f"Tax ({tax_rate:.1f}%)", f"RM {grand_tax:.2f}")
    col3.metric("Grand Total", f"RM {grand_total:.2f}")

    st.markdown("---")
    st.write("**Each person pays:**")

    for person, amount in sorted(totals.items()):
        st.markdown(f"**{person}** — RM {amount:.2f}")

    unassigned = [item["name"] for item in items if not item.get("persons")]
    if unassigned:
        st.warning(f"These items were not assigned to anyone: {', '.join(unassigned)}")

    st.markdown("---")
    if st.button("Start Over"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# session

def init_session():
    defaults = {"step": 1, "bill_items": [], "people": [], "tax_rate": 6.0}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# main

def main():
    st.set_page_config(page_title="Bill Splitter", layout="centered")
    st.markdown(PASTEL_CSS, unsafe_allow_html=True)
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
