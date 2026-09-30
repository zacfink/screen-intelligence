from screen_intelligence.models import Step


def step(**changes):
    """A valid Step; pass only the fields a test cares about."""
    fields = dict(tag="left_click", args=[], description="click", undo_tag=None, conditions=[],
                  requires_confirmation=False, visible_effect="")
    return Step(**{**fields, **changes})
