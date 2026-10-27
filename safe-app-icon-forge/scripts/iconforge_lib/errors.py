from __future__ import annotations


class IconforgeError(Exception):
    """Base class for expected, user-facing Iconforge failures."""

    code = "iconforge_error"

    def __init__(self, message: str, *, context: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.context = {} if context is None else dict(context)


class PathSafetyError(IconforgeError):
    code = "path_safety_error"


class ConfigError(IconforgeError):
    code = "config_error"


class JsonSecurityError(IconforgeError):
    code = "json_security_error"


class StyleLockError(IconforgeError):
    code = "style_lock_error"


class ProvenanceError(IconforgeError):
    code = "provenance_error"


class VisualReviewError(IconforgeError):
    code = "visual_review_error"


class SvgSecurityError(IconforgeError):
    code = "svg_security_error"


class PngError(IconforgeError):
    code = "png_error"


class IcoError(IconforgeError):
    code = "ico_error"


class RendererError(IconforgeError):
    code = "renderer_error"


class BuildError(IconforgeError):
    code = "build_error"


class VerificationError(IconforgeError):
    code = "verification_error"


class ReleaseError(IconforgeError):
    code = "release_error"
