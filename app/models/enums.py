from enum import Enum


class ClipJobStatus(str, Enum):
    queued = "queued"
    analyzed = "analyzed"
    rendering = "rendering"
    rendered = "rendered"
    scheduled = "scheduled"
    uploaded = "uploaded"
    failed = "failed"
