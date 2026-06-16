"""Shared DRF pagination helpers."""

from rest_framework.pagination import PageNumberPagination


class OptionalPageNumberPagination(PageNumberPagination):
    """Page-number pagination that only activates when ``?page=`` is present.

    This lets a single list endpoint serve both:
      * the legacy "give me everything" callers (no ``page`` param → plain list)
      * paginated callers (``?page=1&page_size=50`` → {count, next, previous, results})

    so adding pagination to a viewset does not break existing array consumers.
    """

    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 500

    def paginate_queryset(self, queryset, request, view=None):
        if 'page' not in request.query_params:
            return None
        return super().paginate_queryset(queryset, request, view)
