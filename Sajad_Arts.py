import streamlit as st
from reportlab.lib import colors
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from urllib.parse import quote
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO
import re
from datetime import datetime
import uuid
import hashlib

# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(page_title="MAPOS Billing App", page_icon="🧣", layout="wide")

# ============================================================
# HIDE STREAMLIT INPUT INSTRUCTIONS
# ============================================================

st.markdown(
    """
    <style>
    [data-testid="InputInstructions"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ========================================================
# GOOGLE SHEETS CONNECTION
# ========================================================

conn = st.connection("gsheets", type=GSheetsConnection)


@st.cache_data(ttl=30)
def get_bills():

    try:
        bills_df = conn.read(worksheet="Bills", ttl=30)

        if bills_df.empty:
            return pd.DataFrame()

        # ====================================================
        # CLEAN TEXT COLUMNS
        # ====================================================

        text_columns = [
            "Transaction ID",
            "Date",
            "Customer Name",
            "Customer Number",
            "Item",
            "Payment Mode",
            "Inventory Updated",
        ]

        for column in text_columns:
            if column in bills_df.columns:
                bills_df[column] = bills_df[column].fillna("").astype(str).str.strip()

        # Clean Customer Number so it never displays as 8494001112.0
        if "Customer Number" in bills_df.columns:
            bills_df["Customer Number"] = pd.to_numeric(
                bills_df["Customer Number"], errors="coerce"
            ).apply(lambda x: str(int(x)) if pd.notna(x) else "")

        # ====================================================
        # CLEAN INTEGER COLUMNS
        # ====================================================

        integer_columns = [
            "Bill No",
            "Quantity",
            "Total Stock",
            "Stock at Addition",
            "Remaining Stock",
        ]

        for column in integer_columns:
            if column in bills_df.columns:
                bills_df[column] = (
                    pd
                    .to_numeric(bills_df[column], errors="coerce")
                    .fillna(0)
                    .astype(int)
                )

        # ====================================================
        # CLEAN NUMERIC COLUMNS
        # ====================================================

        numeric_columns = [
            "Rate",
            "Amount",
            "Sub Total",
            "GST %",
            "GST Amount",
            "Grand Total",
        ]

        for column in numeric_columns:
            if column in bills_df.columns:
                bills_df[column] = pd.to_numeric(
                    bills_df[column], errors="coerce"
                ).fillna(0.0)

        return bills_df

    except Exception:
        return pd.DataFrame()


# ========================================================
# GET NEXT BILL NUMBER FROM GOOGLE SHEETS
# ========================================================


def get_next_bill_number():
    """
    Gets the highest Bill No from Google Sheets
    and returns the next bill number.
    """

    try:
        bills_df = get_bills()

        # No bills yet
        if bills_df.empty:
            return 1

        # Bill No column does not exist
        if "Bill No" not in bills_df.columns:
            return 1

        # Convert Bill No values to numbers
        bill_numbers = pd.to_numeric(bills_df["Bill No"], errors="coerce").dropna()

        # No valid bill numbers
        if bill_numbers.empty:
            return 1

        # Highest bill number + 1
        return int(bill_numbers.max()) + 1

    except Exception as e:
        st.error(f"Could not get next Bill Number from Google Sheets: {e}")

        return 1


# ============================================================
# INPUT VALIDATION
# ============================================================


def validate_name(name):
    """
    Allows letters and spaces only.
    Examples:
    Mohammad Amaan -> Valid
    Amaan -> Valid
    Amaan123 -> Invalid
    Amaan@ -> Invalid
    """
    name = name.strip()

    if not name:
        return False, "Name cannot be empty."

    if not re.fullmatch(r"[A-Za-z ]+", name):
        return False, "Name can contain letters and spaces only."

    return True, ""


def validate_phone(phone):
    """
    Allows numbers only and requires exactly 10 digits.
    """
    phone = phone.strip()

    if not phone:
        return False, "Phone number cannot be empty."

    if not phone.isdigit():
        return False, "Phone number can contain numbers only."

    if len(phone) != 10:
        return False, "Phone number must contain exactly 10 digits."

    return True, ""


def validate_shop_phone(phone):
    """
    Allows numbers only and requires exactly 10 digits.
    """
    phone = phone.strip()

    if not phone:
        return False, "Shop phone number cannot be empty."

    if not phone.isdigit():
        return False, "Shop phone number can contain numbers only."

    if len(phone) != 10:
        return False, "Shop phone number must contain exactly 10 digits."

    return True, ""


# ============================================================
# NUMBER TO WORDS
# ============================================================


def number_to_words(number):
    ones = [
        "",
        "One",
        "Two",
        "Three",
        "Four",
        "Five",
        "Six",
        "Seven",
        "Eight",
        "Nine",
        "Ten",
        "Eleven",
        "Twelve",
        "Thirteen",
        "Fourteen",
        "Fifteen",
        "Sixteen",
        "Seventeen",
        "Eighteen",
        "Nineteen",
    ]

    tens = [
        "",
        "",
        "Twenty",
        "Thirty",
        "Forty",
        "Fifty",
        "Sixty",
        "Seventy",
        "Eighty",
        "Ninety",
    ]

    def convert_less_than_thousand(n):

        words = ""

        if n >= 100:
            words += ones[n // 100] + " Hundred"
            n %= 100

            if n:
                words += " "

        if n >= 20:
            words += tens[n // 10]
            n %= 10

            if n:
                words += " " + ones[n]

        elif n > 0:
            words += ones[n]

        return words

    number = float(number)

    rupees = int(number)
    paise = round((number - rupees) * 100)

    if rupees == 0:
        rupees_words = "Zero"
    else:
        parts = []

        crore = rupees // 10000000
        rupees %= 10000000

        lakh = rupees // 100000
        rupees %= 100000

        thousand = rupees // 1000
        rupees %= 1000

        if crore:
            parts.append(convert_less_than_thousand(crore) + " Crore")

        if lakh:
            parts.append(convert_less_than_thousand(lakh) + " Lakh")

        if thousand:
            parts.append(convert_less_than_thousand(thousand) + " Thousand")

        if rupees:
            parts.append(convert_less_than_thousand(rupees))

        rupees_words = " ".join(parts)

    if paise > 0:
        paise_words = convert_less_than_thousand(paise)

        return f"{rupees_words} Rupees and {paise_words} Paise Only"

    return f"{rupees_words} Rupees Only"


# ============================================================
# SESSION STATE
# ============================================================

if "products" not in st.session_state:
    st.session_state.products = []

if "current_bill_no" not in st.session_state:
    st.session_state.current_bill_no = get_next_bill_number()

if "transaction_id" not in st.session_state:
    st.session_state.transaction_id = str(uuid.uuid4())

if "bill_saved" not in st.session_state:
    st.session_state.bill_saved = False

if "inventory_updated" not in st.session_state:
    st.session_state.inventory_updated = False

if "product_form_reset" not in st.session_state:
    st.session_state.product_form_reset = 0


# ============================================================
# PDF GENERATOR
# ============================================================


def generate_pdf(
    shop_name,
    shop_location,
    shop_phone,
    bill_no,
    customer_name,
    customer_phone,
    payment_method,
    products,
    subtotal,
    gst_rate,
    gst_amount,
    grand_total,
    total_items,
    instagram,
):

    buffer = BytesIO()

    # Receipt-style width similar to a thermal printer
    receipt_width = 80 * mm

    doc = SimpleDocTemplate(
        buffer,
        pagesize=(receipt_width, 250 * mm),
        rightMargin=5 * mm,
        leftMargin=5 * mm,
        topMargin=5 * mm,
        bottomMargin=5 * mm,
    )

    styles = getSampleStyleSheet()

    shop_style = ParagraphStyle(
        "ShopName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=2,
    )

    center_style = ParagraphStyle(
        "Center",
        parent=styles["Normal"],
        fontSize=8,
        alignment=TA_CENTER,
        leading=10,
    )
    normal_style = ParagraphStyle(
        "NormalCustom",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
    )

    right_style = ParagraphStyle(
        "RightStyle",
        parent=normal_style,
        alignment=TA_RIGHT,
    )

    bold_style = ParagraphStyle(
        "BoldCustom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
    )

    total_style = ParagraphStyle(
        "Total",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
    )

    story = []

    # ========================================================
    # SHOP HEADER
    # ========================================================

    # ========================================================
    # CLICKABLE SHOP NAME → GOOGLE MAPS
    # ========================================================

    maps_url = "https://www.google.com/maps/search/?api=1&query=" + quote(shop_location)

    shop_name_link = f'<link href="{maps_url}" color="black">{shop_name.upper()}</link>'

    story.append(Paragraph(shop_name_link, shop_style))

    story.append(Paragraph(shop_location, center_style))

    story.append(Paragraph(f"SHOP PHONE: {shop_phone}", center_style))

    story.append(Spacer(1, 5))

    # ========================================================
    # BILL INFORMATION
    # ========================================================

    now = datetime.now()

    bill_info = [
        [
            Paragraph(f"<b>Bill No:</b> {bill_no}", normal_style),
            Paragraph(f"<b>Date:</b> {now.strftime('%d/%m/%y')}", normal_style),
        ],
        [
            Paragraph(f"<b>Customer:</b> {customer_name}", normal_style),
            Paragraph(f"<b>Time:</b> {now.strftime('%H:%M:%S')}", normal_style),
        ],
        [
            Paragraph(f"<b>Customer Phone:</b> {customer_phone}", normal_style),
            "",
        ],
    ]

    info_table = Table(bill_info, colWidths=[38 * mm, 32 * mm])

    info_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ])
    )

    story.append(info_table)

    story.append(Spacer(1, 5))

    # ========================================================
    # PRODUCT TABLE
    # ========================================================

    product_data = [
        [
            Paragraph("<b>Item</b>", center_style),
            Paragraph("<b>Qty</b>", center_style),
            Paragraph("<b>Rate</b>", center_style),
            Paragraph("<b>Amt</b>", center_style),
        ]
    ]

    for product in products:
        amount = product["quantity"] * product["rate"]

        product_data.append([
            Paragraph(product["name"], normal_style),
            Paragraph(str(product["quantity"]), center_style),
            Paragraph(f"{product['rate']:,.2f}", right_style),
            Paragraph(f"{amount:,.2f}", right_style),
        ])

    product_table = Table(product_data, colWidths=[27 * mm, 10 * mm, 17 * mm, 21 * mm])

    product_table.setStyle(
        TableStyle([
            ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ])
    )

    story.append(product_table)

    story.append(Spacer(1, 5))

    # ========================================================
    # TOTALS
    # ========================================================

    # Amount in words
    amount_in_words = number_to_words(grand_total)

    # Style for amount in words
    amount_words_style = ParagraphStyle(
        "AmountWords",
        parent=normal_style,
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
    )

    totals_data = [
        [
            Paragraph("Total Items", normal_style),
            Paragraph(str(total_items), bold_style),
        ],
        [
            Paragraph("Sub Total", normal_style),
            Paragraph(f"{subtotal:,.2f}", bold_style),
        ],
    ]

    # Add GST only if enabled
    if gst_rate > 0:
        totals_data.append([
            Paragraph(f"GST ({gst_rate:g}%)", normal_style),
            Paragraph(f"{gst_amount:,.2f}", normal_style),
        ])

    # ========================================================
    # GRAND TOTAL
    # ========================================================

    totals_data.append([
        Paragraph("GRAND TOTAL", total_style),
        Paragraph(f"{grand_total:,.2f}", total_style),
    ])

    # # ========================================================
    # # TOTALS TABLE
    # # ========================================================

    totals_table = Table(totals_data, colWidths=[40 * mm, 35 * mm])

    totals_table.setStyle(
        TableStyle([
            # Alignment
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            # No borders by default
            ("LINEABOVE", (0, 0), (-1, -1), 0, colors.white),
            ("LINEBELOW", (0, 0), (-1, -1), 0, colors.white),
            # Padding
            ("LEFTPADDING", (0, 0), (-1, -1), 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            # ================================================
            # LINE ABOVE TOTAL ITEMS
            # ================================================
            ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
            # ================================================
            # LINE BELOW TOTAL ITEMS
            # ================================================
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
            # ================================================
            # LINE BELOW SUB TOTAL
            # ================================================
            ("LINEBELOW", (0, 1), (-1, 1), 0.8, colors.black),
        ])
    )

    story.append(totals_table)

    # ========================================================
    # LINE BELOW GST
    # ========================================================

    if gst_rate > 0:
        # GST is row 2 when GST is enabled
        totals_table.setStyle(
            TableStyle([
                ("LINEBELOW", (0, 2), (-1, 2), 0.8, colors.black),
            ])
        )

    # ========================================================
    # LINE AFTER GRAND TOTAL
    # ========================================================

    story.append(Spacer(1, 3))

    story.append(
        HRFlowable(
            width="100%",
            thickness=0.8,
            color=colors.black,
            spaceBefore=1,
            spaceAfter=5,
        )
    )

    # ========================================================
    # AMOUNT IN WORDS
    # ========================================================

    story.append(
        Paragraph(f"<b>Amount in Words:</b><br/>{amount_in_words}", amount_words_style)
    )

    story.append(Spacer(1, 4))

    story.append(
        HRFlowable(
            width="100%",
            thickness=0.8,
            color=colors.black,
            spaceBefore=1,
            spaceAfter=5,
        )
    )

    story.append(Spacer(1, 3))

    # ========================================================
    # PAYMENT
    # ========================================================

    payment_table = Table(
        [
            [
                Paragraph("<b>Payment Mode</b>", normal_style),
                Paragraph(payment_method, normal_style),
            ]
        ],
        colWidths=[40 * mm, 35 * mm],
    )

    payment_table.setStyle(
        TableStyle([
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ])
    )

    story.append(payment_table)

    story.append(Spacer(1, 5))

    # Line after Payment Mode
    story.append(
        HRFlowable(
            width="100%",
            thickness=0.8,
            color=colors.black,
            spaceBefore=1,
            spaceAfter=7,
        )
    )

    # ========================================================
    # FOOTER
    # ========================================================

    story.append(Paragraph("Follow Us on Instagram", center_style))

    # Instagram clickable link
    instagram_username = instagram.strip().replace("@", "")

    instagram_link = (
        f'<link href="https://www.instagram.com/{instagram_username}" '
        f'color="blue">@{instagram_username}</link>'
    )

    story.append(
        Paragraph(
            instagram_link,
            ParagraphStyle(
                "Instagram",
                parent=center_style,
                fontName="Helvetica-Bold",
                underline=True,
            ),
        )
    )

    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            "Thank You. Visit Us Again!",
            ParagraphStyle(
                "ThankYou",
                parent=center_style,
                fontName="Helvetica-Bold",
                fontSize=9,
            ),
        )
    )

    story.append(Spacer(1, 8))

    # ========================================================
    # CLICKABLE POWERED BY MAP
    # ========================================================

    mapos_link = "https://map-portfolio.netlify.app/"

    powered_by_map = f'<link href="{mapos_link}" color="black">Powered by MAPOS</link>'

    story.append(Paragraph(powered_by_map, center_style))

    doc.build(story)

    buffer.seek(0)

    return buffer.getvalue()


# ========================================================
# SAVE BILL TO GOOGLE SHEETS
# ========================================================


def save_bill_to_google_sheet(
    bill_no,
    transaction_id,
    customer_name,
    customer_phone,
    products,
    subtotal,
    gst_rate,
    gst_amount,
    grand_total,
    payment_method,
    inventory_updated="Pending",
):

    bill_date = datetime.now().strftime("%d/%m/%y")

    # ----------------------------------------------------
    # READ EXISTING BILLS
    # ----------------------------------------------------

    existing_data = conn.read(worksheet="Bills", ttl=0)

    # ----------------------------------------------------
    # DUPLICATE PROTECTION
    # ----------------------------------------------------

    if not existing_data.empty:
        # Check Transaction ID
        if "Transaction ID" in existing_data.columns:
            transaction_exists = (
                existing_data["Transaction ID"]
                .astype(str)
                .eq(str(transaction_id))
                .any()
            )

            if transaction_exists:
                return False, "This bill has already been saved."

        # Also check Bill Number
        if "Bill No" in existing_data.columns:
            bill_numbers = pd.to_numeric(existing_data["Bill No"], errors="coerce")

            bill_exists = (bill_numbers == int(bill_no)).any()

            if bill_exists:
                return False, (f"Bill No {bill_no} already exists in Google Sheets.")

    # ----------------------------------------------------
    # CREATE BILL ROWS
    # ----------------------------------------------------

    new_rows = []

    for product in products:
        amount = product["quantity"] * product["rate"]

        new_rows.append({
            "Bill No": bill_no,
            "Transaction ID": transaction_id,
            "Date": bill_date,
            "Customer Name": customer_name,
            "Customer Number": str(customer_phone).strip(),
            "Item": product["name"],
            "Quantity": product["quantity"],
            "Total Stock": product["total_stock"],
            "Stock at Addition": product["stock_at_addition"],
            "Remaining Stock": product["remaining_stock"],
            "Rate": product["rate"],
            "Amount": amount,
            "Sub Total": subtotal,
            "GST %": gst_rate,
            "GST Amount": gst_amount,
            "Grand Total": grand_total,
            "Payment Mode": payment_method,
            "Inventory Updated": inventory_updated,
        })

    new_data = pd.DataFrame(new_rows)

    # ----------------------------------------------------
    # APPEND BILL
    # ----------------------------------------------------

    if existing_data.empty:
        final_data = new_data

    else:
        final_data = pd.concat([existing_data, new_data], ignore_index=True)

    # ====================================================
    # KEEP BILLS COLUMNS IN THE CORRECT ORDER
    # ====================================================

    bill_columns = [
        "Bill No",
        "Transaction ID",
        "Date",
        "Customer Name",
        "Customer Number",
        "Item",
        "Quantity",
        "Total Stock",
        "Stock at Addition",
        "Remaining Stock",
        "Rate",
        "Amount",
        "Sub Total",
        "GST %",
        "GST Amount",
        "Grand Total",
        "Payment Mode",
        "Inventory Updated",
    ]

    # Add any missing columns
    for column in bill_columns:
        if column not in final_data.columns:
            final_data[column] = ""

    # Keep only the required columns in the correct order
    final_data = final_data[bill_columns]

    # ----------------------------------------------------
    # SAVE
    # ----------------------------------------------------

    conn.update(worksheet="Bills", data=final_data)
    get_bills.clear()

    return True, "Bill saved successfully.", final_data


# ========================================================
# MARK INVENTORY AS UPDATED
# ========================================================
def mark_inventory_updated(transaction_id, bills_df):

    try:
        if bills_df is None or bills_df.empty:
            return False

        # Make sure column exists
        if "Inventory Updated" not in bills_df.columns:
            bills_df["Inventory Updated"] = "Pending"

        # Find rows belonging to this transaction
        matching_rows = (
            bills_df["Transaction ID"].astype(str).str.strip()
            == str(transaction_id).strip()
        )

        if not matching_rows.any():
            return False

        # -----------------------------------------------
        # INVENTORY WAS SUCCESSFULLY UPDATED
        # -----------------------------------------------

        bills_df.loc[matching_rows, "Inventory Updated"] = "Updated"

        # Update Google Sheet
        conn.update(worksheet="Bills", data=bills_df)

        # Clear cached bills
        get_bills.clear()

        return True

    except Exception as e:
        raise RuntimeError(f"Could not mark inventory as updated: {e}")


# ========================================================
# INVENTORY / PRODUCT LIST
# ========================================================

DEFAULT_PRODUCTS = [
    {"Item": "Hashidar", "Stock": 0},
    {"Item": "Koundar", "Stock": 0},
    {"Item": "Pointdar", "Stock": 0},
    {"Item": "Paldar", "Stock": 0},
    {"Item": "Jaildar", "Stock": 0},
    {"Item": "Plain Colour", "Stock": 0},
    {"Item": "Zaati", "Stock": 0},
    {"Item": "Ari", "Stock": 0},
]


@st.cache_data(ttl=30)
def get_inventory():

    try:
        inventory_df = conn.read(worksheet="Inventory", ttl=30)

        if inventory_df.empty:
            return pd.DataFrame(columns=["Item", "Stock"])

        # Make sure Item column exists
        if "Item" not in inventory_df.columns:
            return pd.DataFrame(columns=["Item", "Total Stock", "Stock"])

        # Support Google Sheet column name "Current Stock"
        if "Current Stock" in inventory_df.columns:
            inventory_df["Stock"] = inventory_df["Current Stock"]

        # Make sure Stock column exists
        if "Stock" not in inventory_df.columns:
            inventory_df["Stock"] = 0

        # Make sure Total Stock column exists
        if "Total Stock" not in inventory_df.columns:
            inventory_df["Total Stock"] = inventory_df["Stock"]

        # Keep Item, Total Stock and Current Stock
        inventory_df = inventory_df[["Item", "Total Stock", "Stock"]].copy()

        # Clean Item
        inventory_df["Item"] = inventory_df["Item"].fillna("").astype(str).str.strip()

        # Clean Stock
        inventory_df["Stock"] = (
            pd.to_numeric(inventory_df["Stock"], errors="coerce").fillna(0).astype(int)
        )

        inventory_df["Total Stock"] = (
            pd
            .to_numeric(inventory_df["Total Stock"], errors="coerce")
            .fillna(0)
            .astype(int)
        )
        # Remove blank products
        inventory_df = inventory_df[inventory_df["Item"] != ""]

        # Remove duplicate products
        inventory_df = inventory_df.drop_duplicates(
            subset=["Item"], keep="last"
        ).reset_index(drop=True)

        return inventory_df

    except Exception:
        return pd.DataFrame(DEFAULT_PRODUCTS)


def update_inventory(inventory_df):

    # Make sure Total Stock exists
    if "Total Stock" not in inventory_df.columns:
        inventory_df["Total Stock"] = inventory_df["Stock"]

    # Keep all inventory columns
    inventory_df = inventory_df[["Item", "Total Stock", "Stock"]].copy()

    # Clean Item
    inventory_df["Item"] = inventory_df["Item"].fillna("").astype(str).str.strip()

    # Clean Total Stock
    inventory_df["Total Stock"] = (
        pd
        .to_numeric(inventory_df["Total Stock"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    # Clean Current Stock
    inventory_df["Stock"] = (
        pd.to_numeric(inventory_df["Stock"], errors="coerce").fillna(0).astype(int)
    )

    # Remove blank products
    inventory_df = inventory_df[inventory_df["Item"] != ""]

    # Remove duplicate products
    inventory_df = inventory_df.drop_duplicates(
        subset=["Item"], keep="last"
    ).reset_index(drop=True)

    # Save Item + Total Stock + Current Stock
    conn.update(worksheet="Inventory", data=inventory_df)

    # Clear ONLY the inventory cache
    get_inventory.clear()


# ========================================================
# CHECK INVENTORY BEFORE BILL
# ========================================================


def check_inventory(products, inventory_df):

    for product in products:
        product_name = product["name"]
        requested_quantity = int(product["quantity"])

        matching_rows = inventory_df[
            inventory_df["Item"].str.lower() == product_name.lower()
        ]

        # Product doesn't exist
        if matching_rows.empty:
            return (False, f"Product '{product_name}' is not available in inventory.")

        current_stock = int(matching_rows.iloc[0]["Stock"])

        # Not enough stock
        if requested_quantity > current_stock:
            return (
                False,
                f"Not enough stock for '{product_name}'. "
                f"Available: {current_stock}, "
                f"Requested: {requested_quantity}.",
            )

    return True, ""


# ========================================================
# REDUCE INVENTORY SAFELY
# ========================================================


def reduce_inventory_once(products, transaction_id, inventory_df):

    # ----------------------------------------------------
    # CHECK SESSION STATE
    # ----------------------------------------------------

    if st.session_state.get("inventory_updated", False):
        return False, "Inventory has already been updated for this bill."

    # ----------------------------------------------------
    # CHECK ALL PRODUCTS FIRST
    # ----------------------------------------------------

    for product in products:
        product_name = product["name"]
        sold_quantity = int(product["quantity"])

        matching_rows = inventory_df[
            inventory_df["Item"].str.lower() == product_name.lower()
        ]

        if matching_rows.empty:
            raise ValueError(f"Product '{product_name}' was not found in inventory.")

        index = matching_rows.index[0]

        current_stock = int(inventory_df.loc[index, "Stock"])

        if sold_quantity > current_stock:
            raise ValueError(
                f"Not enough stock for '{product_name}'. "
                f"Available: {current_stock}, "
                f"Requested: {sold_quantity}."
            )

    # ----------------------------------------------------
    # ALL STOCK CHECKS PASSED
    # ----------------------------------------------------

    for product in products:
        product_name = product["name"]
        sold_quantity = int(product["quantity"])

        matching_rows = inventory_df[
            inventory_df["Item"].str.lower() == product_name.lower()
        ]

        index = matching_rows.index[0]

        current_stock = int(inventory_df.loc[index, "Stock"])

        inventory_df.loc[index, "Stock"] = current_stock - sold_quantity

    # ----------------------------------------------------
    # SAVE UPDATED INVENTORY
    # ----------------------------------------------------
    update_inventory(inventory_df)

    # Mark inventory as updated for this transaction
    st.session_state.inventory_updated = True

    return True, "Inventory updated successfully."


# ============================================================
# APP HEADER
# ============================================================

st.title("🧾 MAPOS Billing")
st.caption("Simple billing and inventory management system")

# ============================================================
# SIDEBAR - SHOP & CUSTOMER DETAILS
# ============================================================

with st.sidebar.form("bill_details_form"):
    st.subheader("🏪 Shop Details")

    shop_name = st.text_input("Shop Name", value="Sajad Arts", key="shop_name")

    shop_location = st.text_input(
        "Shop Location", value="Srinagar, Jammu & Kashmir", key="shop_location"
    )

    shop_phone = st.text_input(
        "Shop Phone Number", value="8494001112", max_chars=10, key="shop_phone"
    )

    instagram = st.text_input(
        "Instagram Username", value="@mohammadamaan32", key="instagram"
    )

    st.divider()

    st.subheader("👤 Customer Details")

    customer_name = st.text_input("Customer Name", key="customer_name")

    customer_phone = st.text_input(
        "Customer Phone Number", max_chars=10, key="customer_phone"
    )

    payment_method = st.selectbox(
        "Payment Method",
        ["Cash", "UPI", "Card", "Bank Transfer", "Other"],
        key="payment_method",
    )

    apply_details = st.form_submit_button("✅ Apply Details", use_container_width=True)


# ============================================================
# VALIDATE DETAILS AFTER FORM SUBMISSION
# ============================================================

if apply_details:
    if shop_phone:
        shop_phone_valid, shop_phone_error = validate_shop_phone(shop_phone)

        if not shop_phone_valid:
            st.sidebar.error(f"⚠️ {shop_phone_error}")

    if customer_name:
        customer_name_valid, customer_name_error = validate_name(customer_name)

        if not customer_name_valid:
            st.sidebar.error(f"⚠️ {customer_name_error}")

    if customer_phone:
        customer_phone_valid, customer_phone_error = validate_phone(customer_phone)

        if not customer_phone_valid:
            st.sidebar.error(f"⚠️ {customer_phone_error}")

    st.sidebar.success("✅ Details applied.")


st.sidebar.divider()

# ========================================================
# PRODUCT LIST / INVENTORY
# ========================================================

st.sidebar.header("📦 Product List")

st.sidebar.caption(
    "Inventory is managed directly in Google Sheets. "
    "Use Refresh Inventory below to load the latest stock."
)

# Load inventory from Google Sheets
inventory_df = get_inventory()

# --------------------------------------------------------
# REFRESH INVENTORY
# --------------------------------------------------------

if st.sidebar.button(
    "🔄 Refresh Inventory",
    key="refresh_inventory",
    use_container_width=True,
):
    get_inventory.clear()

    try:
        inventory_df = get_inventory()
        st.sidebar.success("✅ Inventory refreshed from Google Sheets.")
    except Exception as e:
        st.sidebar.error(f"Could not refresh inventory: {e}")

# --------------------------------------------------------
# DOWNLOAD INVENTORY
# --------------------------------------------------------

inventory_download_df = inventory_df.copy()

inventory_download_df = inventory_download_df.rename(
    columns={
        "Item": "Product",
        "Stock": "Current Stock",
    }
)

inventory_download_df = inventory_download_df[
    ["Product", "Total Stock", "Current Stock"]
]

inventory_excel_buffer = BytesIO()

with pd.ExcelWriter(inventory_excel_buffer, engine="openpyxl") as writer:
    inventory_download_df.to_excel(writer, index=False, sheet_name="Inventory")

inventory_excel_buffer.seek(0)

st.sidebar.download_button(
    label="📥 Download Inventory",
    data=inventory_excel_buffer,
    file_name="Sajad_Arts_Inventory.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

# --------------------------------------------------------
# DOWNLOAD ALL BILLS
# --------------------------------------------------------

try:
    bills_df = get_bills()

    if not bills_df.empty:
        bills_excel_buffer = BytesIO()

        with pd.ExcelWriter(bills_excel_buffer, engine="openpyxl") as writer:
            bills_df.to_excel(writer, index=False, sheet_name="Bills")

        bills_excel_buffer.seek(0)

        safe_shop_name = re.sub(r"[^A-Za-z0-9]+", "_", shop_name).strip("_")

        databook_filename = f"{safe_shop_name}_Databook.xlsx"

        st.sidebar.download_button(
            label="📥 Download Databook",
            data=bills_excel_buffer,
            file_name=databook_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

except Exception as e:
    st.sidebar.error(f"Could not create Bills Excel file: {e}")


# ============================================================
# BILL NUMBER
# ============================================================

st.sidebar.title("🧾 Bill Information")

bill_no = st.session_state.current_bill_no

st.sidebar.info(f"🧾 Current Bill Number: **{bill_no}**")

# ============================================================
# GET REMAINING STOCK FOR CURRENT BILL
# ============================================================


def get_remaining_stock(product_name, inventory_df):
    """
    Returns stock remaining after quantities already added
    to the current bill.

    Google Sheets inventory is NOT changed here.
    """

    # Get actual inventory stock
    matching_product = inventory_df[
        inventory_df["Item"].str.lower().str.strip() == product_name.lower().strip()
    ]

    if matching_product.empty:
        return 0

    available_stock = int(matching_product.iloc[0]["Stock"])

    # Calculate quantity already added to current bill
    already_added = sum(
        int(product["quantity"])
        for product in st.session_state.products
        if product["name"].strip().lower() == product_name.strip().lower()
    )

    # Remaining stock
    remaining_stock = available_stock - already_added

    return remaining_stock


# ============================================================
# PRODUCT ENTRY / EDIT PRODUCT
# ============================================================

st.header("Add Products")

# Check whether we are editing a product
if "editing_product" not in st.session_state:
    st.session_state.editing_product = None


if st.session_state.editing_product is not None:
    edit_index = st.session_state.editing_product
    edit_product = st.session_state.products[edit_index]

    st.info(f"✏️ Editing Product: {edit_product['name']}")

    # ========================================================
    # PRODUCT OPTIONS FROM INVENTORY
    # ========================================================

    product_options = inventory_df["Item"].dropna().astype(str).str.strip().tolist()

    current_product = edit_product["name"]

    if current_product not in product_options:
        st.error(
            f"❌ '{current_product}' is no longer available in Inventory. "
            "Please cancel this edit and select a product from Inventory."
        )
        st.stop()

    # --------------------------------------------------------
    # INPUT FIELDS
    # --------------------------------------------------------

    col1, col2, col3, col4 = st.columns([3, 2, 2.5, 1])

    # --------------------------------------------------------
    # PRODUCT NAME
    # --------------------------------------------------------

    with col1:
        selected_edit_product = st.selectbox(
            "Product Name",
            product_options,
            index=product_options.index(current_product),
            key="edit_product_select",
        )

        product_name = selected_edit_product

    # --------------------------------------------------------
    # QUANTITY
    # --------------------------------------------------------

    with col2:
        quantity = st.number_input(
            "Quantity",
            min_value=1,
            value=edit_product["quantity"],
            step=1,
            format="%d",
            key="edit_quantity",
        )

    # --------------------------------------------------------
    # RATE
    # --------------------------------------------------------

    with col3:
        rate = st.number_input(
            "Rate",
            min_value=0.0,
            value=float(edit_product["rate"]),
            step=50.0,
            key="edit_rate",
        )

    # --------------------------------------------------------
    # UPDATE BUTTON
    # --------------------------------------------------------

    with col4:
        st.write("")
        st.write("")

        update_product = st.button("💾 Update", width="stretch")

    # --------------------------------------------------------
    # CANCEL BUTTON
    # --------------------------------------------------------

    cancel_edit = st.button("Cancel Edit")

    # --------------------------------------------------------
    # UPDATE PRODUCT
    # --------------------------------------------------------

    if update_product:
        if product_name.strip() == "":
            st.error("Please enter the product name.")

        elif rate <= 0:
            st.error("Please enter a valid rate.")

        else:
            st.session_state.products[edit_index] = {
                "name": product_name,
                "quantity": quantity,
                "rate": rate,
                "total_stock": edit_product.get(
                    "total_stock",
                    int(
                        inventory_df.loc[
                            inventory_df["Item"]
                            .astype(str)
                            .str.strip()
                            .eq(product_name.strip()),
                            "Total Stock",
                        ].iloc[0]
                    ),
                ),
                "stock_at_addition": edit_product.get(
                    "stock_at_addition", get_remaining_stock(product_name, inventory_df)
                ),
                "remaining_stock": edit_product.get(
                    "remaining_stock",
                    get_remaining_stock(product_name, inventory_df) - quantity,
                ),
            }

            st.session_state.editing_product = None

            st.success("✅ Product updated successfully!")

            st.rerun()

    # --------------------------------------------------------
    # CANCEL EDIT
    # --------------------------------------------------------

    if cancel_edit:
        st.session_state.editing_product = None

        st.rerun()

else:
    # ========================================================
    # COLUMNS
    # ========================================================

    col1, col2, col3, col4 = st.columns([3, 2, 2.5, 1])

    # ========================================================
    # PRODUCT NAME
    # ========================================================

    with col1:
        product_options = inventory_df["Item"].dropna().astype(str).str.strip().tolist()

        if not product_options:
            st.warning(
                "⚠️ No products found in Inventory. "
                "Please upload your Inventory Excel file first."
            )
            st.stop()

        selected_product = st.selectbox(
            "Product Name",
            product_options,
            key="selected_product",
        )
        # ----------------------------------------------------
        # ADD NEW PRODUCT
        # ----------------------------------------------------

        product_name = selected_product

        # Get remaining stock for the current bill
        remaining_stock = get_remaining_stock(selected_product, inventory_df)

        # Keep this variable for validation
        available_stock = remaining_stock

        # ----------------------------------------------------
        # AVAILABLE STOCK
        # ----------------------------------------------------

        if remaining_stock >= 0:
            st.caption(f"📦 Remaining Stock: {remaining_stock}")
        else:
            st.caption(f"⚠️ Remaining Stock: {remaining_stock} (Not enough stock)")

    # ========================================================
    # QUANTITY
    # ========================================================

    with col2:
        quantity = st.number_input(
            "Quantity",
            min_value=0,
            value=0,
            step=1,
            format="%d",
            key=(f"new_quantity_{st.session_state.product_form_reset}"),
        )

    # ========================================================
    # RATE
    # ========================================================

    with col3:
        rate = st.number_input(
            "Rate",
            min_value=0.0,
            value=0.0,
            step=50.0,
            key=(f"new_rate_{st.session_state.product_form_reset}"),
        )

    # ========================================================
    # STOCK AFTER SALE
    # ========================================================

    if selected_product != "➕ Add New Product..." and quantity > 0:
        stock_after_this_addition = remaining_stock - quantity

        if stock_after_this_addition >= 0:
            st.caption(f"📉 Stock After This Addition: {stock_after_this_addition}")

        else:
            st.caption(
                f"⚠️ Stock After This Addition: "
                f"{stock_after_this_addition} "
                "(Not enough stock)"
            )

    # ========================================================
    # ADD BUTTON
    # ========================================================

    with col4:
        st.write("")
        st.write("")

        add_product = st.button(
            "➕ Add",
            width="stretch",
            key="add_product_button",
        )

    # ========================================================
    # ADD PRODUCT
    # ========================================================

    if add_product:
        # ----------------------------------------------------
        # PRODUCT NAME VALIDATION
        # ----------------------------------------------------

        if product_name.strip() == "":
            st.error("Please enter the product name.")

        # ----------------------------------------------------
        # QUANTITY VALIDATION
        # ----------------------------------------------------

        elif quantity <= 0:
            st.error("Please enter a quantity greater than 0.")

        # ----------------------------------------------------
        # RATE VALIDATION
        # ----------------------------------------------------

        elif rate <= 0:
            st.error("Please enter a valid rate.")

        # ----------------------------------------------------
        # STOCK VALIDATION
        # ----------------------------------------------------

        elif quantity > available_stock:
            st.error(
                f"❌ Not enough stock for "
                f"{product_name}. "
                f"Available stock: {available_stock}"
            )

        # ----------------------------------------------------
        # ADD PRODUCT SUCCESSFULLY
        # ----------------------------------------------------

        else:
            product = {
                "name": product_name.strip(),
                "quantity": quantity,
                "rate": rate,
                "total_stock": int(
                    inventory_df.loc[
                        inventory_df["Item"]
                        .astype(str)
                        .str.strip()
                        .eq(product_name.strip()),
                        "Total Stock",
                    ].iloc[0]
                ),
                "stock_at_addition": available_stock,
                "remaining_stock": available_stock - quantity,
            }

            st.session_state.products.append(product)

            # ------------------------------------------------
            # RESET QUANTITY AND RATE
            # ------------------------------------------------

            st.session_state.product_form_reset += 1

            st.success(f"✅ {product_name} added successfully!")

            st.rerun()

# ============================================================
# PRODUCT LIST
# ============================================================

st.header("Product List")

if len(st.session_state.products) == 0:
    st.info("No products added yet. Add products using the form above.")

else:
    # Table header
    header = st.columns([4, 1, 2, 2, 2])

    header[0].write("**Product**")
    header[1].write("**Qty**")
    header[2].write("**Rate**")
    header[3].write("**Amount**")
    header[4].write("**Action**")

    st.divider()

    for index, product in enumerate(st.session_state.products):
        amount = product["quantity"] * product["rate"]

        row = st.columns([4, 1, 2, 2, 2])

        row[0].write(product["name"])

        row[1].write(product["quantity"])

        row[2].write(f"{product['rate']:,.2f}")

        row[3].write(f"{amount:,.2f}")

        # ----------------------------------------------------
        # EDIT BUTTON
        # ----------------------------------------------------

        action_col1, action_col2 = row[4].columns(2)

        if action_col1.button("✏️", key=f"edit_{index}", help="Edit product"):
            st.session_state.editing_product = index

            st.rerun()

        # ----------------------------------------------------
        # DELETE BUTTON
        # ----------------------------------------------------

        if action_col2.button("❌", key=f"delete_{index}", help="Delete product"):
            st.session_state.products.pop(index)

            # If the deleted product was being edited
            if st.session_state.editing_product == index:
                st.session_state.editing_product = None

            st.rerun()


# ============================================================
# CALCULATIONS
# ============================================================

subtotal = 0
total_items = 0

for product in st.session_state.products:
    subtotal += product["quantity"] * product["rate"]

    total_items += product["quantity"]


# ============================================================
# GST
# ============================================================

st.divider()

st.header("Bill Calculation")

gst_enabled = st.checkbox(
    "Add GST",
    key="add_gst",
)

gst_rate = 0.0

if gst_enabled:
    gst_rate = st.number_input(
        "GST Rate (%)", min_value=0.0, max_value=100.0, value=5.0, step=1.0
    )

gst_amount = subtotal * gst_rate / 100

grand_total = subtotal + gst_amount

amount_in_words = number_to_words(grand_total)


# ============================================================
# BILL SUMMARY
# ============================================================

summary_col1, summary_col2 = st.columns(2)

with summary_col1:
    st.metric("Total Items", total_items)

with summary_col2:
    st.metric("Grand Total", f"₹{grand_total:,.2f}")


st.write("### Bill Summary")

summary_data = {
    "Subtotal": f"₹{subtotal:,.2f}",
}

if gst_enabled:
    summary_data[f"GST ({gst_rate:g}%)"] = f"₹{gst_amount:,.2f}"

summary_data["Grand Total"] = f"₹{grand_total:,.2f}"

for label, value in summary_data.items():
    col1, col2 = st.columns(2)

    col1.write(f"**{label}**")
    col2.write(f"**{value}**")


# ============================================================
# GENERATE BILL
# ============================================================

st.divider()

st.header("Generate Bill")

generate_bill = st.button("🧾 Generate Bill", type="primary", width="stretch")


if generate_bill:
    # ========================================================
    # BASIC VALIDATION
    # ========================================================

    customer_name_valid, customer_name_error = validate_name(customer_name)

    customer_phone_valid, customer_phone_error = validate_phone(customer_phone)

    shop_phone_valid, shop_phone_error = validate_shop_phone(shop_phone)

    if not customer_name_valid:
        st.error(f"❌ Customer Name: {customer_name_error}")

    elif not customer_phone_valid:
        st.error(f"❌ Customer Phone: {customer_phone_error}")

    elif not shop_phone_valid:
        st.error(f"❌ Shop Phone: {shop_phone_error}")

    elif len(st.session_state.products) == 0:
        st.error("❌ Please add at least one product.")

    elif st.session_state.bill_saved:
        st.warning(f"⚠️ Bill No {bill_no} has already been generated.")

    else:
        # ====================================================
        # CHECK INVENTORY FIRST
        # ====================================================

        stock_available, stock_error = check_inventory(
            st.session_state.products, inventory_df
        )

        if not stock_available:
            st.error(f"❌ {stock_error}")

        else:
            # =================================================
            # GENERATE PDF
            # =================================================

            pdf_bytes = generate_pdf(
                shop_name=shop_name,
                shop_location=shop_location,
                shop_phone=shop_phone,
                bill_no=bill_no,
                customer_name=customer_name,
                customer_phone=customer_phone,
                payment_method=payment_method,
                products=st.session_state.products,
                subtotal=subtotal,
                gst_rate=gst_rate,
                gst_amount=gst_amount,
                grand_total=grand_total,
                total_items=total_items,
                instagram=instagram,
            )

            # =================================================
            # STORE PDF
            # =================================================

            st.session_state.pdf_bytes = pdf_bytes

            st.session_state.generated_bill_no = bill_no

            # =================================================
            # SAVE BILL
            # =================================================

            try:
                bill_saved, bill_message, saved_bills_df = save_bill_to_google_sheet(
                    bill_no=bill_no,
                    transaction_id=(st.session_state.transaction_id),
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    products=(st.session_state.products),
                    subtotal=subtotal,
                    gst_rate=gst_rate,
                    gst_amount=gst_amount,
                    grand_total=grand_total,
                    payment_method=payment_method,
                    inventory_updated="Pending",
                )

                if not bill_saved:
                    st.error(f"❌ {bill_message}")

                else:
                    # =========================================
                    # UPDATE INVENTORY
                    # =========================================

                    inventory_done, inventory_message = reduce_inventory_once(
                        st.session_state.products,
                        st.session_state.transaction_id,
                        inventory_df,
                    )

                    if inventory_done:
                        # =====================================
                        # MARK INVENTORY AS UPDATED
                        # =====================================

                        inventory_marked = mark_inventory_updated(
                            st.session_state.transaction_id, saved_bills_df
                        )

                        if not inventory_marked:
                            st.warning(
                                "⚠️ Inventory was reduced, but the "
                                "Bills sheet could not be marked as Updated."
                            )

                        else:
                            st.session_state.bill_saved = True
                            st.session_state.inventory_updated = True

                            st.success(
                                f"✅ Bill No {bill_no} saved "
                                "and inventory updated successfully!"
                            )

                    else:
                        st.warning(f"⚠️ {inventory_message}")

                        st.warning("The bill was saved, but inventory was not changed.")

            except Exception as e:
                st.error("❌ Bill processing failed.")

                st.error(f"Details: {e}")

# ========================================================
# BILL HISTORY
# ========================================================

st.divider()

st.header("📊 Bill History")

if st.button("🔄 Refresh Bill History", key="refresh_bill_history"):
    try:
        get_bills.clear()  # Force fresh Google Sheet read

        bills_df = get_bills()

        if bills_df.empty:
            st.info("No bills found.")

        else:
            # ====================================================
            # CLEAN DATA TYPES BEFORE DISPLAYING
            # ====================================================

            # Convert Inventory Updated to text
            if "Inventory Updated" in bills_df.columns:
                bills_df["Inventory Updated"] = (
                    bills_df["Inventory Updated"].fillna("").astype(str).str.strip()
                )

            # Convert Transaction ID to text
            if "Transaction ID" in bills_df.columns:
                bills_df["Transaction ID"] = (
                    bills_df["Transaction ID"].fillna("").astype(str)
                )

            # Convert Customer Number to text
            if "Customer Number" in bills_df.columns:
                bills_df["Customer Number"] = (
                    bills_df["Customer Number"].fillna("").astype(str)
                )

            # Convert Bill No safely to integer
            if "Bill No" in bills_df.columns:
                bills_df["Bill No"] = (
                    pd
                    .to_numeric(bills_df["Bill No"], errors="coerce")
                    .fillna(0)
                    .astype(int)
                )

            # Convert Quantity safely to integer
            if "Quantity" in bills_df.columns:
                bills_df["Quantity"] = (
                    pd
                    .to_numeric(bills_df["Quantity"], errors="coerce")
                    .fillna(0)
                    .astype(int)
                )

            # Convert numeric money columns
            money_columns = [
                "Rate",
                "Amount",
                "Sub Total",
                "GST %",
                "GST Amount",
                "Grand Total",
            ]

            for column in money_columns:
                if column in bills_df.columns:
                    bills_df[column] = pd.to_numeric(
                        bills_df[column], errors="coerce"
                    ).fillna(0.0)

            # ====================================================
            # DISPLAY BILL HISTORY
            # ====================================================

            st.dataframe(bills_df, width="stretch", hide_index=True)

    except Exception as e:
        st.error(f"Could not load bill history: {e}")

# ============================================================
# CURRENT INVENTORY
# ============================================================

st.divider()
st.header("📦 Current Inventory")

try:
    inventory_df = get_inventory()

    if inventory_df.empty:
        st.info("No inventory items found.")
    else:
        inventory_display_df = inventory_df.copy()

        inventory_display_df = inventory_display_df.rename(
            columns={
                "Item": "Product",
                "Stock": "Current Stock",
            }
        )

        inventory_display_df = inventory_display_df[
            ["Product", "Total Stock", "Current Stock"]
        ]

        st.dataframe(
            inventory_display_df,
            width="stretch",
            hide_index=True,
        )

except Exception as e:
    st.error(f"Could not load inventory: {e}")


# ============================================================
# DOWNLOAD + WHATSAPP
# ============================================================

if "pdf_bytes" in st.session_state:
    st.divider()

    st.subheader("Bill Ready")

    filename = (
        f"Bill_{st.session_state.generated_bill_no}_"
        f"{customer_name.replace(' ', '_')}.pdf"
    )

    st.download_button(
        label="⬇️ Download Bill PDF",
        data=st.session_state.pdf_bytes,
        file_name=filename,
        mime="application/pdf",
        width="stretch",
    )

    # ========================================================
    # WHATSAPP
    # ========================================================

    whatsapp_number = "".join(
        character for character in customer_phone if character.isdigit()
    )

    # If Indian customer number entered as 10 digits
    if len(whatsapp_number) == 10:
        whatsapp_number = "91" + whatsapp_number

    # ========================================================
    # SHOP WHATSAPP NUMBER
    # ========================================================

    shop_whatsapp_number = "".join(
        character for character in shop_phone if character.isdigit()
    )

    # If Indian shop number entered as 10 digits
    if len(shop_whatsapp_number) == 10:
        shop_whatsapp_number = "91" + shop_whatsapp_number

    # ========================================================
    # CLICKABLE LINKS
    # ========================================================

    # Shop → Google Maps
    maps_url = "https://www.google.com/maps/search/?api=1&query=" + quote(shop_location)

    # Instagram
    instagram_username = instagram.strip().replace("@", "")

    instagram_url = f"https://www.instagram.com/{instagram_username}"

    # MAPOS website
    mapos_url = "https://map-portfolio.netlify.app/"

    # Shop WhatsApp
    shop_whatsapp_url = f"https://wa.me/{shop_whatsapp_number}"

    # ========================================================
    # WHATSAPP MESSAGE
    # ========================================================

    # IMPORTANT:
    # Always use the bill number that was actually generated,
    # not the current bill number after Streamlit reruns.

    whatsapp_bill_no = st.session_state.get("generated_bill_no", bill_no)

    whatsapp_message = (
        f"Hello {customer_name},\n\n"
        f"Thank you for shopping with {shop_name}.\n\n"
        f"Bill Details\n"
        f"Bill No: {whatsapp_bill_no}\n"
        f"Total Items: {total_items}\n"
        f"Grand Total: ₹{grand_total:,.2f}\n\n"
        f"Please find your bill attached.\n\n"
        f"Shop Location\n"
        f"{maps_url}\n\n"
        f"Shop WhatsApp\n"
        f"{shop_whatsapp_url}\n\n"
        f"Instagram\n"
        f"{instagram_url}\n\n"
        f"Powered by MAPOS\n"
        f"{mapos_url}\n\n"
        f"Thank you. Visit Us Again!"
    )

    # ========================================================
    # ENCODE MESSAGE ONCE
    # ========================================================

    whatsapp_url = f"https://wa.me/{whatsapp_number}?text={quote(whatsapp_message)}"

    # ========================================================
    # SEND BUTTON
    # ========================================================

    st.markdown(
        f"""
        <a href="{whatsapp_url}" target="_blank">
            <button style="
                width: 100%;
                padding: 12px;
                background-color: #25D366;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                cursor: pointer;
            ">
                📱 Send Bill on WhatsApp
            </button>
        </a>
        """,
        unsafe_allow_html=True,
    )

st.info(
    "WhatsApp will open with the customer's number and "
    "message already prepared. Attach the downloaded PDF "
    "and press Send."
)
# ============================================================
# NEW BILL
# ============================================================


def reset_new_bill():
    # Clear products
    st.session_state.products = []

    # Clear PDF
    if "pdf_bytes" in st.session_state:
        del st.session_state.pdf_bytes

    # Clear generated bill
    if "generated_bill_no" in st.session_state:
        del st.session_state.generated_bill_no

    # Reset product widgets
    st.session_state.product_form_reset += 1

    # New transaction ID
    st.session_state.transaction_id = str(uuid.uuid4())

    # Reset bill status
    st.session_state.bill_saved = False
    st.session_state.inventory_updated = False

    # Next bill number
    st.session_state.current_bill_no += 1

    # Reset GST
    st.session_state.add_gst = False


st.divider()

st.button(
    "🔄 Start New Bill",
    width="stretch",
    on_click=reset_new_bill,
)
