"""Shared guard against exporting cached geometry from a failed recompute."""


def require_current_solid(obj):
    for dependency in [obj, *obj.OutListRecursive]:
        if any(state in dependency.State for state in ("Invalid", "Touched")):
            raise ValueError(f"Recompute {dependency.Name} successfully before exporting geometry")
    shape = obj.Shape
    if (
        getattr(obj, "GenerationError", "")
        or shape.isNull()
        or not shape.isValid()
        or len(shape.Solids) != 1
    ):
        raise ValueError(f"Invalid part solid on {obj.Name}; need one valid solid")
    return shape
