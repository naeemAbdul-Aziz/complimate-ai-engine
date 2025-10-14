"""Central version definition for CompliMate AI Engine."""

API_VERSION = "2.0.2"
ENGINE_VERSION = API_VERSION  # Keep in sync for now
BUILD_METADATA = {}

def get_version() -> str:
    return API_VERSION
