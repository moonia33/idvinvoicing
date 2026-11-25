from functools import lru_cache


@lru_cache
def _data_only_fetcher():
    """WeasyPrint gali krauti tik data: URI (logotipas), ne file:// ar tinklo adresus."""
    from weasyprint.urls import URLFetcher  # lazy: Windows dev be GTK bibliotekų

    return URLFetcher(allowed_protocols={"data"})


def render_pdf(html: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=html, url_fetcher=_data_only_fetcher()).write_pdf()
