import os
from datetime import datetime, timezone
import httpx

BASE_URL = os.getenv("KINETIC_BASE_URL", "").rstrip("/")
AUTH = (os.getenv("KINETIC_USERNAME", ""), os.getenv("KINETIC_PASSWORD", ""))
LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "30"))


def _client() -> httpx.Client:
    return httpx.Client(auth=AUTH, timeout=30)


def _svc(path: str) -> str:
    return f"{BASE_URL}/{path}"


def _parse(resp: httpx.Response) -> list[dict]:
    resp.raise_for_status()
    return resp.json().get("value", [])


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")


def _future(days: int) -> str:
    from datetime import timedelta
    d = datetime.now(timezone.utc) + timedelta(days=days)
    return d.strftime("%Y-%m-%dT00:00:00Z")


# ── Sales Orders ──────────────────────────────────────────────────────────────

def get_overdue_orders() -> list[dict]:
    today = _today()
    with _client() as c:
        rows = _parse(c.get(_svc(
            "ERP.BO.SalesOrderSvc/SalesOrders"
            f"?$filter=OpenOrder eq true and RequestDate lt {today}"
            "&$select=OrderNum,CustNum,CustomerCustID,BTCustNum,OrderDate,"
            "RequestDate,NeedByDate,OrderAmt"
            "&$top=50&$orderby=RequestDate asc"
        )))
    return [_tag(r, "overdue_order") for r in rows]


def get_order_detail(order_num: int) -> dict:
    with _client() as c:
        headers = _parse(c.get(_svc(
            f"ERP.BO.SalesOrderSvc/SalesOrders"
            f"?$filter=OrderNum eq {order_num}"
            "&$select=OrderNum,CustNum,CustomerCustID,BTCustNum,OrderDate,"
            "RequestDate,NeedByDate,OpenOrder,OrderAmt"
        )))
        lines = _parse(c.get(_svc(
            f"ERP.BO.SalesOrderSvc/OrderDtls"
            f"?$filter=OrderNum eq {order_num} and OpenLine eq true"
            "&$select=OrderNum,OrderLine,PartNum,LineDesc,OrderQty,"
            "RequestDate,NeedByDate,OpenLine"
        )))
        contacts = _parse(c.get(_svc(
            f"ERP.BO.CustCntSvc/CustCnts"
            f"?$filter=CustNum eq {headers[0]['CustNum'] if headers else 0}"
            "&$select=CustNum,ConNum,Name,EmailAddress,PhoneNum,PrimaryContact"
            "&$top=5"
        ))) if headers else []
    return {
        "header": headers[0] if headers else {},
        "lines": lines,
        "contacts": contacts,
    }


# ── Jobs ──────────────────────────────────────────────────────────────────────

def get_atrisk_jobs() -> list[dict]:
    future = _future(LOOKAHEAD_DAYS)
    today = _today()
    with _client() as c:
        rows = _parse(c.get(_svc(
            "ERP.BO.JobStatusSvc/JobStatus"
            f"?$filter=JobComplete eq false and DueDate le {future} and DueDate ge {today}"
            "&$select=JobNum,PartNum,JobEngineered,JobReleased,StartDate,"
            "DueDate,ProdQty,QtyCompleted"
            "&$top=50&$orderby=DueDate asc"
        )))
    return [_tag(r, "atrisk_job") for r in rows]


def get_overdue_jobs() -> list[dict]:
    today = _today()
    with _client() as c:
        rows = _parse(c.get(_svc(
            "ERP.BO.JobStatusSvc/JobStatus"
            f"?$filter=JobComplete eq false and DueDate lt {today}"
            "&$select=JobNum,PartNum,JobEngineered,JobReleased,StartDate,"
            "DueDate,ProdQty,QtyCompleted"
            "&$top=50&$orderby=DueDate asc"
        )))
    return [_tag(r, "overdue_job") for r in rows]


