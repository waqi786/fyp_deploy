from typing import Protocol

from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest


class SearchProvider(Protocol):
    source_name: str

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        ...
