import os
from datetime import datetime, timezone
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

TODAY = lambda: datetime.now(timezone.utc).strftime("%B %d, %Y")

SYSTEM_PROMPT = """You are the Kinetic Communications Agent embedded in an Epicor Kinetic ERP environment.

Your job: given ERP record data, generate a structured communication response.

ALWAYS respond in this exact format — no deviations:

---ERP_SUMMARY---
[2-4 sentence factual summary of the record state. Facts only, no interpretation.]

---KEY_ISSUES---
[Bullet list of issues/risks. Each bullet on its own line starting with •. If none, write: • No critical issues identified.]

---DRAFT---
Subject: [subject line]

[Professional email body. Factual, concise, manufacturing-appropriate. No marketing language. No fluff.]

---NEXT_ACTIONS---
[Bullet list of recommended operational follow-ups. Each on its own line starting with •.]

RULES:
- Never fabricate ERP data. If a field is missing, omit it or say "not on record."
- Separate facts from interpretation.
- Keep draft emails direct and professional.
- You are drafting only — the user must approve before anything is sent."""


def _build_context(record_type: str, data: dict, user_instructions: str) -> str:
    today = TODAY()
    base = f"Today's date: {today}\nCommunication type: {record_type}\n\n"

    if record_type == "overdue_order":
        h = data.get("header", {})
        lines = data.get("lines", [])
        contacts = data.get("contacts", [])
        primary = next((c for c in contacts if c.get("PrimaryContact")), contacts[0] if contacts else {})
        lines_txt = "\n".join(
            f"  - Line {l.get('OrderLine')}: {l.get('PartNum')} — {l.get('LineDesc')} "
            f"| Qty: {l.get('OrderQty')} | Need By: {l.get('NeedByDate','')[:10]}"
            for l in lines
        ) or "  (no open lines found)"
        ctx = f"""ERP RECORD — OVERDUE SALES ORDER
Order #: {h.get('OrderNum','N/A')}
Customer #: {h.get('CustNum','N/A')}
Order Date: {str(h.get('OrderDate',''))[:10]}
Requested Ship Date: {str(h.get('RequestDate',''))[:10]}
Order Value: ${h.get('OrderAmt', 0):,.2f}

Customer Contact on Record:
  Name: {primary.get('Name', 'Not on record')}
  Email: {primary.get('EmailAddress', 'Not on record')}
  Phone: {primary.get('PhoneNum', 'Not on record')}

Open Order Lines:
{lines_txt}"""

    elif record_type == "atrisk_job" or record_type == "overdue_job":
        j = data.get("job", {})
        mtls = data.get("materials", [])
        short_mtls = [m for m in mtls if m.get("ShortageExists")]
        pct = 0
        if j.get("ProdQty", 0) > 0:
            pct = round((j.get("QtyCompleted", 0) / j["ProdQty"]) * 100, 1)
        mtl_txt = "\n".join(
            f"  - {m.get('PartNum')} — {m.get('Description')} "
            f"| Req: {m.get('RequiredQty')} | Issued: {m.get('IssuedQty')} ⚠ SHORTAGE"
            for m in short_mtls
        ) or "  No material shortages on record"
        label = "OVERDUE JOB" if record_type == "overdue_job" else "AT-RISK JOB"
        ctx = f"""ERP RECORD — {label}
Job #: {j.get('JobNum','N/A')}
Part #: {j.get('PartNum','N/A')}
Status: {'Released' if j.get('JobReleased') else 'Not Released'} / {'Engineered' if j.get('JobEngineered') else 'Not Engineered'}
Start Date: {str(j.get('StartDate',''))[:10]}
Due Date: {str(j.get('DueDate',''))[:10]}
Production Qty: {j.get('ProdQty', 0)}
Qty Completed: {j.get('QtyCompleted', 0)} ({pct}%)

Material Shortages:
{mtl_txt}"""

    elif record_type == "overdue_po_line":
        ctx = f"""ERP RECORD — OVERDUE PO RELEASE
PO #: {data.get('PONum','N/A')}
PO Line: {data.get('POLine','N/A')}
Release: {data.get('PORelNum','N/A')}
Part #: {data.get('PartNum','N/A')}
Vendor #: {data.get('VendorNum','N/A')}
Qty Ordered: {data.get('RelQty', 0)}
Qty Received: {data.get('ReceivedQty', 0)}
Due Date: {str(data.get('DueDate',''))[:10]}"""

    elif record_type == "open_po":
        ctx = f"""ERP RECORD — OPEN PURCHASE ORDER
PO #: {data.get('PONum','N/A')}
Vendor #: {data.get('VendorNum','N/A')}
Vendor: {data.get('VendorName', data.get('VendorID','N/A'))}
Order Date: {str(data.get('OrderDate',''))[:10]}
Approval Status: {data.get('ApprovalStatus','N/A')}"""

    else:
        ctx = f"ERP DATA:\n{data}"

    if user_instructions:
        ctx += f"\n\nUSER INSTRUCTIONS: {user_instructions}"

    return base + ctx


def generate_draft(
    record_type: str,
    comm_type: str,
    data: dict,
    user_instructions: str = "",
) -> dict:
    context = _build_context(record_type, data, user_instructions)

    full_prompt = f"""{context}

Generate a {comm_type.replace('_', ' ')} communication for this record.
Follow the exact output format specified."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": full_prompt}],
    )

    raw = message.content[0].text
    return _parse_response(raw)


def refine_draft(original_draft: str, refinement: str) -> dict:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Here is an existing draft communication:\n\n{original_draft}\n\n"
                           f"Please refine it with the following instruction: {refinement}\n\n"
                           f"Return the full response in the standard format.",
            }
        ],
    )
    raw = message.content[0].text
    return _parse_response(raw)


def _parse_response(raw: str) -> dict:
    def extract(tag: str) -> str:
        start = raw.find(f"---{tag}---")
        if start == -1:
            return ""
        start += len(f"---{tag}---")
        tags = ["ERP_SUMMARY", "KEY_ISSUES", "DRAFT", "NEXT_ACTIONS"]
        end = len(raw)
        for t in tags:
            marker = f"---{t}---"
            pos = raw.find(marker, start)
            if pos != -1 and pos < end:
                end = pos
        return raw[start:end].strip()

    return {
        "summary":      extract("ERP_SUMMARY"),
        "issues":       extract("KEY_ISSUES"),
        "draft":        extract("DRAFT"),
        "next_actions": extract("NEXT_ACTIONS"),
        "raw":          raw,
    }