def get_job_detail(job_num: str) -> dict:
    with _client() as c:
        jobs = _parse(c.get(_svc(
            f"ERP.BO.JobStatusSvc/JobStatus"
            f"?$filter=JobNum eq '{job_num}'"
            "&$select=JobNum,PartNum,JobEngineered,JobReleased,JobComplete,"
            "StartDate,DueDate,ProdQty,QtyCompleted"
        )))
        mtls = _parse(c.get(_svc(
            f"ERP.BO.JobEntrySvc/JobMtls"
            f"?$filter=JobNum eq '{job_num}'"
            "&$select=JobNum,AssemblySeq,MtlSeq,PartNum,Description,"
            "RequiredQty,IssuedQty,ShortageExists"
            "&$top=20"
        ))) if jobs else []
    return {
        "job": jobs[0] if jobs else {},
        "materials": mtls,
    }


# ── Purchase Orders ───────────────────────────────────────────────────────────

def get_open_pos() -> list[dict]:
    today = _today()
    with _client() as c:
        rows = _parse(c.get(_svc(
            "ERP.BO.POSvc/POes"
            f"?$filter=OrderDate le {today}"
            "&$select=PONum,VendorNum,VendorID,VendorName,OrderDate,ApprovalStatus"
            "&$top=50&$orderby=OrderDate asc"
        )))
    return [_tag(r, "open_po") for r in rows]


def get_overdue_po_lines() -> list[dict]:
    today = _today()
    with _client() as c:
        rows = _parse(c.get(_svc(
            "ERP.BO.POSvc/PORels"
            f"?$filter=OpenRelease eq true and DueDate lt {today}"
            "&$select=PONum,POLine,PORelNum,PartNum,XRefPartNum,RelQty,"
            "ReceivedQty,DueDate,VendorNum"
            "&$top=50&$orderby=DueDate asc"
        )))
    return [_tag(r, "overdue_po_line") for r in rows]


def get_po_detail(po_num: int) -> dict:
    with _client() as c:
        headers = _parse(c.get(_svc(
            f"ERP.BO.POSvc/POes?$filter=PONum eq {po_num}"
            "&$select=PONum,VendorNum,VendorID,VendorName,OrderDate,ApprovalStatus"
        )))
        lines = _parse(c.get(_svc(
            f"ERP.BO.POSvc/PODetails?$filter=PONum eq {po_num}"
            "&$select=PONum,POLine,PartNum,LineDesc,OrderQty,UnitCost"
            "&$top=20"
        )))
        rels = _parse(c.get(_svc(
            f"ERP.BO.POSvc/PORels?$filter=PONum eq {po_num}"
            "&$select=PONum,POLine,PORelNum,RelQty,ReceivedQty,DueDate,OpenRelease"
            "&$top=20"
        )))
    return {
        "header": headers[0] if headers else {},
        "lines": lines,
        "releases": rels,
    }


# ── Customer Contacts ─────────────────────────────────────────────────────────

def get_customer_contacts(cust_num: int) -> list[dict]:
    with _client() as c:
        return _parse(c.get(_svc(
            f"ERP.BO.CustCntSvc/CustCnts"
            f"?$filter=CustNum eq {cust_num}"
            "&$select=CustNum,ConNum,Name,EmailAddress,PhoneNum,PrimaryContact"
            "&$top=10"
        )))


# ── Scan summary ──────────────────────────────────────────────────────────────

def scan_all() -> dict:
    results = {}
    fetchers = {
        "overdue_orders":   get_overdue_orders,
        "atrisk_jobs":      get_atrisk_jobs,
        "overdue_jobs":     get_overdue_jobs,
        "overdue_po_lines": get_overdue_po_lines,
    }
    errors = {}
    for key, fn in fetchers.items():
        try:
            results[key] = fn()
        except Exception as e:
            results[key] = []
            errors[key] = str(e)
    return {"results": results, "errors": errors}


def _tag(record: dict, record_type: str) -> dict:
    record["_type"] = record_type
    return record
