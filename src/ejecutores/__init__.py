from src.ejecutores.camoufox import CamoufoxEjecutor
from src.ejecutores.httpx import HttpxEjecutor
from src.ejecutores.trawl import TrawlEjecutor

EJECUTORES = {
    "camoufox": CamoufoxEjecutor(),
    "trawl": TrawlEjecutor(),
    "httpx": HttpxEjecutor(),
}
