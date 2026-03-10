"""BeautifulSoup unit: parse HTML, extract text/links/tables/markup."""
from units.web.beautifulsoup.beautifulsoup import (
    BEAUTIFULSOUP_INPUT_PORTS,
    BEAUTIFULSOUP_OUTPUT_PORTS,
    html_to_text,
    register_beautifulsoup,
)

__all__ = [
    "register_beautifulsoup",
    "html_to_text",
    "BEAUTIFULSOUP_INPUT_PORTS",
    "BEAUTIFULSOUP_OUTPUT_PORTS",
]
