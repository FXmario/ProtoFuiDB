from django import template

register = template.Library()


@register.filter
def index(seq, key):
    """Access an element by index or key, like seq[key] in Python."""
    try:
        return seq[key]
    except (IndexError, KeyError, TypeError):
        try:
            return seq[int(key)]
        except (IndexError, KeyError, TypeError, ValueError):
            return ""