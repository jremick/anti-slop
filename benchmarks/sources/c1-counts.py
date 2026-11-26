"""Constructed bug fixture. Counts may be positive, negative or zero integers."""


def total_by_category(rows):
    """Return counts by stripped, case-insensitive category without changing rows."""
    totals = {}
    for row in rows:
        key = row["category"].strip().casefold()
        totals[key] = row["count"]
    return totals
