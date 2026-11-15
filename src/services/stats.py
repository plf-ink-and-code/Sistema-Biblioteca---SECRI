from database import get_db
from datetime import date
from services.loans import overdue_loans


def dashboard_stats():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM books").fetchone()["c"]
        exemplars = conn.execute(
            "SELECT COALESCE(SUM(copies),0) as c FROM books").fetchone()["c"]
        active = conn.execute(
            "SELECT COUNT(*) as c FROM loans WHERE return_date IS NULL").fetchone()["c"]
        available = max(0, exemplars - active)
        loaned = active
        overdue_count = len(overdue_loans())
        month_start = date.today().replace(day=1).isoformat()
        returns_month = conn.execute(
            "SELECT COUNT(*) as c FROM loans WHERE return_date >= ?", (month_start,)).fetchone()["c"]
        return {"total": total, "exemplars": exemplars, "available": available,
                "loaned": loaned, "overdue": overdue_count,
                "returns_month": returns_month}
