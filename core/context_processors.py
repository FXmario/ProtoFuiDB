from Databases.models import Database


def databases_context(request):
    if request.user.is_authenticated:
        active_db_id = None
        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match and "public_id" in (resolver_match.kwargs or {}):
            active_db_id = resolver_match.kwargs["public_id"]
        return {
            "databases": Database.objects.filter(owner=request.user),
            "active_db_id": active_db_id,
        }
    return {"databases": Database.objects.none()}