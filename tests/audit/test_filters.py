def test_audit_query_filters_defaults():
    from src.audit.filters import AuditLogFilters

    filters = AuditLogFilters()
    assert filters.action is None
    assert filters.page == 1
    assert filters.size == 20
