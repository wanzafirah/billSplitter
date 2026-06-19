import re
from collections import defaultdict

import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image

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


def extract_text_from_image(image: Image.Image) -> str:
    """Run Tesseract OCR on the receipt image and return raw text."""
    return pytesseract.image_to_string(image)


def parse_items_from_text(text: str) -> list[dict]:
    """
    Extract item name and price pairs from OCR text.

    Handles two receipt formats:

    Format 1 (multi-line) — item name on its own line starting with *,
    price row follows on a later line:
        *Beef Bolognese with Penne
        Lunch
                            20.00    1    0.00    20.00

    Format 2 (single-line) — name and price on the same line:
        Beef Bolognese with Penne    20.00

    For multi-line receipts the Amount column (last number) is used,
    so quantity > 1 is handled correctly (e.g. 2 x RM13 = RM26).
    """
    items = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # --- Format 1: multi-line (Malaysian cafe style) ---
    # Item name line starts with *
    name_pattern = re.compile(r'^\*(.+)')
    # Price row: price  qty  discount  amount  (e.g. "20.00  1  0.00  20.00")
    price_row_pattern = re.compile(r'(\d+\.\d{2})\s+\d+\s+\d+\.\d{2}\s+(\d+\.\d{2})')
    # Stop scanning when we hit the totals section
    totals_pattern = re.compile(r'^(total|subtotal|tax|service|rounding)', re.IGNORECASE)

    current_name = None
    for line in lines:
        if totals_pattern.match(line):
            current_name = None
            continue

        name_match = name_pattern.match(line)
        if name_match:
            current_name = name_match.group(1).strip()
            continue

        if current_name:
            price_match = price_row_pattern.search(line)
            if price_match:
                amount = float(price_match.group(2))  # use Amount column (qty already applied)
                if amount > 0:
                    items.append({"name": current_name, "price": amount})
                current_name = None

    if items:
        return items

    # --- Format 2: single-line fallback ("Item Name    12.50") ---
    single_line_pattern = re.compile(r'^(.+?)\s{2,}(\d+\.\d{2})\s*$')
    for line in lines:
        match = single_line_pattern.match(line)
        if match:
            name = match.group(1).strip()
            try:
                price = float(match.group(2))
                if name and price > 0:
                    items.append({"name": name, "price": price})
            except ValueError:
                continue

    return items


#bill calc

def calculate_bill(items: list[dict], tax_rate: float) -> dict[str, float]:

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
            with st.spinner("Reading receipt..."):
                raw_text = extract_text_from_image(image)
                st.session_state.bill_items = parse_items_from_text(raw_text)
            if not st.session_state.bill_items:
                st.warning(
                    "Could not detect any items from the image. "
                    "You can enter them manually on the next screen."
                )
            st.session_state.step = 2
            st.rerun()

    st.markdown("---")
    if st.button("Skip — Enter Items Manually"):
        st.session_state.bill_items = []
        st.session_state.step = 2
        st.rerun()


# edit items

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


# enter names

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


#assign item

def step_assign():
    st.subheader("Step 4 of 4 — Assign Items")
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
        # Default: everyone shares the item
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



def init_session():
    defaults = {"step": 1, "bill_items": [], "people": [], "tax_rate": 6.0}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


#main

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
